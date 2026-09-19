# Credential summary consistency

Scope: fix misleading zero model counts and unify subscription badge colors; no deployment,
push, release, provider traffic, or credential changes in this task.

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

Vietnamese: Đã sửa bản local và kiểm thử; chưa cập nhật Oracle, chưa push hoặc release.
