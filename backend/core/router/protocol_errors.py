"""Protocol-specific error responses for public SDK endpoints."""

from __future__ import annotations

import json
from typing import Any, Literal

from core.http_headers import retry_after_headers
from fastapi import Response
from fastapi.responses import JSONResponse
from log import redact_text

ProtocolName = Literal["openai", "anthropic", "gemini"]

_SAFE_RESPONSE_HEADERS = {
    "www-authenticate",
    "x-request-id",
    "request-id",
}


def protocol_for_path(path: str) -> ProtocolName | None:
    """Return the public SDK protocol represented by a request path."""
    if path.startswith("/v1/messages"):
        return "anthropic"
    if path.startswith("/v1beta/models/") or path == "/v1beta/models":
        return "gemini"
    if (
        path == "/vertex/v1beta/models"
        or path.startswith("/vertex/v1beta/models/")
        or path.startswith("/vertex/v1/models/")
    ):
        return "gemini"
    if (
        path.startswith("/v1/")
        or path == "/vertex/v1/models"
        or path.startswith("/vertex/v1/chat/completions")
    ):
        return "openai"
    return None


def _default_message(status_code: int) -> str:
    if status_code == 400:
        return "The request is invalid."
    if status_code == 401:
        return "Authentication failed."
    if status_code == 403:
        return "The request is not permitted."
    if status_code == 404:
        return "The requested resource was not found."
    if status_code == 408:
        return "The request timed out."
    if status_code == 413:
        return "The request is too large."
    if status_code == 429:
        return "The request rate limit was exceeded."
    if status_code in {502, 503, 504}:
        return "The service is temporarily unavailable."
    if status_code >= 500:
        return "The service encountered an internal error."
    return "The request could not be completed."


def _string_message(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        nested = value.get("message") or value.get("detail")
        if isinstance(nested, str):
            return nested
    return ""


def extract_error_message(payload: Any, status_code: int) -> str:
    """Extract and sanitize a bounded public message from an error payload."""
    message = ""
    if isinstance(payload, dict):
        message = _string_message(payload.get("error")) or _string_message(payload.get("detail"))
        if not message:
            message = _string_message(payload.get("message"))
    elif isinstance(payload, str):
        message = payload

    message = redact_text(message).strip()
    if not message:
        message = _default_message(status_code)
    return message[:2000]


def response_error_payload(response: Response) -> Any:
    """Decode a Starlette response body without raising on malformed upstream data."""
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = str(body or "")
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def protocol_error_payload(
    protocol: ProtocolName,
    status_code: int,
    message: str,
) -> dict[str, Any]:
    """Build the documented error envelope for a supported SDK protocol."""
    message = extract_error_message(message, status_code)

    if protocol == "anthropic":
        if status_code == 401:
            error_type = "authentication_error"
        elif status_code == 403:
            error_type = "permission_error"
        elif status_code == 404:
            error_type = "not_found_error"
        elif status_code == 413:
            error_type = "request_too_large"
        elif status_code == 429:
            error_type = "rate_limit_error"
        elif status_code in {502, 503, 504}:
            error_type = "overloaded_error"
        elif status_code >= 500:
            error_type = "api_error"
        else:
            error_type = "invalid_request_error"
        return {
            "type": "error",
            "error": {"type": error_type, "message": message},
        }

    if protocol == "gemini":
        status_name = {
            400: "INVALID_ARGUMENT",
            401: "UNAUTHENTICATED",
            403: "PERMISSION_DENIED",
            404: "NOT_FOUND",
            408: "DEADLINE_EXCEEDED",
            409: "ABORTED",
            413: "RESOURCE_EXHAUSTED",
            429: "RESOURCE_EXHAUSTED",
            502: "UNAVAILABLE",
            503: "UNAVAILABLE",
            504: "DEADLINE_EXCEEDED",
        }.get(status_code, "INTERNAL" if status_code >= 500 else "UNKNOWN")
        return {
            "error": {
                "code": status_code,
                "message": message,
                "status": status_name,
            }
        }

    if status_code == 401:
        error_type, error_code = "authentication_error", "invalid_api_key"
    elif status_code == 403:
        error_type, error_code = "permission_error", "permission_denied"
    elif status_code == 404:
        error_type, error_code = "not_found_error", "not_found"
    elif status_code == 409:
        error_type, error_code = "conflict_error", "conflict"
    elif status_code == 413:
        error_type, error_code = "invalid_request_error", "request_too_large"
    elif status_code == 422:
        error_type, error_code = "unprocessable_entity_error", "unprocessable_entity"
    elif status_code == 429:
        error_type, error_code = "rate_limit_error", "rate_limit_exceeded"
    elif status_code in {502, 503, 504}:
        error_type, error_code = "server_error", "service_unavailable"
    elif status_code >= 500:
        error_type, error_code = "server_error", "internal_error"
    else:
        error_type, error_code = "invalid_request_error", "invalid_request"
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": error_code,
        }
    }


def protocol_error_response(
    protocol: ProtocolName,
    status_code: int,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        content=protocol_error_payload(protocol, status_code, message),
        status_code=status_code,
        headers=headers,
    )


def adapt_protocol_error_response(
    response: Response,
    protocol: ProtocolName,
) -> Response:
    """Normalize a non-success response before it reaches a public SDK client."""
    if response.status_code < 400:
        return response
    payload = response_error_payload(response)
    message = extract_error_message(payload, response.status_code)
    headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in _SAFE_RESPONSE_HEADERS
    }
    headers.update(retry_after_headers(response.headers))
    return protocol_error_response(
        protocol,
        response.status_code,
        message,
        headers=headers or None,
    )
