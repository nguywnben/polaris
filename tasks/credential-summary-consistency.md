# Credential summary consistency

Scope: fix misleading zero model counts and unify subscription badge colors. Initial work
was local only; the user subsequently authorized the private Oracle deployment below.
No push, public release, provider traffic, or credential changes.

The fleet summary counts only stored model_ids, while the management endpoint can return a
provider catalog when that list is missing. The old UI flattened missing/invalid data to zero
and did not synchronize successful management discovery back to the card.

Add the backward-compatible model_count_known flag. Unknown displays an em dash, or retains
the previous count only for the same opaque account scope. An explicitly stored empty list
continues to mean zero. Management success updates the card and current manager record;
closed dialogs and responses belonging to a replaced account cannot update the new card.
This does not expand provider discovery, alter routing, or borrow counts from another account.

Every plan/tier now uses the existing info color token in both themes, preserving literal
provider labels and the no-tooltip requirement. The UI skill guided reuse of existing tokens
and one bounded desktop/mobile visual pass; no redesign or additional loading badge.

Validation: RED regressions before edits; 37 fleet/query/Node contracts and 22 adjacent
route/import tests passed. New credential_summary_smoke.py passed in isolated Chromium with
synthetic responses: unknown, populated, incomplete refresh, management discovery, replacement
account, confirmed empty; matching computed badge colors at 1440px light and 360px dark, no
page errors or horizontal overflow. Screenshots inspected. Python lint and JS syntax passed.
An initial adjacent-suite invocation named a nonexistent module; corrected to the actual
test_credentials_page_route module, which passed. No tests weakened or skipped.

Extraction assessment: credential-manager.js is already large; this change only passes through
two public summary fields. New presentation helpers remain with credential-cards.js rather than
adding state ownership to the manager. Manual five-axis review found no blocking issues.

## Private Oracle deployment — 2026-09-19

Deployed commit 4000b86 presentation fixes together with the existing 6f0d82d session fix.
Private image: polaris-private:credential-summary-4000b86, image ID
sha256:0a25a25f8961ddc25d6a1437aaf0a35dadccb4c10744e25a36db1a30b82e781d.
All 24 fleet/session tests passed inside the candidate image on Oracle before replacement.
Offline data backup validated at /var/backups/polaris/credential-summary-4000b86-ezf2j_ow;
root-only inspection backup retained there. Previous container is stopped and retained as
polaris-rollback-summary-4000b86. The earlier original-release rollback is untouched.

Existing environment (except private BUILD_VERSION), port bindings, hardened runtime settings,
restart policy and polaris-data volume were preserved. Post-deploy checks: healthy, all ready
dependencies available, owner still configured, login page HTTP 200, zero startup error lines.
All six patched source hashes and all three HTTP-served JS hashes match the tested files.
No authenticated live dashboard or real-provider model call was performed in this deployment.

Vietnamese: Đã cập nhật bản vá riêng lên Oracle và kiểm tra thành công; chưa push hoặc release.
