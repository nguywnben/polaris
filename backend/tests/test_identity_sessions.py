import asyncio
import base64
import dataclasses
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (
    IdentityRecord,
    ManagedIdentity,
    ManagementPrincipal,
    ManagementRole,
    OidcRoleSource,
    ResolvedOidcIdentity,
    RoleBindingRecord,
    RoleBindingSource,
)
from core.identity.sessions import (
    CoordinatedSessionStore,
    InProcessSessionStore,
    SessionAuthenticationMethod,
    SessionExpired,
    SessionNotFound,
    SessionPolicy,
    SessionService,
    SessionStale,
    render_management_session_metrics,
)
from core.state_store import InMemoryStateStore
from core.storage.identity_sqlite import SQLiteIdentityRepository
from tests.support import workspace_temp_directory


class FakeIdentityRepository:
    def __init__(self, owner: ManagedIdentity):
        self.owner = owner

    async def get_identity(self, identity_id: str):
        if self.owner is None:
            return None
        if identity_id != self.owner.identity.identity_id:
            return None
        return self.owner


class FakeSessionStorage:
    def __init__(self, owner: ManagedIdentity):
        self.config = {}
        self.repository = FakeIdentityRepository(owner)

    async def get_config(self, key, default=None):
        return self.config.get(key, default)

    async def set_config(self, key, value):
        self.config[key] = value
        return True

    async def create_identity_repository(self):
        return self.repository


class InProcessSessionStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.policy = SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900)
        self.store = InProcessSessionStore(
            hmac_key=b"s" * 32,
            policy=self.policy,
        )
        self.owner = ManagementPrincipal.local_owner()

    async def _issue(self, *, now: float = 1_000.0, epoch: int = 7):
        return await self.store.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=epoch,
            now=now,
        )

    async def test_issue_returns_256_bit_opaque_secret_but_stores_only_hmac_index(self):
        issued = await self._issue()

        self.assertRegex(issued.token, r"^ogs_[A-Za-z0-9_-]{43}$")
        raw = base64.urlsafe_b64decode(issued.token.removeprefix("ogs_") + "=")
        self.assertEqual(len(raw), 32)
        self.assertEqual(issued.session.principal, self.owner)
        self.assertEqual(issued.session.issued_at, 1_000.0)
        self.assertEqual(issued.session.last_seen_at, 1_000.0)
        self.assertEqual(issued.session.idle_expires_at, 1_300.0)
        self.assertEqual(issued.session.absolute_expires_at, 1_900.0)
        self.assertNotIn(issued.token, repr(self.store))
        self.assertNotIn(issued.token, repr(self.store._sessions))
        self.assertFalse(hasattr(issued.session, "token"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            issued.session.authorization_epoch = 8

    async def test_inventory_uses_bounded_non_secret_references_for_revocation(self):
        first = await self._issue(now=1_000.0)
        second = await self._issue(now=1_001.0)

        page = await self.store.list_active(limit=1, now=1_002.0)
        self.assertEqual(len(page), 1)
        self.assertRegex(page[0].reference, r"^ssr_[0-9a-f]{32}$")
        self.assertFalse(hasattr(page[0], "digest"))
        self.assertNotIn(first.token, repr(page))
        self.assertNotIn(second.token, repr(page))

        remaining = await self.store.list_active(
            limit=10,
            after_reference=page[0].reference,
            now=1_002.0,
        )
        self.assertEqual(len(remaining), 1)
        self.assertGreater(remaining[0].reference, page[0].reference)
        self.assertTrue(await self.store.revoke_reference(remaining[0].reference))
        self.assertFalse(await self.store.revoke_reference(remaining[0].reference))

    async def test_current_reference_is_derived_without_returning_digest(self):
        issued = await self._issue()

        reference = await self.store.reference_for_token(issued.token, now=1_001.0)

        self.assertRegex(reference, r"^ssr_[0-9a-f]{32}$")
        self.assertNotEqual(reference.removeprefix("ssr_"), issued.session.digest)

    async def test_resolve_slides_idle_expiry_without_extending_absolute_expiry(self):
        issued = await self._issue()

        resolved = await self.store.resolve(
            issued.token,
            current_authorization_epoch=7,
            now=1_250.0,
        )
        self.assertEqual(resolved.last_seen_at, 1_250.0)
        self.assertEqual(resolved.idle_expires_at, 1_550.0)
        self.assertEqual(resolved.absolute_expires_at, 1_900.0)

        await self.store.resolve(
            issued.token,
            current_authorization_epoch=7,
            now=1_500.0,
        )
        await self.store.resolve(
            issued.token,
            current_authorization_epoch=7,
            now=1_750.0,
        )
        resolved = await self.store.resolve(
            issued.token,
            current_authorization_epoch=7,
            now=1_850.0,
        )
        self.assertEqual(resolved.idle_expires_at, 1_900.0)

    async def test_idle_and_absolute_expiry_are_terminal(self):
        idle = await self._issue()

        with self.assertRaises(SessionExpired):
            await self.store.resolve(idle.token, current_authorization_epoch=7, now=1_300.0)
        with self.assertRaises(SessionNotFound):
            await self.store.resolve(idle.token, current_authorization_epoch=7, now=1_299.0)

        absolute = await self._issue(now=2_000.0)
        await self.store.resolve(
            absolute.token,
            current_authorization_epoch=7,
            now=2_250.0,
        )
        await self.store.resolve(
            absolute.token,
            current_authorization_epoch=7,
            now=2_500.0,
        )
        await self.store.resolve(
            absolute.token,
            current_authorization_epoch=7,
            now=2_750.0,
        )
        with self.assertRaises(SessionExpired):
            await self.store.resolve(
                absolute.token,
                current_authorization_epoch=7,
                now=2_900.0,
            )

    async def test_logout_revocation_and_authorization_epoch_change_block_replay(self):
        revoked = await self._issue()
        stale = await self._issue()

        self.assertTrue(await self.store.revoke(revoked.token))
        self.assertFalse(await self.store.revoke(revoked.token))
        with self.assertRaises(SessionNotFound):
            await self.store.resolve(
                revoked.token,
                current_authorization_epoch=7,
                now=1_001.0,
            )

        with self.assertRaises(SessionStale):
            await self.store.resolve(
                stale.token,
                current_authorization_epoch=8,
                now=1_001.0,
            )
        with self.assertRaises(SessionNotFound):
            await self.store.resolve(
                stale.token,
                current_authorization_epoch=7,
                now=1_001.0,
            )

    async def test_oidc_session_requires_both_identity_and_policy_authorization_epochs(self):
        principal = ManagementPrincipal.oidc_user(
            issuer="https://identity.example.com/tenant",
            subject="subject-1",
            role=ManagementRole.OPERATOR,
            role_source=OidcRoleSource.DIRECT_BINDING,
        )
        issued = await self.store.issue(
            principal=principal,
            authentication_method=SessionAuthenticationMethod.OIDC,
            authorization_epoch=7,
            oidc_policy_authorization_epoch=11,
            now=1_000.0,
        )

        inspected = await self.store.inspect(issued.token, now=1_001.0)
        self.assertEqual(inspected.oidc_policy_authorization_epoch, 11)
        resolved = await self.store.resolve(
            issued.token,
            current_authorization_epoch=7,
            current_oidc_policy_authorization_epoch=11,
            now=1_001.0,
        )
        self.assertEqual(resolved.principal, principal)

        for identity_epoch, policy_epoch in ((8, 11), (7, 12), (7, None)):
            replay = await self.store.issue(
                principal=principal,
                authentication_method=SessionAuthenticationMethod.OIDC,
                authorization_epoch=7,
                oidc_policy_authorization_epoch=11,
                now=1_010.0,
            )
            with self.subTest(identity_epoch=identity_epoch, policy_epoch=policy_epoch):
                with self.assertRaises(SessionStale):
                    await self.store.resolve(
                        replay.token,
                        current_authorization_epoch=identity_epoch,
                        current_oidc_policy_authorization_epoch=policy_epoch,
                        now=1_011.0,
                    )

    async def test_session_method_and_policy_epoch_shape_cannot_be_forged(self):
        oidc = ManagementPrincipal.oidc_user(
            issuer="https://identity.example.com/tenant",
            subject="subject-1",
            role=ManagementRole.VIEWER,
        )
        with self.assertRaises(ValueError):
            await self.store.issue(
                principal=oidc,
                authentication_method=SessionAuthenticationMethod.OIDC,
                authorization_epoch=1,
                now=1_000.0,
            )
        with self.assertRaises(ValueError):
            await self.store.issue(
                principal=self.owner,
                authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
                authorization_epoch=1,
                oidc_policy_authorization_epoch=1,
                now=1_000.0,
            )

    async def test_rotation_is_atomic_and_invalidates_the_old_secret(self):
        issued = await self._issue()

        rotated = await self.store.rotate(
            issued.token,
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=8,
            now=1_100.0,
        )

        self.assertNotEqual(rotated.token, issued.token)
        self.assertEqual(rotated.session.authorization_epoch, 8)
        with self.assertRaises(SessionNotFound):
            await self.store.resolve(
                issued.token,
                current_authorization_epoch=7,
                now=1_101.0,
            )
        self.assertEqual(
            (
                await self.store.resolve(
                    rotated.token,
                    current_authorization_epoch=8,
                    now=1_101.0,
                )
            ).principal,
            self.owner,
        )

    async def test_only_one_concurrent_rotation_can_consume_a_session(self):
        issued = await self._issue()

        results = await asyncio.gather(
            *(
                self.store.rotate(
                    issued.token,
                    principal=self.owner,
                    authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
                    authorization_epoch=7,
                    now=1_010.0,
                )
                for _ in range(8)
            ),
            return_exceptions=True,
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, SessionNotFound)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 7)

    async def test_principal_revocation_is_scoped_and_concurrency_safe(self):
        owner_sessions = [await self._issue(now=1_000.0 + index) for index in range(4)]
        other_owner = ManagementPrincipal.local_owner("secondary-local-owner")
        other = await self.store.issue(
            principal=other_owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=1_000.0,
        )

        counts = await asyncio.gather(*(self.store.revoke_principal(self.owner) for _ in range(4)))

        self.assertEqual(sum(counts), 4)
        for issued in owner_sessions:
            with self.assertRaises(SessionNotFound):
                await self.store.resolve(
                    issued.token,
                    current_authorization_epoch=7,
                    now=1_100.0,
                )
        self.assertEqual(
            (
                await self.store.resolve(
                    other.token,
                    current_authorization_epoch=7,
                    now=1_100.0,
                )
            ).principal,
            other_owner,
        )

    async def test_malformed_and_attacker_chosen_values_never_become_sessions(self):
        for token in ("", "chosen-by-attacker", "ogs_short", "x" * 10_000):
            with self.subTest(token=token[:20]):
                with self.assertRaises(SessionNotFound):
                    await self.store.resolve(
                        token,
                        current_authorization_epoch=7,
                        now=1_000.0,
                    )

        issued = await self._issue()
        self.assertTrue(re.fullmatch(r"ogs_[A-Za-z0-9_-]{43}", issued.token))

    async def test_capacity_is_bounded_and_evicts_the_least_recently_used_session(self):
        store = InProcessSessionStore(
            hmac_key=b"c" * 32,
            policy=SessionPolicy(
                idle_ttl_seconds=300,
                absolute_ttl_seconds=900,
                max_active_sessions=2,
            ),
        )
        first = await store.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=1_000.0,
        )
        second = await store.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=1_001.0,
        )
        await store.resolve(first.token, current_authorization_epoch=7, now=1_010.0)

        third = await store.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=1_011.0,
        )

        self.assertEqual(len(store._sessions), 2)
        await store.resolve(first.token, current_authorization_epoch=7, now=1_012.0)
        await store.resolve(third.token, current_authorization_epoch=7, now=1_012.0)
        with self.assertRaises(SessionNotFound):
            await store.resolve(second.token, current_authorization_epoch=7, now=1_012.0)


class CoordinatedSessionStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = 1_000.0
        self.backend = InMemoryStateStore(clock=lambda: self.clock)
        self.policy = SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900)
        self.first = CoordinatedSessionStore(
            self.backend,
            hmac_key=b"c" * 32,
            policy=self.policy,
        )
        self.second = CoordinatedSessionStore(
            self.backend,
            hmac_key=b"c" * 32,
            policy=self.policy,
        )
        self.owner = ManagementPrincipal.local_owner()

    async def test_two_instances_share_issue_resolve_rotation_and_revocation(self):
        issued = await self.first.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=self.clock,
        )
        resolved = await self.second.resolve(
            issued.token,
            current_authorization_epoch=7,
            now=self.clock,
        )
        self.assertEqual(resolved.principal, self.owner)

        rotated = await self.second.rotate(
            issued.token,
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=8,
            now=self.clock,
        )
        with self.assertRaises(SessionNotFound):
            await self.first.resolve(
                issued.token,
                current_authorization_epoch=7,
                now=self.clock,
            )
        self.assertTrue(await self.first.revoke(rotated.token))
        with self.assertRaises(SessionNotFound):
            await self.second.resolve(
                rotated.token,
                current_authorization_epoch=8,
                now=self.clock,
            )

    async def test_authenticated_payload_and_principal_revocation_are_fail_closed(self):
        issued = await self.first.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=self.clock,
        )
        state = self.backend._security_sessions[issued.session.digest]
        self.assertNotIn(b"local-owner", state.payload)
        self.backend._security_sessions[issued.session.digest] = dataclasses.replace(
            state,
            payload=state.payload[:-1] + bytes([state.payload[-1] ^ 1]),
        )
        with self.assertRaises(SessionNotFound):
            await self.second.resolve(
                issued.token,
                current_authorization_epoch=7,
                now=self.clock,
            )

        source = await self.first.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=self.clock,
        )
        target = await self.first.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=7,
            now=self.clock,
        )
        source_state = self.backend._security_sessions[source.session.digest]
        target_state = self.backend._security_sessions[target.session.digest]
        self.backend._security_sessions[target.session.digest] = dataclasses.replace(
            target_state,
            payload=source_state.payload,
        )
        with self.assertRaises(SessionNotFound):
            await self.second.resolve(
                target.token,
                current_authorization_epoch=7,
                now=self.clock,
            )
        self.assertTrue(await self.first.revoke(source.token))

        sessions = [
            await self.first.issue(
                principal=self.owner,
                authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
                authorization_epoch=7,
                now=self.clock,
            )
            for _ in range(2)
        ]
        self.assertEqual(await self.second.revoke_principal(self.owner), 2)
        for session in sessions:
            with self.assertRaises(SessionNotFound):
                await self.first.resolve(
                    session.token,
                    current_authorization_epoch=7,
                    now=self.clock,
                )


