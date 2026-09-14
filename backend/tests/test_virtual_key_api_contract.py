"""Management API and authentication contracts for W3.6 virtual-key scopes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.virtual_keys import (
    CreateVirtualKeyRequest,
    UpdateVirtualKeyRequest,
    VirtualKeyQualityPolicyRequest,
    update_virtual_key,
    update_virtual_key_quality_policy,
)
from core.request_context import (
    get_key_compression_policy,
    get_request_compression_policy,
    request_scope,
)
from core.utils import authenticate_flexible
from core.virtual_keys import DEFAULT_INFERENCE_SCOPES, VirtualKey
from fastapi import HTTPException
from main import app
from pydantic import ValidationError
from starlette.requests import Request


def _request(path: str, *, method: str = "GET", headers: tuple = ()) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "path": path,
            "query_string": b"",
            "headers": [(b"host", b"localhost:4283"), *headers],
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 4283),
        }
    )


class VirtualKeyRequestModelTests(unittest.TestCase):
    def test_openapi_create_contract_exposes_scope_and_pricing_policy(self):
        schema = app.openapi()
        request_schema = schema["components"]["schemas"]["CreateVirtualKeyRequest"]

        self.assertIn("scopes", request_schema["properties"])
        self.assertIn("unknown_pricing_policy", request_schema["properties"])
        self.assertIn("fallback_price_usd_per_million", request_schema["properties"])

    def test_create_contract_defaults_to_inference_only(self):
        payload = CreateVirtualKeyRequest(name="automation")

        self.assertEqual(payload.scopes, list(DEFAULT_INFERENCE_SCOPES))
        self.assertEqual(payload.unknown_pricing_policy, "deny")
        self.assertIsNone(payload.fallback_price_usd_per_million)

    def test_create_contract_rejects_unknown_scope(self):
        with self.assertRaises(ValidationError):
            CreateVirtualKeyRequest(name="invalid", scopes=["management:owner"])

    def test_create_contract_rejects_fallback_without_price(self):
        with self.assertRaises(ValidationError):
            CreateVirtualKeyRequest(name="invalid", unknown_pricing_policy="fallback")

    def test_update_contract_rejects_unsafe_model_pattern(self):
        with self.assertRaises(ValidationError):
            UpdateVirtualKeyRequest(
                expected_revision=1,
                allowed_models=["gpt-[0-9]*"],
            )


class VirtualKeyRouteContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_validation_error_is_a_client_error(self):
        with patch(
            "core.panel.virtual_keys.virtual_key_manager.update_key",
            new=AsyncMock(side_effect=ValueError("Virtual key scopes contain an unknown value.")),
        ):
            response = await update_virtual_key(
                "vk_example",
                UpdateVirtualKeyRequest(
                    expected_revision=3,
                    scopes=["inference:openai"],
                ),
                token="panel-session",
            )

        self.assertEqual(response.status_code, 400)

    async def test_quality_policy_route_updates_only_the_restrictive_field(self):
        updated = {"id": "vk_example", "compression_policy": "disabled", "revision": 4}
        with patch(
            "core.panel.virtual_keys.virtual_key_manager.update_key",
            new=AsyncMock(return_value=updated),
        ) as update:
            response = await update_virtual_key_quality_policy(
                "vk_example",
                VirtualKeyQualityPolicyRequest(
                    expected_revision=3,
                    compression="disabled",
                ),
                token="panel-session",
            )

        self.assertEqual(response["data"], updated)
        update.assert_awaited_once_with(
            "vk_example",
            {"compression_policy": "disabled"},
            expected_revision=3,
        )

    def test_quality_policy_route_is_an_additive_management_operation(self):
        schema = app.openapi()

        self.assertIn(
            "patch",
            schema["paths"]["/api/virtual-keys/{key_id}/quality-policy"],
        )


class InferenceScopeAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_key_request_can_only_disable_compression(self):
        with (
            request_scope("request-root-quality"),
            patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-root-example")),
        ):
            token = await authenticate_flexible(
                _request(
                    "/v1/models",
                    headers=((b"x-polaris-compression", b"off"),),
                ),
                authorization=None,
                x_api_key="sk-polaris-root-example",
                access_token=None,
                x_goog_api_key=None,
                x_anthropic_auth_token=None,
                anthropic_auth_token=None,
                key=None,
            )

            self.assertEqual(token, "sk-polaris-root-example")
            self.assertEqual(get_key_compression_policy(), "inherit")
            self.assertEqual(get_request_compression_policy(), "disabled")

    async def test_request_rejects_a_compression_enable_override(self):
        with (
            request_scope("request-invalid-quality"),
            patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-root-example")),
            self.assertRaises(HTTPException) as raised,
        ):
            await authenticate_flexible(
                _request(
                    "/v1/models",
                    headers=((b"x-polaris-compression", b"enabled"),),
                ),
                authorization=None,
                x_api_key="sk-polaris-root-example",
                access_token=None,
                x_goog_api_key=None,
                x_anthropic_auth_token=None,
                anthropic_auth_token=None,
                key=None,
            )

        self.assertEqual(raised.exception.status_code, 400)

    async def test_authentication_enforces_protocol_scope_and_records_last_used(self):
        record = VirtualKey(
            id="vk_scoped",
            name="scoped",
            key_hash="hash",
            key_preview="sk-polaris-vk-...oped",
            scopes=("inference:openai",),
        )
        with (
            patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-root-example")),
            patch(
                "core.virtual_keys.virtual_key_manager.verify",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "core.virtual_keys.virtual_key_manager.enforce",
                new=AsyncMock(),
            ) as enforce,
            patch(
                "core.virtual_keys.virtual_key_manager.note_last_used",
                new=AsyncMock(),
            ) as note_last_used,
        ):
            token = await authenticate_flexible(
                _request("/v1/models"),
                authorization=None,
                x_api_key="sk-polaris-vk-example",
                access_token=None,
                x_goog_api_key=None,
                x_anthropic_auth_token=None,
                anthropic_auth_token=None,
                key=None,
            )

        self.assertEqual(token, "sk-polaris-vk-example")
        enforce.assert_awaited_once_with(
            record,
            protocol="openai",
            requested_model="",
            request_body=None,
            candidate_models=None,
            operation_id="",
        )
        note_last_used.assert_awaited_once_with(record)

    async def test_authentication_applies_key_and_request_compression_restrictions(self):
        record = VirtualKey(
            id="vk_quality",
            name="quality",
            key_hash="hash",
            key_preview="sk-polaris-vk-...ity",
            compression_policy="disabled",
        )
        with (
            request_scope("request-quality"),
            patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-root-example")),
            patch(
                "core.virtual_keys.virtual_key_manager.verify", new=AsyncMock(return_value=record)
            ),
            patch("core.virtual_keys.virtual_key_manager.enforce", new=AsyncMock()),
            patch("core.virtual_keys.virtual_key_manager.note_last_used", new=AsyncMock()),
        ):
            await authenticate_flexible(
                _request(
                    "/v1/models",
                    headers=((b"x-polaris-compression", b"off"),),
                ),
                authorization=None,
                x_api_key="sk-polaris-vk-example",
                access_token=None,
                x_goog_api_key=None,
                x_anthropic_auth_token=None,
                anthropic_auth_token=None,
                key=None,
            )

            self.assertEqual(get_key_compression_policy(), "disabled")
            self.assertEqual(get_request_compression_policy(), "disabled")


if __name__ == "__main__":
    unittest.main()
