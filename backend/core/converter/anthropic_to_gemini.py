from __future__ import annotations

import json
import os
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from core.converter.thought_signature import (
    SKIP_THOUGHT_SIGNATURE_VALIDATOR,
    decode_tool_id_and_signature,
    is_internal_placeholder_text,
    is_skip_thought_signature_placeholder,
)
from core.converter.utils import merge_system_messages
from core.protocol_contract import validate_gemini_response_part
from fastapi import Response
from log import log

DEFAULT_TEMPERATURE = 0.4
_DEBUG_TRUE = {"1", "true", "yes", "on"}

# ============================================================================

# ============================================================================


MIN_SIGNATURE_LENGTH = 10


def has_valid_thought_signature(block: Dict[str, Any]) -> bool:
    if not isinstance(block, dict):
        return True

    block_type = block.get("type")
    if block_type not in ("thinking", "redacted_thinking"):
        return True

    thinking = block.get("thinking", "")
    thoughtsignature = block.get("signature") or block.get("thoughtSignature")

    if not thinking and thoughtsignature is not None:
        return True

    if (
        thoughtsignature
        and isinstance(thoughtsignature, str)
        and len(thoughtsignature) >= MIN_SIGNATURE_LENGTH
    ):
        return True

    return False


def sanitize_thinking_block(block: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(block, dict):
        return block

    block_type = block.get("type")
    if block_type not in ("thinking", "redacted_thinking"):
        return block

    sanitized: Dict[str, Any] = {"type": block_type, "thinking": block.get("thinking", "")}

    thoughtsignature = block.get("signature") or block.get("thoughtSignature")
    if thoughtsignature:
        sanitized["signature"] = thoughtsignature

    return sanitized


def remove_trailing_unsigned_thinking(blocks: List[Dict[str, Any]]) -> None:
    if not blocks:
        return

    end_index = len(blocks)
    for i in range(len(blocks) - 1, -1, -1):
        block = blocks[i]
        if not isinstance(block, dict):
            break

        block_type = block.get("type")
        if block_type in ("thinking", "redacted_thinking"):
            if not has_valid_thought_signature(block):
                end_index = i
            else:
                break
        else:
            break

    if end_index < len(blocks):
        removed = len(blocks) - end_index
        del blocks[end_index:]
        log.debug(f"Removed {removed} trailing unsigned thinking block(s)")


def filter_invalid_thinking_blocks(messages: List[Dict[str, Any]]) -> None:
    total_filtered = 0

    for msg in messages:
        role = msg.get("role", "")
        if role not in ("assistant", "model"):
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            continue

        original_len = len(content)
        new_blocks: List[Dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                new_blocks.append(block)
                continue

            block_type = block.get("type")
            if block_type not in ("thinking", "redacted_thinking"):
                new_blocks.append(block)
                continue

            if has_valid_thought_signature(block):
                new_blocks.append(sanitize_thinking_block(block))
            else:
                thinking_text = block.get("thinking", "")
                if thinking_text and str(thinking_text).strip():
                    log.info(
                        f"[Claude-Handler] Converting thinking block with invalid thoughtSignature to text. "
                        f"Content length: {len(thinking_text)} chars"
                    )
                    new_blocks.append({"type": "text", "text": thinking_text})
                else:
                    log.debug(
                        "[Claude-Handler] Dropping empty thinking block with invalid thoughtSignature"
                    )

        msg["content"] = new_blocks
        filtered_count = original_len - len(new_blocks)
        total_filtered += filtered_count

        if not new_blocks:
            msg["content"] = [{"type": "text", "text": ""}]

    if total_filtered > 0:
        log.debug(f"Filtered {total_filtered} invalid thinking block(s) from history")


# ============================================================================

# ============================================================================


def _anthropic_debug_enabled() -> bool:
    return str(os.getenv("ANTHROPIC_DEBUG", "true")).strip().lower() in _DEBUG_TRUE


def _cached_content_token_count(usage_metadata: Any) -> int:
    if not isinstance(usage_metadata, dict):
        return 0
    return int(usage_metadata.get("cachedContentTokenCount", 0) or 0)


def _anthropic_usage_from_metadata(usage_metadata: Any) -> Dict[str, int]:
    if not isinstance(usage_metadata, dict):
        return {"input_tokens": 0, "output_tokens": 0}

    prompt_tokens_total = int(usage_metadata.get("promptTokenCount", 0) or 0)
    cached_tokens = _cached_content_token_count(usage_metadata)
    reasoning_tokens = int(usage_metadata.get("thoughtsTokenCount", 0) or 0)
    usage = {
        "input_tokens": max(prompt_tokens_total - cached_tokens, 0),
        "output_tokens": int(usage_metadata.get("candidatesTokenCount", 0) or 0) + reasoning_tokens,
    }

    if cached_tokens > 0:
        usage["cache_read_input_tokens"] = cached_tokens

    return usage


def _is_non_whitespace_text(value: Any) -> bool:
    if value is None:
        return False
    try:
        return bool(str(value).strip())
    except Exception:
        return False


def _remove_nulls_for_tool_input(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in value.items():
            if v is None:
                continue
            cleaned[k] = _remove_nulls_for_tool_input(v)
        return cleaned

    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            if item is None:
                continue
            cleaned_list.append(_remove_nulls_for_tool_input(item))
        return cleaned_list

    return value


# ============================================================================

# ============================================================================


def clean_json_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema

    unsupported_keys = {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "definitions",
        "title",
        "example",
        "examples",
        "readOnly",
        "writeOnly",
        "default",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "oneOf",
        "anyOf",
        "allOf",
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
        "nullable",
    }

    validation_fields = {
        "minLength": "minLength",
        "maxLength": "maxLength",
        "minimum": "minimum",
        "maximum": "maximum",
        "minItems": "minItems",
        "maxItems": "maxItems",
    }
    fields_to_remove = {"additionalProperties"}

    validations: List[str] = []
    for field, label in validation_fields.items():
        if field in schema:
            validations.append(f"{label}: {schema[field]}")

    cleaned: Dict[str, Any] = {}
    for key, value in schema.items():
        if key in unsupported_keys or key in fields_to_remove or key in validation_fields:
            continue

        if key == "type" and isinstance(value, list):
            # type: ["string", "null"] -> type: "string", nullable: true
            has_null = any(
                isinstance(t, str) and t.strip() and t.strip().lower() == "null" for t in value
            )
            non_null_types = [
                t.strip()
                for t in value
                if isinstance(t, str) and t.strip() and t.strip().lower() != "null"
            ]

            cleaned[key] = non_null_types[0] if non_null_types else "string"
            if has_null:
                cleaned["nullable"] = True
            continue

        if key == "description" and validations:
            cleaned[key] = f"{value} ({', '.join(validations)})"
        elif isinstance(value, dict):
            cleaned[key] = clean_json_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_json_schema(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            cleaned[key] = value

    if validations and "description" not in cleaned:
        cleaned["description"] = f"Validation: {', '.join(validations)}"

    if "properties" in cleaned and "type" not in cleaned:
        cleaned["type"] = "object"

    if isinstance(schema.get("properties"), dict) and isinstance(cleaned.get("required"), list):
        nullable_fields = {
            name
            for name, prop in schema["properties"].items()
            if isinstance(prop, dict)
            and isinstance(prop.get("type"), list)
            and any(str(t).lower() == "null" for t in prop["type"])
        }
        if nullable_fields:
            cleaned["required"] = [
                item for item in cleaned["required"] if item not in nullable_fields
            ]
            if not cleaned["required"]:
                cleaned.pop("required", None)

    return cleaned


# ============================================================================

# ============================================================================


def convert_tools(
    anthropic_tools: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    if not anthropic_tools:
        return None

    gemini_tools: List[Dict[str, Any]] = []
    for tool in anthropic_tools:
        name = tool.get("name", "nameless_function")
        description = tool.get("description", "")
        input_schema = tool.get("input_schema", {}) or {}
        parameters = clean_json_schema(input_schema)

        gemini_tools.append(
            {
                "functionDeclarations": [
                    {
                        "name": name,
                        "description": description,
                        "parametersJsonSchema": parameters,
                    }
                ]
            }
        )

    return gemini_tools or None


# ============================================================================

# ============================================================================


def _extract_tool_result_output(content: Any) -> str:
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    if content is None:
        return ""
    return str(content)


def convert_messages_to_contents(
    messages: List[Dict[str, Any]], *, include_thinking: bool = True
) -> List[Dict[str, Any]]:
    contents: List[Dict[str, Any]] = []

    tool_use_info: Dict[str, tuple[str, Optional[str]]] = {}
    for msg in messages:
        raw_content = msg.get("content", "")
        if isinstance(raw_content, list):
            for item in raw_content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    encoded_tool_id = item.get("id")
                    tool_name = item.get("name")
                    if encoded_tool_id and tool_name:
                        original_id, thoughtsignature = decode_tool_id_and_signature(
                            encoded_tool_id
                        )

                        tool_use_info[str(encoded_tool_id)] = (tool_name, thoughtsignature)

    for msg in messages:
        role = msg.get("role", "user")

        if role == "system":
            continue

        gemini_role = "model" if role in ("assistant", "model") else "user"
        raw_content = msg.get("content", "")

        parts: List[Dict[str, Any]] = []
        if isinstance(raw_content, str):
            if _is_non_whitespace_text(raw_content):
                parts = [{"text": str(raw_content)}]
        elif isinstance(raw_content, list):
            for item in raw_content:
                if not isinstance(item, dict):
                    if _is_non_whitespace_text(item):
                        parts.append({"text": str(item)})
                    continue

                item_type = item.get("type")
                if item_type == "thinking":
                    if include_thinking:
                        signature = item.get("signature") or item.get("thoughtSignature")
                        parts.append(
                            {
                                "text": str(item.get("thinking") or ""),
                                "thought": True,
                                "thoughtSignature": signature,
                            }
                        )
                elif item_type == "redacted_thinking":
                    raise ValueError(
                        "Anthropic redacted_thinking blocks cannot be translated safely."
                    )
                elif item_type == "text":
                    text = item.get("text", "")
                    if _is_non_whitespace_text(text):
                        parts.append({"text": str(text)})
                elif item_type == "image":
                    source = item.get("source", {}) or {}
                    if source.get("type") == "base64":
                        parts.append(
                            {
                                "inlineData": {
                                    "mimeType": source.get("media_type", "image/png"),
                                    "data": source.get("data", ""),
                                }
                            }
                        )
                    else:
                        raise ValueError("Only base64 Anthropic image inputs are supported.")
                elif item_type == "tool_use":
                    encoded_id = item.get("id") or ""
                    original_id, _ = decode_tool_id_and_signature(encoded_id)

                    fc_part: Dict[str, Any] = {
                        "functionCall": {
                            "id": original_id,
                            "name": item.get("name"),
                            "args": item.get("input", {}) or {},
                        }
                    }

                    fc_part["thoughtSignature"] = SKIP_THOUGHT_SIGNATURE_VALIDATOR

                    parts.append(fc_part)
                elif item_type == "tool_result":
                    output = _extract_tool_result_output(item.get("content"))
                    encoded_tool_use_id = item.get("tool_use_id") or ""

                    original_tool_use_id, _ = decode_tool_id_and_signature(encoded_tool_use_id)

                    func_name = item.get("name")
                    if not func_name and encoded_tool_use_id:
                        tool_info = tool_use_info.get(str(encoded_tool_use_id))
                        if tool_info:
                            func_name = tool_info[0]
                    if not func_name:
                        func_name = "unknown_function"

                    parts.append(
                        {
                            "functionResponse": {
                                "id": original_tool_use_id,
                                "name": func_name,
                                "response": {"output": output},
                            }
                        }
                    )
                else:
                    raise ValueError(f"Unsupported Anthropic content block type: {item_type}.")
        else:
            if _is_non_whitespace_text(raw_content):
                parts = [{"text": str(raw_content)}]

        if not parts:
            continue

        contents.append({"role": gemini_role, "parts": parts})

    return contents


def reorganize_tool_messages(contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tool_results: Dict[str, Dict[str, Any]] = {}

    for msg in contents:
        for part in msg.get("parts", []) or []:
            if isinstance(part, dict) and "functionResponse" in part:
                tool_id = (part.get("functionResponse") or {}).get("id")
                if tool_id:
                    tool_results[str(tool_id)] = part

    flattened: List[Dict[str, Any]] = []
    for msg in contents:
        role = msg.get("role")
        for part in msg.get("parts", []) or []:
            flattened.append({"role": role, "parts": [part]})

    new_contents: List[Dict[str, Any]] = []
    i = 0
    while i < len(flattened):
        msg = flattened[i]
        part = msg["parts"][0]

        if isinstance(part, dict) and "functionResponse" in part:
            i += 1
            continue

        if isinstance(part, dict) and "functionCall" in part:
            tool_id = (part.get("functionCall") or {}).get("id")
            new_contents.append({"role": "model", "parts": [part]})

            if tool_id is not None and str(tool_id) in tool_results:
                new_contents.append({"role": "user", "parts": [tool_results[str(tool_id)]]})

            i += 1
            continue

        new_contents.append(msg)
        i += 1

    return new_contents


# ============================================================================

# ============================================================================


def convert_tool_choice_to_tool_config(tool_choice: Any) -> Optional[Dict[str, Any]]:
    if not tool_choice:
        return None

    if isinstance(tool_choice, dict):
        choice_type = tool_choice.get("type")

        if choice_type == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        elif choice_type == "any":
            return {"functionCallingConfig": {"mode": "ANY"}}
        elif choice_type == "tool":
            tool_name = tool_choice.get("name")
            if tool_name:
                return {
                    "functionCallingConfig": {
                        "mode": "ANY",
                        "allowedFunctionNames": [tool_name],
                    }
                }

    return None


# ============================================================================

# ============================================================================


def build_generation_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "topP": 1,
        "candidateCount": 1,
        "stopSequences": [
            "<|user|>",
            "<|bot|>",
            "<|context_request|>",
            "<|endoftext|>",
            "<|end_of_turn|>",
        ],
    }

    temperature = payload.get("temperature", None)
    config["temperature"] = DEFAULT_TEMPERATURE if temperature is None else temperature

    top_p = payload.get("top_p", None)
    if top_p is not None:
        config["topP"] = top_p

    top_k = payload.get("top_k", None)
    if top_k is not None:
        config["topK"] = top_k

    max_tokens = payload.get("max_tokens")
    if max_tokens is not None:
        config["maxOutputTokens"] = max_tokens

    thinking = payload.get("thinking")
    is_plan_mode = False
    if thinking and isinstance(thinking, dict):
        thinking_type = thinking.get("type")
        budget_tokens = thinking.get("budget_tokens")

        if thinking_type == "enabled":
            is_plan_mode = True
            thinking_config: Dict[str, Any] = {}

            if budget_tokens is not None:
                thinking_config["thinkingBudget"] = budget_tokens
            else:
                thinking_config["thinkingBudget"] = 48000

            thinking_config["includeThoughts"] = True

            config["thinkingConfig"] = thinking_config
            log.info(
                f"[ANTHROPIC2GEMINI] Extended thinking enabled with budget: {thinking_config['thinkingBudget']}"
            )
        elif thinking_type == "disabled":
            config["thinkingConfig"] = {"includeThoughts": False}
            log.info("[ANTHROPIC2GEMINI] Extended thinking explicitly disabled")

    stop_sequences = payload.get("stop_sequences")
    if isinstance(stop_sequences, list) and stop_sequences:
        config["stopSequences"] = config["stopSequences"] + [str(s) for s in stop_sequences]
    elif is_plan_mode:
        config["stopSequences"] = []
        log.info(
            "[ANTHROPIC2GEMINI] Plan mode: cleared default stop sequences to prevent premature stopping"
        )

    return config


# ============================================================================

# ============================================================================


async def anthropic_to_gemini_request(payload: Dict[str, Any]) -> Dict[str, Any]:

    payload = await merge_system_messages(payload)

    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        messages = []

    filter_invalid_thinking_blocks(messages)

    generation_config = build_generation_config(payload)
    output_format = (payload.get("output_config") or {}).get("format")
    if output_format:
        if output_format.get("type") != "json_schema" or not isinstance(
            output_format.get("schema"), dict
        ):
            raise ValueError("Unsupported Anthropic structured output format.")
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = clean_json_schema(output_format["schema"])

    contents = convert_messages_to_contents(messages, include_thinking=True)

    for content in contents:
        role = content.get("role", "")
        if role == "model":
            parts = content.get("parts", [])
            if isinstance(parts, list):
                remove_trailing_unsigned_thinking(parts)

    contents = reorganize_tool_messages(contents)

    tools = convert_tools(payload.get("tools"))

    tool_config = convert_tool_choice_to_tool_config(payload.get("tool_choice"))

    gemini_request = {
        "contents": contents,
        "generationConfig": generation_config,
    }

    if "systemInstruction" in payload:
        gemini_request["systemInstruction"] = payload["systemInstruction"]

    if tools:
        gemini_request["tools"] = tools

    if tool_config:
        gemini_request["toolConfig"] = tool_config

    if "size" in payload and payload["size"]:
        gemini_request["size"] = payload["size"]

    return gemini_request


def gemini_to_anthropic_response(
    gemini_response: Dict[str, Any], model: str, status_code: int = 200
) -> Dict[str, Any]:

    if not (200 <= status_code < 300):
        return gemini_response

    if "response" in gemini_response:
        response_data = gemini_response["response"]
    else:
        response_data = gemini_response

    candidate = response_data.get("candidates", [{}])[0] or {}
    parts = candidate.get("content", {}).get("parts", []) or []

    usage_metadata = {}
    if "usageMetadata" in response_data:
        usage_metadata = response_data["usageMetadata"]
    elif "usageMetadata" in candidate:
        usage_metadata = candidate["usageMetadata"]

    content = []
    has_tool_use = False

    for part in parts:
        validate_gemini_response_part(part)

        if part.get("thought") is True:
            if is_skip_thought_signature_placeholder(part):
                continue
            thinking_text = part.get("text", "")
            if thinking_text is None:
                thinking_text = ""

            block: Dict[str, Any] = {"type": "thinking", "thinking": str(thinking_text)}

            thoughtsignature = part.get("thoughtSignature")
            if thoughtsignature:
                block["signature"] = thoughtsignature

            content.append(block)
            continue

        if "text" in part:
            text = part.get("text", "")
            if is_skip_thought_signature_placeholder(part) or is_internal_placeholder_text(text):
                continue
            content.append({"type": "text", "text": text})
            continue

        if "functionCall" in part:
            has_tool_use = True
            fc = part.get("functionCall", {}) or {}
            original_id = fc.get("id") or f"toolu_{uuid.uuid4().hex}"
            content.append(
                {
                    "type": "tool_use",
                    "id": original_id,
                    "name": fc.get("name") or "",
                    "input": _remove_nulls_for_tool_input(fc.get("args", {}) or {}),
                }
            )
            continue

        if "inlineData" in part:
            inline = part.get("inlineData", {}) or {}
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": inline.get("mimeType", "image/png"),
                        "data": inline.get("data", ""),
                    },
                }
            )
            continue

    finish_reason = candidate.get("finishReason")

    if has_tool_use and finish_reason == "STOP":
        stop_reason = "tool_use"
    elif finish_reason == "MAX_TOKENS":
        stop_reason = "max_tokens"
    elif finish_reason in {"SAFETY", "RECITATION"}:
        stop_reason = "refusal"
    else:
        stop_reason = "end_turn"

    usage = _anthropic_usage_from_metadata(usage_metadata)

    message_id = f"msg_{uuid.uuid4().hex}"

    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage,
    }


async def gemini_stream_to_anthropic_stream(
    gemini_stream: AsyncIterator[bytes], model: str, status_code: int = 200
) -> AsyncIterator[bytes]:

    if not (200 <= status_code < 300):
        async for chunk in gemini_stream:
            yield chunk
        return

    message_id = f"msg_{uuid.uuid4().hex}"
    message_start_sent = False
    current_block_type: Optional[str] = None
    current_block_index = -1
    current_thinking_signature: Optional[str] = None
    has_tool_use = False
    input_tokens = 0
    output_tokens = 0
    cached_input_tokens = 0
    finish_reason: Optional[str] = None

    def _sse_event(event: str, data: Dict[str, Any]) -> bytes:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")

    def _close_block() -> Optional[bytes]:
        nonlocal current_block_type
        if current_block_type is None:
            return None
        event = _sse_event(
            "content_block_stop",
            {"type": "content_block_stop", "index": current_block_index},
        )
        current_block_type = None
        return event

    def _usage_payload() -> Dict[str, int]:
        usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        if cached_input_tokens > 0:
            usage["cache_read_input_tokens"] = cached_input_tokens
        return usage

    try:
        async for chunk in gemini_stream:
            if isinstance(chunk, Response):
                log.warning(
                    f"[GEMINI_TO_ANTHROPIC] Response object received, status code: {chunk.status_code}, forwarding error directly"
                )

                error_content = (
                    chunk.body if isinstance(chunk.body, bytes) else chunk.body.encode("utf-8")
                )
                yield error_content
                return

            log.debug(f"[GEMINI_TO_ANTHROPIC] Raw chunk: {chunk[:200] if chunk else b''}")

            if chunk and chunk.lstrip().startswith(b":"):
                yield chunk.strip() + b"\n\n"
                continue
            if not chunk or not chunk.startswith(b"data: "):
                log.debug("[GEMINI_TO_ANTHROPIC] Skipping chunk (not SSE format or empty)")
                continue

            raw = chunk[6:].strip()
            if raw == b"[DONE]":
                log.debug("[GEMINI_TO_ANTHROPIC] Received [DONE] marker")
                break

            log.debug(f"[GEMINI_TO_ANTHROPIC] Parsing JSON: {raw[:200]}")

            try:
                data = json.loads(raw.decode("utf-8", errors="ignore"))
                log.debug(
                    f"[GEMINI_TO_ANTHROPIC] Parsed data: {json.dumps(data, ensure_ascii=False)[:300]}"
                )
            except Exception as e:
                log.warning(f"[GEMINI_TO_ANTHROPIC] JSON parse error: {e}")
                continue

            if data.get("type") == "error" and isinstance(data.get("error"), dict):
                yield _sse_event("error", data)
                return

            if "response" in data:
                response = data["response"]
            else:
                response = data

            candidate = (response.get("candidates", []) or [{}])[0] or {}
            parts = (candidate.get("content", {}) or {}).get("parts", []) or []

            if "usageMetadata" in response:
                usage = response["usageMetadata"]
                if isinstance(usage, dict):
                    if "promptTokenCount" in usage:
                        prompt_tokens_total = int(usage.get("promptTokenCount", 0) or 0)
                        input_tokens = max(prompt_tokens_total - cached_input_tokens, 0)
                    if "candidatesTokenCount" in usage:
                        output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
                    if "cachedContentTokenCount" in usage:
                        cached_input_tokens = int(usage.get("cachedContentTokenCount", 0) or 0)
                        input_tokens = max(
                            int(usage.get("promptTokenCount", 0) or 0) - cached_input_tokens,
                            0,
                        )

            if not message_start_sent:
                message_start_sent = True
                yield _sse_event(
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "model": model,
                            "content": [],
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": _usage_payload(),
                        },
                    },
                )

            for part in parts:
                if not isinstance(part, dict):
                    continue

                if part.get("thought") is True:
                    if is_skip_thought_signature_placeholder(part):
                        continue
                    thinking_text = part.get("text", "")
                    thoughtsignature = part.get("thoughtSignature")

                    if current_block_type != "thinking":
                        close_evt = _close_block()
                        if close_evt:
                            yield close_evt

                        current_block_index += 1
                        current_block_type = "thinking"
                        current_thinking_signature = thoughtsignature

                        block: Dict[str, Any] = {"type": "thinking", "thinking": ""}
                        if thoughtsignature:
                            block["thoughtSignature"] = thoughtsignature
                        yield _sse_event(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": current_block_index,
                                "content_block": block,
                            },
                        )
                    elif thoughtsignature and thoughtsignature != current_thinking_signature:
                        close_evt = _close_block()
                        if close_evt:
                            yield close_evt

                        current_block_index += 1
                        current_block_type = "thinking"
                        current_thinking_signature = thoughtsignature

                        block_new: Dict[str, Any] = {"type": "thinking", "thinking": ""}
                        if thoughtsignature:
                            block_new["thoughtSignature"] = thoughtsignature

                        yield _sse_event(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": current_block_index,
                                "content_block": block_new,
                            },
                        )

                    if thinking_text:
                        yield _sse_event(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": current_block_index,
                                "delta": {"type": "thinking_delta", "thinking": thinking_text},
                            },
                        )
                    continue

                if "text" in part:
                    if is_skip_thought_signature_placeholder(part) or is_internal_placeholder_text(
                        part.get("text")
                    ):
                        continue
                    text = part.get("text", "")
                    if isinstance(text, str) and not text.strip():
                        continue

                    if current_block_type != "text":
                        close_evt = _close_block()
                        if close_evt:
                            yield close_evt

                        current_block_index += 1
                        current_block_type = "text"

                        yield _sse_event(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": current_block_index,
                                "content_block": {"type": "text", "text": ""},
                            },
                        )

                    if text:
                        yield _sse_event(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": current_block_index,
                                "delta": {"type": "text_delta", "text": text},
                            },
                        )
                    continue

                if "functionCall" in part:
                    close_evt = _close_block()
                    if close_evt:
                        yield close_evt

                    has_tool_use = True
                    fc = part.get("functionCall", {}) or {}
                    original_id = fc.get("id") or f"toolu_{uuid.uuid4().hex}"
                    tool_id = original_id
                    tool_name = fc.get("name") or ""
                    tool_args = _remove_nulls_for_tool_input(fc.get("args", {}) or {})

                    if _anthropic_debug_enabled():
                        log.info(
                            f"[ANTHROPIC][tool_use] Processing tool call: name={tool_name}, "
                            f"id={tool_id}"
                        )

                    current_block_index += 1

                    yield _sse_event(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": current_block_index,
                            "content_block": {
                                "type": "tool_use",
                                "id": tool_id,
                                "name": tool_name,
                                "input": {},
                            },
                        },
                    )

                    input_json = json.dumps(tool_args, ensure_ascii=False, separators=(",", ":"))
                    yield _sse_event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": current_block_index,
                            "delta": {"type": "input_json_delta", "partial_json": input_json},
                        },
                    )

                    yield _sse_event(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": current_block_index},
                    )

                    if _anthropic_debug_enabled():
                        log.info(
                            f"[ANTHROPIC] [tool_use] tool call block closed: index = {current_block_index}"
                        )

                    continue

            if candidate.get("finishReason"):
                finish_reason = candidate.get("finishReason")
                break

        close_evt = _close_block()
        if close_evt:
            yield close_evt

        if has_tool_use and finish_reason == "STOP":
            stop_reason = "tool_use"
        elif finish_reason == "MAX_TOKENS":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"

        if _anthropic_debug_enabled():
            log.info(
                f"[ANTHROPIC][stream_end] Stream ended: stop_reason={stop_reason}, "
                f"has_tool_use={has_tool_use}, finish_reason={finish_reason}, "
                f"input_tokens={input_tokens}, output_tokens={output_tokens}"
            )

        yield _sse_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": _usage_payload(),
            },
        )

        yield _sse_event("message_stop", {"type": "message_stop"})

    except Exception as e:
        log.error(f"[ANTHROPIC] Streaming conversion failed: {e}")

        if not message_start_sent:
            yield _sse_event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": message_id,
                        "type": "message",
                        "role": "assistant",
                        "model": model,
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": _usage_payload(),
                    },
                },
            )
        yield _sse_event(
            "error",
            {"type": "error", "error": {"type": "api_error", "message": str(e)}},
        )
    finally:
        from core.router.stream_passthrough import close_async_iterator

        await close_async_iterator(gemini_stream)
