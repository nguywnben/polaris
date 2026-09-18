"""Bounded stateless coding subset of Meta's Responses request contract."""

from __future__ import annotations

import base64
import json
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _keys(value: Any, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"Unsupported {label} fields.")
    return value


def _text(value: Any, label: str, *, nonempty: bool = False, maximum: int | None = None):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError(f"{label} must be a string.")
    if maximum and len(value) > maximum:
        raise ValueError(f"{label} is too long.")


def _content(value: Any, *, summary: bool = False):
    if isinstance(value, str) and not summary:
        return
    if not isinstance(value, list):
        raise ValueError("Response content must be text or a list of text parts.")
    for part in value:
        if isinstance(part, dict) and part.get("type") == "input_image" and not summary:
            _keys(part, {"type", "image_url", "detail"}, "image content")
            url = part.get("image_url")
            _text(url, "Image URL", nonempty=True)
            if url.startswith("data:image/"):
                try:
                    header, encoded = url.split(",", 1)
                    if header not in {
                        "data:image/png;base64",
                        "data:image/jpeg;base64",
                        "data:image/webp;base64",
                        "data:image/gif;base64",
                    }:
                        raise ValueError()
                    base64.b64decode(encoded, validate=True)
                except ValueError:
                    raise ValueError(
                        "Image data must use a supported base64 image format."
                    ) from None
            else:
                parsed = urlsplit(url)
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise ValueError("Image URLs must use HTTPS without embedded credentials.")
            if part.get("detail") not in (None, "auto", "low", "high"):
                raise ValueError("Unsupported image detail.")
            continue
        _keys(part, {"type", "text", "annotations"}, "text content")
        if part.get("type") not in (
            ("summary_text",) if summary else ("input_text", "output_text", "text")
        ):
            raise ValueError("Unsupported Responses content type.")
        _text(part.get("text"), "Content text")
        if part.get("annotations") not in (None, []):
            raise ValueError("Annotated content replay is not supported.")


