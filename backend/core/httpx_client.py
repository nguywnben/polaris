import asyncio
from contextlib import asynccontextmanager
from threading import RLock
from typing import Any, AsyncGenerator, Dict, Hashable, Optional, Tuple

import httpx
from config import get_proxy_config
from log import log

STREAM_READ_CHUNK_BYTES = 64 * 1024
MAX_STREAM_LINE_BYTES = 1024 * 1024


class UpstreamStreamProtocolError(RuntimeError):
    """Raised when an upstream stream violates bounded framing rules."""


async def iter_bounded_lines(
    response: httpx.Response,
    *,
    max_line_bytes: int = MAX_STREAM_LINE_BYTES,
):
    """Decode newline-delimited upstream data without an unbounded line buffer."""
    if max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be positive")

    buffer = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=STREAM_READ_CHUNK_BYTES):
        buffer.extend(chunk)
        while True:
            newline_index = buffer.find(b"\n")
            if newline_index < 0:
                break
            if newline_index > max_line_bytes:
                raise UpstreamStreamProtocolError(
                    f"upstream stream line exceeds {max_line_bytes} bytes"
                )
            line = bytes(buffer[:newline_index])
            del buffer[: newline_index + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            yield line.decode("utf-8", errors="replace")

        if len(buffer) > max_line_bytes:
            raise UpstreamStreamProtocolError(
                f"upstream stream line exceeds {max_line_bytes} bytes"
            )

    if buffer:
        yield bytes(buffer).decode("utf-8", errors="replace")


class HttpxClientManager:
    """Reuse HTTP clients for the lifetime of one application event loop."""

    def __init__(self) -> None:
        self._clients: Dict[Tuple[Hashable, ...], httpx.AsyncClient] = {}
        self._lock = RLock()

    async def get_client_kwargs(self, timeout: float = 30.0, **kwargs) -> Dict[str, Any]:
        client_kwargs = {
            "timeout": timeout,
            "trust_env": False,
            "limits": httpx.Limits(max_connections=100, max_keepalive_connections=20),
            **kwargs,
        }

        current_proxy_config = await get_proxy_config()
        if current_proxy_config:
            client_kwargs["proxy"] = current_proxy_config

        return client_kwargs

    async def _get_or_create_client(
        self, timeout: Optional[float] = 30.0, **kwargs
    ) -> httpx.AsyncClient:
        client_kwargs = await self.get_client_kwargs(timeout=timeout, **kwargs)
        loop_id = id(asyncio.get_running_loop())
        signature = (
            loop_id,
            *((key, repr(value)) for key, value in sorted(client_kwargs.items())),
        )

        with self._lock:
            client = self._clients.get(signature)
            if client is None or client.is_closed:
                self._clients[signature] = httpx.AsyncClient(**client_kwargs)
            return self._clients[signature]

    @asynccontextmanager
    async def get_client(
        self, timeout: float = 30.0, **kwargs
    ) -> AsyncGenerator[httpx.AsyncClient, None]:
        yield await self._get_or_create_client(timeout=timeout, **kwargs)

    @asynccontextmanager
    async def get_streaming_client(
        self, timeout: float = None, **kwargs
    ) -> AsyncGenerator[httpx.AsyncClient, None]:
        yield await self._get_or_create_client(timeout=timeout, **kwargs)

    async def close(self) -> None:
        """Close clients created by the current runtime before its event loop exits."""
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()

        for client in clients:
            try:
                await client.aclose()
            except Exception as exc:
                log.warning(f"Error closing HTTP client: {exc}")


http_client = HttpxClientManager()


async def get_async(
    url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0, **kwargs
) -> httpx.Response:
    async with http_client.get_client(timeout=timeout, **kwargs) as client:
        return await client.get(url, headers=headers)


async def post_async(
    url: str,
    data: Any = None,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 900.0,
    **kwargs,
) -> httpx.Response:
    async with http_client.get_client(timeout=timeout, **kwargs) as client:
        return await client.post(url, data=data, json=json, headers=headers)


_MOCK_STREAM_429 = False


async def stream_post_async(
    url: str,
    body: Dict[str, Any],
    native: bool = False,
    headers: Optional[Dict[str, str]] = None,
    **kwargs,
):
    if _MOCK_STREAM_429:
        import json

        from fastapi import Response

        log.warning("[MOCK] stream_post_async: returning simulated 429 error")
        yield Response(
            content=json.dumps(
                {
                    "error": {
                        "code": 429,
                        "message": "mock rate limit",
                        "status": "RESOURCE_EXHAUSTED",
                    }
                }
            ),
            status_code=429,
        )
        return

    async with http_client.get_streaming_client(**kwargs) as client:
        async with client.stream("POST", url, json=body, headers=headers) as r:
            if r.status_code != 200:
                from fastapi import Response

                yield Response(await r.aread(), r.status_code, dict(r.headers))
                return

            if native:
                async for chunk in r.aiter_bytes(chunk_size=STREAM_READ_CHUNK_BYTES):
                    yield chunk
            else:
                async for line in iter_bounded_lines(r):
                    yield line
