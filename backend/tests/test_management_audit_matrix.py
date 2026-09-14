"""Coverage gate for the management mutation audit matrix."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementPrincipal, ManagementRole
from core.management_audit import (
    MANAGEMENT_AUDIT_EXCLUSIONS,
    MANAGEMENT_MUTATIONS,
    classify_management_denial,
    classify_management_mutation,
    record_management_response,
)
from core.request_context import request_scope, set_api_key_id
from main import app


class ManagementAuditMatrixTests(unittest.TestCase):
    def test_every_control_plane_write_route_is_classified_or_explicitly_excluded(self):
        schema = app.openapi()
        write_methods = {"post", "put", "patch", "delete"}
        routes = {
            (method.upper(), path)
            for path, operations in schema["paths"].items()
            for method in operations
            if method in write_methods and path.startswith("/api/")
        }

        self.assertEqual(routes, set(MANAGEMENT_MUTATIONS) | set(MANAGEMENT_AUDIT_EXCLUSIONS))
        self.assertFalse(set(MANAGEMENT_MUTATIONS) & set(MANAGEMENT_AUDIT_EXCLUSIONS))
        self.assertTrue(all(MANAGEMENT_AUDIT_EXCLUSIONS.values()))

    def test_runtime_paths_resolve_to_redacted_semantic_targets(self):
        mutation = classify_management_mutation(
            "DELETE",
            "/api/virtual-keys/vk_customer-secret",
        )

        self.assertIsNotNone(mutation)
        self.assertEqual(mutation.action, "virtual_key.revoke")
        self.assertEqual(mutation.target_type, "virtual_key")
        self.assertEqual(mutation.change_codes, ("revoked",))
        self.assertEqual(mutation.target_identifier, "vk_customer-secret")

    def test_same_provider_resolves_to_one_stable_semantic_target(self):
        saved = classify_management_mutation(
            "POST",
            "/api/providers/openai/config",
        )
        reset = classify_management_mutation(
            "POST",
            "/api/providers/openai/config/reset",
        )
        credential = classify_management_mutation(
            "POST",
            "/api/credentials/verify/customer.json",
        )

        self.assertEqual(saved.target_identifier, "openai")
        self.assertEqual(reset.target_identifier, "openai")
        self.assertEqual(credential.target_identifier, "customer.json")

    def test_preview_and_oauth_start_routes_are_not_misreported_as_mutations(self):
        for path in (
            "/api/quality-policy/preview",
            "/api/auth/start",
            "/api/providers/openai/codex/oauth/start",
        ):
            with self.subTest(path=path):
                self.assertIsNone(classify_management_mutation("POST", path))

    def test_protected_read_denials_use_template_target_without_path_parameters(self):
        denial = classify_management_denial(
            "GET",
            "/api/identity/identities",
        )

        self.assertEqual(denial.action, "management.access_denied")
        self.assertEqual(denial.target_type, "management_route")
        self.assertEqual(denial.target_identifier, "/api/identity/identities")
        self.assertEqual(denial.change_codes, ("no_change",))


class ManagementAuditResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_response_status_maps_to_bounded_outcome_and_actor(self):
        service = AsyncMock()
        service.record.return_value = object()

        with patch("core.audit_service.get_audit_service", return_value=service):
            await record_management_response(
                method="POST",
                path="/api/config/save",
                status_code=409,
                request_id="request-conflict",
            )

        service.record.assert_awaited_once()
        kwargs = service.record.await_args.kwargs
        self.assertEqual(kwargs["outcome"], "conflict")
        self.assertEqual(kwargs["actor_type"], "panel_session")
        self.assertEqual(kwargs["actor_identifier"], "panel-owner")

    async def test_failed_login_is_attributed_without_persisting_client_identity(self):
        service = AsyncMock()

        with patch("core.audit_service.get_audit_service", return_value=service):
            await record_management_response(
                method="POST",
                path="/api/auth/login",
                status_code=401,
                request_id="request-login",
            )

        kwargs = service.record.await_args.kwargs
        self.assertEqual(kwargs["outcome"], "denied")
        self.assertEqual(kwargs["actor_type"], "system")
        self.assertEqual(kwargs["actor_identifier"], "unauthenticated-control-plane")

    async def test_scoped_virtual_key_is_attributed_to_its_stable_key_id(self):
        service = AsyncMock()

        with (
            request_scope("request-virtual-key"),
            patch("core.audit_service.get_audit_service", return_value=service),
        ):
            set_api_key_id("vk_operations")
            await record_management_response(
                method="POST",
                path="/api/config/save",
                status_code=200,
                request_id="request-virtual-key",
            )

        kwargs = service.record.await_args.kwargs
        self.assertEqual(kwargs["actor_type"], "virtual_key")
        self.assertEqual(kwargs["actor_identifier"], "vk_operations")

    async def test_authenticated_oidc_denial_keeps_typed_redacted_actor(self):
        service = AsyncMock()
        principal = ManagementPrincipal.oidc_user(
            issuer="https://idp.example/tenant",
            subject="subject-123",
            role=ManagementRole.VIEWER,
        )

        with patch("core.audit_service.get_audit_service", return_value=service):
            await record_management_response(
                method="POST",
                path="/api/config/save",
                status_code=403,
                request_id="request-oidc-denied",
                principal=principal,
            )

        kwargs = service.record.await_args.kwargs
        self.assertEqual(kwargs["outcome"], "denied")
        self.assertEqual(kwargs["actor_type"], "oidc_user")
        self.assertEqual(
            kwargs["actor_identifier"],
            "https://idp.example/tenant\0subject-123",
        )

    async def test_local_owner_uses_typed_actor(self):
        service = AsyncMock()

        with patch("core.audit_service.get_audit_service", return_value=service):
            await record_management_response(
                method="POST",
                path="/api/config/save",
                status_code=200,
                request_id="request-owner",
                principal=ManagementPrincipal.local_owner(),
            )

        kwargs = service.record.await_args.kwargs
        self.assertEqual(kwargs["actor_type"], "local_owner")
        self.assertEqual(kwargs["actor_identifier"], "local-owner")

    async def test_excluded_route_does_not_touch_audit_service(self):
        with patch("core.audit_service.get_audit_service") as get_service:
            event = await record_management_response(
                method="POST",
                path="/api/quality-policy/preview",
                status_code=200,
                request_id="request-preview",
            )

        self.assertIsNone(event)
        get_service.assert_not_called()


if __name__ == "__main__":
    unittest.main()
