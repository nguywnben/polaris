# Console scrollbars and trace dialog

Scope: user-requested visual refinement only. No VPS deployment, push or release.
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

Vietnamese: Thanh cuộn gọn theo giao diện sáng/tối; modal dấu vết rõ tiêu đề, nút đóng
và danh sách bước nhẹ hơn. Đã kiểm thử local; chưa cập nhật Oracle.
