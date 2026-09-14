"""Bounded OIDC HTTPS transport with DNS validation and connection pinning."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import re
import socket
import ssl
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import SplitResult, quote_plus, urlencode, urlsplit

from core.identity.oidc_policy import OidcPolicy

_MAX_URL_LENGTH = 2_048
_MAX_RESOLVED_ADDRESSES = 16
_MAX_HEADER_BYTES = 16_384
_MAX_HEADERS = 64
_MAX_CHUNK_LINE_BYTES = 128
_MAX_TRAILER_BYTES = 8_192
_MAX_TRAILERS = 32
_MAX_FORM_FIELDS = 16
_MAX_FORM_BODY_BYTES = 16_384
_HEADER_NAME_PATTERN = re.compile(rb"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_FORM_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

Resolver = Callable[[str, int], Awaitable[Sequence[str]]]
Connector = Callable[..., Awaitable[tuple[asyncio.StreamReader, Any]]]


class OidcHttpError(RuntimeError):
    """Content-free boundary for unsafe or unsuccessful OIDC HTTPS requests."""

    def __init__(self) -> None:
        super().__init__("OIDC HTTPS request failed.")


async def _default_resolver(host: str, port: int) -> tuple[str, ...]:
    try:
        return (ipaddress.ip_address(host).compressed,)
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return tuple(record[4][0] for record in records)


async def _default_connector(
    address: str,
    port: int,
    *,
    ssl_context: ssl.SSLContext,
    server_hostname: str,
    connect_timeout: int,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection(
        address,
        port,
        ssl=ssl_context,
        server_hostname=server_hostname,
        ssl_handshake_timeout=connect_timeout,
        limit=_MAX_HEADER_BYTES,
    )


def _endpoint_origin(parsed: SplitResult) -> str:
    hostname = parsed.hostname
    if hostname is None:
        raise OidcHttpError
    rendered_host = f"[{hostname.lower()}]" if ":" in hostname else hostname.lower()
    return f"https://{rendered_host}" + (
        f":{parsed.port}" if parsed.port not in {None, 443} else ""
    )


def _endpoint_url(url: str, policy: OidcPolicy) -> SplitResult:
    if (
        type(url) is not str
        or not url
        or url != url.strip()
        or len(url) > _MAX_URL_LENGTH
        or not url.startswith("https://")
        or "\\" in url
    ):
        raise OidcHttpError
    try:
        url.encode("ascii")
        parsed = urlsplit(url)
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise OidcHttpError from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path in {"", "/"}
        or not parsed.path.startswith("/")
        or parsed.hostname.endswith(".")
        or "*" in parsed.hostname
        or port is not None
        and not 1 <= port <= 65_535
        or _endpoint_origin(parsed) not in policy.allowed_endpoint_origins
    ):
        raise OidcHttpError
    return parsed


def validate_oidc_endpoint_url(policy: OidcPolicy, url: str) -> None:
    """Validate one endpoint against the immutable policy without performing DNS or I/O."""
    if type(policy) is not OidcPolicy or not policy.enabled:
        raise OidcHttpError
    _endpoint_url(url, policy)


def _approved_addresses(
    addresses: Sequence[str],
    *,
    host: str,
    allowed_private_hosts: tuple[str, ...],
) -> tuple[str, ...]:
    if (
        isinstance(addresses, (str, bytes))
        or not addresses
        or len(addresses) > _MAX_RESOLVED_ADDRESSES
    ):
        raise OidcHttpError
    normalized_host = host.lower()
    try:
        normalized_host = ipaddress.ip_address(host).compressed.lower()
    except ValueError:
        pass
    private_allowed = normalized_host in allowed_private_hosts
    approved: list[str] = []
    for value in addresses:
        if type(value) is not str:
            raise OidcHttpError
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise OidcHttpError from exc
        if address.is_unspecified or address.is_multicast or address.is_reserved:
            raise OidcHttpError
        if not address.is_global and not private_allowed:
            raise OidcHttpError
        rendered = address.compressed.lower()
        if rendered not in approved:
            approved.append(rendered)
    if not approved:
        raise OidcHttpError
    return tuple(approved)


async def _timed(awaitable: Awaitable[Any], timeout: int) -> Any:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise OidcHttpError from exc


async def _read_headers(reader: asyncio.StreamReader, timeout: int) -> bytes:
    try:
        value = await _timed(reader.readuntil(b"\r\n\r\n"), timeout)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise OidcHttpError from exc
    if len(value) > _MAX_HEADER_BYTES:
        raise OidcHttpError
    return value[:-4]


def _parse_headers(raw_headers: bytes) -> tuple[int, dict[bytes, list[bytes]]]:
    lines = raw_headers.split(b"\r\n")
    if not lines or len(lines) - 1 > _MAX_HEADERS:
        raise OidcHttpError
    status_parts = lines[0].split(b" ", 2)
    if (
        len(status_parts) < 2
        or status_parts[0] not in {b"HTTP/1.0", b"HTTP/1.1"}
        or len(status_parts[1]) != 3
        or not status_parts[1].isdigit()
    ):
        raise OidcHttpError
    headers: dict[bytes, list[bytes]] = {}
    for line in lines[1:]:
        if not line or line[:1] in {b" ", b"\t"} or b":" not in line:
            raise OidcHttpError
        name, value = line.split(b":", 1)
        if not _HEADER_NAME_PATTERN.fullmatch(name):
            raise OidcHttpError
        normalized_name = name.lower()
        normalized_value = value.strip(b" \t")
        if b"\x00" in normalized_value or b"\r" in normalized_value or b"\n" in normalized_value:
            raise OidcHttpError
        headers.setdefault(normalized_name, []).append(normalized_value)
    return int(status_parts[1]), headers


def _single_header(
    headers: dict[bytes, list[bytes]],
    name: bytes,
    *,
    required: bool = False,
) -> bytes | None:
    values = headers.get(name, [])
    if len(values) > 1 or required and not values:
        raise OidcHttpError
    return values[0] if values else None


async def _read_exactly(reader: asyncio.StreamReader, size: int, timeout: int) -> bytes:
    try:
        return await _timed(reader.readexactly(size), timeout)
    except asyncio.IncompleteReadError as exc:
        raise OidcHttpError from exc


async def _read_chunked(
    reader: asyncio.StreamReader,
    *,
    timeout: int,
    maximum: int,
) -> bytes:
    body = bytearray()
    while True:
        line = await _timed(reader.readline(), timeout)
        if not line.endswith(b"\r\n") or len(line) > _MAX_CHUNK_LINE_BYTES:
            raise OidcHttpError
        size_text = line[:-2].split(b";", 1)[0]
        if not size_text or any(byte not in b"0123456789abcdefABCDEF" for byte in size_text):
            raise OidcHttpError
        size = int(size_text, 16)
        if size > maximum - len(body):
            raise OidcHttpError
        if size == 0:
            trailer_bytes = 0
            trailer_count = 0
            while True:
                trailer = await _timed(reader.readline(), timeout)
                trailer_bytes += len(trailer)
                if (
                    not trailer.endswith(b"\r\n")
                    or trailer_bytes > _MAX_TRAILER_BYTES
                    or trailer_count > _MAX_TRAILERS
                ):
                    raise OidcHttpError
                if trailer == b"\r\n":
                    return bytes(body)
                trailer_count += 1
                if trailer[:1] in {b" ", b"\t"} or b":" not in trailer:
                    raise OidcHttpError
        chunk = await _read_exactly(reader, size + 2, timeout)
        if not chunk.endswith(b"\r\n"):
            raise OidcHttpError
        body.extend(chunk[:-2])


async def _read_until_eof(
    reader: asyncio.StreamReader,
    *,
    timeout: int,
    maximum: int,
) -> bytes:
    body = bytearray()
    while len(body) <= maximum:
        chunk = await _timed(reader.read(min(65_536, maximum + 1 - len(body))), timeout)
        if not chunk:
            return bytes(body)
        body.extend(chunk)
    raise OidcHttpError


async def _response_body(
    reader: asyncio.StreamReader,
    *,
    headers: dict[bytes, list[bytes]],
    timeout: int,
    maximum: int,
) -> bytes:
    content_type = _single_header(headers, b"content-type", required=True)
    if content_type is None:
        raise OidcHttpError
    media_type = content_type.split(b";", 1)[0].strip().lower()
    if media_type not in {b"application/json", b"application/jwk-set+json"}:
        raise OidcHttpError
    content_encoding = _single_header(headers, b"content-encoding")
    if content_encoding is not None and content_encoding.lower() != b"identity":
        raise OidcHttpError
    content_length = _single_header(headers, b"content-length")
    transfer_encoding = _single_header(headers, b"transfer-encoding")
    if content_length is not None and transfer_encoding is not None:
        raise OidcHttpError
    if transfer_encoding is not None:
        if transfer_encoding.lower() != b"chunked":
            raise OidcHttpError
        return await _read_chunked(reader, timeout=timeout, maximum=maximum)
    if content_length is not None:
        if not content_length.isdigit():
            raise OidcHttpError
        length = int(content_length)
        if length > maximum:
            raise OidcHttpError
        return await _read_exactly(reader, length, timeout)
    return await _read_until_eof(reader, timeout=timeout, maximum=maximum)


def _strict_json(body: bytes) -> object:
    try:
        text = body.decode("utf-8")

        def reject_constant(value: str) -> None:
            raise ValueError(value)

        def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
            value: dict[str, object] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate JSON key")
                value[key] = item
            return value

        return json.loads(
            text,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeError, ValueError) as exc:
        raise OidcHttpError from exc


def _form_body(fields: object) -> bytes:
    if type(fields) is not tuple or not 1 <= len(fields) <= _MAX_FORM_FIELDS:
        raise OidcHttpError
    normalized: list[tuple[str, str]] = []
    names: set[str] = set()
    for item in fields:
        if type(item) is not tuple or len(item) != 2:
            raise OidcHttpError
        name, value = item
        if (
            type(name) is not str
            or not _FORM_NAME_PATTERN.fullmatch(name)
            or name in names
            or type(value) is not str
            or not value
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise OidcHttpError
        names.add(name)
        normalized.append((name, value))
    encoded = urlencode(normalized).encode("ascii")
    if len(encoded) > _MAX_FORM_BODY_BYTES:
        raise OidcHttpError
    return encoded


def _basic_authorization(value: object) -> str:
    if type(value) is not tuple or len(value) != 2:
        raise OidcHttpError
    client_id, client_secret = value
    if any(
        type(item) is not str
        or not item
        or len(item) > 4_096
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in item)
        for item in (client_id, client_secret)
    ):
        raise OidcHttpError
    credentials = f"{quote_plus(client_id)}:{quote_plus(client_secret)}".encode("ascii")
    return base64.b64encode(credentials).decode("ascii")


class OidcHttpClient:
    """Fetch OIDC JSON without redirects, proxies, compression, or DNS re-resolution."""

    def __init__(
        self,
        policy: OidcPolicy,
        *,
        resolver: Resolver = _default_resolver,
        connector: Connector = _default_connector,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if type(policy) is not OidcPolicy or not policy.enabled:
            raise OidcHttpError
        self._policy = policy
        self._resolver = resolver
        self._connector = connector
        self._ssl_context = ssl_context or ssl.create_default_context()
        if (
            not self._ssl_context.check_hostname
            or self._ssl_context.verify_mode != ssl.CERT_REQUIRED
        ):
            raise OidcHttpError

    def validate_endpoint_url(self, url: str) -> None:
        validate_oidc_endpoint_url(self._policy, url)

    async def _connect(
        self,
        parsed: SplitResult,
    ) -> tuple[asyncio.StreamReader, Any]:
        hostname = parsed.hostname
        if hostname is None:
            raise OidcHttpError
        port = parsed.port or 443
        addresses = await _timed(
            self._resolver(hostname, port),
            self._policy.connect_timeout_seconds,
        )
        approved = _approved_addresses(
            addresses,
            host=hostname,
            allowed_private_hosts=self._policy.allowed_private_hosts,
        )
        for address in approved:
            try:
                return await _timed(
                    self._connector(
                        address,
                        port,
                        ssl_context=self._ssl_context,
                        server_hostname=hostname,
                        connect_timeout=self._policy.connect_timeout_seconds,
                    ),
                    self._policy.connect_timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                continue
        raise OidcHttpError

    async def get_json(self, url: str) -> object:
        try:
            parsed = _endpoint_url(url, self._policy)
            host_header = parsed.netloc
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            request = (
                f"GET {target} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Accept: application/json, application/jwk-set+json\r\n"
                "Accept-Encoding: identity\r\n"
                "Connection: close\r\n"
                "User-Agent: Polaris-OIDC/1\r\n"
                "\r\n"
            ).encode("ascii")
            return await self._send_json(parsed, request)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise OidcHttpError from None

    async def post_form_json(
        self,
        url: str,
        fields: tuple[tuple[str, str], ...],
        *,
        basic_auth: tuple[str, str] | None = None,
    ) -> object:
        """POST one bounded OAuth form without redirects or ambient credentials."""
        try:
            parsed = _endpoint_url(url, self._policy)
            body = _form_body(fields)
            authorization = (
                f"Authorization: Basic {_basic_authorization(basic_auth)}\r\n"
                if basic_auth is not None
                else ""
            )
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            request = (
                f"POST {target} HTTP/1.1\r\n"
                f"Host: {parsed.netloc}\r\n"
                "Accept: application/json\r\n"
                "Accept-Encoding: identity\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"{authorization}"
                "Connection: close\r\n"
                "User-Agent: Polaris-OIDC/1\r\n"
                "\r\n"
            ).encode("ascii") + body
            return await self._send_json(parsed, request)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise OidcHttpError from None

    async def _send_json(self, parsed: SplitResult, request: bytes) -> object:
        reader, writer = await self._connect(parsed)
        try:
            writer.write(request)
            await _timed(writer.drain(), self._policy.read_timeout_seconds)
            raw_headers = await _read_headers(reader, self._policy.read_timeout_seconds)
            status, headers = _parse_headers(raw_headers)
            if status != 200:
                raise OidcHttpError
            body = await _response_body(
                reader,
                headers=headers,
                timeout=self._policy.read_timeout_seconds,
                maximum=self._policy.max_response_bytes,
            )
            return _strict_json(body)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
