# Redis Quota State v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Redis quota hot-path lifecycle scan with exact, constant-bounded RPM/TPM buckets while leaving daily/monthly budget authority exclusively in the durable usage ledger.

**Architecture:** A shared 61-slot, second-granularity model defines conservative rate semantics for the in-memory reference and three atomic Redis Lua transitions. Redis retains lifecycle/replay records for direct idempotency checks, while a versioned schema marker and bounded operator reconciliation prevent v1, corrupt, or unverified state from becoming ready.

**Tech Stack:** Python 3.12+, asyncio, Redis Lua, redis-py asyncio, unittest, existing durable usage ledger and HA operator.

**Spec:** `docs/superpowers/specs/2026-09-04-redis-quota-state-v2-design.md`

## Global Constraints

- Redis owns RPM, TPM, reservation lifecycle, and replay protection only.
- The durable usage ledger is the sole daily/monthly monetary-budget authority.
- The rate window contains absolute seconds `[floor(now)-60, floor(now)]`, uses exactly 61 circular slots, and may over-enforce by less than one second but never under-enforce.
- Quota reservation TTL is at least 61 seconds; the production value remains 900 seconds.
- Each mutation inspects at most 61 buckets, one directly addressed lifecycle record, and 256 due lifecycle/replay entries.
- No quota mutation may use `HGETALL` on the lifecycle-record hash or a per-record `ZSCORE` loop.
- Preserve exact integer behavior through `2**63 - 1`, replay fingerprints, ownership locators, fencing, and fail-closed corruption handling.
- Keep `SUPPORTED_HA_ACTIVATION_RECORDS` empty and all worker/replica ceilings at one.
- Do not claim live Redis latency or two-replica topology evidence unless those environments actually run.
- Add no dependency; perform every behavior change through RED-GREEN-REFACTOR.

---

### Task 1: Freeze the v2 public contract and budget-ownership boundary

**Files:**
- Modify: `backend/core/coordination.py`
- Modify: `backend/core/virtual_keys.py`
- Modify: `backend/tests/test_coordination_contract.py`
- Modify: `backend/tests/coordination_store_contract.py`
- Modify: `backend/tests/test_coordination_in_memory.py`
- Modify: `backend/tests/test_coordination_redis_live.py`
- Modify: `backend/tests/test_redis_state_store.py`
- Modify: `backend/tests/test_quota_reservations.py`
- Modify: `backend/tests/test_virtual_key_reservations.py`
- Modify: `backend/tests/test_virtual_keys.py`

**Interfaces:**
- Produces: `MIN_QUOTA_RESERVATION_TTL_SECONDS: Final[float] = 61.0`.
- Preserves: `QuotaReservationRequest`, `QuotaCommitRequest`, `QuotaReservationDecision`, and `QuotaCommitResult` field shapes.
- Contract: budget/cost fields remain validated and replay-addressable, but coordination stores do not use them for admission; `VirtualKeyManager` sends neutral reserve values and continues durable budget reserve/settle/release first.

- [x] **Step 1: Write failing contract tests for the 61-second floor and neutral coordination input**

```python
def test_quota_reservation_ttl_covers_the_conservative_window(self) -> None:
    with self.assertRaisesRegex(ValueError, "Quota TTL"):
        _quota_request(ttl_seconds=60.999)
    self.assertEqual(_quota_request(ttl_seconds=61.0).ttl_seconds, 61.0)

async def test_virtual_key_coordination_receives_no_budget_authority(self) -> None:
    await manager.reserve_request(key, request_body, reservation_id="qrs_" + "a" * 32)
    request = state_store.reserve_requests[-1]
    self.assertEqual(request.estimated_cost_usd, 0.0)
    self.assertIsNone(request.daily_budget_usd)
    self.assertIsNone(request.monthly_budget_usd)
    self.assertEqual((request.daily_spend_usd, request.monthly_spend_usd), (0.0, 0.0))
```

