import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from core.converter.thought_signature import (
    SKIP_THOUGHT_SIGNATURE_VALIDATOR,
    decode_tool_id_and_signature,
    is_internal_placeholder_text,
    is_skip_thought_signature_placeholder,
)
from core.converter.utils import merge_system_messages
from core.protocol_contract import validate_gemini_response_part
from log import log
from pypinyin import Style, lazy_pinyin


def _convert_usage_metadata(usage_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not usage_metadata:
        return None

    prompt_tokens_total = int(usage_metadata.get("promptTokenCount", 0) or 0)
    cached_tokens = int(usage_metadata.get("cachedContentTokenCount", 0) or 0)
    prompt_tokens = prompt_tokens_total
    reasoning_tokens = int(usage_metadata.get("thoughtsTokenCount", 0) or 0)
    completion_tokens = int(usage_metadata.get("candidatesTokenCount", 0) or 0) + reasoning_tokens
    raw_total_tokens = int(
        usage_metadata.get(
            "totalTokenCount",
            prompt_tokens_total + completion_tokens + reasoning_tokens,
        )
        or 0
    )

    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": max(raw_total_tokens, prompt_tokens + completion_tokens),
    }

    if cached_tokens > 0:
        usage["prompt_tokens_details"] = {"cached_tokens": cached_tokens}

    if reasoning_tokens > 0:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}

    return usage


def _build_message_with_reasoning(role: str, content: str, reasoning_content: str) -> dict:
    message = {"role": role, "content": content}

    if reasoning_content:
        message["reasoning_content"] = reasoning_content

    return message


def _map_finish_reason(gemini_reason: Optional[str]) -> Optional[str]:
    if gemini_reason is None:
        return None
    if gemini_reason == "STOP":
        return "stop"
    elif gemini_reason == "MAX_TOKENS":
        return "length"
    elif gemini_reason in ["SAFETY", "RECITATION"]:
        return "content_filter"
    else:
        return "stop"


# ==================== Tool Conversion Functions ====================


def _normalize_function_name(name: str) -> str:
    import re

    if not name:
        return "_unnamed_function"

    if re.search(r"[\u4e00-\u9fff]", name):
        try:
            parts = []
            for char in name:
                if "\u4e00" <= char <= "\u9fff":
                    pinyin = lazy_pinyin(char, style=Style.NORMAL)
                    parts.append("".join(pinyin))
                else:
                    parts.append(char)
            normalized = "".join(parts)
        except ImportError:
            log.warning("pypinyin not installed, cannot convert Chinese characters to pinyin")
            normalized = name
    else:
        normalized = name

    normalized = re.sub(r"[^a-zA-Z0-9_.\-]", "_", normalized)

    if normalized and not (normalized[0].isalpha() or normalized[0] == "_"):
        normalized = "_" + normalized

    if len(normalized) > 64:
        normalized = normalized[:64]

    if not normalized:
        normalized = "_unnamed_function"

    return normalized


