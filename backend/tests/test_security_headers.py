"""Security header regression tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.requests import Request
from starlette.responses import JSONResponse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import add_security_headers


def build_request(path: str, *, forwarded_proto: str = "", method: str = "GET") -> Request:
    headers = []
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "path": path,
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 4283),
        }
    )


class SecurityHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_config_writes_emit_correlated_redacted_audit_outcomes(self):
        for path in ("/api/providers/google/config", "/api/providers/google/config/reset"):
            for status, outcome in (
                (200, "succeeded"),
                (400, "invalid"),
                (403, "denied"),
                (500, "failed"),
            ):
                with self.subTest(path=path, status=status):
                    service = AsyncMock()

                    async def next_handler(_request):
                        return JSONResponse(
                            {"detail": "test-only-sensitive-value"}, status_code=status
                        )

                    with patch("core.audit_service.get_audit_service", return_value=service):
                        response = await add_security_headers(
                            build_request(path, method="POST"), next_handler
                        )

                    self.assertEqual(response.status_code, status)
                    service.record.assert_awaited_once()
                    mutation = service.record.await_args.args[0]
                    evidence = service.record.await_args.kwargs
                    self.assertEqual(mutation.action, "provider.update")
                    self.assertEqual(mutation.target_type, "provider")
                    self.assertEqual(mutation.target_identifier, "google")
                    self.assertEqual(mutation.change_codes, ("settings_changed",))
                    self.assertEqual(evidence["outcome"], outcome)
                    self.assertEqual(evidence["request_id"], response.headers["x-request-id"])
                    self.assertNotIn("test-only-sensitive-value", repr(service.record.await_args))

    async def test_management_mutation_is_correlated_after_response(self):
        async def next_handler(_request):
            return JSONResponse({"ok": False}, status_code=409)

        audit_response = AsyncMock()
        with patch("main.record_classified_management_response", audit_response):
            response = await add_security_headers(
                build_request("/api/config/save", method="POST"),
                next_handler,
            )

        self.assertEqual(response.status_code, 409)
        audit_response.assert_awaited_once()
        kwargs = audit_response.await_args.kwargs
        mutation = audit_response.await_args.args[0]
        self.assertEqual(mutation.action, "config.update")
        self.assertEqual(kwargs["status_code"], 409)
        self.assertEqual(kwargs["request_id"], response.headers["x-request-id"])

    async def test_dynamic_api_responses_are_not_cached(self):
        async def next_handler(_request):
            return JSONResponse({"ok": True})

        response = await add_security_headers(
            build_request("/api/config/get"),
            next_handler,
        )

        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["cross-origin-opener-policy"], "same-origin")
        csp = response.headers["content-security-policy"]
        self.assertIn("script-src 'self';", csp)
        self.assertIn("script-src-attr 'none';", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)

    async def test_untrusted_forwarded_proto_does_not_enable_hsts(self):
        async def next_handler(_request):
            return JSONResponse({"ok": True})

        with patch.dict(os.environ, {"TRUST_PROXY_HEADERS": ""}):
            response = await add_security_headers(
                build_request("/health", forwarded_proto="https"),
                next_handler,
            )

        self.assertNotIn("strict-transport-security", response.headers)

    async def test_trusted_https_proxy_requests_receive_hsts(self):
        async def next_handler(_request):
            return JSONResponse({"ok": True})

        with patch.dict(os.environ, {"TRUST_PROXY_HEADERS": "true"}):
            response = await add_security_headers(
                build_request("/health", forwarded_proto="https"),
                next_handler,
            )

        self.assertIn("max-age=31536000", response.headers["strict-transport-security"])

    async def test_static_assets_receive_explicit_cache_policy(self):
        async def next_handler(_request):
            return JSONResponse({"ok": True})

        response = await add_security_headers(
            build_request("/frontend/assets/logo.png"),
            next_handler,
        )

        self.assertEqual(
            response.headers["cache-control"],
            "public, max-age=86400",
        )


if __name__ == "__main__":
    unittest.main()