- [x] **Step 2: Run focused tests and verify the legacy 1-second TTL and non-budget estimated cost fail**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_coordination_contract backend.tests.test_virtual_key_reservations backend.tests.test_virtual_keys -v`

Expected: FAIL because `QuotaReservationRequest` accepts TTL below 61 seconds and non-budget calls forward `estimated_cost_usd`.

- [x] **Step 3: Add the quota-specific TTL constant and neutralize the runtime reservation payload**

```python
MIN_QUOTA_RESERVATION_TTL_SECONDS: Final[float] = 61.0

_require_finite_float(
    self.ttl_seconds,
    "Quota TTL",
    minimum=MIN_QUOTA_RESERVATION_TTL_SECONDS,
    maximum=MAX_TTL_SECONDS,
)
```

In `VirtualKeyManager.reserve_request`, construct the coordination request with:

```python
estimated_cost_usd=0.0,
daily_budget_usd=None,
monthly_budget_usd=None,
daily_spend_usd=0.0,
monthly_spend_usd=0.0,
daily_snapshot_started_at=current,
monthly_snapshot_started_at=current,
```

Retain actual cost and durability fields on commit for replay compatibility and tracing, but do not make Redis an accounting authority.

- [x] **Step 4: Migrate synthetic quota fixtures from sub-61-second TTLs and rerun focused tests**

Replace quota fixture defaults such as `1.0`, `10.0`, `20.0`, and `60.0` with `61.0` or a larger value. Advance fake clocks past `active_expires_at` rather than relying on the old short TTL.

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_coordination_contract backend.tests.test_coordination_in_memory backend.tests.test_coordination_redis_live backend.tests.test_redis_state_store backend.tests.test_quota_reservations backend.tests.test_virtual_key_reservations backend.tests.test_virtual_keys -v`

Expected: PASS.

- [x] **Step 5: Commit the contract boundary**

```powershell
git add backend/core/coordination.py backend/core/virtual_keys.py `
  backend/tests/test_coordination_contract.py backend/tests/coordination_store_contract.py `
  backend/tests/test_coordination_in_memory.py backend/tests/test_coordination_redis_live.py `
  backend/tests/test_redis_state_store.py backend/tests/test_quota_reservations.py `
  backend/tests/test_virtual_key_reservations.py backend/tests/test_virtual_keys.py `
  docs/superpowers/plans/2026-09-04-redis-quota-state-v2.md
git commit -m "refactor(quota): separate rate and budget authority"
```

### Task 2: Implement the bounded Python reference window

**Files:**
- Create: `backend/core/quota_rate_window.py`
- Create: `backend/tests/test_quota_rate_window.py`
- Modify: `backend/core/state_store.py`
- Modify: `backend/tests/test_coordination_in_memory.py`
- Modify: `backend/tests/coordination_store_contract.py`
- Modify: `backend/tests/test_quota_reservations.py`

**Interfaces:**
- Produces: `RATE_WINDOW_SECONDS = 60`, `RATE_BUCKET_COUNT = 61`, `RateTotals`, and `QuotaRateWindow`.
- `QuotaRateWindow.reserve(now: float, tokens: int) -> None` adds one accepted contribution.
- `QuotaRateWindow.commit(accepted_at: float, estimated_tokens: int, now: float, actual_tokens: int) -> None` replaces a live estimate with actual usage at commit time.
- `QuotaRateWindow.release(accepted_at: float, estimated_tokens: int, now: float) -> None` reverses a live estimate.
- `QuotaRateWindow.totals(now: float) -> RateTotals` and `retry_after_seconds(now: float) -> int` inspect at most 61 slots.

- [x] **Step 1: Write failing unit tests for bucket boundaries, replacement, reversal, overflow, and fixed capacity**

```python
def test_boundary_second_is_conservatively_included(self) -> None:
    window = QuotaRateWindow()
    window.reserve(1_000.999, 7)
    self.assertEqual(window.totals(1_060.999), RateTotals(requests=1, tokens=7))
    self.assertEqual(window.totals(1_061.000), RateTotals(requests=0, tokens=0))

def test_commit_replaces_the_estimate_exactly_once(self) -> None:
    window = QuotaRateWindow()
    window.reserve(1_000.1, 100)
    window.commit(1_000.1, 100, 1_001.2, 250)
    self.assertEqual(window.totals(1_001.2), RateTotals(requests=1, tokens=250))

