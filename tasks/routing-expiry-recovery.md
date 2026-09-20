# Recover credential routing after expiry backlog

## Accepted scope

Owner approved fixing the Oracle 503 incident, testing, then installing a private patch with
one restart, backup and rollback. No public release or unrelated pending feature deployment.

## Evidence

- Oracle logged `CoordinationReconciliationRequiredError` for credential routing at
  2026-09-20 03:16–03:28 UTC. Container stayed healthy, restart count zero, resources available.
- Deployed state-store, coordination-service and routing-adapter hashes matched local source.
- Deterministic reproduction: 256 expired CAS replay records recover; 257 cause three
  consecutive admission failures while the epoch still reports ready.

## Contract and plan

1. Keep normal store mutations atomic and their 256-record cleanup budget unchanged.
2. Add bounded, epoch-checked maintenance for expired CAS/invalidation replay evidence only.
   Never remove live replay proofs, active leases, quota state, credentials or sessions.
3. At the service boundary, retry the identical mutation after maintenance makes progress,
   yielding between batches and enforcing a finite retry bound. Live capacity exhaustion,
   corruption, stale epochs, admission fences and unknown failures remain fail-closed.
4. Verify idle backlog recovery, idempotency, concurrency/settlement, bounded work and the
   public streaming boundary. Then test the exact private image in isolation on Oracle.
5. Back up the stopped volume, retain the old container, preserve configuration, replace once,
   verify real streamed/non-streamed inference and login/readiness, then report evidence.

## Extraction assessment

`state_store.py` is already over 1,500 lines. A small maintenance method belongs with the
existing lock, private replay indexes and epoch checks; extracting those private internals
would expand this incident patch into a state-store refactor. Keep the delta narrowly scoped.

## Review and deployment hold

- Independent RED tests reproduced four failures on the original code; live-capacity control
  passed. Initial patch passed 96 coordination/routing/session tests.
- Fresh-context adversarial review found two actionable issues: duplicate expiry entries could
  cause a partial cleanup commit, and no-progress cleanup could falsely mark service recovery.
  Both were reproduced in failing tests, then corrected. The final mutation now owns health
  attribution, and each cleanup batch rejects duplicate identifiers before committing.
- The owner chose manual external review. No external CLI/model was invoked. Prepare a bounded
  review packet and hold replacement of the Oracle container pending their review/confirmation.
- During the implementation/review-packet turn, no Oracle writes, restarts, backup/restore,
  image changes or production credential changes occurred.

## Final focused verification

- Task quality gate passed with 109 tests covering expiry recovery/maintenance, coordination
  store/service, routing adapter, session expiry, public streaming lifecycle and runtime wiring.
- Static checks passed: Ruff lint/format, compilation, test manifest, JavaScript, YAML, shell
  syntax and diff whitespace. The 1,025-record fixture setup emits an asyncio debug slow-task
  diagnostic under concurrent local test load; cooperative maintenance yielding is asserted.
- Final source SHA-256:
  - state_store.py: `d0f05cf7d563fef4bf70b5c2161cc820adc7c3390e27b2ec18f5204d6d87c2db`
  - coordination_service.py: `0726bab707c2b7f8234b054e0f0f5fd072c6bcb5dc0086f97c511e6aeb9b06fe`
- The full backend suite started before the last two review corrections; its result is
  supplementary baseline evidence, not a replacement for the final 109-test gate.
  It completed with exit code 0; optional live-backend cases were skipped without configured
  PostgreSQL/MongoDB test services. No required affected test was skipped.

## External review and deployment completed

The owner returned `temp/REVIEW-routing-expiry-report.md` on 2026-09-20. The reviewer reported
no blocking findings, matching source hashes and an independent 109-test pass. Non-blocking
notes were evaluated: the unreachable assertion is a defensive invariant consistent with the
existing session helper; `recovered_at` can transiently reflect successful maintenance before
final failure (final availability remains correct); direct `operation=` kwargs cannot replace
the lambda because `_run` already owns an `operation` parameter. Keep the reviewed runtime
unchanged rather than introduce another variant during incident deployment.

The original approved Oracle update resumed after external review. See
[deployment evidence](oracle-routing-expiry-update.md) for exact images, isolated candidate
testing, backup, rollback and successful live streaming/non-streaming checks.

Tiếng Việt: Bản vá dọn từng đợt các bản ghi điều phối đã hết hạn, giữ nguyên dữ liệu còn hiệu lực
và cơ chế chống thực hiện trùng lặp. Đã hoàn tất đánh giá bên ngoài và cập nhật Oracle; không
ghép thay đổi danh sách model hay bộ cài đang chờ vào bản vá sự cố này.
