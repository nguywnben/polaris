"""Authorization-safe OIDC identity resolution tests."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (  # noqa: E402
    InProcessSessionStore,
    ManagementRole,
    OidcIdentityResolutionError,
    OidcIdentityResolver,
    OidcRoleSource,
    RoleBindingSource,
    SessionPolicy,
    SessionService,
    SessionStale,
    VerifiedOidcIdToken,
    load_oidc_configuration,
)
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402
from core.storage.identity_sqlite import SQLiteIdentityRepository  # noqa: E402
from tests.support import workspace_temp_directory  # noqa: E402

NOW = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)
ISSUER = "https://identity.example.com/tenant"


def _configuration(*, mappings: str = "{}", revision: int = 1, epoch: int = 1):
    policy_revision = OidcPolicyRevisionRecord(
        schema_version=1,
        revision=revision,
        authorization_epoch=epoch,
        updated_at=NOW.isoformat(),
    )
    return load_oidc_configuration(
        policy_revision,
        environ={
            "OIDC_ENABLED": "true",
            "OIDC_ISSUER": ISSUER,
            "OIDC_CLIENT_ID": "polaris",
            "OIDC_CLIENT_SECRET": "enterprise-client-secret",
            "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
            "OIDC_ROLE_MAPPINGS": mappings,
        },
    )


def _token(*, subject: str = "subject-1", groups: tuple[str, ...] = (), revision: int = 1):
    return VerifiedOidcIdToken(
        issuer=ISSUER,
        subject=subject,
        audiences=("polaris",),
        authorized_party=None,
        expires_at=2_000_000_000,
        issued_at=1_999_999_900,
        not_before=None,
        nonce="nonce",
        username=None,
        display_name=None,
        email=None,
        groups=groups,
        userinfo_subject_validated=False,
        policy_revision=revision,
        jwks_generation=1,
    )


class OidcIdentityResolverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        temp_path = self.temp_dir.__enter__()
        self.addCleanup(self.temp_dir.__exit__, None, None, None)
        self.repository = SQLiteIdentityRepository(
            Path(temp_path) / "identity.db", clock=lambda: NOW
        )
        await self.repository.initialize()

    async def test_direct_exact_subject_binding_wins_over_claims(self):
        await self.repository.create_oidc_identity(
            issuer=ISSUER,
            subject="Subject-Case-Sensitive",
            role=ManagementRole.SECURITY_ADMIN,
            source=RoleBindingSource.DIRECT_BINDING,
        )
        resolver = OidcIdentityResolver(
            _configuration(mappings='{"operators":"operator","viewers":"viewer"}').policy,
            self.repository,
        )

        resolved = await resolver.resolve(
            _token(subject="Subject-Case-Sensitive", groups=("operators", "viewers"))
        )

        self.assertIs(resolved.principal.role, ManagementRole.SECURITY_ADMIN)
        self.assertIs(resolved.principal.role_source, OidcRoleSource.DIRECT_BINDING)
        with self.assertRaises(OidcIdentityResolutionError):
            await resolver.resolve(_token(subject="subject-case-sensitive", groups=()))

    async def test_claim_mapping_creates_only_a_non_owner_allowlisted_identity(self):
        resolver = OidcIdentityResolver(
            _configuration(mappings='{"gateway-operators":"operator"}').policy,
            self.repository,
        )

        resolved = await resolver.resolve(_token(groups=("unrelated", "gateway-operators")))
        stored = await self.repository.get_identity_by_oidc(issuer=ISSUER, subject="subject-1")

        self.assertIs(resolved.principal.role, ManagementRole.OPERATOR)
        self.assertIs(resolved.principal.role_source, OidcRoleSource.CLAIM_MAPPING)
        self.assertIs(stored.binding.source, RoleBindingSource.CLAIM_MAPPING)
        self.assertEqual(stored.identity.identity_id, resolved.identity_id)

    async def test_missing_unmapped_malformed_and_ambiguous_claims_fail_closed(self):
        resolver = OidcIdentityResolver(
            _configuration(mappings='{"operators":"operator","viewers":"viewer"}').policy,
            self.repository,
        )

        for groups in ((), ("unknown",), ("operators", "viewers"), ("",), ("x" * 257,)):
            with self.subTest(groups=groups), self.assertRaises(OidcIdentityResolutionError):
                await resolver.resolve(
                    _token(subject=f"subject-{len(groups)}-{groups[:1]}", groups=groups)
                )

    async def test_same_role_matches_are_not_ambiguous(self):
        resolver = OidcIdentityResolver(
            _configuration(mappings='{"operators-a":"operator","operators-b":"operator"}').policy,
            self.repository,
        )

        resolved = await resolver.resolve(_token(groups=("operators-a", "operators-b")))

        self.assertIs(resolved.principal.role, ManagementRole.OPERATOR)

    async def test_claim_mapping_is_re_evaluated_and_downgraded_each_login(self):
        created = await self.repository.create_oidc_identity(
            issuer=ISSUER,
            subject="subject-1",
            role=ManagementRole.OPERATOR,
            source=RoleBindingSource.CLAIM_MAPPING,
        )
        resolver = OidcIdentityResolver(
            _configuration(mappings='{"viewers":"viewer"}').policy,
            self.repository,
        )

        resolved = await resolver.resolve(_token(groups=("viewers",)))
        stored = await self.repository.get_identity(created.identity.identity_id)

        self.assertIs(resolved.principal.role, ManagementRole.VIEWER)
        self.assertGreater(
            resolved.identity_authorization_epoch, created.identity.authorization_epoch
        )
        self.assertIs(stored.binding.role, ManagementRole.VIEWER)

    async def test_failed_claim_re_evaluation_advances_authorization_epoch(self):
        created = await self.repository.create_oidc_identity(
            issuer=ISSUER,
            subject="subject-1",
            role=ManagementRole.OPERATOR,
            source=RoleBindingSource.CLAIM_MAPPING,
        )
        resolver = OidcIdentityResolver(
            _configuration(mappings='{"operators":"operator"}').policy,
            self.repository,
        )
        initial = await resolver.resolve(_token(groups=("operators",)))
        session_service = SessionService(
            InProcessSessionStore(
                hmac_key=b"s" * 32,
                policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
            ),
            identity_repository=self.repository,
        )
        issued = await session_service.issue_oidc(initial, now=1_000.0)

        with self.assertRaises(OidcIdentityResolutionError):
            await resolver.resolve(_token(groups=("unmapped",)))

        stored = await self.repository.get_identity(created.identity.identity_id)
        self.assertGreater(
            stored.identity.authorization_epoch,
            created.identity.authorization_epoch,
        )
        self.assertIs(stored.binding.role, ManagementRole.OPERATOR)
        with self.assertRaises(SessionStale):
            await session_service.resolve(issued.token, now=1_001.0)

    async def test_disabled_identity_and_stale_policy_revision_cannot_authenticate(self):
        created = await self.repository.create_oidc_identity(
            issuer=ISSUER,
            subject="subject-1",
            role=ManagementRole.VIEWER,
        )
        await self.repository.set_identity_enabled(
            identity_id=created.identity.identity_id,
            enabled=False,
            expected_revision=created.identity.revision,
        )
        resolver = OidcIdentityResolver(_configuration().policy, self.repository)

        with self.assertRaises(OidcIdentityResolutionError):
            await resolver.resolve(_token())
        with self.assertRaises(OidcIdentityResolutionError):
            await resolver.resolve(_token(subject="other", revision=2))


if __name__ == "__main__":
    unittest.main()
