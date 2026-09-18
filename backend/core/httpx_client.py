import asyncio
import ipaddress
import os
from contextlib import asynccontextmanager
from threading import RLock
from typing import Any, AsyncGenerator, Dict, Hashable, Optional, Tuple
from urllib.parse import urlsplit

import httpx
from config import get_proxy_config
from log import log

STREAM_READ_CHUNK_BYTES = 64 * 1024
MAX_STREAM_LINE_BYTES = 1024 * 1024


def _bypass_configured_proxy(destination_url: Optional[str]) -> bool:
    """Honor explicit no_proxy/NO_PROXY only; never resolve names or infer local bypass.

    Comma-separated rules support '*', domain suffixes on a label boundary,
    host[:port] (brackets for IPv6 with a port), and literal-IP CIDR networks.
    Lowercase takes precedence, including an explicitly empty value. CIDR rules
    never resolve a hostname; malformed rules are ignored and retain the proxy.
    """
    rules = os.environ.get("no_proxy", os.environ.get("NO_PROXY", ""))
    if not destination_url or not rules:
        return False
    try:
        destination = urlsplit(str(destination_url))
        host = (destination.hostname or "").lower().rstrip(".")
        port = destination.port
        if port is None:
            port = {"http": 80, "https": 443}.get(destination.scheme)
    except ValueError:
        return False
    if not host or destination.scheme not in {"http", "https"}:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    for raw_rule in rules.split(","):
        rule = raw_rule.strip().lower()
        if rule == "*":
            return True
        if not rule or any(character.isspace() for character in rule):
            continue
        if "/" in rule:
            try:
                if address is not None and address in ipaddress.ip_network(rule, strict=False):
                    return True
            except ValueError:
                pass
            continue
        rule_port = None
        if rule.startswith("["):
            closing = rule.find("]")
            if closing < 0:
                continue
            rule_host, suffix = rule[1:closing], rule[closing + 1 :]
            try:
                ipaddress.IPv6Address(rule_host)
            except ValueError:
                continue
            if suffix:
                if not suffix.startswith(":") or not suffix[1:].isdigit() or len(suffix) > 6:
                    continue
                rule_port = int(suffix[1:])
        elif rule.count(":") == 1:
            rule_host, port_text = rule.rsplit(":", 1)
            if not port_text.isdigit() or len(port_text) > 5:
                continue
            rule_port = int(port_text)
        else:
            rule_host = rule
        if rule_port is not None and (not 1 <= rule_port <= 65535 or rule_port != port):
            continue
        try:
            if address is not None and address == ipaddress.ip_address(rule_host):
                return True
        except ValueError:
            pass
        rule_host = rule_host.lstrip(".").rstrip(".")
        if address is None and rule_host and (host == rule_host or host.endswith("." + rule_host)):
            return True
    return False


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

    async def get_client_kwargs(
        self, timeout: float = 30.0, *, destination_url: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        client_kwargs = {
            "timeout": timeout,
            "trust_env": False,
            "limits": httpx.Limits(max_connections=100, max_keepalive_connections=20),
            **kwargs,
        }

        current_proxy_config = await get_proxy_config()
        if current_proxy_config:
            client_kwargs["proxy"] = current_proxy_config
        if _bypass_configured_proxy(destination_url):
            client_kwargs.pop("proxy", None)

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
    async with http_client.get_client(timeout=timeout, destination_url=url, **kwargs) as client:
        return await client.get(url, headers=headers)


async def post_async(
    url: str,
    data: Any = None,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 900.0,
    **kwargs,
) -> httpx.Response:
    async with http_client.get_client(timeout=timeout, destination_url=url, **kwargs) as client:
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

    async with http_client.get_streaming_client(destination_url=url, **kwargs) as client:
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
