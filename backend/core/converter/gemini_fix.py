import json
from typing import Any, Dict, Optional

from core.converter.thought_signature import SKIP_THOUGHT_SIGNATURE_VALIDATOR
from log import log

# ====================== Model Configuration ======================

# Default Safety Settings for Google API
DEFAULT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

LITE_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]


def _append_schema_hint(schema: Dict[str, Any], hint: str) -> None:
    """Move fragile validation details into description instead of sending them raw."""
    if not hint:
        return
    desc = schema.get("description")
    schema["description"] = f"{desc} ({hint})" if desc else hint


def _resolve_schema_ref(ref: str, root_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None

    node: Any = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]

    return node if isinstance(node, dict) else None


def _clean_parameters_json_schema(
    schema: Any,
    root_schema: Optional[Dict[str, Any]] = None,
    visited: Optional[set] = None,
) -> Any:
    """Clean a tool schema for Code Assist's parametersJsonSchema field."""
    if isinstance(schema, list):
        return [_clean_parameters_json_schema(item, root_schema, visited) for item in schema]
    if not isinstance(schema, dict):
        return schema

    if root_schema is None:
        root_schema = schema
    if visited is None:
        visited = set()

    schema_id = id(schema)
    if schema_id in visited:
        return {"type": "object", "description": "circular reference"}
    visited.add(schema_id)

    ref_key = "$ref" if "$ref" in schema else ("ref" if "ref" in schema else None)
    if ref_key:
        resolved = _resolve_schema_ref(schema[ref_key], root_schema)
        if resolved:
            merged = dict(resolved)
            for key in ("description", "default"):
                if key in schema:
                    merged[key] = schema[key]
            schema = merged

    if "allOf" in schema:
        result: Dict[str, Any] = {}
        for item in schema.get("allOf") or []:
            cleaned_item = _clean_parameters_json_schema(item, root_schema, visited)
            if not isinstance(cleaned_item, dict):
                continue
            if "properties" in cleaned_item:
                result.setdefault("properties", {}).update(cleaned_item["properties"])
            if "required" in cleaned_item:
                result.setdefault("required", []).extend(cleaned_item["required"])
            for key, value in cleaned_item.items():
                if key not in ("properties", "required"):
                    result[key] = value
        for key, value in schema.items():
            if key not in ("allOf", "properties", "required"):
                result[key] = value
            elif key in ("properties", "required") and key not in result:
                result[key] = value
    else:
        result = dict(schema)

    if result.get("nullable") is True:
        _append_schema_hint(result, "nullable")

    if "type" in result:
        type_value = result["type"]
        if isinstance(type_value, list):
            non_null_types = [
                str(t).lower() for t in type_value if isinstance(t, str) and t.lower() != "null"
            ]
            if non_null_types:
                result["type"] = non_null_types[0]
                if any(str(t).lower() == "null" for t in type_value):
                    _append_schema_hint(result, "nullable")
            else:
                result["type"] = "string"
        elif isinstance(type_value, str):
            lower_type = type_value.lower()
            if lower_type in {"string", "number", "integer", "boolean", "array", "object"}:
                result["type"] = lower_type
            elif lower_type == "null":
                result["type"] = "string"
                _append_schema_hint(result, "nullable")
            else:
                result.pop("type", None)

    if "anyOf" in result or "oneOf" in result:
        union_key = "anyOf" if "anyOf" in result else "oneOf"
        union_items = result.get(union_key) or []
        cleaned_items = [
            item
            for item in (
                _clean_parameters_json_schema(item, root_schema, visited) for item in union_items
            )
            if isinstance(item, dict)
        ]
        enum_values = [
            item.get("const")
            for item in union_items
            if isinstance(item, dict) and item.get("const") not in ("", None)
        ]
        if enum_values and len(enum_values) == len(union_items):
            result["type"] = "string"
            result["enum"] = [str(v) for v in enum_values]
        else:
            preferred = next(
                (
                    item
                    for item in cleaned_items
                    if item.get("type") in ("object", "array") or item.get("properties")
                ),
                None,
            )
            if preferred is None:
                preferred = next(
                    (item for item in cleaned_items if item.get("type") or item.get("enum")), None
                )
            if preferred:
                original_description = result.get("description")
                result.update(preferred)
                if original_description:
                    _append_schema_hint(result, original_description)
        result.pop("anyOf", None)
        result.pop("oneOf", None)

    if result.get("type") == "array":
        items = result.get("items")
        if isinstance(items, list):
            if items:
                result["items"] = _clean_parameters_json_schema(items[0], root_schema, visited)
                _append_schema_hint(result, "tuple schema simplified")
            else:
                result.pop("items", None)
        elif isinstance(items, dict):
            result["items"] = _clean_parameters_json_schema(items, root_schema, visited)

    validation_keys = {
        "default",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "pattern",
        "format",
        "uniqueItems",
    }
    for key in list(result.keys()):
        if key in validation_keys:
            value = result.pop(key)
            if value not in (None, "", {}, []):
                _append_schema_hint(result, f"{key}: {json.dumps(value, ensure_ascii=False)}")

    unsupported_keys = {
        "title",
        "$schema",
        "$id",
        "$ref",
        "ref",
        "strict",
        "nullable",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "additionalProperties",
        "allOf",
        "anyOf",
        "oneOf",
        "$defs",
        "definitions",
        "example",
        "examples",
        "readOnly",
        "writeOnly",
        "const",
        "additionalItems",
        "contains",
        "patternProperties",
        "dependencies",
        "propertyNames",
        "if",
        "then",
        "else",
        "contentEncoding",
        "contentMediaType",
    }
    for key in list(result.keys()):
        if key in unsupported_keys or key.startswith("x-"):
            del result[key]

    nullable_props = set()
    if isinstance(result.get("properties"), dict):
        cleaned_props = {}
        for prop_name, prop_schema in result["properties"].items():
            if isinstance(prop_schema, dict):
                prop_type = prop_schema.get("type")
                if prop_schema.get("nullable") is True or (
                    isinstance(prop_type, list) and any(str(t).lower() == "null" for t in prop_type)
                ):
                    nullable_props.add(prop_name)
            cleaned_props[prop_name] = _clean_parameters_json_schema(
                prop_schema, root_schema, visited
            )
        result["properties"] = cleaned_props

    if "properties" in result and "type" not in result:
        result["type"] = "object"

    if isinstance(result.get("required"), list):
        prop_names = (
            set(result.get("properties", {}).keys())
            if isinstance(result.get("properties"), dict)
            else None
        )
        required = []
        for item in result["required"]:
            if not isinstance(item, str):
                continue
            if prop_names is not None and item not in prop_names:
                continue
            if item in nullable_props:
                continue
            if item not in required:
                required.append(item)
        if required:
            result["required"] = required
        else:
            result.pop("required", None)

    return result


