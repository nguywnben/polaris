# Session expiry recovery — private validation

## Scope and evidence

Owner authorized investigating and fixing Oracle dashboard login HTTP 500 while model
inference still works. No push, release, public image publication, or data reset is authorized.
The same failure was reproduced in an isolated process on the installed image with synthetic
sessions: issue, 300 resolves, advance past the 1,800-second idle TTL, then issue again.
Readiness still succeeds while session issue fails with `Session is unavailable.`

## Cause and repair

Every resolve leaves bounded-lifetime replay evidence. More than 256 expired session/replay
records exceeds the atomic mutation cleanup budget. The store correctly refuses partial
mutation, but the standalone runtime had no maintenance path to make progress.

Add separate expiry maintenance (maximum 256 records per lock acquisition), then retry the
same request/operation ID through CoordinationService. Yield between batches and stop after
512 batches or no progress. Never issue/extend a session during maintenance. Preserve all
epoch, admission, clock, corruption, replay and TTL checks. Do not clear the store, relax
authentication, change passwords, migrate data, or restart as the permanent solution.

Extraction assessment: state_store.py already exceeds 1,500 lines. The small maintenance
method stays with its private indexes and lock so ownership/atomicity remain explicit;
extracting a second owner for those indexes would broaden this security fix. Retry policy
stays in the existing runtime facade rather than altering raw-store atomicity contracts.

## Validation

- Regression tests were RED before the production patch (login and revoke failure).
- Focused recovery, maintenance and existing raw-store security contracts passed locally.
- Same focused tests passed on Python 3.12 in the installed Docker image with read-only
  patched files, no network, and synthetic data only.
- One independent cross-model security/correctness review: no required findings. Additional
  tests cover concurrent recovery and corrupt replay indexes; worst-case recovery latency
  remains a bounded first-request cost, not an inference hot-path change.
- Full core invocation: 2,363 tests in 393 seconds; 22 optional skips and 33 environment
  errors from Windows sandbox temporary-directory ACLs. All six affected modules were
  rerun elevated: 38 tests passed. No test/assertion was weakened or skipped to recover.
- Final new regression set: 13 tests passed locally and in an isolated container on Oracle.
  Real ASGI login/cookie/logout path passed after 300 dashboard requests plus idle expiry.
- Adjacent session/auth/rate-limit/coordination tests: 73 passed. Lint, format, diff whitespace
  and test-manifest audit passed. Isolated Docker install/restart/backup/restore/rollback
  smoke passed; only its synthetic containers and volumes were removed.
- Synthetic replay backlog recovery on local Docker: 300 entries ~3 ms, 10,000 ~127 ms,
  99,990 ~1,695 ms. These are bounded recovery costs, not normal-request latency claims.

## Deployment guard

The owner explicitly approved a restart after testing. Deployed an unpublished derived image
on Oracle, without changing the published tag or any remote Git branch. Only the two patched
Python source files differ from the installed base image; BUILD_VERSION/private-patch labels
identify the private build. Existing runtime environment and hardening were copied in memory
(except BUILD_VERSION), never displayed. The same polaris-data volume is mounted.

- Private Oracle image: `sha256:b70f656e11b2e09cac17ca9a6b9d949d15c21ad0d317d9afefad432dcf7c812b`.
- Verified stopped-volume backup and original container config, root-only:
  `/var/backups/polaris/session-expiry-20260919-a1vfay0m`.
- Original stopped container: `polaris-rollback-session-20260919`; not deleted.
- Rollback: stop the new polaris container, rename it aside, rename the original back to
  polaris and start it; use the same volume (no schema migration). Backup is an additional
  recovery option, not something to restore over live newer data without approval.
- Post-deploy: healthy, `/ready` all available, `/login` 200, setup_required false,
  zero startup error lines, zero restarts/OOM, unchanged public port 4283/unless-stopped.
- Both running source SHA-256 hashes match the validated local files exactly.
- Actual owner-password login on the deployed instance and longer real-world idle usage
  remain for the owner; no password or provider credential was requested/exposed.

Vietnamese summary: Đã sửa lỗi đăng nhập sau khi nhiều phiên hết hạn và cập nhật bản vá riêng
lên Oracle, giữ nguyên dữ liệu/credentials và có bản sao lưu. Chưa push hoặc phát hành.
