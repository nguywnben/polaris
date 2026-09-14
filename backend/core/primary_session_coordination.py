"""Fenced, atomic upstream conversation metadata shared by gateway replicas."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import uuid
from dataclasses import asdict, dataclass

from core.coordination import CasRequest, CoordinationUnavailableError
from core.coordination_service import CoordinationService

SESSION_TTL_SECONDS = 6 * 60 * 60
_MAX_CAS_ATTEMPTS = 16
_KEY_DOMAIN = b"polaris:primary-session:v1\0"


@dataclass(frozen=True, slots=True)
class PrimarySessionState:
    conversation_id: str
    trajectory_id: str
    session_id: str
    step_index: int
    created_at: float
    last_used_at: float


class PrimarySessionCoordinator:
    """Advance provider conversation steps with fenced compare-and-set semantics."""

    def __init__(
        self,
        coordination: CoordinationService,
        *,
        identifier_key: bytes,
        fencing_epoch: int,
    ) -> None:
        if not isinstance(identifier_key, bytes) or len(identifier_key) < 32:
            raise ValueError("Primary session identifier key is invalid.")
        if type(fencing_epoch) is not int or fencing_epoch < 1:
            raise ValueError("Primary session fencing epoch is invalid.")
        self._coordination = coordination
        self._identifier_key = identifier_key
        self._fencing_epoch = fencing_epoch

    def _coordination_key(self, source_key: str) -> str:
        if not isinstance(source_key, str) or not source_key:
            raise ValueError("Primary session key is invalid.")
        digest = hmac.digest(
            self._identifier_key,
            _KEY_DOMAIN + source_key.encode("utf-8"),
            hashlib.sha256,
        ).hex()
        return f"primary-session-{digest}"

    def _request(
        self, key: str, expected_revision: int, payload: bytes, operation_id: str
    ) -> CasRequest:
        return CasRequest(
            key=key,
            expected_revision=expected_revision,
            payload=payload,
            ttl_seconds=SESSION_TTL_SECONDS,
            epoch=self._fencing_epoch,
            operation_id=operation_id,
        )

    @staticmethod
    def _new_state(first_user_text: str, now: float) -> PrimarySessionState:
        if first_user_text:
            digest = hashlib.sha256(first_user_text.encode("utf-8")).digest()
            session_number = int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
            session_id = f"-{session_number}"
        else:
            session_id = f"-{uuid.uuid4().int % 9_000_000_000_000_000_000}"
        return PrimarySessionState(
            conversation_id=str(uuid.uuid4()),
            trajectory_id=str(uuid.uuid4()),
            session_id=session_id,
            step_index=1,
            created_at=now,
            last_used_at=now,
        )

    @staticmethod
    def _decode(payload: bytes) -> PrimarySessionState:
        try:
            value = json.loads(payload)
            if not isinstance(value, dict) or set(value) != {
                "schema_version",
                "conversation_id",
                "trajectory_id",
                "session_id",
                "step_index",
                "created_at",
                "last_used_at",
            }:
                raise ValueError
            if value.pop("schema_version") != 1:
                raise ValueError
            state = PrimarySessionState(**value)
            uuid.UUID(state.conversation_id)
            uuid.UUID(state.trajectory_id)
            if (
                not state.session_id.startswith("-")
                or not state.session_id[1:].isdigit()
                or type(state.step_index) is not int
                or state.step_index < 1
                or not all(
                    type(item) in {int, float} and math.isfinite(item) and item >= 0
                    for item in (state.created_at, state.last_used_at)
                )
                or state.created_at > state.last_used_at
            ):
                raise ValueError
            return state
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("Primary session coordination payload is corrupt.") from None

    @staticmethod
    def _encode(state: PrimarySessionState) -> bytes:
        return json.dumps(
            {"schema_version": 1, **asdict(state)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    async def next_state(self, source_key: str, first_user_text: str) -> PrimarySessionState:
        key = self._coordination_key(source_key)
        for _attempt in range(_MAX_CAS_ATTEMPTS):
            snapshot = await self._coordination.read_cas(key, epoch=self._fencing_epoch)
            now = (
                await self._coordination.read_coordination_time(epoch=self._fencing_epoch)
            ).milliseconds / 1000.0
            if snapshot.payload is None:
                state = self._new_state(first_user_text, now)
                revision = 0
            else:
                prior = self._decode(snapshot.payload)
                state = PrimarySessionState(
                    conversation_id=prior.conversation_id,
                    trajectory_id=prior.trajectory_id,
                    session_id=prior.session_id,
                    step_index=prior.step_index + 1,
                    created_at=prior.created_at,
                    last_used_at=now,
                )
                assert snapshot.revision is not None
                revision = snapshot.revision
            operation_id = f"primary-session-{uuid.uuid4().hex}"
            result = await self._coordination.compare_and_set(
                self._request(key, revision, self._encode(state), operation_id)
            )
            if result.applied:
                return state
        raise CoordinationUnavailableError("Primary session coordination is contended.")


_primary_session_coordinator: PrimarySessionCoordinator | None = None


def configure_primary_session_coordinator(
    coordinator: PrimarySessionCoordinator | None,
) -> None:
    global _primary_session_coordinator
    _primary_session_coordinator = coordinator


def get_primary_session_coordinator() -> PrimarySessionCoordinator:
    if _primary_session_coordinator is None:
        raise CoordinationUnavailableError("Primary session coordination is not initialized.")
    return _primary_session_coordinator