def _normalize_tools_for_internal_api(tools: Any) -> Any:
    if not isinstance(tools, list):
        return tools

    normalized_tools = []
    for tool in tools:
        if not isinstance(tool, dict):
            normalized_tools.append(tool)
            continue

        normalized_tool = tool.copy()
        declarations = normalized_tool.get("functionDeclarations")
        if declarations is None:
            declarations = normalized_tool.get("function_declarations")
        if isinstance(declarations, list):
            normalized_declarations = []
            for declaration in declarations:
                if not isinstance(declaration, dict):
                    normalized_declarations.append(declaration)
                    continue

                normalized_declaration = declaration.copy()
                if "parametersJsonSchema" in normalized_declaration:
                    schema = normalized_declaration["parametersJsonSchema"]
                elif "parameters_json_schema" in normalized_declaration:
                    schema = normalized_declaration.pop("parameters_json_schema", None)
                else:
                    schema = normalized_declaration.pop("parameters", None)

                normalized_declaration.pop("parameters", None)
                normalized_declaration.pop("parameters_json_schema", None)
                if schema not in (None, {}, []):
                    normalized_declaration["parametersJsonSchema"] = _clean_parameters_json_schema(
                        schema
                    )
                else:
                    normalized_declaration.pop("parametersJsonSchema", None)

                normalized_declarations.append(normalized_declaration)

            normalized_tool.pop("function_declarations", None)
            normalized_tool["functionDeclarations"] = normalized_declarations

        normalized_tools.append(normalized_tool)

    return normalized_tools


