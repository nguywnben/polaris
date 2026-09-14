"""Bound request bodies before application parsers allocate unbounded memory."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from core.router.protocol_errors import protocol_error_response, protocol_for_path
from fastapi.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

DEFAULT_MAX_REQUEST_BODY_MB = 64
MIN_MAX_REQUEST_BODY_MB = 1
MAX_MAX_REQUEST_BODY_MB = 512
REQUEST_TOO_LARGE_MESSAGE = "The request body exceeds the configured size limit."


def get_max_request_body_bytes() -> int:
    """Return the validated global request-body ceiling in bytes."""
    raw_value = os.getenv("MAX_REQUEST_BODY_MB", str(DEFAULT_MAX_REQUEST_BODY_MB)).strip()
    try:
        megabytes = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("MAX_REQUEST_BODY_MB must be an integer.") from exc
    if megabytes < MIN_MAX_REQUEST_BODY_MB or megabytes > MAX_MAX_REQUEST_BODY_MB:
        raise RuntimeError(
            "MAX_REQUEST_BODY_MB must be between "
            f"{MIN_MAX_REQUEST_BODY_MB} and {MAX_MAX_REQUEST_BODY_MB}."
        )
    return megabytes * 1024 * 1024


class RequestBodyTooLarge(Exception):
    """Signal that an ASGI request exceeded its configured body ceiling."""


class RequestBodyLimitMiddleware:
    """Reject oversized fixed-length and chunked HTTP request bodies."""

    def __init__(
        self,
        app: Callable[..., Awaitable[Any]],
        max_body_bytes: int,
        path_limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.path_limits = dict(path_limits or {})

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                length = int(value.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                return None
            return max(length, 0)
        return None

    @staticmethod
    def _response(scope: Scope):
        protocol = protocol_for_path(str(scope.get("path") or ""))
        if protocol:
            return protocol_error_response(protocol, 413, REQUEST_TOO_LARGE_MESSAGE)
        return JSONResponse(
            status_code=413,
            content={"detail": REQUEST_TOO_LARGE_MESSAGE},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        max_body_bytes = self.path_limits.get(path, self.max_body_bytes)
        content_length = self._content_length(scope)
        if content_length is not None and content_length > max_body_bytes:
            await self._response(scope)(scope, receive, send)
            return

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._response(scope)(scope, receive, send)
