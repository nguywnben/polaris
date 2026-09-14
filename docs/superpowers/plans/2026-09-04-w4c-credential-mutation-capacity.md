# W4-C Credential Mutation and Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining process-local credential-pool mutation authority and prove the
historical 256-entry credential-batch domain caps without opening HA activation.

**Architecture:** Credential pool planning becomes pure code executed inside a durable,
mode-scoped backend transaction. Batch preview and idempotency admissions use compact encrypted CAS
registries with backend time, exact HMAC identifiers, bounded pruning, and no unbounded scans.

**Tech Stack:** Python 3.12+, asyncio, aiosqlite, asyncpg, PyMongo asynchronous API, existing fenced
coordination CAS, AES-GCM, unittest.

**Spec:** `docs/specs/credential-pool-atomic-mutation.md` and
`docs/specs/credential-batch-coordination.md`

## Global Constraints

- Keep `SUPPORTED_HA_ACTIVATION_RECORDS` empty and worker/replica ceilings at one.
- Do not use an expiring distributed lock as durable mutation authority.
- Fail closed on unavailable dependencies, stale epoch, corrupt state, invalid plans, and unknown
  transaction outcomes.
- Do not expose credential payloads, email addresses, tokens, raw idempotency keys, or filenames in
  coordination keys, logs, or metric labels.
- Preserve current HTTP response shapes and standalone behavior.
- Add no dependency and perform every behavior change through RED-GREEN-REFACTOR.

---

### Task 1: Durable credential-pool transaction boundary

**Files:**
- Create: `backend/core/credential_pool_mutation.py`
- Modify: `backend/core/storage_adapter.py`
- Modify: `backend/core/storage/sqlite_manager.py`
- Modify: `backend/core/storage/postgresql_manager.py`
- Modify: `backend/core/storage/mongodb_manager.py`
- Test: `backend/tests/test_credential_pool_mutation.py`
- Test: `backend/tests/test_mongodb_driver.py`

**Interfaces:**
- Produces: `CredentialPoolRecord`, `CredentialPoolWrite`, `CredentialPoolMutation`,
  `validate_credential_pool_mutation`, and
  `StorageAdapter.mutate_credential_pool(mode, planner) -> dict[str, Any]`.
- The planner signature is
  `Callable[[tuple[CredentialPoolRecord, ...]], CredentialPoolMutation]` and must not await or
  perform I/O.

- [x] **Step 1: Write contract and SQLite atomicity tests**

```python
async def test_sqlite_mutation_commits_one_validated_plan_atomically():
    result = await manager.mutate_credential_pool("primary", planner)
    assert result == {"action": "created"}
    assert await manager.list_credentials("primary") == ["one.json"]

async def test_invalid_plan_rolls_back_without_partial_write():
    with self.assertRaises(CredentialPoolMutationError):
        await manager.mutate_credential_pool("primary", overlapping_write_delete_planner)
    self.assertEqual(await manager.list_credentials("primary"), [])
```

- [x] **Step 2: Run the new tests and observe failure because the contract and method do not exist**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_pool_mutation -v`

- [x] **Step 3: Implement immutable records/plans, closed validation, adapter delegation, SQLite
  `BEGIN IMMEDIATE`, PostgreSQL transactional table locking, and MongoDB transactional gate writes**

```python
@dataclass(frozen=True, slots=True)
class CredentialPoolMutation:
    writes: tuple[CredentialPoolWrite, ...]
    deletes: tuple[str, ...]
    result: dict[str, Any]

async def mutate_credential_pool(self, mode: str, planner: CredentialPoolPlanner) -> dict[str, Any]:
    mutation = await self._backend.mutate_credential_pool(mode, planner)
    await self._publish_credential_invalidations()
    return mutation.result
```

- [x] **Step 4: Run focused storage/driver tests until green**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_pool_mutation backend.tests.test_mongodb_driver -v`

- [x] **Step 5: Commit the durable transaction boundary**

```powershell
git add backend/core/credential_pool_mutation.py backend/core/storage_adapter.py `
  backend/core/storage/sqlite_manager.py backend/core/storage/postgresql_manager.py `
  backend/core/storage/mongodb_manager.py backend/tests/test_credential_pool_mutation.py `
  backend/tests/test_mongodb_driver.py docs/specs/credential-pool-atomic-mutation.md `
  docs/superpowers/plans/2026-09-04-w4c-credential-mutation-capacity.md
git commit -m "feat(storage): add atomic credential pool mutations"
```

### Task 2: Move upsert and deduplication into the durable transaction

**Files:**
- Modify: `backend/core/credential_pool.py`
- Modify: `backend/tests/test_pool_import.py`
- Test: `backend/tests/test_credential_pool_mutation.py`