def test_storage_never_exceeds_61_slots(self) -> None:
    window = QuotaRateWindow()
    for second in range(10_000):
        window.reserve(float(second), 1)
    self.assertLessEqual(window.slot_count, 61)
```

Also assert release underflow, a future-dated slot, invalid counters, and sums above `2**63 - 1` raise `CoordinationCorruptError` rather than wrapping.

- [x] **Step 2: Run the new unit module and verify imports fail**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_quota_rate_window -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'core.quota_rate_window'`.

- [x] **Step 3: Implement the 61-slot reference type**

```python
@dataclass(frozen=True, slots=True)
class RateTotals:
    requests: int
    tokens: int

@dataclass(slots=True)
class _RateBucket:
    second: int
    requests: int = 0
    tokens: int = 0

class QuotaRateWindow:
    def __init__(self) -> None:
        self._slots: list[_RateBucket | None] = [None] * RATE_BUCKET_COUNT

    def totals(self, now: float) -> RateTotals:
        current = math.floor(now)
        requests = tokens = 0
        for bucket in self._slots:
            if bucket is not None and current - RATE_WINDOW_SECONDS <= bucket.second <= current:
                requests = _safe_add(requests, bucket.requests)
                tokens = _safe_add(tokens, bucket.tokens)
        return RateTotals(requests, tokens)
```

Use `math.floor(now) % 61` for writes, reject future or position-mismatched buckets, clear only stale slots, and calculate retry-after as `max(1, math.ceil(earliest_second + 61 - now))`.

- [x] **Step 4: Replace in-memory list aggregation and budget reconciliation with one window per key**

Initialize `self._quota_rate_windows: dict[str, QuotaRateWindow] = {}`. On accepted reserve call `window.reserve(coordination_now, request.estimated_tokens)`. Commit calls `window.commit(record.accepted_at, record.request.estimated_tokens, coordination_now, actual_tokens)`. Release calls `window.release(...)` before changing lifecycle state.

Delete `_active_for_key_locked`, `_committed_for_key_locked`, `_reconcile_committed_for_key_locked`, daily/monthly unreconciled aggregation, and budget denial/overspend branches. Retain replay, record capacity, cleanup, and direct lifecycle behavior. Retention becomes `max(request.ttl_seconds, 61.0)` and committed retention becomes 61 seconds from commit unless the active reservation expires later.

- [x] **Step 5: Rewrite shared/in-memory assertions around rate-only ownership and run them**

```python
async def test_coordination_ignores_legacy_budget_inputs(self) -> None:
    accepted = await self.store.reserve_quota(
        _reservation("rate-only", estimated_cost_usd=99.0, daily_budget_usd=0.0)
    )
    self.assertTrue(accepted.accepted)

async def test_commit_reports_only_tpm_overspend(self) -> None:
    await self.store.reserve_quota(_reservation("overspend", estimated_tokens=1, tpm_limit=5))
    result = await self.store.commit_quota(
        QuotaCommitRequest("overspend", 1_000.0, 6, 999.0, False)
    )
    self.assertTrue(result.overspent)
```

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_quota_rate_window backend.tests.test_coordination_in_memory backend.tests.test_quota_reservations -v`

Expected: PASS.

- [x] **Step 6: Commit the bounded reference implementation**

```powershell
git add backend/core/quota_rate_window.py backend/core/state_store.py `
  backend/tests/test_quota_rate_window.py backend/tests/test_coordination_in_memory.py `
  backend/tests/coordination_store_contract.py backend/tests/test_quota_reservations.py
