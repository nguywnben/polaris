"""Reusable semantic assertions for every CoordinationStore implementation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from core.coordination import (
    CasRequest,
    CoordinationUnavailableError,
    EpochState,
    InvalidationRequest,
    QuotaCommitRequest,
    QuotaReservationRequest,
)

if TYPE_CHECKING:
    from core.coordination import CoordinationStore


class CoordinationStoreContract:
    """Mixin for async tests; implementations provide ``self.store``."""

    store: CoordinationStore

    async def install_admission_fence(self, **changes: object) -> None:
        namespace = getattr(self, "namespace", "production-east")
        namespace_digest = hashlib.sha256(namespace.encode()).hexdigest()
        binding = {
            "schema_version": 2,
            "deployment_id": "gateway-east-01",
            "namespace_digest": namespace_digest,
            "identifier_key_fingerprint": "a" * 64,
            "fencing_epoch": 1,
            "manifest_checksum": "b" * 64,
            "activation_record": "act_" + "c" * 32,
            "migration_plan_id": "dmg_" + "d" * 32,
            "migration_checkpoint_revision": 4,
            "migration_source_revision": 7,
            "migration_target_revision": 11,
            "migration_checkpoint_checksum": "e" * 64,
        }
        await self.store.set(
            "ha-runtime-binding-v1", json.dumps(binding, separators=(",", ":"), sort_keys=True)
        )
        record = {
            "schema_version": 3,
            "namespace_digest": namespace_digest,
            "epoch": 1,
            "reconciliation_receipt_checksum": None,
            "reconciliation_complete": False,
            **changes,
        }
        await self.store.set("ha-runtime-drain-v1", json.dumps(record))

    async def assert_admission_fence_contract(self) -> None:
        from core.security_coordination import (
            AttemptClearRequest,
            AttemptReservationRequest,
            OidcTransactionCreateRequest,
            SecurityAttemptCategory,
            SessionResolveRequest,
            SessionRevokeRequest,
            SessionRevokeTarget,
            SessionRotateRequest,
        )
        from tests.security_coordination_store_contract import SecurityCoordinationStoreContract

        issue = SecurityCoordinationStoreContract._issue("abc")
        await self.store.issue_security_session(issue)
        await self.install_admission_fence()
        operations = {
            "credential-reservation": lambda: self.store.compare_and_set(
                CasRequest("credential", 0, b"admit", 300, 1, "credential-admit")
            ),
            "replay-nonce": lambda: self.store.compare_and_set(
                CasRequest("nonce", 0, b"nonce", 300, 1, "nonce-admit")
            ),
            "rate-budget": lambda: self.store.reserve_quota(
                self._quota_request("fenced", key_id="fenced-key", operation_id="fenced-reserve")
            ),
            "security-issue": lambda: self.store.issue_security_session(
                SecurityCoordinationStoreContract._issue("def")
            ),
            "security-resolve": lambda: self.store.resolve_security_session(
                SessionResolveRequest(issue.session_digest, 300, 1, "fenced-resolve")
            ),
            "security-rotate": lambda: self.store.rotate_security_session(
                SessionRotateRequest(
                    issue.session_digest,
                    SecurityCoordinationStoreContract._issue("def", operation_id="fenced-rotate"),
                    1,
                    "fenced-rotate",
                )
            ),
            "security-revoke": lambda: self.store.revoke_security_sessions(
                SessionRevokeRequest(
                    SessionRevokeTarget.REFERENCE, issue.session_reference, 1, "fenced-revoke"
                )
            ),
            "security-attempt": lambda: self.store.reserve_security_attempt(
                AttemptReservationRequest(
                    SecurityAttemptCategory.LOGIN, "a" * 64, 10, 300, 1, "fenced-attempt"
                )
            ),
            "security-clear": lambda: self.store.clear_security_attempts(
                AttemptClearRequest(SecurityAttemptCategory.LOGIN, "a" * 64, 1, "fenced-clear")
            ),
            "oidc-create": lambda: self.store.create_oidc_transaction(
                OidcTransactionCreateRequest("a" * 64, "b" * 64, b"proof", 300, 1, "fenced-oidc")
            ),
            "invalidation": lambda: self.store.invalidate(
                InvalidationRequest("fenced-scope", 1, "fenced-invalidate")
            ),
        }
        for family, operation in operations.items():
            with self.subTest(family=family):
                with self.assertRaises(CoordinationUnavailableError):
                    await operation()

    async def assert_fence_linearization_and_settlement_contract(self) -> None:
        from core.coordination import CasSettlementTarget, CasSettlementTransition
        from core.routing_coordination import RoutingCoordinationAdapter
        from core.security_coordination import (
            OidcTransactionConsumeRequest,
            OidcTransactionCreateRequest,
        )

        routing = RoutingCoordinationAdapter(self.store, identifier_key=b"k" * 32, fencing_epoch=1)
        lease = await routing.acquire_credential("gemini", "credential.json", ttl_seconds=60)
        self.assertIsNotNone(lease)
        self.assertEqual(
            lease.admission.settlement_targets,
            (CasSettlementTarget(lease.record_key, CasSettlementTransition.UPDATE),),
        )
        self.assertTrue(
            (
                await self.store.create_oidc_transaction(
                    OidcTransactionCreateRequest(
                        "e" * 64, "f" * 64, b"pre-drain-proof", 300, 1, "pre-drain-oidc"
                    )
                )
            ).applied
        )
        for suffix in ("commit", "release"):
            self.assertTrue(
                (
                    await self.store.reserve_quota(
                        self._quota_request(suffix, key_id=suffix, operation_id=suffix)
                    )
                ).accepted
            )
        await self.install_admission_fence()
        # Every queued operation starts strictly after the drain write has linearized.
        outcomes = await asyncio.gather(
            *(
                self.store.reserve_quota(
                    self._quota_request(f"late-{i}", key_id="late", operation_id=f"late-{i}")
                )
                for i in range(12)
            ),
            return_exceptions=True,
        )
        self.assertTrue(
            all(isinstance(result, CoordinationUnavailableError) for result in outcomes)
        )
        with self.assertRaises(CoordinationUnavailableError):
            await routing.acquire_credential("gemini", "credential.json", ttl_seconds=60)
        self.assertTrue(await routing.release_credential(lease))
        self.assertFalse(await routing.release_credential(lease))
        commit = QuotaCommitRequest("commit", 1_001, 2, 0, False, operation_id="settle")
        self.assertTrue((await self.store.commit_quota(commit)).committed)
        self.assertTrue((await self.store.commit_quota(commit)).idempotent)
        self.assertTrue(
            await self.store.release_quota("release", now=1_001, operation_id="release-op")
        )
        self.assertFalse(
            await self.store.release_quota("release", now=1_001, operation_id="release-op")
        )
        consume = OidcTransactionConsumeRequest("e" * 64, "f" * 64, 1, "settle-oidc")
        self.assertTrue((await self.store.consume_oidc_transaction(consume)).consumed)
        replay = await self.store.consume_oidc_transaction(consume)
        self.assertFalse(replay.consumed)
        self.assertTrue(replay.idempotent)

    async def assert_device_authorization_settlement_contract(
        self, *, advance_device_clock: Callable[[float], Awaitable[None]]
    ) -> None:
        from core.coordination import CasSettlementTarget, CasSettlementTransition
        from core.device_authorization_coordination import (
            DeviceAuthorizationError,
            DeviceAuthorizationService,
        )

        tokens = iter(("A" * 43, "C" * 22, "B" * 43, "D" * 22, "E" * 43, "F" * 22))
        service = DeviceAuthorizationService(
            self.store,
            key=b"d" * 32,
            fencing_epoch=1,
            token_factory=lambda _size: next(tokens),
        )
        release_flow = await service.create(b"release-proof", ttl_seconds=300)
        release_claim = await service.claim(release_flow, lease_seconds=5)
        consume_flow = await service.create(b"consume-proof", ttl_seconds=300)
        consume_claim = await service.claim(consume_flow, lease_seconds=5)
        unsettled_flow = await service.create(b"unsettled-proof", ttl_seconds=300)
        unsettled_claim = await service.claim(unsettled_flow, lease_seconds=5)

        release_target = CasSettlementTarget(
            service._key(release_flow), CasSettlementTransition.UPDATE
        )
        self.assertEqual(release_claim.admission.settlement_targets, (release_target,))
        self.assertNotIn(release_claim.admission.operation_id, repr(release_claim))

        await self.install_admission_fence()
        with self.assertRaises(DeviceAuthorizationError):
            await service.release(replace(release_claim, lease_id="Z" * 22))
        with self.assertRaises(DeviceAuthorizationError):
            await service.release(
                replace(
                    release_claim,
                    admission=replace(
                        release_claim.admission,
                        operation_id="device-auth-claim-never-admitted",
                    ),
                )
            )

        await service.release(release_claim)
        await service.release(release_claim)
        with self.assertRaises(DeviceAuthorizationError):
            await service.release(
                replace(
                    release_claim,
                    admission=replace(
                        release_claim.admission,
                        operation_id="device-auth-claim-never-admitted",
                    ),
                )
            )
        await service.consume(consume_claim)
        await service.consume(consume_claim)
        await advance_device_clock(6)
        await service.release(release_claim)
        await service.consume(consume_claim)
        with self.assertRaises(DeviceAuthorizationError):
            await service.release(unsettled_claim)
        released = await self.store.read_cas(
            service._key(release_flow), epoch=service._fencing_epoch
        )
        consumed = await self.store.read_cas(
            service._key(consume_flow), epoch=service._fencing_epoch
        )
        self.assertEqual(
            service._decrypt(service._key(release_flow), released.payload)["status"], "ready"
        )
        self.assertEqual(
            service._decrypt(service._key(consume_flow), consumed.payload)["status"], "consumed"
        )

    async def assert_cas_settlement_proof_contract(self) -> None:
        from dataclasses import replace

        from core.coordination import (
            CasSettlementProof,
            CasSettlementTarget,
            CasSettlementTransition,
        )

        target = CasSettlementTarget("proof-root", CasSettlementTransition.UPDATE)
        admission = CasRequest(
            "proof-root",
            0,
            b"accepted",
            300,
            1,
            "proof-admission",
            settlement_targets=(target,),
        )
        self.assertTrue((await self.store.compare_and_set(admission)).applied)
        await self.install_admission_fence()
        settlement = CasRequest(
            "proof-root",
            1,
            b"settled",
            300,
            1,
            "proof-settle",
            settlement=CasSettlementProof(admission, target),
        )
        self.assertTrue((await self.store.compare_and_set(settlement)).applied)
        self.assertTrue((await self.store.compare_and_set(settlement)).idempotent)
        for proof in (
            replace(admission, operation_id="never-admitted"),
            replace(admission, payload=b"changed"),
            replace(admission, key="wrong-resource"),
        ):
            with self.subTest(proof=proof):
                with self.assertRaises(CoordinationUnavailableError):
                    await self.store.compare_and_set(
                        replace(
                            settlement,
                            operation_id="invalid-proof",
                            settlement=CasSettlementProof(proof, target),
                        )
                    )

    async def assert_cas_settlement_proof_cannot_be_reused_for_other_work(self) -> None:
        from core.coordination import (
            CasSettlementProof,
            CasSettlementTarget,
            CasSettlementTransition,
        )

        other = CasRequest("other-existing", 0, b"other", 300, 1, "other-admission")
        self.assertTrue((await self.store.compare_and_set(other)).applied)
        update_target = CasSettlementTarget("existing-work", CasSettlementTransition.UPDATE)
        create_target = CasSettlementTarget("other-existing", CasSettlementTransition.CREATE)
        admission = CasRequest(
            "existing-work",
            0,
            b"accepted",
            300,
            1,
            "existing-admission",
            settlement_targets=(update_target, create_target),
        )
        self.assertTrue((await self.store.compare_and_set(admission)).applied)
        await self.install_admission_fence()

        attempts = (
            CasRequest(
                "never-admitted-nonce",
                0,
                b"invented",
                300,
                1,
                "cross-key-settlement",
                settlement=CasSettlementProof(admission, update_target),
            ),
            CasRequest(
                "other-existing",
                1,
                b"wrong-transition",
                300,
                1,
                "wrong-transition-settlement",
                settlement=CasSettlementProof(admission, create_target),
            ),
        )
        for attempt in attempts:
            with self.subTest(key=attempt.key, expected_revision=attempt.expected_revision):
                with self.assertRaises(CoordinationUnavailableError):
                    await self.store.compare_and_set(attempt)

    async def assert_unknown_settlement_does_not_admit_replays(
        self, retained_replay_count: Callable[[], Awaitable[int]]
    ) -> None:
        from core.security_coordination import (
            OidcTransactionConsumeRequest,
            OidcTransactionCreateRequest,
        )

        await self.store.create_oidc_transaction(
            OidcTransactionCreateRequest("a" * 64, "b" * 64, b"retained", 300, 1, "known-oidc")
        )
        prior_denial = OidcTransactionConsumeRequest("a" * 64, "c" * 64, 1, "prior-mismatch")
        await self.store.consume_oidc_transaction(prior_denial)
        await self.install_admission_fence()
        before = await retained_replay_count()
        for _ in range(2):
            commit = await self.store.commit_quota(
                QuotaCommitRequest("unknown", 1_001, 2, 0, False, operation_id="unknown-commit")
            )
            self.assertFalse(commit.committed)
            self.assertFalse(commit.idempotent)
            self.assertFalse(
                await self.store.release_quota("unknown", now=1_001, operation_id="unknown-release")
            )
            for state, browser, reason in (
                ("d" * 64, "b" * 64, "not_found"),
                ("a" * 64, "c" * 64, "browser_mismatch"),
            ):
                result = await self.store.consume_oidc_transaction(
                    OidcTransactionConsumeRequest(state, browser, 1, "new-" + reason)
                )
                self.assertFalse(result.consumed)
                self.assertEqual(result.reason, reason)
                self.assertFalse(result.idempotent)
        self.assertEqual(await retained_replay_count(), before)
        self.assertTrue((await self.store.consume_oidc_transaction(prior_denial)).idempotent)
        self.assertTrue(
            (
                await self.store.consume_oidc_transaction(
                    OidcTransactionConsumeRequest("a" * 64, "b" * 64, 1, "valid-consume")
                )
            ).consumed
        )

    async def assert_settlement_replay_after_proof_expiry(
        self, advance: Callable[[float], Awaitable[None]]
    ) -> None:
        from dataclasses import replace

        from core.coordination import (
            CasSettlementProof,
            CasSettlementTarget,
            CasSettlementTransition,
        )

        target = CasSettlementTarget("short-proof", CasSettlementTransition.UPDATE)
        admission = CasRequest(
            "short-proof",
            0,
            b"admitted",
            1,
            1,
            "short-admit",
            settlement_targets=(target,),
        )
        await self.store.compare_and_set(admission)
        await self.install_admission_fence()
        settlement = CasRequest(
            "short-proof",
            1,
            b"settled",
            300,
            1,
            "long-settle",
            settlement=CasSettlementProof(admission, target),
        )
        self.assertTrue((await self.store.compare_and_set(settlement)).applied)
        await advance(2)
        self.assertTrue((await self.store.compare_and_set(settlement)).idempotent)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.compare_and_set(replace(settlement, operation_id="new-settlement"))

    async def assert_batch_settlement_during_drain_contract(self) -> None:
        from core.coordination import CasSettlementTarget, CasSettlementTransition
        from core.credential_batch_coordination import (
            BatchIdempotencyReplay,
            CredentialBatchCoordinationError,
            CredentialBatchCoordinationService,
        )

        batch = CredentialBatchCoordinationService(self.store, key=b"k" * 32, fencing_epoch=1)
        complete = await batch.reserve("batch-complete", "a" * 64)
        release = await batch.reserve("batch-release", "b" * 64)
        self.assertEqual(len(complete.admission.settlement_targets), 34)
        self.assertIn(
            CasSettlementTarget(complete.root_key, CasSettlementTransition.UPDATE),
            complete.admission.settlement_targets,
        )
        self.assertEqual(
            sum(
                target.transition is CasSettlementTransition.CREATE
                for target in complete.admission.settlement_targets
            ),
            32,
        )
        await self.install_admission_fence()
        with self.assertRaises(CredentialBatchCoordinationError):
            await batch.reserve("batch-new-admission", "c" * 64)
        await batch.complete(complete, 200, {"done": True})
        await batch.complete(complete, 200, {"done": True})
        self.assertEqual(
            await batch.lookup("batch-complete", "a" * 64),
            BatchIdempotencyReplay(200, {"done": True}),
        )
        with self.assertRaises(CredentialBatchCoordinationError):
            await batch.complete(complete, 200, {"changed": True})
        await batch.release(release)
        await batch.release(release)
        self.assertIsNone(await batch.lookup("batch-release", "b" * 64))

    async def assert_batch_partial_settlement_retry_contract(self) -> None:
        from unittest.mock import patch

        from core.credential_batch_coordination import (
            CredentialBatchCoordinationError,
            CredentialBatchCoordinationService,
        )

        batch = CredentialBatchCoordinationService(self.store, key=b"k" * 32, fencing_epoch=1)
        reservation = await batch.reserve("batch-crash", "a" * 64)
        await self.install_admission_fence()
        original = self.store.compare_and_set

        async def crash_after_chunk(request):
            result = await original(request)
            if "-chunk-" in request.operation_id:
                raise RuntimeError("injected post-chunk crash")
            return result

        with patch.object(self.store, "compare_and_set", side_effect=crash_after_chunk):
            with self.assertRaises(CredentialBatchCoordinationError):
                await batch.complete(reservation, 200, {"done": True})
        await batch.complete(reservation, 200, {"done": True})

    async def assert_corrupt_fence_blocks_settlement_contract(self) -> None:
        from core.coordination import CoordinationCorruptError

        await self.store.reserve_quota(
            self._quota_request(
                "corrupt-settle", key_id="corrupt-settle", operation_id="corrupt-settle"
            )
        )
        await self.install_admission_fence(epoch=True)
        with self.assertRaises(CoordinationCorruptError):
            await self.store.commit_quota(
                QuotaCommitRequest(
                    "corrupt-settle", 1_001, 2, 0, False, operation_id="corrupt-commit"
                )
            )
        with self.assertRaises(CoordinationCorruptError):
            await self.store.release_quota(
                "corrupt-settle", now=1_001, operation_id="corrupt-release"
            )

    async def assert_ambiguous_fence_json_blocks_settlement(self) -> None:
        from core.coordination import CoordinationCorruptError

        await self.install_admission_fence()
        encoded = await self.store.get("ha-runtime-drain-v1")
        for raw in (
            '{"epoch":1,' + encoded[1:],
            r'{"\u0065poch":1,' + encoded[1:],
        ):
            with self.subTest(raw=raw):
                await self.store.set("ha-runtime-drain-v1", raw)
                with self.assertRaises(CoordinationCorruptError):
                    await self.store.release_quota("unknown", now=1_001)

    async def assert_drain_completion_identity_contract(self) -> None:
        from core.coordination import AdmissionFence

        await self.install_admission_fence()
        await self.store.advance_epoch(1, "drain-advance")
        binding = json.loads(await self.store.get("ha-runtime-binding-v1"))
        binding["fencing_epoch"] = 2
        await self.store.set("ha-runtime-binding-v1", json.dumps(binding))
        value = json.loads(await self.store.get("ha-runtime-drain-v1"))
        value.update(
            reconciliation_receipt_checksum="f" * 64,
            reconciliation_complete=True,
        )
        fence = AdmissionFence.decode(value)
        await self.store.set("ha-runtime-drain-v1", fence.encode())
        await self.store.mark_epoch_ready(2, "drain-ready")
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.complete_admission_drain(fence, epoch=2, operation_id="wrong-ready")
        self.assertIsNotNone(await self.store.get("ha-runtime-drain-v1"))
        await self.store.complete_admission_drain(fence, epoch=2, operation_id="drain-ready")
        await self.store.complete_admission_drain(fence, epoch=2, operation_id="drain-ready")
        self.assertIsNone(await self.store.get("ha-runtime-drain-v1"))

    @staticmethod
    def _quota_request(
        reservation_id: str, *, key_id: str, operation_id: str, **changes: object
    ) -> QuotaReservationRequest:
        values: dict[str, object] = {
            "reservation_id": reservation_id,
            "key_id": key_id,
            "now": 1_000.0,
            "ttl_seconds": 61.0,
            "estimated_tokens": 1,
            "estimated_cost_usd": 0.0,
            "rpm_limit": None,
            "tpm_limit": None,
            "daily_budget_usd": None,
            "monthly_budget_usd": None,
            "daily_spend_usd": 0.0,
            "monthly_spend_usd": 0.0,
            "daily_snapshot_started_at": 1_000.0,
            "monthly_snapshot_started_at": 1_000.0,
            "operation_id": operation_id,
        }
        values.update(changes)
        return QuotaReservationRequest(**values)  # type: ignore[arg-type]

    async def assert_quota_lifecycle_replay_expiry_and_capacity_contract(
        self, *, advance_quota_clock: Callable[[float], Awaitable[None]]
    ) -> None:
        """Assert the quota semantics shared by the reference and registered Lua."""

        replay_request = self._quota_request(
            "quota-replay", key_id="quota-replay-key", operation_id="quota-replay-operation"
        )
        first = await self.store.reserve_quota(replay_request)
        replay = await self.store.reserve_quota(replay_request)
        conflict = await self.store.reserve_quota(
            self._quota_request(
                "quota-replay",
                key_id="quota-replay-key",
                operation_id="quota-replay-operation",
                estimated_tokens=2,
            )
        )
        self.assertTrue(first.accepted)
        self.assertTrue(replay.idempotent)
        self.assertEqual(conflict.reason, "conflict")

        for suffix in ("a", "b"):
            self.assertTrue(
                (
                    await self.store.reserve_quota(
                        self._quota_request(
                            f"capacity-{suffix}",
                            key_id="quota-capacity-key",
                            operation_id=f"capacity-{suffix}",
                        )
                    )
                ).accepted
            )
        capacity = await self.store.reserve_quota(
            self._quota_request(
                "capacity-c", key_id="quota-capacity-key", operation_id="capacity-c"
            )
        )
        self.assertEqual(capacity.reason, "capacity")

        self.assertTrue(
            (
                await self.store.reserve_quota(
                    self._quota_request(
                        "large-token-a",
                        key_id="quota-large-token-key",
                        operation_id="large-token-a",
                        estimated_tokens=2**53 + 1,
                        tpm_limit=2**53 + 1,
                    )
                )
            ).accepted
        )
        exact_token_denial = await self.store.reserve_quota(
            self._quota_request(
                "large-token-b",
                key_id="quota-large-token-key",
                operation_id="large-token-b",
                estimated_tokens=1,
                tpm_limit=2**53 + 1,
            )
        )
        self.assertEqual(exact_token_denial.reason, "tpm")

        budget_neutral = await self.store.reserve_quota(
            self._quota_request(
                "quota-budget-neutral",
                key_id="quota-budget-neutral-key",
                operation_id="quota-budget-neutral-operation",
                estimated_cost_usd=99.0,
                daily_budget_usd=0.0,
                monthly_budget_usd=0.0,
            )
        )
        self.assertTrue(budget_neutral.accepted)

        self.assertTrue(
            (
                await self.store.reserve_quota(
                    self._quota_request(
                        "quota-tpm-overspend",
                        key_id="quota-tpm-overspend-key",
                        operation_id="quota-tpm-overspend-reserve",
                        estimated_tokens=1,
                        tpm_limit=5,
                    )
                )
            ).accepted
        )
        tpm_overspend = await self.store.commit_quota(
            QuotaCommitRequest(
                "quota-tpm-overspend",
                1_001.0,
                6,
                999.0,
                False,
                operation_id="quota-tpm-overspend-commit",
            )
        )
        self.assertTrue(tpm_overspend.committed)
        self.assertTrue(tpm_overspend.overspent)

        self.assertTrue(
            (
                await self.store.reserve_quota(
                    self._quota_request(
                        "quota-commit",
                        key_id="quota-commit-key",
                        operation_id="quota-commit-reserve",
                        ttl_seconds=61.0,
                    )
                )
            ).accepted
        )
        commit_request = QuotaCommitRequest(
            "quota-commit", 1_001.0, 2, 0.0, False, operation_id="quota-commit-operation"
        )
        committed = await self.store.commit_quota(commit_request)
        committed_replay = await self.store.commit_quota(commit_request)
        self.assertTrue(committed.committed)
        self.assertTrue(committed_replay.idempotent)
        self.assertFalse(await self.store.release_quota("quota-commit", now=1_002.0))

        self.assertTrue(
            (
                await self.store.reserve_quota(
                    self._quota_request(
                        "quota-release",
                        key_id="quota-release-key",
                        operation_id="quota-release-reserve",
                        ttl_seconds=61.0,
                    )
                )
            ).accepted
        )
        self.assertTrue(
            await self.store.release_quota(
                "quota-release", now=1_001.0, operation_id="quota-release-operation"
            )
        )
        self.assertFalse(
            await self.store.release_quota(
                "quota-release", now=1_001.0, operation_id="quota-release-operation"
            )
        )

        identical_expiry = self._quota_request(
            "quota-expiry-identical",
            key_id="quota-expiry-identical-key",
            operation_id="quota-expiry-identical-operation",
        )
        changed_expiry = self._quota_request(
            "quota-expiry-changed",
            key_id="quota-expiry-changed-key",
            operation_id="quota-expiry-changed-operation",
        )
        self.assertTrue((await self.store.reserve_quota(identical_expiry)).accepted)
        self.assertTrue((await self.store.reserve_quota(changed_expiry)).accepted)
        await advance_quota_clock(61.1)

        identical_after_retention = await self.store.reserve_quota(identical_expiry)
        changed_after_retention = await self.store.reserve_quota(
            self._quota_request(
                "quota-expiry-changed",
                key_id="quota-expiry-changed-key",
                operation_id="quota-expiry-changed-operation",
                estimated_tokens=2,
            )
        )
        self.assertTrue(identical_after_retention.accepted)
        self.assertFalse(identical_after_retention.idempotent)
        self.assertTrue(changed_after_retention.accepted)
        self.assertFalse(changed_after_retention.idempotent)

    async def assert_epoch_cas_and_invalidation_contract(
        self, *, advance_cas_clock: Callable[[float], Awaitable[None]]
    ) -> None:
        """Assert parity with an implementation-supplied clock/server-time advance hook."""
        epoch = await self.store.read_epoch()
        self.assertEqual(epoch.epoch, 1)
        self.assertEqual(epoch.state, EpochState.READY)
        from core.routing_coordination import VALID_INVALIDATION_SCOPES

        self.assertEqual(
            {
                scope: (await self.store.read_invalidation_generation(scope)).generation
                for scope in VALID_INVALIDATION_SCOPES
            },
            {scope: 1 for scope in VALID_INVALIDATION_SCOPES},
        )
        first_clock = await self.store.read_coordination_time(epoch=1)
        self.assertGreaterEqual(first_clock.milliseconds, 0)

        advanced = await self.store.advance_epoch(1, "advance-1")
        self.assertEqual(advanced.epoch, 2)
        self.assertEqual(advanced.state, EpochState.RECONCILING)
        self.assertEqual(await self.store.advance_epoch(1, "advance-1"), advanced)
        self.assertEqual(await self.store.advance_epoch(2, "advance-1"), advanced)
        self.assertEqual(await self.store.advance_epoch(1, "advance-conflict"), advanced)

        stale_cas = await self.store.compare_and_set(
            CasRequest("contract-key", 0, b"value", 1.0, 2, "cas-1")
        )
        self.assertFalse(stale_cas.applied)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_cas("contract-key", epoch=2)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_coordination_time(epoch=2)
        reconciling_invalidation = await self.store.invalidate(
            InvalidationRequest("reconciling-scope", 2, "reconciling-invalidate")
        )
        self.assertFalse(reconciling_invalidation.applied)

        self.assertEqual(await self.store.mark_epoch_ready(1, "ready-stale"), advanced)
        ready = await self.store.mark_epoch_ready(2, "ready-1")
        self.assertEqual(ready.state, EpochState.READY)
        ready_clock = await self.store.read_coordination_time(epoch=2)
        self.assertGreaterEqual(ready_clock.milliseconds, first_clock.milliseconds)
        self.assertEqual(await self.store.mark_epoch_ready(2, "ready-1"), ready)
        self.assertEqual(await self.store.mark_epoch_ready(1, "ready-1"), ready)
        self.assertEqual(await self.store.mark_epoch_ready(1, "ready-conflict"), ready)

        stale_epoch_cas = await self.store.compare_and_set(
            CasRequest("stale-epoch-key", 0, b"value", 1.0, 1, "stale-epoch-cas")
        )
        self.assertFalse(stale_epoch_cas.applied)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_cas("stale-epoch-key", epoch=1)
        stale_epoch_invalidation = await self.store.invalidate(
            InvalidationRequest("stale-epoch-scope", 1, "stale-epoch-invalidate")
        )
        self.assertFalse(stale_epoch_invalidation.applied)

        cas = await self.store.compare_and_set(
            CasRequest("contract-key", 0, b"value", 1.0, 2, "cas-1")
        )
        self.assertTrue(cas.applied)
        self.assertEqual(cas.revision, 1)
        snapshot = await self.store.read_cas("contract-key", epoch=2)
        self.assertEqual((snapshot.revision, snapshot.payload), (1, b"value"))
        wrong_revision = await self.store.compare_and_set(
            CasRequest("contract-key", 0, b"different", 1.0, 2, "wrong-revision")
        )
        self.assertFalse(wrong_revision.applied)
        replayed_cas = await self.store.compare_and_set(
            CasRequest("contract-key", 0, b"value", 1.0, 2, "cas-1")
        )
        self.assertEqual(replayed_cas.revision, 1)
        self.assertTrue(replayed_cas.idempotent)
        conflicting_cas = await self.store.compare_and_set(
            CasRequest("contract-key", 1, b"different", 1.0, 2, "cas-1")
        )
        self.assertFalse(conflicting_cas.applied)
        updated_cas = await self.store.compare_and_set(
            CasRequest("contract-key", 1, b"updated", 1.0, 2, "cas-2")
        )
        self.assertEqual(updated_cas.revision, 2)
        updated_snapshot = await self.store.read_cas("contract-key", epoch=2)
        self.assertEqual((updated_snapshot.revision, updated_snapshot.payload), (2, b"updated"))

        expiring_cas = await self.store.compare_and_set(
            CasRequest("expiry-key", 0, b"value", 2.0, 2, "expiry-1")
        )
        self.assertEqual(expiring_cas.revision, 1)
        await advance_cas_clock(1.0)
        replayed_expiring_cas = await self.store.compare_and_set(
            CasRequest("expiry-key", 0, b"value", 2.0, 2, "expiry-1")
        )
        self.assertTrue(replayed_expiring_cas.idempotent)
        await advance_cas_clock(1.1)
        expired_snapshot = await self.store.read_cas("expiry-key", epoch=2)
        self.assertEqual((expired_snapshot.revision, expired_snapshot.payload), (None, None))
        expired_cas = await self.store.compare_and_set(
            CasRequest("expiry-key", 0, b"replacement", 2.0, 2, "expiry-2")
        )
        self.assertEqual(expired_cas.revision, 1)

        self.assertIsNone(
            (await self.store.read_invalidation_generation("contract-scope")).generation
        )
        invalidation = await self.store.invalidate(
            InvalidationRequest("contract-scope", 2, "invalidate-1")
        )
        self.assertTrue(invalidation.applied)
        self.assertEqual(invalidation.generation, 1)
        replayed_invalidation = await self.store.invalidate(
            InvalidationRequest("contract-scope", 2, "invalidate-1")
        )
        self.assertEqual(replayed_invalidation.generation, 1)
        self.assertTrue(replayed_invalidation.idempotent)
        conflicting_invalidation = await self.store.invalidate(
            InvalidationRequest("contract-scope", 2, "invalidate-1", replay_ttl_seconds=2.0)
        )
        self.assertFalse(conflicting_invalidation.applied)
        incremented_invalidation = await self.store.invalidate(
            InvalidationRequest("contract-scope", 2, "invalidate-2")
        )
        self.assertEqual(incremented_invalidation.generation, 2)
        self.assertEqual(
            (await self.store.read_invalidation_generation("contract-scope")).generation, 2
        )

        await self.store.close()
        await self.store.close()
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_epoch()
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.advance_epoch(2, "after-close-advance")
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.mark_epoch_ready(2, "after-close-ready")
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.compare_and_set(
                CasRequest("after-close-key", 0, b"value", 1.0, 2, "after-close-cas")
            )
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_cas("after-close-key", epoch=2)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_coordination_time(epoch=2)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.invalidate(
                InvalidationRequest("after-close-scope", 2, "after-close-invalidate")
            )
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.read_invalidation_generation("after-close-scope")