def _ensure_empty_tool_schema_for_claude(tools: Any, model_name: str) -> Any:
    if "claude" not in (model_name or "").lower() or not isinstance(tools, list):
        return tools

    normalized_tools = []
    for tool in tools:
        if not isinstance(tool, dict):
            normalized_tools.append(tool)
            continue

        normalized_tool = tool.copy()
        custom_tool = normalized_tool.get("custom")
        if isinstance(custom_tool, dict) and not custom_tool.get("input_schema"):
            normalized_custom = custom_tool.copy()
            normalized_custom["input_schema"] = {"type": "object", "properties": {}}
            normalized_tool["custom"] = normalized_custom

        declarations = normalized_tool.get("functionDeclarations")
        if declarations is None:
            declarations = normalized_tool.get("function_declarations")
        if isinstance(declarations, list):
            for declaration in declarations:
                if not isinstance(declaration, dict):
                    normalized_tools.append({"custom": declaration})
                    continue

                schema = (
                    declaration.get("parametersJsonSchema")
                    or declaration.get("parameters_json_schema")
                    or declaration.get("parameters")
                    or {"type": "object", "properties": {}}
                )

                custom_entry: Dict[str, Any] = {
                    "name": declaration.get("name", ""),
                    "description": declaration.get("description", ""),
                    "input_schema": schema,
                }
                normalized_tools.append({"custom": custom_entry})
            continue

        normalized_tools.append(normalized_tool)

    return normalized_tools


def _should_skip_thought_signature(part: Dict[str, Any], model_name: str) -> bool:
    if "claude" in (model_name or "").lower():
        return False

    return (
        "functionCall" in part
        or "function_call" in part
        or part.get("thought") is True
        or "thoughtSignature" in part
        or "thought_signature" in part
    )