git commit -m "feat(quota): add bounded rate-window reference"
```

### Task 3: Introduce the Redis v2 schema and fixed bucket primitives

**Files:**
- Create: `backend/core/quota_redis_scripts.py`
- Modify: `backend/core/redis_state_store.py`
- Modify: `backend/tests/test_redis_state_store.py`
- Modify: `backend/tests/test_coordination_redis_live.py`

**Interfaces:**
- Produces: `QUOTA_RESERVE_SCRIPT`, `QUOTA_COMMIT_SCRIPT`, and `QUOTA_RELEASE_SCRIPT` with headers `polaris:quota_*:v2`.
- Extends `_quota_keys(...)` with `quota:rate-buckets` and `quota:state-schema` keys while preserving the existing hash tag.
- Schema marker encoding: `2|<epoch>|ready`; malformed, missing over non-empty state, v1, future, stale, or expiring markers fail closed.
- Bucket encoding: `2|<absolute_second>|<requests>|<tokens>` in fields `0` through `60`.

- [x] **Step 1: Write failing static and key-contract tests**

```python
def test_quota_v2_scripts_are_constant_bounded(self) -> None:
    for name in ("quota_reserve", "quota_commit", "quota_release"):
        source = SCRIPT_SOURCES[name].upper()
        self.assertIn(f"POLARIS:{name}:V2".upper(), source)
        self.assertNotIn("HGETALL', KEYS[2]", source)
        self.assertNotIn("FOR RESERVATION_ID", source)
        self.assertIn("RATE_BUCKET_COUNT = 61", source)

def test_quota_keys_include_rate_and_schema_in_the_same_cluster_slot(self) -> None:
    keys = store._quota_keys(b"a" * 64, "reservation", "operation")
    self.assertEqual(len(keys), 10)
    self.assertTrue(all("{" + store._tag + "}" in key for key in keys))
```

Add script tests proving a missing marker with non-empty lifecycle state and markers `1|...`, `2|future|...`, or an expiry return `COORDINATION_CORRUPT`/`reconciliation_required` without mutation. A missing marker may initialize to `2|<current_epoch>|ready` only when that target's records, indexes, replay state, and bucket hash are all empty.

- [x] **Step 2: Run Redis transport tests and verify v1 sources/eight-key bundles fail**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_redis_state_store -v`

Expected: FAIL on v1 headers, forbidden `HGETALL`, and missing v2 keys.

- [x] **Step 3: Extract quota scripts and implement closed bucket helpers**

In `quota_redis_scripts.py`, define the shared Lua constants and functions:

```lua
local RATE_BUCKET_COUNT = 61
local RATE_WINDOW_SECONDS = 60

local function parse_bucket(value, slot, now_second)
  local schema, second, requests, tokens = string.match(
    value, '^([^|]+)|([^|]+)|([^|]+)|([^|]+)$')
  if schema ~= '2' or not valid_safe_uint(second) or not valid_uint(requests)
    or not valid_uint(tokens) or tonumber(second) % RATE_BUCKET_COUNT ~= slot
    or tonumber(second) > now_second then return nil end
  return {second=tonumber(second), requests=requests, tokens=tokens}
end
```

Implement `read_rate_window(now_second)` with exactly 61 `HGET` operations, `adjust_bucket(second, request_delta, token_delta)` with checked add/subtract, and `retry_after(now_ms, earliest_second)` using the conservative expiry boundary. Keep `plan_prune_target` capped at 256 and direct-record validation, but remove `aggregate_target_records` entirely.

- [x] **Step 4: Wire the v2 scripts and ten-key bundle without changing decoded replies**

```python
from core.quota_redis_scripts import (
    QUOTA_COMMIT_SCRIPT,
    QUOTA_RELEASE_SCRIPT,
    QUOTA_RESERVE_SCRIPT,
)

SCRIPT_SOURCES = {
    # existing scripts unchanged
    "quota_reserve": QUOTA_RESERVE_SCRIPT,
    "quota_commit": QUOTA_COMMIT_SCRIPT,
    "quota_release": QUOTA_RELEASE_SCRIPT,
}
```

Append rate and schema keys to `_quota_keys`; retain the existing locator and operation locator categories. Update the fake Redis client to store `quota_buckets: dict[bytes, dict[int, tuple[int, int, int]]]` and `quota_schema: dict[bytes, tuple[int, int, str]]` rather than deriving totals from `quota_records`.

- [x] **Step 5: Run static, transport, and live-discovery tests**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_redis_state_store backend.tests.test_coordination_redis_live -v`

Expected: dependency-free cases PASS; live Redis cases SKIP only when `POLARIS_TEST_REDIS_URI` is absent.

- [x] **Step 6: Commit the Redis v2 foundation**

```powershell
git add backend/core/quota_redis_scripts.py backend/core/redis_state_store.py `
  backend/tests/test_redis_state_store.py backend/tests/test_coordination_redis_live.py
git commit -m "refactor(redis): introduce quota state v2 buckets"
```

