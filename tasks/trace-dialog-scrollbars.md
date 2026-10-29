# Console scrollbars and trace dialog

Scope: user-requested visual refinement, followed by explicitly authorized private Oracle
deployment. No push or public release.
Preserve trace data, translations, APIs, authentication and credential behavior.

- Shared foundation uses native thin scrollbars on both axes with palette tokens and
  an older-WebKit fallback. Forced colors restores system scrollbar sizing/colors.
- Trace details uses its translated title as the dialog name, with the exact trace ID
  as supporting text. The close control reuses button styles and an inline SVG.
- Header/actions remain outside the scrolling body. Decision rows use separators rather
  than boxed cards; long data wraps. Reopening starts at the top. Escape and focus return
  retain the existing native dialog implementation.
- Impeccable refinement guidance preserved existing tokens, typography and content.
  Its context launcher was unavailable; PRODUCT.md/DESIGN.md were absent, so existing
  CSS and the user screenshot were the visual authority. DevTools was unavailable;
  the project's isolated Playwright/Chromium runtime supplied browser verification.

Validation: new trace_dialog_smoke.py failed before edits on the dialog's accessible name
(previously only the opaque ID). After edits it passes at 320/360/768/1024/1440px with
light/dark screenshots inspected, no horizontal overflow, wheel scrolling, fixed header,
keyboard containment, Escape/focus return, reopen reset, empty/error responses, and
forced-colors fallback. A synthetic two-axis surface loads the actual console CSS and
verifies both scrollLeft and scrollTop change. The initial test polling expression was
corrected to a function for CSP compatibility; application CSP was not changed.

The existing activity smoke passes filters, failure/retry, trace-to-audit navigation,
English/Vietnamese and responsive layouts. All 18 activity/trace console contract tests
pass. Ruff lint/format, JS syntax and diff whitespace checks pass. Manual five-axis
review found no blocking issue; no new dependency, security boundary or rendering sink.
No touched source module exceeds the project's 1,500-line extraction threshold.

## Private Oracle deployment — 2026-09-19

Deployed bea0026 as polaris-private:trace-ui-bea0026, based on the exact running
credential-summary image so the session and credential fixes remain included.
Image ID: sha256:5737f614c0d00ea5587dd6bf6c561bc0be7e543224fe2f3d488ddde673c040be.
Six trace console tests passed in the candidate container. The initial test mount used
/tests, which broke the test's repository-relative paths; corrected to /app/backend/tests.
No application or test assertions were changed for that correction.

Verified offline root-only backup: /var/backups/polaris/trace-ui-bea0026-l2lo7lao.
Previous container retained stopped as polaris-rollback-trace-ui-bea0026; older rollback
containers untouched. Existing owner, volume, environment (except build version), port,
restart policy and security settings preserved.

Post-deploy: healthy; all readiness dependencies available; login HTTP 200; no startup
error lines. Eleven source hashes, four served JS hashes and the new served CSS rules
verified. No real-provider request or authenticated production UI session was used.

Vietnamese: Đã cập nhật thanh cuộn và modal lên Oracle, kiểm tra thành công; dữ liệu
và các bản vá trước được giữ nguyên. Chưa push hoặc release công khai.