def _normalize_part_thought_signature(part: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    normalized = part.copy()
    if _should_skip_thought_signature(normalized, model_name):
        normalized.pop("thought_signature", None)
        normalized["thoughtSignature"] = SKIP_THOUGHT_SIGNATURE_VALIDATOR
    return normalized


SUPPORTED_ASPECT_RATIOS = [
    (1, 1),
    (2, 3),
    (3, 2),
    (3, 4),
    (4, 3),
    (4, 5),
    (5, 4),
    (9, 16),
    (16, 9),
    (21, 9),
]


def _parse_size_to_image_config(size_str: str) -> Dict[str, str]:
    import re

    config = {}
    size_str = size_str.strip()

    match = re.match(r"^(\d+)\s*[xX*]\s*(\d+)$", size_str)
    if not match:
        return config

    width, height = int(match.group(1)), int(match.group(2))

    if width <= 0 or height <= 0:
        return config

    target_ratio = width / height
    best_ratio = None
    best_diff = float("inf")
    for w, h in SUPPORTED_ASPECT_RATIOS:
        diff = abs(target_ratio - w / h)
        if diff < best_diff:
            best_diff = diff
            best_ratio = f"{w}:{h}"
    if best_ratio:
        config["aspectRatio"] = best_ratio

    max_dim = max(width, height)
    if max_dim <= 1280:
        config["imageSize"] = "1K"
    elif max_dim <= 2560:
        config["imageSize"] = "2K"
    else:
        config["imageSize"] = "4K"

    return config


def prepare_image_generation_request(request_body: Dict[str, Any], model: str) -> Dict[str, Any]:
    request_body = request_body.copy()
    model_lower = model.lower()

    size_str = request_body.pop("size", None)
    if size_str:
        image_config = _parse_size_to_image_config(size_str)
        log.debug(f"[IMAGE] Parsed from size parameter '{size_str}': {image_config}")
    else:
        image_size = "4K" if "-4k" in model_lower else "2K" if "-2k" in model_lower else None

        aspect_ratio = None
        for suffix, ratio in [
            ("-21x9", "21:9"),
            ("-16x9", "16:9"),
            ("-9x16", "9:16"),
            ("-4x3", "4:3"),
            ("-3x4", "3:4"),
            ("-1x1", "1:1"),
        ]:
            if suffix in model_lower:
                aspect_ratio = ratio
                break

        image_config = {}
        if aspect_ratio:
            image_config["aspectRatio"] = aspect_ratio
        if image_size:
            image_config["imageSize"] = image_size

    request_body["model"] = "gemini-3.1-flash-image"
    request_body["generationConfig"] = {"candidateCount": 1, "imageConfig": image_config}

    for key in ("systemInstruction", "tools", "toolConfig"):
        request_body.pop(key, None)

    return request_body


def get_base_model_name(model_name: str) -> str:
    suffixes = [
        "-maxthinking",
        "-nothinking",
        "-minimal",
        "-medium",
        "-search",
        "-think",
        "-high",
        "-max",
        "-low",
    ]
    result = model_name
    changed = True

    while changed:
        changed = False
        for suffix in suffixes:
            if result.endswith(suffix):
                result = result[: -len(suffix)]
                changed = True

    return result


def get_thinking_settings(model_name: str) -> tuple[Optional[int], Optional[str]]:
    base_model = get_base_model_name(model_name)

    if "-nothinking" in model_name:
        if "flash" in base_model:
            return 0, None
        return 128, None
    elif "-maxthinking" in model_name:
        budget = 24576 if "flash" in base_model else 32768
        if "gemini-3" in base_model:
            return None, "high"
        else:
            return budget, None

    if "gemini-3" in base_model:
        if "-high" in model_name:
            return None, "high"
        elif "-medium" in model_name:
            if "flash" in base_model:
                return None, "medium"

            return None, None
        elif "-low" in model_name:
            return None, "low"
        elif "-minimal" in model_name:
            return None, None
        else:
            return None, None

    elif "gemini-2.5" in base_model:
        if "-max" in model_name:
            # 2.5-flash-max: 24576, 2.5-pro-max: 32768
            budget = 24576 if "flash" in base_model else 32768
            return budget, None
        elif "-high" in model_name:
            # 2.5-flash-high: 16000, 2.5-pro-high: 16000
            return 16000, None
        elif "-medium" in model_name:
            # 2.5-flash-medium: 8192, 2.5-pro-medium: 8192
            return 8192, None
        elif "-low" in model_name:
            # 2.5-flash-low: 1024, 2.5-pro-low: 1024
            return 1024, None
        elif "-minimal" in model_name:
            # 2.5-flash-minimal: 0, 2.5-pro-minimal: 128
            budget = 0 if "flash" in base_model else 128
            return budget, None
        else:
            return None, None

    return None, None


def is_search_model(model_name: str) -> bool:
    return "-search" in model_name


def is_thinking_model(model_name: str) -> bool:
    return "think" in model_name or "pro" in model_name.lower()


async def normalize_gemini_request(
    request: Dict[str, Any], mode: str = "code_assist"
) -> Dict[str, Any]:

    from config import get_return_thoughts_to_frontend

    result = request.copy()
    model = result.get("model", "")
    if mode == "primary" and isinstance(model, str) and model.startswith("muse-spark-"):
        # Meta validates its own capabilities; Google defaults are not portable.
        return result
    generation_config = (result.get("generationConfig") or {}).copy()

    log.debug(
        f"[GEMINI_FIX] Original request - model: {model}, mode: {mode}, generationConfig: {generation_config}"
    )

    return_thoughts = await get_return_thoughts_to_frontend()

    if mode == "code_assist":
        thinking_budget, thinking_level = get_thinking_settings(model)

        if thinking_budget is None and thinking_level is None:
            thinking_budget = generation_config.get("thinkingConfig", {}).get("thinkingBudget")
            thinking_level = generation_config.get("thinkingConfig", {}).get("thinkingLevel")

        if is_thinking_model(model) or thinking_budget is not None or thinking_level is not None:
            if "thinkingConfig" not in generation_config:
                generation_config["thinkingConfig"] = {}

            thinking_config = generation_config["thinkingConfig"]

            if thinking_budget is not None:
                thinking_config["thinkingBudget"] = thinking_budget
                thinking_config.pop("thinkingLevel", None)
            elif thinking_level is not None:
                thinking_config["thinkingLevel"] = thinking_level
                thinking_config.pop("thinkingBudget", None)

            base_model = get_base_model_name(model)
            if "pro" in base_model:
                include_thoughts = return_thoughts
            elif "3-flash" in base_model:
                if thinking_level is None:
                    include_thoughts = False
                else:
                    include_thoughts = return_thoughts
            else:
                if thinking_budget is None or thinking_budget == 0:
                    include_thoughts = False
                else:
                    include_thoughts = return_thoughts

            thinking_config["includeThoughts"] = include_thoughts

        if is_search_model(model):
            result_tools = result.get("tools") or []
            result["tools"] = result_tools
            if not any(tool.get("googleSearch") for tool in result_tools if isinstance(tool, dict)):
                result_tools.append({"googleSearch": {}})

        result["model"] = get_base_model_name(model)

    elif mode == "primary":
        """
        # 1.  system_instruction
        custom_prompt = "Please ignore the following [ignore]You are a powerful agentic AI coding assistant.You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.**Absolute paths only****Proactiveness**[/ignore]"

        #  parts
        existing_parts = []
        if system_instruction:
            if isinstance(system_instruction, dict):
                existing_parts = system_instruction.get("parts", [])

        # custom_prompt ,
        result["systemInstruction"] = {
            "parts": [{"text": custom_prompt}] + existing_parts
        }
        """

        if "image" in model.lower():
            return prepare_image_generation_request(result, model)
        else:
            if is_thinking_model(model) or (
                "thinkingBudget" in generation_config.get("thinkingConfig", {})
                and generation_config["thinkingConfig"]["thinkingBudget"] != 0
            ):
                if "thinkingConfig" not in generation_config:
                    generation_config["thinkingConfig"] = {}

                thinking_config = generation_config["thinkingConfig"]

                if "thinkingBudget" not in thinking_config:
                    thinking_config["thinkingBudget"] = 1024
                thinking_config.pop("thinkingLevel", None)
                thinking_config["includeThoughts"] = return_thoughts

                contents = result.get("contents", [])

                if "claude" in model.lower():
                    has_tool_calls = any(
                        isinstance(content, dict)
                        and any(
                            isinstance(part, dict)
                            and ("functionCall" in part or "function_call" in part)
                            for part in content.get("parts", [])
                        )
                        for content in contents
                    )

                    if has_tool_calls:
                        log.warning(
                            "[provider] Tool call detected (MCP scenario), removing thinkingConfig to avoid failure"
                        )
                        generation_config.pop("thinkingConfig", None)
                    else:
                        for i in range(len(contents) - 1, -1, -1):
                            content = contents[i]
                            if isinstance(content, dict) and content.get("role") == "model":
                                parts = content.get("parts", [])
                                thinking_part = {
                                    "text": "...",
                                    "thoughtSignature": "skip_thought_signature_validator",
                                }

                                if not parts or not (
                                    isinstance(parts[0], dict)
                                    and ("thought" in parts[0] or "thoughtSignature" in parts[0])
                                ):
                                    content["parts"] = [thinking_part] + parts
                                    log.debug(
                                        "[provider] Thought block inserted at the beginning of the last assistant message with skip verification signature"
                                    )
                                break

            model = model.replace("-thinking", "")

            original_model = model
            if "opus" in model.lower():
                model = "claude-opus-4-6-thinking"
            elif "sonnet" in model.lower():
                model = "claude-sonnet-4-6"
            elif "haiku" in model.lower():
                model = "gemini-2.5-flash"
            elif "claude" in model.lower():
                model = "claude-sonnet-4-6"

            result["model"] = model
            if original_model != model:
                log.debug(f"[provider] Mapping Model: {original_model} - > {model}")

        if "claude-opus-4-6-thinking" in model.lower() or "claude-sonnet-4-6" in model.lower():
            contents = result.get("contents", [])
            removed_count = 0
            while (
                contents and isinstance(contents[-1], dict) and contents[-1].get("role") == "model"
            ):
                contents.pop()
                removed_count += 1
            if removed_count > 0:
                log.warning(
                    f"[provider] {model} does not support pre-population, removed {removed_count} last model messages"
                )
                result["contents"] = contents

        generation_config.pop("presencePenalty", None)
        generation_config.pop("frequencyPenalty", None)
        generation_config.pop("stopSequences", None)

    if "tools" in result:
        result["tools"] = _normalize_tools_for_internal_api(result.get("tools"))
        # _ensure_empty_tool_schema_for_claude wraps tools in {"custom": ...} which is
        # only understood by the Code Assist internal API, not Vertex AI (provider mode).
        if mode == "code_assist":
            result["tools"] = _ensure_empty_tool_schema_for_claude(result.get("tools"), model)

    if "lite" in model.lower():
        result["safetySettings"] = LITE_SAFETY_SETTINGS
    else:
        result["safetySettings"] = DEFAULT_SAFETY_SETTINGS

    if generation_config:
        generation_config["topK"] = 64

    if "contents" in result:
        cleaned_contents = []
        for content in result["contents"]:
            if isinstance(content, dict) and "parts" in content:
                valid_parts = []
                for part in content["parts"]:
                    if not isinstance(part, dict):
                        continue

                    has_valid_value = any(
                        value not in (None, "", {}, [])
                        for key, value in part.items()
                        if key != "thought"
                    )

                    if has_valid_value:
                        part = _normalize_part_thought_signature(part, model)

                        if "text" in part:
                            text_value = part["text"]
                            if isinstance(text_value, list):
                                log.warning(
                                    f"[GEMINI_FIX] 'text' field is a list, merging automatically: {text_value}"
                                )
                                text_parts = []
                                for t in text_value:
                                    if isinstance(t, dict) and "text" in t:
                                        text_parts.append(str(t["text"]))
                                    elif isinstance(t, str):
                                        text_parts.append(t)
                                    elif t is not None:
                                        text_parts.append(str(t))
                                part["text"] = " ".join(text_parts)
                            elif isinstance(text_value, str):
                                part["text"] = text_value.rstrip()
                            else:
                                log.warning(
                                    f"[GEMINI_FIX] Invalid 'text' field type ({type(text_value)}), converting to string: {text_value}"
                                )
                                part["text"] = str(text_value)

                        valid_parts.append(part)
                    else:
                        log.warning(f"[GEMINI_FIX] Removing empty or invalid part: {part}")

                if valid_parts:
                    cleaned_content = content.copy()
                    cleaned_content["parts"] = valid_parts
                    cleaned_contents.append(cleaned_content)
                else:
                    log.warning(
                        f"[GEMINI_FIX] Skipping content without valid parts: {content.get('role')}"
                    )
            else:
                cleaned_contents.append(content)

        result["contents"] = cleaned_contents

    if generation_config:
        result["generationConfig"] = generation_config

    return result