### Task 4: Implement atomic Redis reserve admission

**Files:**
- Modify: `backend/core/quota_redis_scripts.py`
- Modify: `backend/core/redis_state_store.py`
- Modify: `backend/tests/test_redis_state_store.py`
- Modify: `backend/tests/test_coordination_redis_live.py`

**Interfaces:**
- Consumes: v2 marker, `read_rate_window`, `adjust_bucket`, direct lifecycle lookup, and bounded cleanup from Task 3.
- Produces: unchanged six-field reserve reply decoded by `_decode_quota_reserve_reply`.
- Reserve counts one request and `estimated_tokens` in the Redis-clock second only after every denial, replay, capacity, and corruption check succeeds.

- [x] **Step 1: Write failing reserve tests for boundaries and no-mutation denials**

```python
async def test_stateful_v2_reserve_uses_buckets_not_record_population(self) -> None:
    for index in range(100_000):
        client.seed_retained_record(key_id=b"key-a", reservation_id=f"old-{index}".encode())
    before = client.quota_record_inspections
    decision = await store.reserve_quota(reservation("new", rpm_limit=100_001))
    self.assertTrue(decision.accepted)
    self.assertEqual(client.quota_record_inspections - before, 1)
    self.assertEqual(client.rate_bucket_inspections, 61)

async def test_denied_or_replayed_reserve_never_double_counts(self) -> None:
    first = await store.reserve_quota(reservation("first", rpm_limit=1))
    replay = await store.reserve_quota(reservation("first", rpm_limit=1))
    denied = await store.reserve_quota(reservation("second", rpm_limit=1))
    self.assertTrue(first.accepted)
    self.assertTrue(replay.idempotent)
    self.assertEqual(denied.reason, "rpm")
    self.assertEqual(client.bucket_totals(b"key-a"), (1, 1))
```

Also cover TPM equality/overflow, the full boundary second, retry-after, record/replay capacity, locator conflict, stale/reconciling epoch, cleanup backlog, and marker corruption.

- [x] **Step 2: Run reserve-focused tests and verify the v2 stub does not enforce them**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_redis_state_store.RedisStateStoreTests.test_stateful_v2_reserve_uses_buckets_not_record_population backend.tests.test_redis_state_store.RedisStateStoreTests.test_denied_or_replayed_reserve_never_double_counts -v`

Expected: FAIL because reserve does not yet mutate/read the v2 rate hash.

- [x] **Step 3: Implement reserve ordering and the compact v2 lifecycle record**

Use this exact order inside one Lua script: validate epoch/schema/arguments and locators; acquire Redis time; plan bounded cleanup; resolve replay; directly read the target record; check record/replay capacity; aggregate 61 buckets; decide RPM then TPM; apply cleanup; persist denial replay or accepted bucket + lifecycle + replay + locators.

The v2 lifecycle record contains:

```text
2|fingerprint|key_digest|state|active_until_ms|retained_until_ms|
accepted_at_ms|estimated_tokens|committed_at_ms|actual_tokens|
rpm_limit_or_n|tpm_limit_or_n|retention_ms|next_expiry_ms
```

Do not store cost, daily/monthly budgets, spend snapshots, or reconciliation flags.

- [x] **Step 4: Prove accepted, denied, and replay outcomes preserve fixed work**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_redis_state_store -v`

Run when configured: `.venv\Scripts\python.exe -m unittest backend.tests.test_coordination_redis_live.RedisCoordinationLiveTests.test_quota_v2_reserve_boundaries -v`

Expected: PASS, or explicit environment skip for the live case.

- [x] **Step 5: Commit reserve admission**

```powershell
git add backend/core/quota_redis_scripts.py backend/core/redis_state_store.py `
  backend/tests/test_redis_state_store.py backend/tests/test_coordination_redis_live.py
