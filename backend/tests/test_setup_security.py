"""Security contracts for first-run setup."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.models import SetupRequest
from core.panel.setup_security import (
    get_setup_access_policy,
    is_local_setup_request,
    verify_setup_access,
)


def build_request(*, client_host: str, hostname: str, forwarded_for: str = "") -> Request:
    headers = [(b"host", f"{hostname}:4283".encode("ascii"))]
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/setup",
            "headers": headers,
            "client": (client_host, 50000),
            "server": (hostname, 4283),
        }
    )


class SetupSecurityTests(unittest.TestCase):
    def test_setup_payload_keeps_r1_wire_schema_and_redacts_runtime_secrets(self):
        password = "owner-passphrase-never-render"
        token = "setup-token-never-render-2026"
        payload = SetupRequest(
            password=password,
            confirm_password=password,
            setup_token=token,
        )

        rendered = repr(payload)
        self.assertNotIn(password, rendered)
        self.assertNotIn(token, rendered)
        properties = SetupRequest.model_json_schema()["properties"]
        self.assertEqual(properties["password"], {"title": "Password", "type": "string"})
        self.assertEqual(properties["setup_token"]["anyOf"][0], {"type": "string"})

    def test_direct_loopback_setup_does_not_require_a_token(self):
        request = build_request(client_host="127.0.0.1", hostname="localhost")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SETUP_TOKEN", None)
            self.assertTrue(is_local_setup_request(request))
            self.assertFalse(get_setup_access_policy(request).token_required)
            verify_setup_access(request, None)

    def test_remote_setup_requires_the_configured_token(self):
        request = build_request(client_host="198.51.100.20", hostname="gateway.example.com")
        configured_token = "one-time-token-with-strong-entropy-123"

        with patch.dict(os.environ, {"SETUP_TOKEN": configured_token}):
            with self.assertRaises(HTTPException) as context:
                verify_setup_access(request, "incorrect-token")

            self.assertEqual(context.exception.status_code, 403)
            verify_setup_access(request, configured_token)

    def test_external_host_through_a_local_proxy_is_not_treated_as_local(self):
        request = build_request(client_host="127.0.0.1", hostname="gateway.example.com")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SETUP_TOKEN", None)
            self.assertFalse(is_local_setup_request(request))
            self.assertTrue(get_setup_access_policy(request).token_required)

    def test_remote_setup_without_operator_configured_token_fails_closed(self):
        request = build_request(client_host="198.51.100.20", hostname="gateway.example.com")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SETUP_TOKEN", None)
            with self.assertRaises(HTTPException) as context:
                verify_setup_access(request, None)

        self.assertEqual(context.exception.status_code, 503)

    def test_remote_setup_rejects_a_weak_operator_token(self):
        request = build_request(client_host="198.51.100.20", hostname="gateway.example.com")

        with patch.dict(os.environ, {"SETUP_TOKEN": "weak-token"}):
            with self.assertRaises(HTTPException) as context:
                verify_setup_access(request, "weak-token")

        self.assertEqual(context.exception.status_code, 503)

    def test_trusted_forwarded_client_address_controls_loopback_detection(self):
        request = build_request(
            client_host="127.0.0.1",
            hostname="localhost",
            forwarded_for="198.51.100.20",
        )

        with patch.dict(os.environ, {"TRUST_PROXY_HEADERS": "true"}):
            self.assertFalse(is_local_setup_request(request))


if __name__ == "__main__":
    unittest.main()