class SessionPolicyTests(unittest.TestCase):
    def test_policy_is_bounded_and_absolute_ttl_must_exceed_idle_ttl(self):
        self.assertEqual(
            SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900).idle_ttl_seconds,
            300,
        )
        for values in (
            (299, 900),
            (300, 299),
            (900, 900),
            (300, 2_592_001),
            (True, 900),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SessionPolicy(idle_ttl_seconds=values[0], absolute_ttl_seconds=values[1])

        for capacity in (0, 100_001, True):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                SessionPolicy(
                    idle_ttl_seconds=300,
                    absolute_ttl_seconds=900,
                    max_active_sessions=capacity,
                )


class SessionServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        now = datetime(2026, 8, 27, tzinfo=timezone.utc)
        self.owner = ManagedIdentity(
            identity=IdentityRecord.local_owner(now=now),
            binding=RoleBindingRecord.local_owner(now=now),
        )
        self.storage = FakeSessionStorage(self.owner)

    async def test_service_persists_only_a_master_key_and_uses_durable_owner_epoch(self):
        service = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )

        issued = await service.issue_local_owner(now=1_000.0)
        resolved = await service.resolve(issued.token, now=1_001.0)

        self.assertEqual(resolved.principal, ManagementPrincipal.local_owner())
        self.assertEqual(resolved.authorization_epoch, 1)
        self.assertIsInstance(service._store, CoordinatedSessionStore)
        self.assertEqual(len(self.storage.config), 1)
        serialized_config = repr(self.storage.config)
        self.assertNotIn(issued.token, serialized_config)
        self.assertNotIn(issued.token, repr(service))

    async def test_factories_with_shared_hmac_key_interoperate_without_storage_write(self) -> None:
        coordination = InMemoryStateStore(clock=lambda: 1_000.0)

        async def reject_non_atomic_write(key, value):
            raise AssertionError("coordinated session keys must not race through storage")

        self.storage.set_config = reject_non_atomic_write
        first, second = await asyncio.gather(
            SessionService.create(
                self.storage,
                coordination=coordination,
                hmac_key=b"h" * 32,
            ),
            SessionService.create(
                self.storage,
                coordination=coordination,
                hmac_key=b"h" * 32,
            ),
        )

        issued = await first.issue_local_owner(now=1_000.0)
        resolved = await second.resolve(issued.token, now=1_001.0)
        self.assertEqual(resolved.principal, ManagementPrincipal.local_owner())
        self.assertEqual(self.storage.config, {})

    async def test_factory_preserves_selected_nondefault_coordination_epoch(self):
        coordination = InMemoryStateStore(clock=lambda: 1_000.0)
        await coordination.advance_epoch(1, "session-advance-epoch")
        await coordination.mark_epoch_ready(2, "session-mark-ready")
        service = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
            coordination=coordination,
            fencing_epoch=2,
        )

        issued = await service.issue_local_owner(now=1_000.0)
        resolved = await service.resolve(issued.token, now=1_001.0)

        self.assertEqual(resolved.principal, ManagementPrincipal.local_owner())
        self.assertEqual(service._store._fencing_epoch, 2)

    async def test_epoch_advance_prevents_prior_session_resurrection(self):
        coordination = InMemoryStateStore(clock=lambda: 1_000.0)
        first = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
            coordination=coordination,
            fencing_epoch=1,
        )
        issued = await first.issue_local_owner(now=1_000.0)

        await coordination.advance_epoch(1, "session-invalidation-advance")
        await coordination.mark_epoch_ready(2, "session-invalidation-ready")
        second = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
            coordination=coordination,
            fencing_epoch=2,
        )

        with self.assertRaises(SessionNotFound):
            await second.resolve(issued.token, now=1_001.0)

    async def test_factory_rejects_invalid_coordination_epoch_before_persisting_key(self):
        with self.assertRaises(ValueError):
            await SessionService.create(
                self.storage,
                policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
                fencing_epoch=True,
            )

        self.assertEqual(self.storage.config, {})

    async def test_factory_rejects_invalid_explicit_hmac_key_without_storage_write(self):
        for invalid in (b"", b"h" * 31, b"h" * 33, bytearray(b"h" * 32)):
            with self.subTest(invalid_type=type(invalid).__name__, length=len(invalid)):
                with self.assertRaises(ValueError):
                    await SessionService.create(self.storage, hmac_key=invalid)

        self.assertEqual(self.storage.config, {})

    async def test_password_rotation_revokes_every_owner_session_before_reissue(self):
        service = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        sessions = [await service.issue_local_owner(now=1_000.0 + i) for i in range(3)]

        self.assertEqual(await service.revoke_local_owner_sessions(), 3)
        replacement = await service.issue_local_owner(now=1_100.0)

        for issued in sessions:
            with self.assertRaises(SessionNotFound):
                await service.resolve(issued.token, now=1_101.0)
        self.assertEqual(
            (await service.resolve(replacement.token, now=1_101.0)).principal,
            ManagementPrincipal.local_owner(),
        )

    async def test_identity_epoch_change_invalidates_session_without_explicit_revoke(self):
        service = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        issued = await service.issue_local_owner(now=1_000.0)
        changed = dataclasses.replace(self.owner.identity, authorization_epoch=2, revision=2)
        self.storage.repository.owner = dataclasses.replace(self.owner, identity=changed)

        with self.assertRaises(SessionStale):
            await service.resolve(issued.token, now=1_001.0)

    async def test_missing_or_disabled_durable_identity_fails_closed(self):
        service = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        self.storage.repository.owner = None

        with self.assertRaises(RuntimeError):
            await service.issue_local_owner(now=1_000.0)

    async def test_corrupt_persisted_master_key_fails_initialization(self):
        self.storage.config["_internal_session_master_key_v1"] = "not-a-valid-key"

        with self.assertRaises(RuntimeError):
            await SessionService.create(
                self.storage,
                policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
            )

    async def test_operational_metrics_are_fixed_cardinality_and_secret_free(self):
        service = await SessionService.create(
            self.storage,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        issued = await service.issue_local_owner(now=1_000.0)
        await service.resolve(issued.token, now=1_001.0)
        await service.revoke(issued.token)
        with self.assertRaises(SessionNotFound):
            await service.resolve(issued.token, now=1_002.0)

        rendered = render_management_session_metrics()
        self.assertIn('action="issue",outcome="succeeded"', rendered)
        self.assertIn('action="resolve",outcome="not_found"', rendered)
        self.assertIn('action="revoke",outcome="succeeded"', rendered)
        self.assertNotIn(issued.token, rendered)
        self.assertNotIn("local-owner", rendered)


class OidcSessionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        temp_path = self.temp_dir.__enter__()
        self.addCleanup(self.temp_dir.__exit__, None, None, None)
        self.temp_path = Path(temp_path)
        self.repository = SQLiteIdentityRepository(self.temp_path / "identity.db")
        await self.repository.initialize()
        self.store = InProcessSessionStore(
            hmac_key=b"o" * 32,
            policy=SessionPolicy(idle_ttl_seconds=300, absolute_ttl_seconds=900),
        )
        self.service = SessionService(self.store, identity_repository=self.repository)

    async def _resolved(
        self,
        *,
        subject="subject-1",
        source=RoleBindingSource.DIRECT_BINDING,
    ):
        managed = await self.repository.create_oidc_identity(
            issuer="https://identity.example.com/tenant",
            subject=subject,
            role=ManagementRole.OPERATOR,
            source=source,
        )
        policy = await self.repository.get_oidc_policy_revision()
        return ResolvedOidcIdentity(
            principal=ManagementPrincipal.oidc_user(
                issuer=managed.identity.issuer,
                subject=managed.identity.subject,
                role=managed.binding.role,
                role_source=(
                    OidcRoleSource.DIRECT_BINDING
                    if source is RoleBindingSource.DIRECT_BINDING
                    else OidcRoleSource.CLAIM_MAPPING
                ),
            ),
            identity_id=managed.identity.identity_id,
            identity_authorization_epoch=managed.identity.authorization_epoch,
            binding_revision=managed.binding.revision,
            policy_revision=policy.revision,
            policy_authorization_epoch=policy.authorization_epoch,
        )

    async def test_service_issues_and_resolves_an_exact_oidc_principal(self):
        resolved = await self._resolved()

        issued = await self.service.issue_oidc(resolved, now=1_000.0)
        session = await self.service.resolve(issued.token, now=1_001.0)

        self.assertEqual(session.principal, resolved.principal)
        self.assertIs(session.authentication_method, SessionAuthenticationMethod.OIDC)
        self.assertEqual(session.oidc_policy_authorization_epoch, 1)

    async def test_identity_disable_role_change_and_policy_revision_revoke_oidc_sessions(self):
        for mutation in ("disable", "role", "policy"):
            with self.subTest(mutation=mutation):
                resolved = await self._resolved(subject=f"subject-{mutation}")
                issued = await self.service.issue_oidc(resolved, now=1_000.0)
                managed = await self.repository.get_identity(resolved.identity_id)
                if mutation == "disable":
                    await self.repository.set_identity_enabled(
                        identity_id=resolved.identity_id,
                        enabled=False,
                        expected_revision=managed.identity.revision,
                    )
                elif mutation == "role":
                    await self.repository.set_role(
                        identity_id=resolved.identity_id,
                        role=ManagementRole.VIEWER,
                        source=RoleBindingSource.DIRECT_BINDING,
                        expected_revision=managed.binding.revision,
                    )
                else:
                    await self.repository.advance_oidc_policy_revision(expected_revision=1)

                with self.assertRaises(SessionStale):
                    await self.service.resolve(issued.token, now=1_001.0)


if __name__ == "__main__":
    unittest.main()
