import asyncio
import base64
import ssl
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity.oidc_http import OidcHttpClient, OidcHttpError  # noqa: E402
from core.identity.oidc_policy import load_oidc_configuration  # noqa: E402
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402


def _policy(**environment_overrides):
    environment = {
        "OIDC_ENABLED": "true",
        "OIDC_ISSUER": "https://identity.example.com/tenant",
        "OIDC_CLIENT_ID": "polaris",
        "OIDC_CLIENT_SECRET": "enterprise-client-secret",
        "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
    } | environment_overrides
    revision = OidcPolicyRevisionRecord.initial(
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    )
    return load_oidc_configuration(revision, environ=environment).policy


def _reader(response: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader(limit=16_384)
    reader.feed_data(response)
    reader.feed_eof()
    return reader


class FakeWriter:
    def __init__(self):
        self.request = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.request += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _response(
    body: bytes = b'{"issuer":"https://identity.example.com/tenant"}',
    *,
    status: str = "200 OK",
    content_type: str = "application/json",
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> bytes:
    headers = [
        f"HTTP/1.1 {status}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        *[f"{name}: {value}" for name, value in extra_headers],
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii") + body


class OidcHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_connects_to_approved_ip_while_validating_original_tls_hostname(self):
        calls = []
        writer = FakeWriter()

        async def resolver(host, port):
            self.assertEqual((host, port), ("identity.example.com", 443))
            return ("93.184.216.34", "1.1.1.1")

        async def connector(address, port, **kwargs):
            calls.append((address, port, kwargs))
            return _reader(_response()), writer

        client = OidcHttpClient(_policy(), resolver=resolver, connector=connector)
        payload = await client.get_json(
            "https://identity.example.com/tenant/.well-known/openid-configuration"
        )

        self.assertEqual(payload["issuer"], "https://identity.example.com/tenant")
        self.assertEqual(calls[0][0:2], ("93.184.216.34", 443))
        self.assertEqual(calls[0][2]["server_hostname"], "identity.example.com")
        context = calls[0][2]["ssl_context"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertIn(b"Host: identity.example.com\r\n", writer.request)
        self.assertIn(b"Accept-Encoding: identity\r\n", writer.request)
        self.assertIn(b"Connection: close\r\n", writer.request)
        self.assertTrue(writer.closed)

    async def test_invalid_endpoint_urls_fail_before_dns(self):
        resolver_called = False

        async def resolver(host, port):
            nonlocal resolver_called
            resolver_called = True
            return ("93.184.216.34",)

        client = OidcHttpClient(_policy(), resolver=resolver)
        invalid_urls = (
            "http://identity.example.com/jwks",
            "https://user@identity.example.com/jwks",
            "https://identity.example.com/jwks#fragment",
            "https://identity.example.com",
            "https://keys.example.net/jwks",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(OidcHttpError):
                    await client.get_json(url)
        self.assertFalse(resolver_called)

    async def test_connection_fallback_uses_only_the_single_approved_dns_snapshot(self):
        resolver_calls = 0
        connector_calls = []

        async def resolver(host, port):
            nonlocal resolver_calls
            resolver_calls += 1
            return ("93.184.216.34", "1.1.1.1")

        async def connector(address, port, **kwargs):
            connector_calls.append(address)
            if address == "93.184.216.34":
                raise OSError("simulated first-address outage")
            return _reader(_response()), FakeWriter()

        client = OidcHttpClient(_policy(), resolver=resolver, connector=connector)
        await client.get_json("https://identity.example.com/metadata")

        self.assertEqual(resolver_calls, 1)
        self.assertEqual(connector_calls, ["93.184.216.34", "1.1.1.1"])

    async def test_private_reserved_and_mixed_dns_answers_fail_closed(self):
        async def connector(*args, **kwargs):
            self.fail("Unsafe addresses must never reach the connector.")

        address_sets = (
            ("127.0.0.1",),
            ("169.254.1.1",),
            ("10.20.30.40",),
            ("0.0.0.0",),
            ("224.0.0.1",),
            ("93.184.216.34", "10.20.30.40"),
        )
        for addresses in address_sets:
            with self.subTest(addresses=addresses):

                async def resolver(host, port, result=addresses):
                    return result

                client = OidcHttpClient(
                    _policy(),
                    resolver=resolver,
                    connector=connector,
                )
                with self.assertRaises(OidcHttpError):
                    await client.get_json("https://identity.example.com/jwks")

    async def test_exact_private_host_allowlist_permits_private_but_not_dangerous_addresses(self):
        calls = []

        async def resolver(host, port):
            return ("10.20.30.40",)

        async def connector(address, port, **kwargs):
            calls.append(address)
            return _reader(_response()), FakeWriter()

        client = OidcHttpClient(
            _policy(OIDC_ALLOWED_PRIVATE_HOSTS="identity.example.com"),
            resolver=resolver,
            connector=connector,
        )
        await client.get_json("https://identity.example.com/jwks")
        self.assertEqual(calls, ["10.20.30.40"])

        async def unspecified_resolver(host, port):
            return ("0.0.0.0",)

        client = OidcHttpClient(
            _policy(OIDC_ALLOWED_PRIVATE_HOSTS="identity.example.com"),
            resolver=unspecified_resolver,
            connector=connector,
        )
        with self.assertRaises(OidcHttpError):
            await client.get_json("https://identity.example.com/jwks")

    async def test_redirect_status_content_type_and_content_encoding_are_rejected(self):
        responses = (
            _response(status="302 Found", extra_headers=(("Location", "https://evil.test"),)),
            _response(content_type="text/html"),
            _response(extra_headers=(("Content-Encoding", "gzip"),)),
        )
        for response in responses:
            with self.subTest(response=response[:40]):

                async def connector(address, port, **kwargs):
                    return _reader(response), FakeWriter()

                client = OidcHttpClient(
                    _policy(),
                    resolver=lambda host, port: asyncio.sleep(0, result=("93.184.216.34",)),
                    connector=connector,
                )
                with self.assertRaises(OidcHttpError):
                    await client.get_json("https://identity.example.com/metadata")

    async def test_declared_streamed_and_chunked_bodies_are_bounded(self):
        policy = _policy(OIDC_MAX_RESPONSE_BYTES="4096")
        oversized_length = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 4097\r\n\r\n"
        )
        oversized_stream = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + b"x" * 4097
        )
        oversized_chunk = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n1001\r\n" + b"x" * 4097 + b"\r\n0\r\n\r\n"
        )
        for response in (oversized_length, oversized_stream, oversized_chunk):

            async def connector(address, port, **kwargs):
                return _reader(response), FakeWriter()

            client = OidcHttpClient(
                policy,
                resolver=lambda host, port: asyncio.sleep(0, result=("93.184.216.34",)),
                connector=connector,
            )
            with self.assertRaises(OidcHttpError):
                await client.get_json("https://identity.example.com/metadata")

        body = b'{"keys":[]}'
        valid_chunked = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b'Transfer-Encoding: chunked\r\n\r\n5\r\n{"key\r\n6\r\ns":[]}\r\n0\r\n\r\n'
        )

        async def chunked_connector(address, port, **kwargs):
            return _reader(valid_chunked), FakeWriter()

        client = OidcHttpClient(
            policy,
            resolver=lambda host, port: asyncio.sleep(0, result=("93.184.216.34",)),
            connector=chunked_connector,
        )
        self.assertEqual(await client.get_json("https://identity.example.com/jwks"), {"keys": []})
        self.assertEqual(len(body), 11)

    async def test_dns_connect_and_read_timeouts_are_content_free(self):
        async def never_resolve(host, port):
            await asyncio.Event().wait()

        client = OidcHttpClient(_policy(OIDC_CONNECT_TIMEOUT_SECONDS="1"), resolver=never_resolve)
        with self.assertRaisesRegex(OidcHttpError, "OIDC HTTPS request failed") as caught:
            await client.get_json("https://identity.example.com/metadata")
        self.assertNotIn("identity.example.com", str(caught.exception))

    async def test_duplicate_length_conflicting_transfer_and_nonstandard_json_fail(self):
        responses = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}",
            _response(b'{"value":NaN}'),
            _response(b'{"issuer":"trusted","issuer":"poisoned"}'),
            _response(b"\xff"),
        )
        for response in responses:

            async def connector(address, port, **kwargs):
                return _reader(response), FakeWriter()

            client = OidcHttpClient(
                _policy(),
                resolver=lambda host, port: asyncio.sleep(0, result=("93.184.216.34",)),
                connector=connector,
            )
            with self.assertRaises(OidcHttpError):
                await client.get_json("https://identity.example.com/metadata")

    async def test_post_form_json_uses_bounded_body_and_oauth_basic_auth(self):
        writer = FakeWriter()
        body = b'{"token_type":"Bearer","access_token":"opaque","id_token":"signed"}'

        async def connector(address, port, **kwargs):
            return _reader(_response(body)), writer

        client = OidcHttpClient(
            _policy(),
            resolver=lambda host, port: asyncio.sleep(0, result=("93.184.216.34",)),
            connector=connector,
        )
        payload = await client.post_form_json(
            "https://identity.example.com/token?tenant=enterprise",
            (
                ("grant_type", "authorization_code"),
                ("code", "provider-code"),
                ("redirect_uri", "https://gateway.example.com/api/identity/oidc/callback"),
                ("code_verifier", "A" * 43),
            ),
            basic_auth=("client:id", "secret:value"),
        )

        headers, encoded_body = writer.request.split(b"\r\n\r\n", 1)
        request_line = headers.split(b"\r\n", 1)[0]
        self.assertEqual(
            request_line,
            b"POST /token?tenant=enterprise HTTP/1.1",
        )
        self.assertNotIn(b"provider-code", request_line)
        self.assertNotIn(b"secret", request_line)
        self.assertIn(b"Content-Type: application/x-www-form-urlencoded\r\n", headers)
        self.assertIn(f"Content-Length: {len(encoded_body)}\r\n".encode("ascii"), headers)
        authorization = next(
            line.removeprefix(b"Authorization: Basic ")
            for line in headers.split(b"\r\n")
            if line.startswith(b"Authorization: Basic ")
        )
        self.assertEqual(
            base64.b64decode(authorization),
            b"client%3Aid:secret%3Avalue",
        )
        self.assertEqual(
            parse_qs(encoded_body.decode("ascii"), strict_parsing=True),
            {
                "grant_type": ["authorization_code"],
                "code": ["provider-code"],
                "redirect_uri": ["https://gateway.example.com/api/identity/oidc/callback"],
                "code_verifier": ["A" * 43],
            },
        )
        self.assertEqual(payload["id_token"], "signed")
        self.assertTrue(writer.closed)

    async def test_post_form_json_rejects_malformed_or_oversized_inputs_before_dns(self):
        resolver_called = False

        async def resolver(host, port):
            nonlocal resolver_called
            resolver_called = True
            return ("93.184.216.34",)

        client = OidcHttpClient(_policy(), resolver=resolver)
        invalid_requests = (
            (("not-a-pair",),),
            (("code", "one"), ("code", "two")),
            (("bad field", "value"),),
            (("code", "line\nbreak"),),
            (("code", "x" * 16_385),),
            tuple((f"field_{index}", "value") for index in range(17)),
        )
        for fields in invalid_requests:
            with self.subTest(fields_type=type(fields).__name__):
                with self.assertRaisesRegex(OidcHttpError, "OIDC HTTPS request failed") as caught:
                    await client.post_form_json(
                        "https://identity.example.com/token",
                        fields,
                    )
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)
        self.assertFalse(resolver_called)


if __name__ == "__main__":
    unittest.main()
