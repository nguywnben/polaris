"""Meta Model API's stateless Responses transport.

Contract: https://dev.meta.ai/docs/protocols/responses and /docs/models.
Only coding-capable Muse Spark models are exposed. Discovery authenticates without
generating content; Contributor tiers are never selected or substituted here.
"""

from __future__ import annotations

import copy
import json
import math
import re

import httpx
from core.converter.thought_signature import SKIP_THOUGHT_SIGNATURE_VALIDATOR
from core.httpx_client import http_client
from core.meta_native_boundary import validate_native_request
from core.meta_responses_models import validate_native_payload
from core.provider_registry import MAX_DECLARED_MODELS, MAX_MODEL_ID_LENGTH

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
MAX_CATALOG_BYTES = 1024 * 1024
USER_AGENT = "Polaris/0.1 (Meta Model API integration)"
_MODEL_ID = re.compile(r"^muse-spark-1\.(?:1|[23](?:-contributor)?)$")
_CATALOG_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class MetaModelAPIError(ValueError):
    """Sanitized management/request error without upstream secrets."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_credential(data: dict) -> dict:
    if not isinstance(data, dict):
        raise MetaModelAPIError("Meta credential must be an object.")
    key = data.get("api_key")
    if (
        not isinstance(key, str)
        or not key.strip()
        or len(key) > 8192
        or any(not 33 <= ord(character) <= 126 for character in key.strip())
    ):
        raise MetaModelAPIError("A valid Meta Model API key is required.")
    base = data.get("base_url") or DEFAULT_BASE_URL
    if not isinstance(base, str) or base.strip().rstrip("/") != DEFAULT_BASE_URL:
        raise MetaModelAPIError("Meta API base URL must be https://api.meta.ai/v1.")
    models = data.get("model_ids", [])
    if not isinstance(models, list) or len(models) > MAX_DECLARED_MODELS:
        raise MetaModelAPIError("Invalid Meta model list.")
    result = {
        **data,
        "provider": "meta",
        "credential_type": "api_key",
        "api_key": key.strip(),
        "base_url": DEFAULT_BASE_URL,
        "model_ids": [],
    }
    for model in models:
        protocol_for_model(result, model)
        if model not in result["model_ids"]:
            result["model_ids"].append(model)
    return result


def protocol_for_model(data: dict, model: str) -> str:
    del data
    if (
        not isinstance(model, str)
        or len(model) > MAX_MODEL_ID_LENGTH
        or not _MODEL_ID.fullmatch(model)
    ):
        raise MetaModelAPIError("Meta model is not a supported Muse Spark coding model.")
    return "responses"


async def discover_models(data: dict) -> list[str]:
    normalized = normalize_credential(data)
    url = DEFAULT_BASE_URL + "/models"
    try:
        async with http_client.get_client(
            timeout=20.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream(
                "GET",
                url,
                headers={
                    "Authorization": "Bearer " + normalized["api_key"],
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            ) as response:
                if response.status_code != 200:
                    raise MetaModelAPIError(
                        "Meta model discovery failed.",
                        response.status_code if response.status_code >= 400 else 502,
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    body.extend(chunk)
                    if len(body) > MAX_CATALOG_BYTES:
                        raise MetaModelAPIError("Meta model catalog exceeds the size limit.", 502)
        payload = json.loads(body)
    except httpx.HTTPError:
        raise MetaModelAPIError("Meta model discovery could not reach the server.", 502) from None
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        if isinstance(exc, MetaModelAPIError):
            raise
        raise MetaModelAPIError("Meta returned an invalid model catalog.", 502) from None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) > MAX_DECLARED_MODELS:
        raise MetaModelAPIError("Meta returned an invalid model catalog.", 502)
    models = []
    for item in items:
        identifier = item.get("id") if isinstance(item, dict) else None
        if not isinstance(identifier, str) or not _CATALOG_ID.fullmatch(identifier):
            raise MetaModelAPIError("Meta returned an invalid model identifier.", 502)
        if _MODEL_ID.fullmatch(identifier) and identifier not in models:
            models.append(identifier)
    if not models:
        raise MetaModelAPIError("Meta returned no supported Muse Spark models.", 502)
    return models


def _object(value, description):
    if not isinstance(value, dict):
        raise MetaModelAPIError(f"Meta {description} must be an object.")
    return value


def _numeric(value, minimum, maximum, *, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, int if integer else (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise MetaModelAPIError("Meta generation option is outside its supported range.")
    return value


def _generation_options(source):
    config = _object(source.get("generationConfig") or {}, "generation configuration")
    allowed = {
        "maxOutputTokens",
        "temperature",
        "topP",
        "responseMimeType",
        "responseSchema",
        "candidateCount",
    }
    if any(value is not None and key not in allowed for key, value in config.items()):
        raise MetaModelAPIError("Requested generation option is unsupported by Meta.")
    if type(config.get("candidateCount", 1)) is not int or config.get("candidateCount", 1) != 1:
        raise MetaModelAPIError("Meta supports exactly one response candidate.")
    result = {}
    for field, target, low, high, integer in (
        ("maxOutputTokens", "max_output_tokens", 16, 1048576, True),
        ("temperature", "temperature", 0, 2, False),
        ("topP", "top_p", 0, 1, False),
    ):
        if config.get(field) is not None:
            result[target] = _numeric(config[field], low, high, integer=integer)
    mime = config.get("responseMimeType")
    if mime not in {None, "text/plain", "application/json"}:
        raise MetaModelAPIError("Meta supports text or JSON output.")
    schema = config.get("responseSchema")
    if schema is not None and mime != "application/json":
        raise MetaModelAPIError("Meta response schema requires JSON output.")
    if mime == "application/json":
        result["text"] = {"format": {"type": "json_object"}}
        if schema is not None:
            result["text"]["format"] = {
                "type": "json_schema",
                "name": "response",
                "schema": _object(schema, "response schema"),
            }
    return result


def _tool_options(source):
    tools = []
    names = set()
    for group in source.get("tools") or []:
        if set(_object(group, "tool group")) - {"functionDeclarations"}:
            raise MetaModelAPIError("Only function tools are supported by this Meta integration.")
        for declaration in group.get("functionDeclarations") or []:
            declaration = _object(declaration, "function declaration")
            name = declaration.get("name")
            if not isinstance(name, str) or not _NAME.fullmatch(name) or name in names:
                raise MetaModelAPIError("Invalid or duplicate Meta function name.")
            names.add(name)
            tool = {
                "type": "function",
                "name": name,
                "parameters": declaration.get("parametersJsonSchema")
                or declaration.get("parameters")
                or {"type": "object", "properties": {}},
            }
            _object(tool["parameters"], "function parameters")
            if declaration.get("description") is not None:
                tool["description"] = declaration["description"]
            tools.append(tool)
    function = _object(
        (_object(source.get("toolConfig") or {}, "tool configuration")).get("functionCallingConfig")
        or {},
        "function configuration",
    )
    mode = function.get("mode", "AUTO")
    allowed = function.get("allowedFunctionNames") or []
    if (
        set(function) - {"mode", "allowedFunctionNames"}
        or not isinstance(mode, str)
        or mode.upper() not in {"AUTO", "ANY", "NONE"}
        or not isinstance(allowed, list)
        or len(allowed) > 1
        or any(name not in names for name in allowed)
        or (allowed and mode.upper() != "ANY")
    ):
        raise MetaModelAPIError("Requested tool selection is unsupported by Meta.")
    if not tools:
        if mode.upper() == "ANY" or allowed:
            raise MetaModelAPIError("Requested Meta function is not declared.")
        return {}
    choice = {"AUTO": "auto", "ANY": "required", "NONE": "none"}[mode.upper()]
    if allowed and mode.upper() != "NONE":
        choice = {"type": "function", "name": allowed[0]}
    return {"tools": tools, "tool_choice": choice}


def _canonical_input(source):
    """Keep mixed message/tool order and pair name-only Gemini calls safely."""
    output = []
    pending = {}
    used = set()
    counter = 0
    for content in source.get("contents") or []:
        content = _object(content, "content")
        if content.get("role") not in {"user", "model"}:
            raise MetaModelAPIError("Unsupported Meta message role.")
        role = "assistant" if content["role"] == "model" else "user"
        for part in content.get("parts") or []:
            part = _object(part, "content part")
            # Chat tool history receives this Gemini-only bypass marker in the
            # shared converter. It is not signed reasoning and must not reach Meta.
            if (
                part.get("thoughtSignature") == SKIP_THOUGHT_SIGNATURE_VALIDATOR
                and ("functionCall" in part or "function_call" in part)
                and not part.get("thought")
            ):
                part = {key: value for key, value in part.items() if key != "thoughtSignature"}
            if part.get("thought") or "thoughtSignature" in part:
                raise MetaModelAPIError("Signed reasoning requires native Meta Responses replay.")
            kinds = set(part) - {"thought"}
            if kinds == {"text"} and isinstance(part["text"], str):
                output.append(
                    {
                        "type": "message",
                        "role": role,
                        "content": [
                            {
                                "type": "output_text" if role == "assistant" else "input_text",
                                "text": part["text"],
                            }
                        ],
                    }
                )
                continue
            if kinds in ({"inlineData"}, {"inline_data"}) and role == "user":
                inline = _object(part.get("inlineData") or part.get("inline_data"), "image")
                mime = inline.get("mimeType") or inline.get("mime_type")
                if mime not in {
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                    "image/gif",
                } or not isinstance(inline.get("data"), str):
                    raise MetaModelAPIError("Unsupported Meta inline image.")
                output.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": f"data:{mime};base64,{inline['data']}",
                            }
                        ],
                    }
                )
                continue
            call = part.get("functionCall") or part.get("function_call")
            if kinds in ({"functionCall"}, {"function_call"}) and role == "assistant":
                call = _object(call, "function call")
                name = call.get("name")
                if not isinstance(name, str) or not _NAME.fullmatch(name):
                    raise MetaModelAPIError("Invalid Meta function name.")
                counter += 1
                identifier = call.get("id") or f"polaris_meta_call_{counter}"
                if (
                    not isinstance(identifier, str)
                    or not identifier.isprintable()
                    or len(identifier) > 64
                    or identifier in used
                ):
                    raise MetaModelAPIError("Invalid or duplicate Meta function call identifier.")
                used.add(identifier)
                pending[identifier] = name
                # Meta requires assistant preambles immediately before calls to
                # be labelled commentary, not interpreted as a final answer.
                for previous in reversed(output):
                    if previous.get("type") != "message" or previous.get("role") != "assistant":
                        break
                    previous["phase"] = "commentary"
                output.append(
                    {
                        "type": "function_call",
                        "call_id": identifier,
                        "name": name,
                        "arguments": json.dumps(
                            _object(call.get("args") or {}, "function arguments"),
                            separators=(",", ":"),
                        ),
                    }
                )
                continue
            result = part.get("functionResponse") or part.get("function_response")
            if kinds in ({"functionResponse"}, {"function_response"}) and role == "user":
                result = _object(result, "function result")
                identifier = result.get("id")
                matches = [key for key, name in pending.items() if name == result.get("name")]
                if not identifier and len(matches) == 1:
                    identifier = matches[0]
                if not identifier or identifier not in matches:
                    raise MetaModelAPIError(
                        "Tool result requires an unambiguous matching call identifier."
                    )
                del pending[identifier]
                output.append(
                    {
                        "type": "function_call_output",
                        "call_id": identifier,
                        "output": json.dumps(result.get("response") or {}, separators=(",", ":")),
                    }
                )
                continue
            raise MetaModelAPIError("Requested content part is unsupported by Meta.")
    return output


async def anthropic_request_to_meta_canonical(payload: dict) -> dict:
    """Use the existing Messages converter without its Gemini-only defaults.

    Explicit caller options are retained so unsupported sampling/stop settings fail
    closed; only defaults demonstrably absent from the original request are removed.
    """
    from core.converter.anthropic_to_gemini import anthropic_to_gemini_request
    from core.converter.thought_signature import (
        SKIP_THOUGHT_SIGNATURE_VALIDATOR,
        THOUGHT_SIGNATURE_SEPARATOR,
    )

    source = copy.deepcopy(_object(payload, "Messages request"))
    if source.get("thinking") is not None or "effort" in (source.get("output_config") or {}):
        raise MetaModelAPIError("Meta reasoning options require the native Responses endpoint.")
    for message in source.get("messages") or []:
        content = message.get("content")
        for part in content if isinstance(content, list) else []:
            if part.get("type") in {"thinking", "redacted_thinking"} or any(
                THOUGHT_SIGNATURE_SEPARATOR in str(part.get(field) or "")
                for field in ("id", "tool_use_id")
            ):
                raise MetaModelAPIError("Signed reasoning requires native Meta Responses replay.")
    result = await anthropic_to_gemini_request(source)
    config = result.get("generationConfig") or {}
    for original, generated in (
        ("stop_sequences", "stopSequences"),
        ("temperature", "temperature"),
        ("top_p", "topP"),
    ):
        if original not in payload:
            config.pop(generated, None)
    # The legacy converter synthesizes this placeholder for every tool call. It
    # is not a real reasoning signature and must never be sent to Meta.
    for content in result.get("contents") or []:
        for part in content.get("parts") or []:
            if (
                "functionCall" in part
                and part.get("thoughtSignature") == SKIP_THOUGHT_SIGNATURE_VALIDATOR
            ):
                part.pop("thoughtSignature")
    # Reject unsupported explicit options before entering routing/retry accounting.
    _generation_options(result)
    return result


def prepare_request(
    data: dict, gemini_request: dict, model: str, streaming: bool, *, native_provider: str = "meta"
) -> tuple[str, dict, dict]:
    try:
        normalized = normalize_credential(data)
    except MetaModelAPIError as error:
        # Stored configuration failures are not invalid inference requests.
        # Keep management/import validation's HTTP 400 semantics unchanged.
        raise ValueError(str(error)) from error
    protocol_for_model(normalized, model)
    validate_native_request(gemini_request, native_provider)
    source = copy.deepcopy(_object(gemini_request, "request"))
    if source.get("_polaris_meta_responses") is not None:
        # Recheck at the transport boundary, even when ingress already validated.
        native = _object(source["_polaris_meta_responses"], "Responses replay")
        try:
            body = validate_native_payload({**native, "model": model})
        except (ValueError, TypeError, RecursionError):
            raise MetaModelAPIError("Unsupported native Meta Responses option.") from None
        if (body.get("reasoning") or {}).get("effort") == "max" and model != "muse-spark-1.3":
            raise MetaModelAPIError("Maximum reasoning requires the standard Muse Spark 1.3 model.")
    else:
        body = {
            "input": _canonical_input(source),
            **_generation_options(source),
            **_tool_options(source),
        }
        system = _object(source.get("systemInstruction") or {}, "system instruction")
        parts = system.get("parts") or []
        if any(
            not isinstance(part, dict) or set(part) != {"text"} or not isinstance(part["text"], str)
            for part in parts
        ):
            raise MetaModelAPIError("Meta system instructions support text only.")
        if parts:
            body["instructions"] = "\n".join(part["text"] for part in parts)
    body.update({"model": model, "stream": bool(streaming), "store": False})
    headers = {
        "Authorization": "Bearer " + normalized["api_key"],
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if streaming:
        headers["Accept"] = "text/event-stream"
    return DEFAULT_BASE_URL + "/responses", headers, body