class MetaResponsesRequest(BaseModel):
    """Native replay stays separate from the legacy chat-only Responses schema."""

    model_config = ConfigDict(extra="forbid", strict=True)

    model: str = Field(min_length=1, max_length=512)
    input: str | list[dict[str, Any]]
    instructions: str | None = None
    stream: bool = False
    store: Literal[False] = False
    temperature: float | None = Field(None, ge=0, le=2)
    top_p: float | None = Field(None, ge=0, le=1)
    max_output_tokens: int | None = Field(None, ge=16)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool = True
    reasoning: dict[str, Any] | None = None
    include: list[Literal["reasoning.encrypted_content"]] | None = None
    text: dict[str, Any] | None = None
    metadata: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_native_contract(self):
        if (
            len(json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False).encode())
            > 8 * 1024 * 1024
        ):
            raise ValueError("Responses input exceeds the supported size limit.")
        if self.reasoning is not None:
            _keys(self.reasoning, {"effort", "summary"}, "reasoning")
            if self.reasoning.get("effort") not in (
                None,
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ):
                raise ValueError("Unsupported reasoning effort.")
            if (
                self.reasoning.get("effort") == "max"
                and self.model.startswith("muse-")
                and self.model != "muse-spark-1.3"
            ):
                raise ValueError(
                    "Maximum reasoning effort requires the Standard Muse Spark 1.3 model."
                )
            if self.reasoning.get("summary") not in (None, "auto", "concise", "detailed"):
                raise ValueError("Unsupported reasoning summary.")
        if self.text is not None:
            _keys(self.text, {"format"}, "text")
            fmt = _keys(
                self.text.get("format"),
                {"type", "name", "description", "schema", "strict"},
                "text format",
            )
            if fmt.get("type") not in ("text", "json_object", "json_schema"):
                raise ValueError("Unsupported text format.")
            if fmt["type"] == "json_schema":
                _text(fmt.get("name"), "Schema name", nonempty=True)
                if not isinstance(fmt.get("schema"), dict):
                    raise ValueError("A JSON schema object is required.")
            elif set(fmt) != {"type"}:
                raise ValueError("Unsupported text format fields.")
            if "strict" in fmt and not isinstance(fmt["strict"], bool):
                raise ValueError("Schema strict must be a boolean.")
        for tool in self.tools or []:
            _keys(tool, {"type", "name", "description", "parameters", "strict"}, "function tool")
            if tool.get("type") != "function":
                raise ValueError("Only function tools are supported.")
            _text(tool.get("name"), "Function name", nonempty=True)
            if "description" in tool:
                _text(tool["description"], "Function description")
            if "parameters" in tool and not isinstance(tool["parameters"], dict):
                raise ValueError("Function parameters must be an object.")
            if "strict" in tool and not isinstance(tool["strict"], bool):
                raise ValueError("Function strict must be a boolean.")
        if isinstance(self.tool_choice, dict):
            _keys(self.tool_choice, {"type", "name"}, "tool choice")
            if self.tool_choice.get("type") != "function":
                raise ValueError("Only function tool choices are supported.")
            _text(self.tool_choice.get("name"), "Tool choice name", nonempty=True)
        elif self.tool_choice not in {None, "none", "auto", "required"}:
            raise ValueError("Unsupported tool choice.")
        if isinstance(self.input, str):
            _text(self.input, "Input", nonempty=True)
        else:
            self._validate_history()
        return self

    def _validate_history(self):
        if not self.input:
            raise ValueError("At least one input item is required.")
        calls = set()
        resolved = set()
        for index, item in enumerate(self.input):
            kind = item.get("type", "message")
            if kind == "message":
                _keys(item, {"type", "id", "role", "content", "phase", "status"}, "message")
                if item.get("role") not in ("system", "developer", "user", "assistant"):
                    raise ValueError("Unsupported message role.")
                if "phase" in item and (
                    item["role"] != "assistant"
                    or item["phase"] not in ("commentary", "final_answer")
                ):
                    raise ValueError("Phase is supported only for assistant messages.")
                _content(item.get("content"))
            elif kind == "reasoning":
                _keys(
                    item, {"type", "id", "summary", "encrypted_content", "status"}, "reasoning item"
                )
                _content(item.get("summary"), summary=True)
                if "encrypted_content" in item:
                    _text(item["encrypted_content"], "Encrypted reasoning", nonempty=True)
                following = self.input[index + 1] if index + 1 < len(self.input) else {}
                if (
                    following.get("type") != "function_call"
                    and following.get("role") != "assistant"
                ):
                    raise ValueError(
                        "Reasoning must precede an assistant message or function call."
                    )
            elif kind in ("function_call", "function_call_output"):
                allowed = {"type", "id", "call_id", "status"} | (
                    {"name", "arguments"} if kind == "function_call" else {"output"}
                )
                _keys(item, allowed, "function history")
                call_id = item.get("call_id")
                _text(call_id, "Call ID", nonempty=True, maximum=64)
                if kind == "function_call":
                    if call_id in calls:
                        raise ValueError("Duplicate function call ID.")
                    calls.add(call_id)
                    _text(item.get("name"), "Function name", nonempty=True)
                    _text(item.get("arguments"), "Function arguments")
                    try:
                        arguments = json.loads(item["arguments"])
                    except (ValueError, TypeError):
                        raise ValueError("Function arguments must be JSON.") from None
                    if not isinstance(arguments, dict):
                        raise ValueError("Function arguments must be a JSON object.")
                else:
                    if call_id not in calls or call_id in resolved:
                        raise ValueError("Function output must match one preceding call.")
                    resolved.add(call_id)
                    _text(item.get("output"), "Function output")
            else:
                raise ValueError("Unsupported Responses input item.")
            if "id" in item:
                _text(item["id"], "Item ID", nonempty=True)
            if "status" in item and item["status"] not in (
                "completed",
                "incomplete",
                "in_progress",
            ):
                raise ValueError("Unsupported item status.")


def validate_native_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Shared by ingress and the protected provider transport boundary."""
    return MetaResponsesRequest.model_validate(payload).model_dump(exclude_none=True)
