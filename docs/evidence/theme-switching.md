# Synchronized theme changes

Verified on 2026-09-15.

The page background changed immediately while fields and quality cards animated
their palette over 140-150ms. The shared theme controller now suppresses CSS
transitions for the first paint of a changed palette, then restores normal
interaction transitions. The guard includes pseudo-elements and dialog backdrops;
it does not stop keyframe animations. Rapid switches replace the pending cleanup.
Initial theme application still precedes styles, and storage/system behavior is unchanged.

Verification:

- `tools/theme_switch_smoke.py --baseline-ref 980c6a3` reproduces outstanding
  background/border transitions on Settings fields using the previous theme script.
- The fixed implementation passes the same browser test across all 11 authenticated
  pages, four widths (320/768/1024/1440), and both theme directions. Visible computed
  colors match between the first frame and 180ms later; no palette transition lags.
- Manual selection, reload persistence, system theme changes, reduced motion,
  rapid toggling, guard cleanup and restored 140ms field transitions pass.
- 26 asset/callback tests, changed-file lint/format, JS syntax and diff checks pass.
- Browser verification uses disposable data and blocks external requests. No live
  credentials or provider calls, dependencies, layout changes or test suppressions.
- This scoped verification does not resolve the unrelated repository-wide failures
  documented in `claude-platform-private-settings.md`.