def _resolve_ref(ref: str, root_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(ref, str):
        return None

    if not ref.startswith("#/"):
        for key in ["definitions", "$defs"]:
            if key in root_schema and ref in root_schema[key]:
                return root_schema[key][ref]
        return None

    path = ref[2:].split("/")
    current = root_schema

    for segment in path:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None

    return current if isinstance(current, dict) else None


def _clean_schema_for_claude(
    schema: Any, root_schema: Optional[Dict[str, Any]] = None, visited: Optional[set] = None
) -> Any:

    if not isinstance(schema, dict):
        return schema

    if root_schema is None:
        root_schema = schema
    if visited is None:
        visited = set()

    schema_id = id(schema)
    if schema_id in visited:
        return schema
    visited.add(schema_id)

    result = {}

    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], root_schema)
        if resolved:
            import copy

            result = copy.deepcopy(resolved)
            for key, value in schema.items():
                if key != "$ref":
                    result[key] = value
            schema = result
            result = {}

    if "allOf" in schema:
        all_of_schemas = schema["allOf"]
        for item in all_of_schemas:
            cleaned_item = _clean_schema_for_claude(item, root_schema, visited)

            if "properties" in cleaned_item:
                if "properties" not in result:
                    result["properties"] = {}
                result["properties"].update(cleaned_item["properties"])

            if "required" in cleaned_item:
                if "required" not in result:
                    result["required"] = []
                result["required"].extend(cleaned_item["required"])

            for key, value in cleaned_item.items():
                if key not in ["properties", "required"]:
                    result[key] = value

        for key, value in schema.items():
            if key not in ["allOf", "properties", "required"]:
                result[key] = value
            elif key in ["properties", "required"] and key not in result:
                result[key] = value
    else:
        result = dict(schema)

    if "type" in result:
        type_value = result["type"]
        if isinstance(type_value, list):
            pass

    if result.get("type") == "array":
        if "items" not in result:
            result["items"] = {}
        elif isinstance(result["items"], list):
            tuple_items = result["items"]
            first_type = tuple_items[0].get("type") if tuple_items else None
            is_homogeneous = all(item.get("type") == first_type for item in tuple_items)

            if is_homogeneous and first_type:
                result["items"] = _clean_schema_for_claude(tuple_items[0], root_schema, visited)
            else:
                result["items"] = {
                    "anyOf": [
                        _clean_schema_for_claude(item, root_schema, visited) for item in tuple_items
                    ]
                }
        else:
            result["items"] = _clean_schema_for_claude(result["items"], root_schema, visited)

    if "anyOf" in result:
        result["anyOf"] = [
            _clean_schema_for_claude(item, root_schema, visited) for item in result["anyOf"]
        ]

    unsupported_keys = {
        "title",
        "$schema",
        "strict",
        "additionalItems",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "$defs",
        "definitions",
        "example",
        "examples",
        "readOnly",
        "writeOnly",
        "const",
        "contentEncoding",
        "contentMediaType",
        "oneOf",
        "patternProperties",
        "dependencies",
        "propertyNames",
    }

    for key in list(result.keys()):
        if key in unsupported_keys:
            del result[key]

    if "additionalProperties" in result and isinstance(result["additionalProperties"], dict):
        result["additionalProperties"] = _clean_schema_for_claude(
            result["additionalProperties"], root_schema, visited
        )

    if "properties" in result:
        cleaned_props = {}
        for prop_name, prop_schema in result["properties"].items():
            cleaned_props[prop_name] = _clean_schema_for_claude(prop_schema, root_schema, visited)
        result["properties"] = cleaned_props

    if "properties" in result and "type" not in result:
        result["type"] = "object"

    if "required" in result and isinstance(result["required"], list):
        result["required"] = list(dict.fromkeys(result["required"]))

    return result


