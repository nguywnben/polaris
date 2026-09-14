"""Constant-bounded conservative rate accounting for quota coordination."""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.coordination import MAX_COORDINATION_INTEGER, CoordinationCorruptError

RATE_WINDOW_SECONDS = 60
RATE_BUCKET_COUNT = RATE_WINDOW_SECONDS + 1


@dataclass(frozen=True, slots=True)
class RateTotals:
    requests: int
    tokens: int


@dataclass(slots=True)
class _RateBucket:
    second: int
    requests: int = 0
    tokens: int = 0


def _safe_input_integer(value: object, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_COORDINATION_INTEGER
    ):
        raise ValueError(f"{label} is invalid.")
    return value


def _safe_add(left: int, right: int) -> int:
    result = left + right
    if not 0 <= result <= MAX_COORDINATION_INTEGER:
        raise CoordinationCorruptError("Quota rate state is invalid.")
    return result


def _second(value: object, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= MAX_COORDINATION_INTEGER
    ):
        raise ValueError(f"{label} is invalid.")
    return math.floor(float(value))


class QuotaRateWindow:
    """A 61-slot window that conservatively includes the complete boundary second."""

    def __init__(self) -> None:
        self._slots: list[_RateBucket | None] = [None] * RATE_BUCKET_COUNT

    @property
    def slot_count(self) -> int:
        return sum(bucket is not None for bucket in self._slots)

    def copy(self) -> QuotaRateWindow:
        candidate = QuotaRateWindow()
        candidate._slots = [
            None if bucket is None else _RateBucket(bucket.second, bucket.requests, bucket.tokens)
            for bucket in self._slots
        ]
        return candidate

    def _validated_buckets(self, current: int) -> list[_RateBucket]:
        buckets: list[_RateBucket] = []
        for slot, bucket in enumerate(self._slots):
            if bucket is None:
                continue
            if (
                isinstance(bucket.second, bool)
                or not isinstance(bucket.second, int)
                or not 0 <= bucket.second <= MAX_COORDINATION_INTEGER
                or bucket.second % RATE_BUCKET_COUNT != slot
                or bucket.second > current
                or isinstance(bucket.requests, bool)
                or not isinstance(bucket.requests, int)
                or not 0 <= bucket.requests <= MAX_COORDINATION_INTEGER
                or isinstance(bucket.tokens, bool)
                or not isinstance(bucket.tokens, int)
                or not 0 <= bucket.tokens <= MAX_COORDINATION_INTEGER
            ):
                raise CoordinationCorruptError("Quota rate state is invalid.")
            buckets.append(bucket)
        return buckets

    def _adjust(self, second: int, request_delta: int, token_delta: int) -> None:
        slot = second % RATE_BUCKET_COUNT
        bucket = self._slots[slot]
        if bucket is None or bucket.second != second:
            if request_delta < 0 or token_delta < 0:
                raise CoordinationCorruptError("Quota rate state is invalid.")
            bucket = _RateBucket(second)
            self._slots[slot] = bucket
        bucket.requests = _safe_add(bucket.requests, request_delta)
        bucket.tokens = _safe_add(bucket.tokens, token_delta)

    def totals(self, now: float) -> RateTotals:
        current = _second(now, "Quota time")
        requests = tokens = 0
        for bucket in self._validated_buckets(current):
            if current - RATE_WINDOW_SECONDS <= bucket.second:
                requests = _safe_add(requests, bucket.requests)
                tokens = _safe_add(tokens, bucket.tokens)
        return RateTotals(requests, tokens)

    def retry_after_seconds(self, now: float) -> int:
        current = _second(now, "Quota time")
        live = [
            bucket.second
            for bucket in self._validated_buckets(current)
            if current - RATE_WINDOW_SECONDS <= bucket.second and (bucket.requests or bucket.tokens)
        ]
        if not live:
            return 1
        return max(1, math.ceil(min(live) + RATE_BUCKET_COUNT - float(now)))

    def reserve(self, now: float, tokens: int) -> None:
        current = _second(now, "Quota time")
        amount = _safe_input_integer(tokens, "Estimated tokens")
        candidate = self.copy()
        candidate._validated_buckets(current)
        candidate._adjust(current, 1, amount)
        self._slots = candidate._slots

    def commit(
        self,
        accepted_at: float,
        estimated_tokens: int,
        now: float,
        actual_tokens: int,
    ) -> None:
        accepted = _second(accepted_at, "Accepted quota time")
        current = _second(now, "Quota time")
        estimate = _safe_input_integer(estimated_tokens, "Estimated tokens")
        actual = _safe_input_integer(actual_tokens, "Actual tokens")
        if accepted > current:
            raise CoordinationCorruptError("Quota rate state is invalid.")
        candidate = self.copy()
        candidate._validated_buckets(current)
        if current - RATE_WINDOW_SECONDS <= accepted:
            candidate._adjust(accepted, -1, -estimate)
        candidate._adjust(current, 1, actual)
        self._slots = candidate._slots

    def release(self, accepted_at: float, estimated_tokens: int, now: float) -> None:
        accepted = _second(accepted_at, "Accepted quota time")
        current = _second(now, "Quota time")
        estimate = _safe_input_integer(estimated_tokens, "Estimated tokens")
        if accepted > current:
            raise CoordinationCorruptError("Quota rate state is invalid.")
        candidate = self.copy()
        candidate._validated_buckets(current)
        if current - RATE_WINDOW_SECONDS <= accepted:
            candidate._adjust(accepted, -1, -estimate)
        self._slots = candidate._slots
