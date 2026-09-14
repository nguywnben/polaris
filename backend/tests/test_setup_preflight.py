"""Contracts for first-run setup state, preflight, and owner creation safety."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.models import SetupRequest
from core.panel.auth import complete_setup
from core.panel.setup_preflight import (
    SETUP_CHECKPOINT_KEY,
    build_setup_status,
    run_setup_preflight,
)
from core.panel.setup_security import validate_owner_password


def build_request(
    *,
    client_host: str = "127.0.0.1",
    hostname: str = "localhost",
    scheme: str = "http",
    forwarded_proto: str = "",
    forwarded_host: str = "",
) -> Request:
    headers = [(b"host", f"{hostname}:4283".encode("ascii"))]
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    if forwarded_host:
        headers.append((b"x-forwarded-host", forwarded_host.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": scheme,
            "path": "/api/auth/setup/preflight",
            "headers": headers,
            "client": (client_host, 50000),
            "server": (hostname, 4283),
        }
    )


class FakeStorage:
    def __init__(self, values: dict | None = None, *, fail_write: bool = False):
        self.values = dict(values or {})
        self.fail_write = fail_write

    async def get_config(self, key, default=None):
        return self.values.get(key, default)

    async def set_config(self, key, value):
        if self.fail_write:
            return False
        self.values[key] = value
        return True

    async def delete_config(self, key):
        return self.values.pop(key, None) is not None


class SetupPasswordPolicyTests(unittest.TestCase):
    def test_owner_password_accepts_a_long_passphrase(self):
        validate_owner_password("correct horse battery staple")

    def test_owner_password_rejects_short_common_or_repetitive_values(self):
        for candidate in ("short", "password1234", "aaaaaaaaaaaaaaaa"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(HTTPException) as context:
                    validate_owner_password(candidate)
                self.assertEqual(context.exception.status_code, 400)


class SetupPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_local_install_has_one_run_preflight_action(self):
        result = await build_setup_status(
            build_request(),
            FakeStorage(),
            setup_required=True,
            authenticated=False,
        )

        self.assertEqual(result["state"], "fresh")
        self.assertEqual(result["next_action"], "run_preflight")
        self.assertEqual(result["checks"]["data"]["status"], "pending")
        self.assertEqual(result["base_url"], "http://localhost:4283")
        self.assertEqual(result["listener"], "0.0.0.0:4283")

    async def test_successful_preflight_persists_a_secret_free_resume_checkpoint(self):
        storage = FakeStorage()

        result = await run_setup_preflight(build_request(), storage, supplied_token=None)

        self.assertEqual(result["state"], "resumed")
        self.assertEqual(result["next_action"], "create_owner")
        self.assertEqual(result["checks"]["data"]["status"], "pass")
        checkpoint = storage.values[SETUP_CHECKPOINT_KEY]
        self.assertEqual(checkpoint, {"version": 1, "preflight": "passed"})
        self.assertNotIn("token", repr(checkpoint).lower())
        self.assertNotIn("password", repr(checkpoint).lower())

    async def test_failed_storage_write_returns_invalid_with_one_recovery_action(self):
        result = await run_setup_preflight(
            build_request(),
            FakeStorage(fail_write=True),
            supplied_token=None,
        )

        self.assertEqual(result["state"], "invalid")
        self.assertEqual(result["next_action"], "fix_data_permissions")
        self.assertEqual(result["checks"]["data"]["status"], "fail")

    async def test_configured_install_points_to_sign_in_or_dashboard(self):
        storage = FakeStorage()
        signed_out = await build_setup_status(
            build_request(), storage, setup_required=False, authenticated=False
        )
        signed_in = await build_setup_status(
            build_request(), storage, setup_required=False, authenticated=True
        )

        self.assertEqual(
            (signed_out["state"], signed_out["next_action"]), ("configured", "sign_in")
        )
        self.assertEqual(
            (signed_in["state"], signed_in["next_action"]),
            ("configured", "open_dashboard"),
        )

    async def test_remote_http_install_fails_closed_with_actionable_transport_state(self):
        request = build_request(client_host="198.51.100.20", hostname="gateway.example.com")
        with patch.dict(os.environ, {"SETUP_TOKEN": "a-strong-setup-token-value-123"}):
            result = await build_setup_status(
                request,
                FakeStorage(),
                setup_required=True,
                authenticated=False,
            )

        self.assertEqual(result["state"], "invalid")
        self.assertEqual(result["next_action"], "use_https")
        self.assertEqual(result["checks"]["transport"]["status"], "fail")

    async def test_docker_bridge_request_to_loopback_origin_allows_local_http(self):
        request = build_request(client_host="172.18.0.1", hostname="127.0.0.1")
        with patch.dict(os.environ, {"SETUP_TOKEN": "a-strong-setup-token-value-123"}):
            result = await build_setup_status(
                request,
                FakeStorage(),
                setup_required=True,
                authenticated=False,
            )

        self.assertEqual(result["state"], "fresh")
        self.assertEqual(result["next_action"], "enter_setup_token")
        self.assertEqual(
            result["checks"]["transport"], {"status": "pass", "code": "transport_local"}
        )

    async def test_remote_setup_without_operator_token_fails_closed(self):
        request = build_request(client_host="198.51.100.20", hostname="gateway.example.com")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SETUP_TOKEN", None)
            result = await build_setup_status(
                request,
                FakeStorage(),
                setup_required=True,
                authenticated=False,
            )

        self.assertEqual(result["state"], "invalid")
        self.assertEqual(result["next_action"], "configure_setup_token")


class SetupOwnerCreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_creation_refuses_a_failed_durable_write(self):
        storage = FakeStorage(fail_write=True)
        payload = SetupRequest(
            password="correct horse battery staple",
            confirm_password="correct horse battery staple",
        )
        with (
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=False)
            ),
            patch("core.panel.auth.get_storage_adapter", new=AsyncMock(return_value=storage)),
        ):
            with self.assertRaises(HTTPException) as context:
                await complete_setup(payload, build_request())

        self.assertEqual(context.exception.status_code, 503)
        self.assertNotIn("panel_password", storage.values)

    def test_setup_secrets_are_body_only_and_never_printed_or_added_to_history(self):
        main_source = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
        client_source = (ROOT / "frontend" / "js" / "features" / "authentication.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("Remote initial setup token:", main_source)
        self.assertIn("body: JSON.stringify", client_source)
        self.assertNotRegex(client_source, r"history\.(?:push|replace)State\([^\n]+setup[_-]token")


if __name__ == "__main__":
    unittest.main()