def _clean_schema_for_gemini(
    schema: Any, root_schema: Optional[Dict[str, Any]] = None, visited: Optional[set] = None
) -> Any:

    if not isinstance(schema, dict):
        return schema

    if root_schema is None:
        root_schema = schema
    if visited is None:
        visited = set()

    schema_id = id(schema)
    if schema_id in visited:
        return schema
    visited.add(schema_id)

    result = {}

    ref_key = "$ref" if "$ref" in schema else ("ref" if "ref" in schema else None)
    if ref_key:
        resolved = _resolve_ref(schema[ref_key], root_schema)
        if resolved:
            resolved_id = id(resolved)
            if resolved_id in visited:
                return {"type": "OBJECT", "description": "(circular reference)"}

            visited.add(resolved_id)

            merged = dict(resolved)

            for key in ["description", "default"]:
                if key in schema:
                    merged[key] = schema[key]

            schema = merged
            result = {}

    if "allOf" in schema:
        all_of_schemas = schema["allOf"]
        for item in all_of_schemas:
            cleaned_item = _clean_schema_for_gemini(item, root_schema, visited)

            if "properties" in cleaned_item:
                if "properties" not in result:
                    result["properties"] = {}
                result["properties"].update(cleaned_item["properties"])

            if "required" in cleaned_item:
                if "required" not in result:
                    result["required"] = []
                result["required"].extend(cleaned_item["required"])

            for key, value in cleaned_item.items():
                if key not in ["properties", "required"]:
                    result[key] = value

        for key, value in schema.items():
            if key not in ["allOf", "properties", "required"]:
                result[key] = value
            elif key in ["properties", "required"] and key not in result:
                result[key] = value
    else:
        result = dict(schema)

    if "type" in result:
        type_value = result["type"]

        if isinstance(type_value, list):
            primary_type = next((t for t in type_value if t != "null"), None)
            type_value = primary_type if primary_type else "STRING"

        type_map = {
            "string": "STRING",
            "number": "NUMBER",
            "integer": "INTEGER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT",
        }

        if isinstance(type_value, str) and type_value.lower() in type_map:
            result["type"] = type_map[type_value.lower()]
        else:
            del result["type"]

    if result.get("type") == "ARRAY":
        if "items" not in result:
            result["items"] = {}
        elif isinstance(result["items"], list):
            tuple_items = result["items"]

            tuple_types = [item.get("type", "any") for item in tuple_items]
            tuple_desc = f"(Tuple: [{', '.join(tuple_types)}])"

            original_desc = result.get("description", "")
            result["description"] = f"{original_desc} {tuple_desc}".strip()

            first_type = tuple_items[0].get("type") if tuple_items else None
            is_homogeneous = all(item.get("type") == first_type for item in tuple_items)

            if is_homogeneous and first_type:
                result["items"] = _clean_schema_for_gemini(tuple_items[0], root_schema, visited)
            else:
                result["items"] = {}
        else:
            result["items"] = _clean_schema_for_gemini(result["items"], root_schema, visited)

    if "anyOf" in result:
        any_of_schemas = result["anyOf"]

        cleaned_any_of = [
            _clean_schema_for_gemini(item, root_schema, visited) for item in any_of_schemas
        ]

        if all("const" in item for item in cleaned_any_of):
            enum_values = [
                str(item["const"]) for item in cleaned_any_of if item.get("const") not in ["", None]
            ]
            if enum_values:
                result["type"] = "STRING"
                result["enum"] = enum_values
        elif "type" not in result:
            first_valid = next(
                (item for item in cleaned_any_of if item.get("type") or item.get("enum")), None
            )
            if first_valid:
                result.update(first_valid)

        del result["anyOf"]

    if "default" in result:
        default_value = result["default"]
        original_desc = result.get("description", "")
        result["description"] = f"{original_desc} (Default: {json.dumps(default_value)})".strip()
        del result["default"]

    unsupported_keys = {
        "title",
        "$schema",
        "$ref",
        "ref",
        "strict",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "additionalProperties",
        "oneOf",
        "allOf",
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
        if key in unsupported_keys:
            del result[key]

    if "properties" in result:
        cleaned_props = {}
        for prop_name, prop_schema in result["properties"].items():
            cleaned_props[prop_name] = _clean_schema_for_gemini(prop_schema, root_schema, visited)
        result["properties"] = cleaned_props

    if "properties" in result and "type" not in result:
        result["type"] = "OBJECT"

    if "required" in result and isinstance(result["required"], list):
        result["required"] = list(dict.fromkeys(result["required"]))

    return result


def _append_schema_hint(schema: Dict[str, Any], hint: str) -> None:
    if not hint:
        return
    desc = schema.get("description")
    schema["description"] = f"{desc} ({hint})" if desc else hint


def _clean_schema_for_parameters_json_schema(
    schema: Any,
    root_schema: Optional[Dict[str, Any]] = None,
    visited: Optional[set] = None,
) -> Any:
    if not isinstance(schema, dict):
        return schema

    if root_schema is None:
        root_schema = schema
    if visited is None:
        visited = set()

    schema_id = id(schema)
    if schema_id in visited:
        return {"type": "object", "description": "(circular reference)"}
    visited.add(schema_id)

    result: Dict[str, Any]

    ref_key = "$ref" if "$ref" in schema else ("ref" if "ref" in schema else None)
    if ref_key:
        resolved = _resolve_ref(schema[ref_key], root_schema)
        if resolved:
            import copy

            result = copy.deepcopy(resolved)
            for key in ("description", "default"):
                if key in schema:
                    result[key] = schema[key]
            schema = result

    if "allOf" in schema:
        result = {}
        for item in schema.get("allOf") or []:
            cleaned_item = _clean_schema_for_parameters_json_schema(item, root_schema, visited)
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

    if "type" in result:
        type_value = result["type"]
        if isinstance(type_value, list):
            non_null_types = [t for t in type_value if isinstance(t, str) and t.lower() != "null"]
            if non_null_types:
                result["type"] = non_null_types[0]
                if "null" in [str(t).lower() for t in type_value]:
                    _append_schema_hint(result, "nullable")
            else:
                result["type"] = "string"
        elif isinstance(type_value, str):
            lower_type = type_value.lower()
            if lower_type in {"string", "number", "integer", "boolean", "array", "object", "null"}:
                result["type"] = "string" if lower_type == "null" else lower_type
            else:
                del result["type"]

    if "anyOf" in result or "oneOf" in result:
        union_key = "anyOf" if "anyOf" in result else "oneOf"
        union_items = result.get(union_key) or []
        cleaned_items = [
            item
            for item in (
                _clean_schema_for_parameters_json_schema(item, root_schema, visited)
                for item in union_items
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
                existing_description = result.get("description")
                result.update(preferred)
                if existing_description:
                    _append_schema_hint(result, existing_description)
        result.pop("anyOf", None)
        result.pop("oneOf", None)

    if result.get("type") == "array":
        items = result.get("items")
        if isinstance(items, list):
            if items:
                result["items"] = _clean_schema_for_parameters_json_schema(
                    items[0], root_schema, visited
                )
                _append_schema_hint(result, "tuple schema simplified")
            else:
                result.pop("items", None)
        elif isinstance(items, dict):
            result["items"] = _clean_schema_for_parameters_json_schema(items, root_schema, visited)

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
    if "properties" in result and isinstance(result["properties"], dict):
        cleaned_props = {}
        for prop_name, prop_schema in result["properties"].items():
            if isinstance(prop_schema, dict):
                prop_type = prop_schema.get("type")
                if isinstance(prop_type, list) and any(str(t).lower() == "null" for t in prop_type):
                    nullable_props.add(prop_name)
            cleaned_props[prop_name] = _clean_schema_for_parameters_json_schema(
                prop_schema, root_schema, visited
            )
        result["properties"] = cleaned_props

    if "properties" in result and "type" not in result:
        result["type"] = "object"

    if "required" in result and isinstance(result["required"], list):
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


def fix_tool_call_args_types(
    args: Dict[str, Any], parameters_schema: Dict[str, Any]
) -> Dict[str, Any]:
    if not args or not parameters_schema:
        return args

    properties = parameters_schema.get("properties", {})
    if not properties:
        return args

    fixed_args = {}
    for key, value in args.items():
        if key not in properties:
            fixed_args[key] = value
            continue

        param_schema = properties[key]
        param_type = param_schema.get("type")

        if param_type == "number" or param_type == "integer":
            if isinstance(value, str):
                try:
                    if param_type == "integer":
                        fixed_args[key] = int(value)
                    else:
                        num_value = float(value)
                        fixed_args[key] = int(num_value) if num_value.is_integer() else num_value
                    log.debug(
                        f"[OPENAI2GEMINI] Fixed parameter type: {key} '{value}' -> {fixed_args[key]} ({param_type})"
                    )
                except (ValueError, AttributeError):
                    fixed_args[key] = value
                    log.warning(
                        f"[OPENAI2GEMINI] Unable to convert value '{key}' of parameter {value} to {param_type}"
                    )
            else:
                fixed_args[key] = value
        elif param_type == "boolean":
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    fixed_args[key] = True
                elif value.lower() in ("false", "0", "no"):
                    fixed_args[key] = False
                else:
                    fixed_args[key] = value

                if fixed_args[key] != value:
                    log.debug(
                        f"[OPENAI2GEMINI] Fixed parameter type: {key} '{value}' -> {fixed_args[key]} (boolean)"
                    )
            else:
                fixed_args[key] = value
        elif param_type == "string":
            if not isinstance(value, str):
                fixed_args[key] = str(value)
                log.debug(
                    f"[OPENAI2GEMINI] Fixed parameter type: {key} {value} -> '{fixed_args[key]}' (string)"
                )
            else:
                fixed_args[key] = value
        else:
            fixed_args[key] = value

    return fixed_args


def convert_openai_tools_to_gemini(openai_tools: List, model: str = "") -> List[Dict[str, Any]]:
    if not openai_tools:
        return []

    is_claude_model = "claude" in model.lower()

    function_declarations = []

    for tool in openai_tools:
        if tool.get("type") != "function":
            log.warning(f"Skipping non-function tool type: {tool.get('type')}")
            continue

        function = tool.get("function")
        if not function:
            log.warning("Tool missing 'function' field")
            continue

        original_name = function.get("name")
        if not original_name:
            log.warning("Tool missing 'name' field, using default")
            original_name = "_unnamed_function"

        normalized_name = _normalize_function_name(original_name)

        if normalized_name != original_name:
            log.debug(f"Function name normalized: '{original_name}' -> '{normalized_name}'")

        declaration = {
            "name": normalized_name,
            "description": function.get("description", ""),
        }

        if "parameters" in function:
            if is_claude_model:
                cleaned_params = _clean_schema_for_parameters_json_schema(function["parameters"])
                log.debug(
                    f"[OPENAI2GEMINI] Using Claude schema cleaning for tool: {normalized_name}"
                )
            else:
                cleaned_params = _clean_schema_for_parameters_json_schema(function["parameters"])

            if cleaned_params:
                declaration["parametersJsonSchema"] = cleaned_params
            elif is_claude_model:
                declaration["parametersJsonSchema"] = {"type": "object", "properties": {}}
        elif is_claude_model:
            declaration["parametersJsonSchema"] = {"type": "object", "properties": {}}

        function_declarations.append(declaration)

    if not function_declarations:
        return []

    return [{"functionDeclarations": function_declarations}]


def convert_tool_choice_to_tool_config(tool_choice: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        elif tool_choice == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
        elif tool_choice == "required":
            return {"functionCallingConfig": {"mode": "ANY"}}
    elif isinstance(tool_choice, dict):
        # {"type": "function", "function": {"name": "my_function"}}
        if tool_choice.get("type") == "function":
            function_name = tool_choice.get("function", {}).get("name")
            if function_name:
                return {
                    "functionCallingConfig": {
                        "mode": "ANY",
                        "allowedFunctionNames": [function_name],
                    }
                }

    return {"functionCallingConfig": {"mode": "AUTO"}}


def convert_tool_message_to_function_response(message, all_messages: List = None) -> Dict[str, Any]:

    name = getattr(message, "name", None)
    encoded_tool_call_id = getattr(message, "tool_call_id", None) or ""

    original_tool_call_id, _ = decode_tool_id_and_signature(encoded_tool_call_id)

    if not name and encoded_tool_call_id and all_messages:
        for msg in all_messages:
            if (
                getattr(msg, "role", None) == "assistant"
                and hasattr(msg, "tool_calls")
                and msg.tool_calls
            ):
                for tool_call in msg.tool_calls:
                    if getattr(tool_call, "id", None) == encoded_tool_call_id:
                        func = getattr(tool_call, "function", None)
                        if func:
                            name = getattr(func, "name", None)
                            break
                if name:
                    break

    if not name:
        name = "unknown_function"
        log.warning(f"Tool message missing function name, using default: {name}")

    try:
        response_data = (
            json.loads(message.content) if isinstance(message.content, str) else message.content
        )
    except (json.JSONDecodeError, TypeError):
        response_data = {"result": str(message.content)}

    if not isinstance(response_data, dict):
        response_data = {"result": response_data}

    return {
        "functionResponse": {"id": original_tool_call_id, "name": name, "response": response_data}
    }


def _reverse_transform_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    if value == "true":
        return True
    if value == "false":
        return False

    # null
    if value == "null":
        return None

    return value


def _reverse_transform_args(args: Any) -> Any:
    if not isinstance(args, (dict, list)):
        return args

    if isinstance(args, list):
        return [_reverse_transform_args(item) for item in args]

    result = {}
    for key, value in args.items():
        if isinstance(value, (dict, list)):
            result[key] = _reverse_transform_args(value)
        else:
            result[key] = _reverse_transform_value(value)

    return result


def extract_tool_calls_from_parts(
    parts: List[Dict[str, Any]], is_streaming: bool = False
) -> Tuple[List[Dict[str, Any]], str]:
    tool_calls = []
    text_content = ""

    for idx, part in enumerate(parts):
        if "functionCall" in part:
            function_call = part["functionCall"]

            original_id = function_call.get("id") or f"call_{uuid.uuid4().hex[:24]}"

            args = function_call.get("args", {})

            args = _reverse_transform_args(args)

            tool_call = {
                "id": original_id,
                "type": "function",
                "function": {
                    "name": function_call.get("name", "nameless_function"),
                    "arguments": json.dumps(args),
                },
            }

            if is_streaming:
                tool_call["index"] = idx
            tool_calls.append(tool_call)

        elif "text" in part and not part.get("thought", False):
            text = part["text"]
            if is_skip_thought_signature_placeholder(part) or is_internal_placeholder_text(text):
                continue
            text_content += text

    return tool_calls, text_content


def extract_images_from_content(content: Any) -> Dict[str, Any]:
    result = {"text": "", "images": []}

    if isinstance(content, str):
        result["text"] = content
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    result["text"] += item.get("text", "")
                elif item.get("type") == "image_url":
                    image_url = item.get("image_url", {}).get("url", "")

                    if image_url.startswith("data:image/"):
                        import re

                        match = re.match(r"^data:image/(\w+);base64,(.+)$", image_url)
                        if match:
                            mime_type = match.group(1)
                            base64_data = match.group(2)
                            result["images"].append(
                                {
                                    "inlineData": {
                                        "mimeType": f"image/{mime_type}",
                                        "data": base64_data,
                                    }
                                }
                            )

    return result


def _sanitize_openai_roundtrip_signatures(contents: List[Dict[str, Any]]) -> None:
    """
    OpenAI-compatible clients may round-trip Gemini thinking signatures through
    fields we do not fully control. Keep tool calls on the safe bypass sentinel
    and drop signatures everywhere else to avoid Corrupted thought signature.
    """
    for content in contents:
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue

            sanitized_part = part.copy()
            if "thoughtSignature" in sanitized_part:
                if "functionCall" in sanitized_part or "function_call" in sanitized_part:
                    sanitized_part["thoughtSignature"] = SKIP_THOUGHT_SIGNATURE_VALIDATOR
                else:
                    sanitized_part.pop("thoughtSignature", None)

            if sanitized_part.get("thought") is True and not sanitized_part.get("thoughtSignature"):
                sanitized_part.pop("thought", None)

            parts[index] = sanitized_part


async def convert_openai_to_gemini_request(openai_request: Dict[str, Any]) -> Dict[str, Any]:

    openai_request = await merge_system_messages(openai_request)

    contents = []

    messages = openai_request.get("messages", [])

    tool_call_mapping = {}
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                encoded_id = tc.get("id", "")
                func_name = tc.get("function", {}).get("name") or ""
                if encoded_id:
                    original_id, _ = decode_tool_id_and_signature(encoded_id)
                    tool_call_mapping[encoded_id] = (func_name, original_id, None)

    tool_schemas = {}
    if "tools" in openai_request and openai_request["tools"]:
        for tool in openai_request["tools"]:
            if tool.get("type") == "function":
                function = tool.get("function", {})
                func_name = function.get("name")
                if func_name:
                    tool_schemas[func_name] = function.get("parameters", {})

    pending_tool_parts = []

    def flush_pending_tool_parts():
        nonlocal pending_tool_parts
        if pending_tool_parts:
            contents.append({"role": "user", "parts": pending_tool_parts})
            pending_tool_parts = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        if role == "tool":
            tool_call_id = message.get("tool_call_id", "")
            func_name = message.get("name")

            if tool_call_id in tool_call_mapping:
                func_name, original_id, _ = tool_call_mapping[tool_call_id]
            else:
                if not func_name and tool_call_id:
                    for msg in messages:
                        if msg.get("role") == "assistant" and msg.get("tool_calls"):
                            for tc in msg["tool_calls"]:
                                if tc.get("id") == tool_call_id:
                                    func_name = tc.get("function", {}).get("name")
                                    break
                            if func_name:
                                break

                original_id, _ = decode_tool_id_and_signature(tool_call_id)

            if not func_name:
                func_name = "unknown_function"
                log.warning(
                    f"Tool message missing function name for tool_call_id={tool_call_id}, using default: {func_name}"
                )

            try:
                response_data = json.loads(content) if isinstance(content, str) else content
            except (json.JSONDecodeError, TypeError):
                response_data = {"result": str(content)}

            if not isinstance(response_data, dict):
                response_data = {"result": response_data}

            pending_tool_parts.append(
                {
                    "functionResponse": {
                        "id": original_id,
                        "name": func_name,
                        "response": response_data,
                    }
                }
            )
            continue

        flush_pending_tool_parts()

        if role == "system":
            continue

        if role == "assistant":
            role = "model"

        tool_calls = message.get("tool_calls")
        if tool_calls:
            parts = []

            if content:
                if isinstance(content, list):
                    for _part in content:
                        if isinstance(_part, dict):
                            if _part.get("type") == "text" or "text" in _part:
                                _t = _part.get("text", "")
                                if _t:
                                    parts.append({"text": _t})
                        elif isinstance(_part, str) and _part:
                            parts.append({"text": _part})
                elif isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, dict):
                    _t = content.get("text", "")
                    if _t:
                        parts.append({"text": _t})
                else:
                    parts.append({"text": str(content)})

            for tool_call in tool_calls:
                try:
                    args = (
                        json.loads(tool_call["function"]["arguments"])
                        if isinstance(tool_call["function"]["arguments"], str)
                        else tool_call["function"]["arguments"]
                    )

                    func_name = tool_call["function"]["name"]
                    if func_name in tool_schemas:
                        args = fix_tool_call_args_types(args, tool_schemas[func_name])

                    encoded_id = tool_call.get("id", "")
                    original_id, signature = decode_tool_id_and_signature(encoded_id)

                    function_call_part = {
                        "functionCall": {"id": original_id, "name": func_name, "args": args}
                    }

                    function_call_part["thoughtSignature"] = SKIP_THOUGHT_SIGNATURE_VALIDATOR

                    parts.append(function_call_part)
                except (json.JSONDecodeError, KeyError) as e:
                    log.error(f"Failed to parse tool call: {e}")
                    continue

            if parts:
                contents.append({"role": role, "parts": parts})
            continue

        if isinstance(content, list):
            parts = []
            for part in content:
                if part.get("type") == "text":
                    parts.append({"text": part.get("text", "")})
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {}).get("url")
                    if image_url:
                        try:
                            mime_type, base64_data = image_url.split(";")
                            _, mime_type = mime_type.split(":")
                            _, base64_data = base64_data.split(",")
                            parts.append(
                                {
                                    "inlineData": {
                                        "mimeType": mime_type,
                                        "data": base64_data,
                                    }
                                }
                            )
                        except ValueError:
                            continue
            if parts:
                contents.append({"role": role, "parts": parts})
        elif content:
            contents.append({"role": role, "parts": [{"text": content}]})

    flush_pending_tool_parts()
    _sanitize_openai_roundtrip_signatures(contents)

    generation_config = {}
    model = openai_request.get("model", "")

    if "temperature" in openai_request:
        generation_config["temperature"] = openai_request["temperature"]
    if "top_p" in openai_request:
        generation_config["topP"] = openai_request["top_p"]
    if "top_k" in openai_request:
        generation_config["topK"] = openai_request["top_k"]
    if "max_tokens" in openai_request or "max_completion_tokens" in openai_request:
        max_tokens = openai_request.get("max_completion_tokens") or openai_request.get("max_tokens")
        generation_config["maxOutputTokens"] = max_tokens
    if "stop" in openai_request:
        stop = openai_request["stop"]
        generation_config["stopSequences"] = [stop] if isinstance(stop, str) else stop
    if "frequency_penalty" in openai_request:
        generation_config["frequencyPenalty"] = openai_request["frequency_penalty"]
    if "presence_penalty" in openai_request:
        generation_config["presencePenalty"] = openai_request["presence_penalty"]
    if "n" in openai_request:
        generation_config["candidateCount"] = openai_request["n"]
    if "seed" in openai_request:
        generation_config["seed"] = openai_request["seed"]

    if "response_format" in openai_request and openai_request["response_format"]:
        response_format = openai_request["response_format"]
        format_type = response_format.get("type")

        if format_type == "json_schema":
            if "json_schema" in response_format and "schema" in response_format["json_schema"]:
                schema = response_format["json_schema"]["schema"]

                generation_config["responseSchema"] = _clean_schema_for_gemini(schema)
                generation_config["responseMimeType"] = "application/json"
        elif format_type == "json_object":
            generation_config["responseMimeType"] = "application/json"
        elif format_type == "text":
            generation_config["responseMimeType"] = "text/plain"

    if not contents:
        contents.append(
            {
                "role": "user",
                "parts": [{"text": "Please answer according to the system instructions."}],
            }
        )

    gemini_request = {"contents": contents, "generationConfig": generation_config}

    if "systemInstruction" in openai_request:
        gemini_request["systemInstruction"] = openai_request["systemInstruction"]

    model = openai_request.get("model", "")
    if "tools" in openai_request and openai_request["tools"]:
        gemini_request["tools"] = convert_openai_tools_to_gemini(openai_request["tools"], model)

    if "tool_choice" in openai_request and openai_request["tool_choice"]:
        gemini_request["toolConfig"] = convert_tool_choice_to_tool_config(
            openai_request["tool_choice"]
        )

    if "size" in openai_request and openai_request["size"]:
        gemini_request["size"] = openai_request["size"]

    return gemini_request


def convert_gemini_to_openai_response(
    gemini_response: Union[Dict[str, Any], Any], model: str, status_code: int = 200
) -> Dict[str, Any]:

    if not (200 <= status_code < 300):
        if isinstance(gemini_response, dict):
            return gemini_response
        else:
            try:
                if hasattr(gemini_response, "json"):
                    return gemini_response.json()
                elif hasattr(gemini_response, "body"):
                    body = gemini_response.body
                    if isinstance(body, bytes):
                        return json.loads(body.decode())
                    return json.loads(str(body))
                else:
                    return {"error": str(gemini_response)}
            except Exception:
                return {"error": str(gemini_response)}

    if not isinstance(gemini_response, dict):
        try:
            if hasattr(gemini_response, "json"):
                gemini_response = gemini_response.json()
            elif hasattr(gemini_response, "body"):
                body = gemini_response.body
                if isinstance(body, bytes):
                    gemini_response = json.loads(body.decode())
                else:
                    gemini_response = json.loads(str(body))
            else:
                gemini_response = json.loads(str(gemini_response))
        except Exception:
            return {"error": "Invalid response format"}

    if "response" in gemini_response:
        gemini_response = gemini_response["response"]

    choices = []

    for candidate in gemini_response.get("candidates", []):
        role = candidate.get("content", {}).get("role", "assistant")

        if role == "model":
            role = "assistant"

        parts = candidate.get("content", {}).get("parts", [])

        tool_calls, text_content = extract_tool_calls_from_parts(parts)

        content_parts = []
        reasoning_parts = []

        for part in parts:
            validate_gemini_response_part(part)
            if "executableCode" in part:
                exec_code = part["executableCode"]
                lang = exec_code.get("language", "python").lower()
                code = exec_code.get("code", "")

                content_parts.append(f"\n```{lang}\n{code}\n```\n")

            elif "codeExecutionResult" in part:
                result = part["codeExecutionResult"]
                outcome = result.get("outcome")
                output = result.get("output", "")

                if output:
                    label = "output" if outcome == "OUTCOME_OK" else "error"
                    content_parts.append(f"\n```{label}\n{output}\n```\n")

            elif (
                part.get("thought", False)
                and "text" in part
                and not is_skip_thought_signature_placeholder(part)
            ):
                reasoning_parts.append(part["text"])

            elif "text" in part and not part.get("thought", False):
                pass

            elif "inlineData" in part:
                inline_data = part["inlineData"]
                mime_type = inline_data.get("mimeType", "image/png")
                base64_data = inline_data.get("data", "")

                content_parts.append(
                    f"![gemini-generated-content](data:{mime_type};base64,{base64_data})"
                )

            elif "functionCall" in part:
                pass

        if content_parts:
            additional_content = "\n\n".join(content_parts)
            if text_content:
                text_content = text_content + "\n\n" + additional_content
            else:
                text_content = additional_content

        reasoning_content = "\n\n".join(reasoning_parts) if reasoning_parts else ""

        message = {"role": role}

        gemini_finish_reason = candidate.get("finishReason")

        if tool_calls:
            message["tool_calls"] = tool_calls
            message["content"] = text_content if text_content else None

            if gemini_finish_reason == "STOP":
                finish_reason = "tool_calls"
            else:
                finish_reason = _map_finish_reason(gemini_finish_reason)
        else:
            message["content"] = text_content
            finish_reason = _map_finish_reason(gemini_finish_reason)

        if reasoning_content:
            message["reasoning_content"] = reasoning_content

        choices.append(
            {
                "index": candidate.get("index", 0),
                "message": message,
                "finish_reason": finish_reason,
            }
        )

    usage = _convert_usage_metadata(gemini_response.get("usageMetadata"))

    response_data = {
        "id": str(uuid.uuid4()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
    }

    if usage:
        response_data["usage"] = usage

    return response_data


def convert_gemini_to_openai_stream(
    gemini_stream_chunk: str, model: str, response_id: str, status_code: int = 200
) -> Optional[str]:

    if not (200 <= status_code < 300):
        return gemini_stream_chunk

    try:
        if isinstance(gemini_stream_chunk, bytes):
            if gemini_stream_chunk.startswith(b"data: "):
                payload_str = gemini_stream_chunk[len(b"data: ") :].strip().decode("utf-8")
            else:
                payload_str = gemini_stream_chunk.strip().decode("utf-8")
        else:
            if gemini_stream_chunk.startswith("data: "):
                payload_str = gemini_stream_chunk[len("data: ") :].strip()
            else:
                payload_str = gemini_stream_chunk.strip()

        if not payload_str:
            return None

        gemini_chunk = json.loads(payload_str)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if "response" in gemini_chunk:
        gemini_response = gemini_chunk["response"]
    else:
        gemini_response = gemini_chunk

    choices = []

    for candidate in gemini_response.get("candidates", []):
        role = candidate.get("content", {}).get("role", "assistant")

        if role == "model":
            role = "assistant"

        parts = candidate.get("content", {}).get("parts", [])

        tool_calls, text_content = extract_tool_calls_from_parts(parts, is_streaming=True)

        content_parts = []
        reasoning_parts = []

        for part in parts:
            if "executableCode" in part:
                exec_code = part["executableCode"]
                lang = exec_code.get("language", "python").lower()
                code = exec_code.get("code", "")
                content_parts.append(f"\n```{lang}\n{code}\n```\n")

            elif "codeExecutionResult" in part:
                result = part["codeExecutionResult"]
                outcome = result.get("outcome")
                output = result.get("output", "")

                if output:
                    label = "output" if outcome == "OUTCOME_OK" else "error"
                    content_parts.append(f"\n```{label}\n{output}\n```\n")

            elif (
                part.get("thought", False)
                and "text" in part
                and not is_skip_thought_signature_placeholder(part)
            ):
                reasoning_parts.append(part["text"])

            elif "text" in part and not part.get("thought", False):
                pass

            elif "inlineData" in part:
                inline_data = part["inlineData"]
                mime_type = inline_data.get("mimeType", "image/png")
                base64_data = inline_data.get("data", "")
                content_parts.append(
                    f"![gemini-generated-content](data:{mime_type};base64,{base64_data})"
                )

        if content_parts:
            additional_content = "\n\n".join(content_parts)
            if text_content:
                text_content = text_content + "\n\n" + additional_content
            else:
                text_content = additional_content

        reasoning_content = "\n\n".join(reasoning_parts) if reasoning_parts else ""

        delta = {}

        if tool_calls:
            delta["tool_calls"] = tool_calls
            if text_content:
                delta["content"] = text_content
        elif text_content:
            delta["content"] = text_content

        if reasoning_content:
            delta["reasoning_content"] = reasoning_content

        gemini_finish_reason = candidate.get("finishReason")
        finish_reason = _map_finish_reason(gemini_finish_reason)

        if tool_calls and gemini_finish_reason == "STOP":
            finish_reason = "tool_calls"

        choices.append(
            {
                "index": candidate.get("index", 0),
                "delta": delta,
                "finish_reason": finish_reason,
            }
        )

    usage = _convert_usage_metadata(gemini_response.get("usageMetadata"))

    response_data = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
    }

    if usage:
        has_finish_reason = any(choice.get("finish_reason") for choice in choices)
        if has_finish_reason:
            response_data["usage"] = usage

    return f"data: {json.dumps(response_data)}\n\n"