git commit -m "feat(redis): bound quota reserve admission"
```

### Task 5: Implement atomic Redis commit and release transitions

**Files:**
- Modify: `backend/core/quota_redis_scripts.py`
- Modify: `backend/core/redis_state_store.py`
- Modify: `backend/tests/test_redis_state_store.py`
- Modify: `backend/tests/test_coordination_redis_live.py`
- Modify: `backend/tests/coordination_store_contract.py`

**Interfaces:**
- Consumes: the accepted second and estimated tokens in the v2 lifecycle record.
- Produces: unchanged four-field commit/release replies and TPM-only `QuotaCommitResult.overspent`.
- Commit/release subtract the original active contribution only when its second remains inside `[current_second-60, current_second]`; underflow or slot mismatch fails closed.

- [x] **Step 1: Write failing transition tests**

```python
async def test_commit_moves_estimate_to_the_commit_second(self) -> None:
    await store.reserve_quota(reservation("commit", estimated_tokens=100, tpm_limit=500))
    client.advance(1_000)
    result = await store.commit_quota(
        QuotaCommitRequest("commit", 1_001.0, 250, 9.0, True, operation_id="commit-op")
    )
    self.assertTrue(result.committed)
    self.assertEqual(client.bucket_totals(b"key-a"), (1, 250))

async def test_release_reverses_only_a_live_bucket_contribution(self) -> None:
    await store.reserve_quota(reservation("release", estimated_tokens=50))
    self.assertTrue(await store.release_quota("release", now=1_000.0))
    self.assertEqual(client.bucket_totals(b"key-a"), (0, 0))
```

Add cases for same-second commit, commit after the accepted bucket ages out, fallback to estimated tokens, TPM overspend, released/committed replay, changed-operation conflict, expired active record, large integers, and bucket underflow corruption.

- [x] **Step 2: Run transition-focused tests and verify bucket totals fail**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_redis_state_store.RedisStateStoreTests.test_commit_moves_estimate_to_the_commit_second backend.tests.test_redis_state_store.RedisStateStoreTests.test_release_reverses_only_a_live_bucket_contribution -v`

Expected: FAIL because the scripts still mutate lifecycle state without v2 bucket replacement/reversal.

- [x] **Step 3: Implement commit replacement and TPM overspend**

Before mutating the record, parse and validate the direct hash/ZSET pair. If active and unexpired, subtract `(1, estimated_tokens)` from `floor(accepted_at_ms / 1000)` when live, add `(1, actual_tokens_or_estimate)` to the Redis current second, and calculate:

```lua
overspent = record.tpm_limit ~= 'n'
  and (rate_tokens_saturated or uint_greater_than(rate_tokens, record.tpm_limit))
```

Set the compact record to committed, retain it for `max(active_until_ms, now_ms + 61000)`, and persist replay/locator changes only after every validation succeeds.

- [x] **Step 4: Implement release reversal with the same preflight-before-mutation rule**

For an active, unexpired record, reverse its live bucket contribution and set state to `released`. Unknown, terminal, expired, stale-epoch, and conflicting operations return the existing safe false result. Exact replay sets `idempotent=true` without touching buckets.

- [x] **Step 5: Run shared, fake Redis, and live transition matrices**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.coordination_store_contract backend.tests.test_redis_state_store backend.tests.test_coordination_redis_live -v`

Expected: PASS with only explicitly configured live-backend skips.

- [x] **Step 6: Commit lifecycle transitions**

```powershell
git add backend/core/quota_redis_scripts.py backend/core/redis_state_store.py `
  backend/tests/test_redis_state_store.py backend/tests/test_coordination_redis_live.py `
  backend/tests/coordination_store_contract.py
