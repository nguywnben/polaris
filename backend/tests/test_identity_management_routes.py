"""Contract tests for the bounded enterprise identity/session management API."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (
    IdentityRecord,
    IdentityRevisionConflict,
    ManagedIdentity,
    ManagementPrincipal,
    ManagementRole,
    OidcPolicyRevisionRecord,
    RoleBindingRecord,
    RoleBindingSource,
)
from core.identity.sessions import (
    InProcessSessionStore,
    SessionAuthenticationMethod,
    SessionPolicy,
    SessionService,
)
from core.management_audit import classify_management_mutation
from core.panel.identity_routes import (
    AdvanceOidcPolicyRequest,
    CreateIdentityRequest,
    SetIdentityEnabledRequest,
    SetRoleBindingRequest,
    _management_context,
    _ManagementContext,
    advance_oidc_policy,
    create_identity,
    get_current_session,
    get_oidc_policy,
    get_recovery_status,
    list_identities,
    list_sessions,
    revoke_session,
    set_identity_enabled,
    set_role_binding,
)
from core.utils import _VerifiedPanelToken

NOW = datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)


def _owner() -> ManagedIdentity:
    return ManagedIdentity(
        identity=IdentityRecord.local_owner(now=NOW),
        binding=RoleBindingRecord.local_owner(now=NOW),
    )


def _oidc(
    *,
    identity_id: str = "idn_0123456789abcdef0123456789abcdef",
    binding_id: str = "rbd_0123456789abcdef0123456789abcdef",
    role: ManagementRole = ManagementRole.VIEWER,
) -> ManagedIdentity:
    return ManagedIdentity(
        identity=IdentityRecord.oidc_user(
            identity_id=identity_id,
            issuer="https://idp.example/tenant",
            subject="subject-123",
            now=NOW,
        ),
        binding=RoleBindingRecord.oidc_user(
            binding_id=binding_id,
            identity_id=identity_id,
            role=role,
            source=RoleBindingSource.DIRECT_BINDING,
            now=NOW,
        ),
    )


class IdentityManagementRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.owner = _owner()
        self.repository = AsyncMock()
        self.repository.get_identity.return_value = self.owner
        self.repository.get_identity_by_oidc.return_value = _oidc()
        self.context = _ManagementContext(
            token="ogs_" + "A" * 43,
            principal=ManagementPrincipal.local_owner(),
        )

    async def test_identity_page_is_bounded_cursor_based_and_typed(self):
        first = self.owner
        second = _oidc()
        self.repository.list_identities.return_value = [first, second]

        with patch(
            "core.panel.identity_routes._identity_repository",
            new=AsyncMock(return_value=self.repository),
        ):
            page = await list_identities(self.context, page_size=1, cursor=None)

        self.assertEqual(page.page_size, 1)
        self.assertTrue(page.has_more)
        self.assertIsNotNone(page.next_cursor)
        self.assertEqual(page.identities[0].identity_id, "local-owner")
        self.assertFalse(hasattr(page, "token"))
        self.repository.list_identities.assert_awaited_once()
        self.assertEqual(self.repository.list_identities.await_args.kwargs["limit"], 2)

    async def test_security_admin_cannot_assign_owner_through_identity_manage(self):
        principal = ManagementPrincipal.oidc_user(
            issuer="https://idp.example/tenant",
            subject="security-admin",
            role=ManagementRole.SECURITY_ADMIN,
        )
        context = _ManagementContext(token="ogs_" + "B" * 43, principal=principal)

        with self.assertRaises(HTTPException) as raised:
            await create_identity(
                CreateIdentityRequest(
                    issuer="https://idp.example/tenant",
                    subject="new-owner",
                    role=ManagementRole.OWNER,
                ),
                context,
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.repository.create_oidc_identity.assert_not_awaited()

    async def test_enablement_and_role_changes_revoke_old_principal_sessions(self):
        existing = _oidc(role=ManagementRole.OPERATOR)
        disabled = ManagedIdentity(
            identity=IdentityRecord(
                **{
                    **existing.identity.to_record(),
                    "principal_type": existing.identity.principal_type,
                    "enabled": False,
                    "revision": 2,
                    "authorization_epoch": 2,
                }
            ),
            binding=existing.binding,
        )
        service = AsyncMock()
        self.repository.get_identity.return_value = existing
        self.repository.set_identity_enabled.return_value = disabled
        self.repository.set_role.return_value = existing

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch("core.panel.identity_routes.get_session_service", return_value=service),
        ):
            await set_identity_enabled(
                SetIdentityEnabledRequest(enabled=False, expected_revision=1),
                self.context,
                identity_id=existing.identity.identity_id,
            )
            await set_role_binding(
                SetRoleBindingRequest(role=ManagementRole.VIEWER, expected_revision=1),
                self.context,
                identity_id=existing.identity.identity_id,
            )

        self.assertEqual(service.revoke_principal.await_count, 2)

    async def test_stale_mutation_revision_returns_generic_conflict(self):
        existing = _oidc()
        self.repository.get_identity.return_value = existing
        self.repository.set_identity_enabled.side_effect = IdentityRevisionConflict(
            "database detail that must not escape"
        )

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            await set_identity_enabled(
                SetIdentityEnabledRequest(enabled=False, expected_revision=1),
                self.context,
                identity_id=existing.identity.identity_id,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, "Management identity revision conflict.")
        self.assertNotIn("database detail", raised.exception.detail)

    async def test_current_session_and_inventory_never_return_bearer_or_digest(self):
        store = InProcessSessionStore(
            hmac_key=b"s" * 32,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        issued = await store.issue(
            principal=ManagementPrincipal.local_owner(),
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=1,
            now=1_000.0,
        )
        service = SessionService(store, identity_repository=self.repository)
        context = _ManagementContext(token=issued.token, principal=issued.session.principal)

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch("core.panel.identity_routes.get_session_service", return_value=service),
            patch("core.panel.identity_routes.time.time", return_value=1_001.0),
        ):
            current = await get_current_session(context)
            inventory = await list_sessions(context, page_size=10, cursor=None)

        serialized = current.model_dump_json() + inventory.model_dump_json()
        self.assertNotIn(issued.token, serialized)
        self.assertNotIn(issued.session.digest, serialized)
        self.assertRegex(current.session.reference, r"^ssr_[0-9a-f]{32}$")
        self.assertTrue(current.session.current)

    async def test_verified_token_wrapper_is_normalized_before_session_lookup(self):
        store = InProcessSessionStore(
            hmac_key=b"s" * 32,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        issued = await store.issue(
            principal=ManagementPrincipal.local_owner(),
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=1,
            now=1_000.0,
        )
        service = SessionService(store, identity_repository=self.repository)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/identity/session",
                "headers": [],
            }
        )
        request.state.management_principal = issued.session.principal
        verified = _VerifiedPanelToken(issued.token, issued.session.principal)

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch("core.panel.identity_routes.get_session_service", return_value=service),
            patch("core.panel.identity_routes.time.time", return_value=1_001.0),
        ):
            context = await _management_context(request, verified)
            current = await get_current_session(context)

        self.assertEqual(type(context.token), str)
        self.assertEqual(current.authentication_context, "opaque_session")
        self.assertTrue(current.session.current)

    async def test_legacy_migration_session_returns_no_synthetic_identifier(self):
        context = _ManagementContext(
            token="legacy-jwt-without-session-reference",
            principal=ManagementPrincipal.local_owner(),
        )
        service = AsyncMock()

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch("core.panel.identity_routes.get_session_service", return_value=service),
        ):
            response = await get_current_session(context)

        self.assertEqual(response.authentication_context, "legacy_session")
        self.assertIsNone(response.session)
        service.managed_for_token.assert_not_awaited()

    async def test_session_revocation_uses_reference_and_audit_target_is_constant(self):
        service = AsyncMock()
        service.revoke_reference.return_value = True
        reference = "ssr_" + "a" * 32

        with patch("core.panel.identity_routes.get_session_service", return_value=service):
            response = await revoke_session(self.context, session_reference=reference)

        self.assertTrue(response.revoked)
        service.revoke_reference.assert_awaited_once_with(reference)
        mutation = classify_management_mutation(
            "POST", f"/api/identity/sessions/{reference}/revoke"
        )
        self.assertEqual(mutation.target_identifier, "panel")
        self.assertNotIn(reference, mutation.target_identifier)

    async def test_oidc_policy_response_contains_only_configuration_markers(self):
        revision = OidcPolicyRevisionRecord.initial(now=NOW)
        self.repository.get_oidc_policy_revision.return_value = revision

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch.dict("os.environ", {"OIDC_ENABLED": "false"}, clear=True),
        ):
            response = await get_oidc_policy(self.context)

        payload = response.model_dump()
        self.assertEqual(payload["readiness"], "disabled")
        self.assertNotIn("client_secret", payload)
        self.assertNotIn("token", payload)

    async def test_policy_advance_uses_revision_cas_and_revokes_oidc_sessions(self):
        revision = OidcPolicyRevisionRecord(
            schema_version=1,
            revision=2,
            authorization_epoch=2,
            updated_at=NOW.isoformat(),
        )
        self.repository.advance_oidc_policy_revision.return_value = revision
        service = SimpleNamespace(revoke_oidc_sessions=AsyncMock(return_value=3))

        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch("core.panel.identity_routes.get_session_service", return_value=service),
        ):
            response = await advance_oidc_policy(
                AdvanceOidcPolicyRequest(expected_revision=1),
                self.context,
            )

        self.assertEqual(response.revoked_sessions, 3)
        self.repository.advance_oidc_policy_revision.assert_awaited_once_with(expected_revision=1)

    async def test_recovery_status_reports_the_effective_ingress_policy(self):
        with (
            patch(
                "core.panel.identity_routes._identity_repository",
                new=AsyncMock(return_value=self.repository),
            ),
            patch(
                "core.panel.identity_routes.config.has_password_configured",
                new=AsyncMock(return_value=True),
            ),
        ):
            with patch.dict("os.environ", {}, clear=True):
                remote = await get_recovery_status(self.context)
            with patch.dict("os.environ", {"PANEL_RECOVERY_LOCAL_ONLY": "true"}, clear=True):
                local = await get_recovery_status(self.context)

        self.assertEqual(remote.ingress_policy, "network_reachable")
        self.assertEqual(local.ingress_policy, "direct_loopback_only")
        self.assertTrue(remote.ready)


if __name__ == "__main__":
    unittest.main()