**Interfaces:**
- Consumes: `StorageAdapter.mutate_credential_pool` and the immutable mutation records from Task 1.
- Produces: existing `upsert_credential_by_email` and
  `deduplicate_credentials_by_account_email` result contracts without `_POOL_LOCKS`.

- [x] **Step 1: Add cross-client concurrent admission, replacement, provider isolation, filename
  collision, deduplication, and rollback tests**

```python
first, second = await asyncio.gather(
    upsert_credential_by_email("first.json", incoming),
    upsert_credential_by_email("second.json", incoming),
)
self.assertEqual(sum(item["stored"] for item in (first, second)), 1)
self.assertEqual(len(await manager.list_credentials("primary")), 1)
```

- [x] **Step 2: Run the new tests and observe duplicate admission under the old process-local path**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_pool_mutation backend.tests.test_pool_import -v`

- [x] **Step 3: Refactor external email resolution before the transaction and express every
  admission/deduplication decision as one pure mutation plan**

```python
return await storage_adapter.mutate_credential_pool(
    mode,
    lambda records: _plan_upsert(records, filename, credential_data, email, static_identity),
)
```

- [x] **Step 4: Run pool, import, provider, and storage tests until green**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_pool_mutation backend.tests.test_pool_import backend.tests.test_provider_pool_filter -v`

- [x] **Step 5: Commit the pool migration**

```powershell
git add backend/core/credential_pool.py backend/tests/test_pool_import.py `
  backend/tests/test_credential_pool_mutation.py
git commit -m "feat(credentials): serialize pool identity mutations durably"
```

### Task 3: Enforce dedicated 256-entry batch domains

**Files:**
- Modify: `backend/core/credential_batch_coordination.py`
- Modify: `backend/tests/test_credential_batch_coordination.py`
- Modify: `docs/specs/credential-batch-coordination.md`

**Interfaces:**
- Produces: compact encrypted preview and idempotency admission registries capped at exactly 256
  live entries per domain.
- Consumes: backend-owned coordination time and existing fenced CAS operations.

- [x] **Step 1: Add exact-capacity, expiry-pruning, cross-client race, release, and dependency-loss
  tests**

```python
for index in range(256):
    await service.issue_preview(f"fingerprint-{index}")
with self.assertRaises(CredentialBatchCapacityError):
    await service.issue_preview("fingerprint-over-capacity")
```

- [x] **Step 2: Run tests and observe the 257th admission succeed under the unbounded domain path**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_batch_coordination -v`

- [x] **Step 3: Implement HMAC-addressed fixed-cap registries with coordination time, bounded expiry
  pruning, CAS retries, and refresh/remove transitions**

```python
_DOMAIN_CAPACITY = 256
await self._admit("preview", token, ttl_seconds=_PREVIEW_TTL_SECONDS)
await self._admit("idempotency", idempotency_key, ttl_seconds=_IDEMPOTENCY_TTL_SECONDS)
```

- [x] **Step 4: Run batch coordination and route tests until green**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_batch_coordination backend.tests.test_credential_batch_operations -v`

- [x] **Step 5: Commit the capacity gate**

```powershell
git add backend/core/credential_batch_coordination.py `
  backend/tests/test_credential_batch_coordination.py docs/specs/credential-batch-coordination.md
git commit -m "feat(credentials): bound shared batch coordination domains"
```

### Task 4: Review, evidence, and checkpoint

**Files:**
- Modify: `docs/reviews/w4c-coordination-blocker-review.md`
- Modify: `tasks/current.md`
- Modify: `tasks/todo.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: Run focused concurrency and backend parity tests**

Run: `.venv\\Scripts\\python.exe -m unittest backend.tests.test_credential_pool_mutation backend.tests.test_pool_import backend.tests.test_credential_batch_coordination backend.tests.test_credential_batch_operations -v`

- [x] **Step 2: Run the complete backend suite and repository gates**

Run: `.venv\\Scripts\\python.exe -m unittest discover -s backend/tests`

- [x] **Step 3: Perform security and code-quality review; resolve every load-bearing finding**

Review transaction ownership, rollback, cancellation, bounded retries, corruption handling,
secret-free identifiers/logging, mutation invalidation ordering, and cross-backend parity.

- [x] **Step 4: Record exact evidence and retained external-topology blockers**

Document observed counts and unavailable evidence. Keep HA activation denied until Redis quota and
real two-replica tests pass.

- [x] **Step 5: Commit the verified checkpoint without pushing**

```powershell
git add CHANGELOG.md docs/reviews/w4c-coordination-blocker-review.md tasks/current.md tasks/todo.md
git commit -m "docs(roadmap): record W4-C mutation evidence"
```