git commit -m "feat(redis): make quota lifecycle bucket-atomic"
```

### Task 6: Gate v1 migration and bounded reconciliation

**Files:**
- Modify: `backend/core/coordination.py`
- Modify: `backend/core/state_store.py`
- Modify: `backend/core/redis_state_store.py`
- Modify: `backend/core/ha_operator.py`
- Modify: `backend/ha_admin.py`
- Modify: `backend/tests/test_ha_operator.py`
- Modify: `backend/tests/test_redis_state_store.py`
- Modify: `backend/tests/test_ha_admin.py`
- Modify: `docs/runbooks/ha-lifecycle.md`

**Interfaces:**
- Produces: immutable `QuotaReconciliationResult(scanned: int, complete: bool, cursor: str | None)`.
- Extends `CoordinationStore` with `reconcile_quota_state(*, epoch: int, cursor: str | None, limit: int, apply: bool) -> QuotaReconciliationResult`.
- Redis cursor is an opaque, validated URL-safe base64 encoding of scan progress; its decoded payload is closed to `{"schema_version": 1, "family": "records" | "replays", "key_scan": int, "target": str | None, "member_scan": int}`.
- `HaRuntimeOperator.reconcile` records the cursor in the drain record and refuses `mark_ready` until quota reconciliation is complete.

- [x] **Step 1: Write failing migration and operator-gate tests**

```python
async def test_v1_quota_state_requires_reconciliation(self) -> None:
    client.seed_v1_quota_state(b"key-a")
    decision = await store.reserve_quota(reservation("blocked"))
    self.assertEqual(decision.reason, "reconciliation_required")
    self.assertEqual(client.quota_buckets, {})

async def test_mark_ready_requires_complete_quota_reconciliation(self) -> None:
    await operator.drain(apply=True)
    await operator.advance_epoch("advance", apply=True)
    page = await next_operator.reconcile(apply=True)
    self.assertFalse(page["quota_complete"])
    with self.assertRaisesRegex(RuntimeError, "quota reconciliation"):
        await next_operator.mark_ready("ready", apply=True)
```

Add dry-run no-mutation, exact cursor replay, malformed cursor, 256-record page ceiling, hash/ZSET mismatch, malformed record, and complete/resumed reconciliation cases.

- [x] **Step 2: Run migration/operator tests and verify the interface and gate are absent**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_ha_operator backend.tests.test_ha_admin backend.tests.test_redis_state_store -v`

Expected: FAIL because `reconcile_quota_state` and reconciliation progress do not exist.

- [x] **Step 3: Implement the transport-neutral reconciliation result and reference behavior**

```python
@dataclass(frozen=True, slots=True)
class QuotaReconciliationResult:
    scanned: int
    complete: bool
    cursor: str | None

    def __post_init__(self) -> None:
        _require_int(self.scanned, "Quota reconciliation count", minimum=0, maximum=256)
        if self.complete != (self.cursor is None):
            raise ValueError("Quota reconciliation result is invalid.")
```

The in-memory implementation validates at most `limit <= 256` lifecycle/replay records per call in sorted `(key_id, reservation_id)` order. Dry-run returns the next cursor without modifying state. Apply mode rejects any still-active reservation, removes validated terminal/expired v1 evidence, initializes empty v2 windows only while the epoch is reconciling, and records completion for that epoch.

- [x] **Step 4: Implement bounded Redis paging and v1 disposal**

Redis reconciliation runs only in the exact reconciling epoch and never in a mutation Lua script. It walks record-key and replay-key families separately; each call reads at most 256 hash entries plus their matching ZSET scores, validates the closed v1/v2 schema, and advances the opaque cursor. Because daily/monthly authority is durable, v1 cost evidence is not copied into Redis buckets. Apply mode rejects still-active reservations, removes each validated terminal/expired v1 hash/ZSET pair and its matching reservation/operation locator, initializes `2|<epoch>|ready` only after both families for that target are empty, and records the completed epoch. Any mismatch fails closed without advancing the persisted cursor.

Do not use unbounded `KEYS`, `HGETALL`, or recursive deletion. Use Redis `SCAN`/`HSCAN` cursors with an explicit remaining-item budget and retain progress in the drain record so repeated CLI calls resume safely.

- [x] **Step 5: Integrate reconciliation progress into the dry-run-first HA workflow**

Extend the drain record with `quota_reconciliation_cursor` and `quota_reconciliation_complete`.
`reconcile --apply` first reconciles durable bindings/ledger, then performs one quota page. Its
response includes `quota_scanned`, `quota_complete`, and `quota_cursor_present` but never exposes
the cursor value. `mark-ready` requires the complete flag and exact epoch, then performs a fresh
authoritative reconciliation confirmation before calling `mark_epoch_ready`.

