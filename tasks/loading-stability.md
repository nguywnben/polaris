# Loading stability: dialogs and Identity

Scope: local UI fixes requested 2026-09-19. No VPS update, push, tag or release.
Keep the existing visual system; no additional animation or UI framework.

## Reproduction

- Controlled slow localhost APIs reproduced trace modal top shifting 109px and
  height growing 218px; credential-management header shifted 43px.
- Identity's generic three-line skeleton did not match its 6/8/3 summary facts.
  Loading status removal and staged responses displaced the inventory heading.
- Refresh recreated permission details in their closed state and erased session
  content on a transient 503.

## Implementation

- Bounded viewport-aware heights only for async trace/credential-management
  dialogs; keep their existing body scrolling and header/footer controls.
- Show the known requested trace ID immediately; never carry prior response
  details into a failed request.
- Identity skeletons reuse translated labels and the final fact grid/line boxes.
  Remove the redundant layout-taking loading message, retaining aria-busy.
- Preserve permission disclosure state and restore focused summary on rerender.
- Console refresh keeps existing lists on transient errors, but not on 403/401.
  Pagination retains its prior error behavior rather than displaying old rows
  under a new page number. Failure to load the current principal clears protected
  content; backend authorization and session behavior are unchanged.

## Verification

- New modal-loading regression observed RED (109px top displacement), then GREEN
  at 360/768/1024/1440, staged responses, 503 and keyboard exit/focus restoration.
- Independent Identity loading regression observed RED before the fix; checks
  staged fact geometry, keyboard disclosure, 503 preservation, 403 clearing and
  401 sign-out at desktop/mobile sizes.
- Existing trace dialog and credential-management browser suites pass, including
  themes, keyboard, scrolling, empty/error states and forced-colors behavior.
- Identity DOM contract suite: 17 tests pass, including added disclosure refresh
  state/focus assertions. Extended its DOM stub for real query/containment APIs.
- Existing Identity browser suite passes at five widths in Vietnamese/English,
  light/dark, with read-only owner, create conflict draft, Escape, revoke cancel
  and error/busy-reset checks. Trace contract suite: 6 tests pass.
- Final staged Identity regression passes after matching the permissions line
  box, plus Python Ruff, JavaScript syntax and git whitespace checks.
- Visually inspected desktop loading/loaded Identity and the narrow dark trace
  dialog. No production credentials or data used by the test harness.

Impeccable hardening guidance informed stable loading/refresh behavior while
preserving the current design. Its engine and DevTools connector were unavailable;
verification uses the repository's real Chromium/Playwright localhost harness.
Unknown list length and genuinely different content may still change body length;
the tests do not pretend to know these heights in advance.
