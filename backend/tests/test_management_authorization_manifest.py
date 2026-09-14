"""Coverage and authorization matrix for protected management routes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.routing import APIWebSocketRoute

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from core.identity import (
    AuthorizationDenied,
    ManagementPermission,
    ManagementPrincipal,
    ManagementRole,
    ManagementRouteTransport,
    UnclassifiedManagementRoute,
    management_route_manifest,
    permissions_for_role,
    require_management_route,
)
from core.panel.logs import router as logs_router


def _protected_openapi_operations() -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for path, path_item in main.app.openapi()["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            if any("HTTPBearer" in requirement for requirement in operation.get("security", [])):
                operations.add((method.upper(), path))
    return operations


class ManagementRouteManifestCoverageTests(unittest.TestCase):
    def test_every_protected_http_operation_is_classified_exactly_once(self):
        entries = management_route_manifest()
        http_keys = [
            (entry.method, entry.path)
            for entry in entries
            if entry.transport is ManagementRouteTransport.HTTP
        ]

        self.assertEqual(len(http_keys), len(set(http_keys)))
        self.assertEqual(set(http_keys), _protected_openapi_operations())

    def test_every_management_websocket_is_classified_exactly_once(self):
        actual = {
            ("WEBSOCKET", route.path)
            for route in logs_router.routes
            if isinstance(route, APIWebSocketRoute)
        }
        entries = management_route_manifest()
        classified = [
            (entry.method, entry.path)
            for entry in entries
            if entry.transport is ManagementRouteTransport.WEBSOCKET
        ]

        self.assertEqual(len(classified), len(set(classified)))
        self.assertEqual(set(classified), actual)

    def test_manifest_uses_closed_typed_permissions(self):
        for entry in management_route_manifest():
            self.assertIs(type(entry.permission), ManagementPermission)
            self.assertIs(type(entry.transport), ManagementRouteTransport)

    def test_sensitive_routes_have_distinct_least_privilege_permissions(self):
        expected = {
            (
                "GET",
                "/api/credentials/configuration/{filename}",
            ): ManagementPermission.CREDENTIALS_READ,
            (
                "PATCH",
                "/api/credentials/configuration/{filename}",
            ): ManagementPermission.CREDENTIALS_MANAGE,
            ("GET", "/api/auth/keys"): ManagementPermission.ROOT_KEY_READ,
            ("POST", "/api/auth/keys/reset"): ManagementPermission.ROOT_KEY_ROTATE,
            ("POST", "/api/config/access"): ManagementPermission.CONFIGURATION_MANAGE,
            ("GET", "/api/credentials/download-all"): ManagementPermission.CREDENTIALS_EXPORT,
            ("GET", "/api/observability/routing"): ManagementPermission.DASHBOARD_READ,
            ("GET", "/api/providers/capabilities"): ManagementPermission.PROVIDERS_READ,
            ("GET", "/api/audit/export"): ManagementPermission.AUDIT_EXPORT,
            ("GET", "/api/traces/export"): ManagementPermission.TRACES_EXPORT,
            ("WEBSOCKET", "/api/logs/stream"): ManagementPermission.LOGS_READ,
            ("GET", "/api/identity/session"): ManagementPermission.IDENTITY_READ,
            ("POST", "/api/identity/identities"): ManagementPermission.IDENTITY_MANAGE,
            ("GET", "/api/identity/sessions"): ManagementPermission.SESSIONS_MANAGE,
            (
                "POST",
                "/api/identity/sessions/{session_reference}/revoke",
            ): ManagementPermission.SESSIONS_MANAGE,
            (
                "POST",
                "/api/identity/oidc-policy/advance",
            ): ManagementPermission.OIDC_MANAGE,
            ("GET", "/api/identity/recovery"): ManagementPermission.RECOVERY_MANAGE,
        }
        actual = {
            (entry.method, entry.path): entry.permission for entry in management_route_manifest()
        }

        for route, permission in expected.items():
            self.assertEqual(actual[route], permission)


class ManagementRouteAuthorizationMatrixTests(unittest.TestCase):
    def test_unknown_route_and_wrong_transport_fail_closed(self):
        owner = ManagementPrincipal.local_owner()

        with self.assertRaises(UnclassifiedManagementRoute):
            require_management_route(
                owner,
                transport=ManagementRouteTransport.HTTP,
                method="GET",
                path="/api/not-classified",
            )
        with self.assertRaises(UnclassifiedManagementRoute):
            require_management_route(
                owner,
                transport=ManagementRouteTransport.WEBSOCKET,
                method="GET",
                path="/api/logs/stream",
            )

    def test_untyped_route_inputs_fail_closed(self):
        with self.assertRaises(UnclassifiedManagementRoute):
            require_management_route(
                ManagementPrincipal.local_owner(),
                transport="http",
                method="GET",
                path="/api/config/get",
            )

    def test_owner_is_allowed_across_the_complete_manifest(self):
        owner = ManagementPrincipal.local_owner()

        for entry in management_route_manifest():
            with self.subTest(entry=entry):
                decision = require_management_route(
                    owner,
                    transport=entry.transport,
                    method=entry.method,
                    path=entry.path,
                )
                self.assertTrue(decision.allowed)

    def test_all_human_roles_match_the_generated_allow_deny_matrix(self):
        for role in ManagementRole:
            principal = ManagementPrincipal.oidc_user(
                issuer="https://idp.example",
                subject=f"{role.value}-1",
                role=role,
            )
            expected_permissions = permissions_for_role(role)
            for entry in management_route_manifest():
                with self.subTest(role=role, entry=entry):
                    if entry.permission in expected_permissions:
                        self.assertTrue(
                            require_management_route(
                                principal,
                                transport=entry.transport,
                                method=entry.method,
                                path=entry.path,
                            ).allowed
                        )
                    else:
                        with self.assertRaises(AuthorizationDenied):
                            require_management_route(
                                principal,
                                transport=entry.transport,
                                method=entry.method,
                                path=entry.path,
                            )

    def test_viewer_can_read_but_cannot_export_or_mutate(self):
        viewer = ManagementPrincipal.oidc_user(
            issuer="https://idp.example",
            subject="viewer-1",
            role=ManagementRole.VIEWER,
        )

        require_management_route(
            viewer,
            transport=ManagementRouteTransport.HTTP,
            method="GET",
            path="/api/config/get",
        )
        for method, path in (
            ("GET", "/api/auth/keys"),
            ("GET", "/api/credentials/download-all"),
            ("POST", "/api/config/save"),
            ("POST", "/api/auth/keys/reset"),
        ):
            with self.subTest(method=method, path=path), self.assertRaises(AuthorizationDenied):
                require_management_route(
                    viewer,
                    transport=ManagementRouteTransport.HTTP,
                    method=method,
                    path=path,
                )

    def test_legacy_read_key_keeps_every_existing_safe_http_route(self):
        reader = ManagementPrincipal.virtual_key("legacy-reader", scopes=("management:read",))

        for entry in management_route_manifest():
            if entry.transport is not ManagementRouteTransport.HTTP:
                continue
            with self.subTest(entry=entry):
                if entry.method in {"GET", "HEAD", "OPTIONS"} and not entry.path.startswith(
                    "/api/identity/"
                ):
                    self.assertTrue(
                        require_management_route(
                            reader,
                            transport=entry.transport,
                            method=entry.method,
                            path=entry.path,
                        ).allowed
                    )
                else:
                    with self.assertRaises(AuthorizationDenied):
                        require_management_route(
                            reader,
                            transport=entry.transport,
                            method=entry.method,
                            path=entry.path,
                        )

    def test_legacy_write_key_keeps_every_existing_http_route(self):
        writer = ManagementPrincipal.virtual_key(
            "legacy-writer",
            scopes=("management:read", "management:write"),
        )

        for entry in management_route_manifest():
            if entry.transport is ManagementRouteTransport.HTTP:
                with self.subTest(entry=entry):
                    if entry.path.startswith("/api/identity/"):
                        with self.assertRaises(AuthorizationDenied):
                            require_management_route(
                                writer,
                                transport=entry.transport,
                                method=entry.method,
                                path=entry.path,
                            )
                    else:
                        self.assertTrue(
                            require_management_route(
                                writer,
                                transport=entry.transport,
                                method=entry.method,
                                path=entry.path,
                            ).allowed
                        )

    def test_legacy_keys_gain_no_future_identity_permissions(self):
        writer = ManagementPrincipal.virtual_key(
            "legacy-writer",
            scopes=("management:read", "management:write"),
        )

        self.assertNotIn(ManagementPermission.IDENTITY_READ, writer.permissions)
        self.assertNotIn(ManagementPermission.IDENTITY_MANAGE, writer.permissions)
        self.assertNotIn(ManagementPermission.OWNERS_MANAGE, writer.permissions)
        self.assertNotIn(ManagementPermission.RECOVERY_MANAGE, writer.permissions)


if __name__ == "__main__":
    unittest.main()