- [x] **Step 6: Run operator, transport, corruption, and CLI tests**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_ha_operator backend.tests.test_ha_admin backend.tests.test_coordination_in_memory backend.tests.test_redis_state_store -v`

Expected: PASS.

- [x] **Step 7: Commit the upgrade gate**

```powershell
git add backend/core/coordination.py backend/core/state_store.py `
  backend/core/redis_state_store.py backend/core/ha_operator.py backend/ha_admin.py `
  backend/tests/test_ha_operator.py backend/tests/test_ha_admin.py `
  backend/tests/test_coordination_in_memory.py backend/tests/test_redis_state_store.py `
  docs/runbooks/ha-lifecycle.md
git commit -m "feat(ha): gate quota state v2 reconciliation"
```

### Task 7: Close algorithmic evidence without activating HA

**Files:**
- Modify: `docs/specs/coordination-store.md`
- Modify: `docs/architecture.md`
- Modify: `docs/superpowers/specs/2026-09-04-redis-quota-state-v2-design.md`
- Modify: `docs/reviews/w4.15-adversarial-review.md`
- Modify: `docs/reviews/w4c-coordination-blocker-review.md`
- Modify: `docs/evidence/w4.19-ha-activation-disposition.md`
- Modify: `tasks/current.md`
- Modify: `tasks/plan.md`
- Modify: `tasks/todo.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: reproducible static/synthetic bounded-work evidence and an explicit retained external-topology blocker.
- Preserves: empty `SUPPORTED_HA_ACTIVATION_RECORDS`, `WORKERS=1`, `POLARIS_REPLICA_COUNT=1`, and Helm `replicaCount: 1`.

- [x] **Step 1: Run the focused quota and HA matrix**

Run: `.venv\Scripts\python.exe -m unittest backend.tests.test_quota_rate_window backend.tests.test_coordination_contract backend.tests.test_coordination_in_memory backend.tests.test_redis_state_store backend.tests.test_coordination_redis_live backend.tests.test_quota_reservations backend.tests.test_virtual_key_reservations backend.tests.test_ha_operator backend.tests.test_ha_admin -v`

Record the exact pass/skip counts; an absent live Redis URI is a skip, not a pass.

- [x] **Step 2: Run the complete backend and repository gates**

Run: `.venv\Scripts\python.exe -m unittest discover -s backend/tests`

Run: `.venv\Scripts\python.exe -m ruff check backend`

Run: `.venv\Scripts\python.exe -m ruff format --check backend`

Run: `.venv\Scripts\python.exe -m compileall -q backend`

Run: `.venv\Scripts\python.exe -m pip check`

Run: `git diff --check`

Expected: every available gate PASS; all unavailable external gates remain explicitly identified.

- [x] **Step 3: Perform security, correctness, and performance review**

Review exact-second boundary math, reserve/commit/release atomicity, replay-before-mutation ordering, bucket underflow/overflow, Redis cluster key tags, locator isolation, schema/epoch fencing, bounded cleanup, cursor secrecy, dry-run behavior, budget single-authority, and all exception-to-fail-closed mappings. Resolve every load-bearing finding and rerun affected tests.

- [x] **Step 4: Update specifications, reviews, evidence, and roadmap truthfully**

Document the exact v2 record/bucket schema, 61-slot bound, 256 cleanup/reconciliation bound, budget ownership, migration sequence, observed test counts, and whether live Redis ran. Mark the O(n) algorithmic blocker closed only when the 100,000-record synthetic test proves constant record inspection. Keep Checkpoint W4-C and Phase 6 failure/load unchecked while the two-replica shared-database topology matrix is unavailable.

- [x] **Step 5: Commit the verified checkpoint without pushing**

```powershell
git add backend docs tasks CHANGELOG.md
git commit -m "docs(roadmap): record quota state v2 evidence"
```

- [x] **Step 6: Verify the final checkpoint**

Run: `git status --short`

Run: `git log -8 --oneline`

Expected: clean worktree and nine reviewable plan, implementation, hardening, and evidence commits
after the approved design commit `68ee168`.
