from typing import Any, Mapping, Optional, Tuple

THOUGHT_SIGNATURE_SEPARATOR = "__thought__"
SKIP_THOUGHT_SIGNATURE_VALIDATOR = "skip_thought_signature_validator"
SKIP_THOUGHT_SIGNATURE_PLACEHOLDER_TEXT = "..."


def is_internal_placeholder_text(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    return text == "" or text.strip() == SKIP_THOUGHT_SIGNATURE_PLACEHOLDER_TEXT


def is_skip_thought_signature_placeholder(part: Mapping[str, Any]) -> bool:
    """Return True for the internal placeholder that should not reach clients."""
    if not isinstance(part, Mapping):
        return False
    if part.get("thoughtSignature") != SKIP_THOUGHT_SIGNATURE_VALIDATOR:
        return False
    if "functionCall" in part or "function_call" in part or "functionResponse" in part:
        return False
    text = part.get("text")
    return isinstance(text, str) and text.strip() in (SKIP_THOUGHT_SIGNATURE_PLACEHOLDER_TEXT, "")


def encode_tool_id_with_signature(tool_id: str, signature: Optional[str]) -> str:
    if not signature:
        return tool_id
    return f"{tool_id}{THOUGHT_SIGNATURE_SEPARATOR}{signature}"


def decode_tool_id_and_signature(encoded_id: str) -> Tuple[str, Optional[str]]:
    if not encoded_id or THOUGHT_SIGNATURE_SEPARATOR not in encoded_id:
        return encoded_id, None
    parts = encoded_id.split(THOUGHT_SIGNATURE_SEPARATOR, 1)
    return parts[0], parts[1] if len(parts) == 2 else None
