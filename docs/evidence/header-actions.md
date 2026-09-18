# Consistent page actions and Identity refresh

Verified on 2026-09-15.

## Scope

Page headers, Activity view headers, and the virtual-key header use shared action
sizing: 34px above the 960px drawer breakpoint, 44px on phones/tablets. Labels
stay on one line; the toolbar wraps its buttons when necessary. Body controls,
destructive-action semantics and authentication permissions are unchanged.

Identity uses the existing translated Refresh label; the quality header uses
Save. Specific labels such as Export CSV and Restore balanced retain their meaning.
Manual Identity refresh uses the shared toast renderer without changing focus.
Initial loading remains quiet; failed subsections retain their diagnostic state
and prevent a misleading success toast. Refresh is disabled while loading and
reset on completion or console cleanup; cancelled generations cannot emit stale feedback.

## Verification

- New Identity regression failed before implementation because no toast was emitted.
- All 17 Identity contracts pass, including initial quiet load, success, partial
  failure, total failure, busy-state cleanup, cancellation, and unchanged focus.
- `tools/header_actions_smoke.py` passes against disposable storage: 128 height
  measurements across seven pages, all three Activity views, 320/768/1024/1440px,
  light/dark; all 15 locale labels fit at 320px without clipping or page overflow.
- Real browser refresh success and intercepted 503 failures use toasts, leave
  the page-level status empty, and do not focus an input, textarea or select.
- Desktop/light and mobile/dark screenshots visually reviewed; evidence is
  local under `temp/header-actions/`. No live credentials or provider calls used.
- Changed-file lint/format, JS syntax, diff whitespace and frontend locale audits pass.
- No dependencies, backend API changes, or test suppressions added. This scoped
  verification does not claim the repository-wide baseline failures documented
  in `claude-platform-private-settings.md` are resolved.
