"""W4.2 contracts for typed management principals and permissions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (
    AuthorizationDenied,
    AuthorizationReason,
    InvalidPrincipal,
    ManagementPermission,
    ManagementPrincipal,
    ManagementRole,
    OidcRoleSource,
    PrincipalType,
    evaluate_permission,
    permission_scope,
    permissions_for_role,
    require_permission,
)

VIEWER = {
    ManagementPermission.DASHBOARD_READ,
    ManagementPermission.CONFIGURATION_READ,
    ManagementPermission.CREDENTIALS_READ,
    ManagementPermission.PROVIDERS_READ,
    ManagementPermission.QUALITY_READ,
    ManagementPermission.ACCESS_READ,
    ManagementPermission.AUDIT_READ,
    ManagementPermission.TRACES_READ,
    ManagementPermission.LOGS_READ,
    ManagementPermission.IDENTITY_READ,
}
OPERATOR = VIEWER | {
    ManagementPermission.CREDENTIALS_OPERATE,
    ManagementPermission.ROUTING_MANAGE,
    ManagementPermission.QUALITY_MANAGE,
    ManagementPermission.LOGS_MANAGE,
}
SECURITY_ADMIN = VIEWER | {
    ManagementPermission.CREDENTIALS_OPERATE,
    ManagementPermission.CREDENTIALS_MANAGE,
    ManagementPermission.CREDENTIALS_EXPORT,
    ManagementPermission.PROVIDERS_MANAGE,
    ManagementPermission.ACCESS_MANAGE,
    ManagementPermission.AUDIT_MANAGE,
    ManagementPermission.AUDIT_EXPORT,
    ManagementPermission.TRACES_MANAGE,
    ManagementPermission.TRACES_EXPORT,
    ManagementPermission.IDENTITY_MANAGE,
    ManagementPermission.SESSIONS_MANAGE,
    ManagementPermission.OIDC_MANAGE,
    ManagementPermission.BACKUP_EXPORT,
}
OWNER = (
    OPERATOR
    | SECURITY_ADMIN
    | {
        ManagementPermission.CONFIGURATION_MANAGE,
        ManagementPermission.ROOT_KEY_READ,
        ManagementPermission.ROOT_KEY_ROTATE,
        ManagementPermission.BACKUP_RESTORE,
        ManagementPermission.OWNERS_MANAGE,
        ManagementPermission.RECOVERY_MANAGE,
    }
)


class RolePermissionContractTests(unittest.TestCase):
    def test_four_roles_resolve_the_exact_immutable_permission_bundles(self):
        expected = {
            ManagementRole.VIEWER: VIEWER,
            ManagementRole.OPERATOR: OPERATOR,
            ManagementRole.SECURITY_ADMIN: SECURITY_ADMIN,
            ManagementRole.OWNER: OWNER,
        }

        for role, permissions in expected.items():
            with self.subTest(role=role):
                resolved = permissions_for_role(role)
                self.assertIsInstance(resolved, frozenset)
                self.assertEqual(resolved, permissions)

    def test_unknown_or_string_role_values_fail_closed(self):
        self.assertEqual(permissions_for_role("owner"), frozenset())
        self.assertEqual(permissions_for_role("security_admin"), frozenset())
        self.assertEqual(permissions_for_role(object()), frozenset())

    def test_role_sets_are_explicit_not_lexically_inferred(self):
        self.assertNotIn(
            ManagementPermission.CREDENTIALS_MANAGE,
            permissions_for_role(ManagementRole.OPERATOR),
        )
        self.assertNotIn(
            ManagementPermission.ROUTING_MANAGE,
            permissions_for_role(ManagementRole.SECURITY_ADMIN),
        )


class PrincipalContractTests(unittest.TestCase):
    def test_local_owner_adapter_has_the_owner_role(self):
        principal = ManagementPrincipal.local_owner("deployment-owner")

        self.assertEqual(principal.principal_type, PrincipalType.LOCAL_OWNER)
        self.assertEqual(principal.role, ManagementRole.OWNER)
        self.assertEqual(principal.permissions, frozenset(OWNER))
        self.assertEqual(principal.stable_identity, "deployment-owner")

    def test_oidc_identity_is_the_exact_issuer_subject_pair(self):
        principal = ManagementPrincipal.oidc_user(
            issuer="https://idp.example.com/tenant",
            subject="case-sensitive-subject",
            role=ManagementRole.OPERATOR,
        )

        self.assertEqual(
            principal.stable_identity,
            ("https://idp.example.com/tenant", "case-sensitive-subject"),
        )
        self.assertEqual(principal.role_source, OidcRoleSource.DIRECT_BINDING)

    def test_oidc_claim_adapter_cannot_assign_owner(self):
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal.oidc_user(
                issuer="https://idp.example.com",
                subject="subject",
                role=ManagementRole.OWNER,
                role_source=OidcRoleSource.CLAIM_MAPPING,
            )

    def test_malformed_and_spoofed_principals_fail_closed(self):
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal(
                principal_type="local_owner",
                principal_id="deployment-owner",
                role=ManagementRole.OWNER,
            )
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal(
                principal_type=PrincipalType.OIDC_USER,
                principal_id="",
                role=ManagementRole.VIEWER,
            )
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal.local_owner("x" * 129)

    def test_system_principal_has_no_request_permissions(self):
        principal = ManagementPrincipal.system("runtime-maintenance")

        self.assertEqual(principal.permissions, frozenset())
        decision = evaluate_permission(principal, ManagementPermission.DASHBOARD_READ)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, AuthorizationReason.SYSTEM_PRINCIPAL_DENIED)


class VirtualKeyCompatibilityTests(unittest.TestCase):
    def test_legacy_read_scope_grants_existing_reads_but_not_new_identity_read(self):
        principal = ManagementPrincipal.virtual_key(
            "vk_read",
            scopes=("inference:openai", "management:read"),
        )

        self.assertTrue(principal.uses_legacy_management_scope)
        self.assertIn(ManagementPermission.DASHBOARD_READ, principal.permissions)
        self.assertIn(ManagementPermission.AUDIT_READ, principal.permissions)
        self.assertNotIn(ManagementPermission.IDENTITY_READ, principal.permissions)
        self.assertNotIn(ManagementPermission.CONFIGURATION_MANAGE, principal.permissions)

    def test_legacy_write_scope_preserves_existing_routes_without_new_sensitive_rights(self):
        principal = ManagementPrincipal.virtual_key(
            "vk_write",
            scopes=("management:read", "management:write"),
        )

        self.assertIn(ManagementPermission.CONFIGURATION_MANAGE, principal.permissions)
        self.assertIn(ManagementPermission.ROOT_KEY_ROTATE, principal.permissions)
        self.assertIn(ManagementPermission.BACKUP_RESTORE, principal.permissions)
        for permission in (
            ManagementPermission.IDENTITY_READ,
            ManagementPermission.IDENTITY_MANAGE,
            ManagementPermission.SESSIONS_MANAGE,
            ManagementPermission.OIDC_MANAGE,
            ManagementPermission.OWNERS_MANAGE,
            ManagementPermission.RECOVERY_MANAGE,
        ):
            with self.subTest(permission=permission):
                self.assertNotIn(permission, principal.permissions)

    def test_granular_scope_grants_only_the_named_permission(self):
        scope = permission_scope(ManagementPermission.AUDIT_EXPORT)
        principal = ManagementPrincipal.virtual_key("vk_granular", scopes=(scope,))

        self.assertFalse(principal.uses_legacy_management_scope)
        self.assertEqual(principal.permissions, frozenset({ManagementPermission.AUDIT_EXPORT}))

    def test_malformed_management_scopes_fail_closed(self):
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal.virtual_key("vk_bad", scopes=("management:owner",))
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal.virtual_key("vk_bad", scopes=("management:write",))
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal.virtual_key(
                "vk_bad",
                scopes=("management:permission:not.real",),
            )
        with self.assertRaises(InvalidPrincipal):
            ManagementPrincipal.virtual_key(
                "vk_bad",
                scopes=(scope for scope in ("management:read",)),
            )


class AuthorizationDecisionTests(unittest.TestCase):
    def test_known_permission_returns_a_typed_allow_decision(self):
        principal = ManagementPrincipal.local_owner()

        decision = evaluate_permission(principal, ManagementPermission.DASHBOARD_READ)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, AuthorizationReason.ROLE_PERMISSION)
        self.assertEqual(decision.permission, ManagementPermission.DASHBOARD_READ)

    def test_string_or_unknown_permission_fails_closed(self):
        principal = ManagementPrincipal.local_owner()

        decision = evaluate_permission(principal, "ha.activate")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, AuthorizationReason.INVALID_PERMISSION)
        self.assertIsNone(decision.permission)

    def test_require_permission_raises_a_generic_typed_denial(self):
        principal = ManagementPrincipal.oidc_user(
            issuer="https://idp.example.com",
            subject="viewer-subject",
            role=ManagementRole.VIEWER,
        )

        with self.assertRaises(AuthorizationDenied) as context:
            require_permission(principal, ManagementPermission.CONFIGURATION_MANAGE)

        self.assertEqual(context.exception.reason, AuthorizationReason.PERMISSION_NOT_GRANTED)
        self.assertEqual(str(context.exception), "Management permission denied.")
        self.assertNotIn("viewer-subject", str(context.exception))


if __name__ == "__main__":
    unittest.main()
