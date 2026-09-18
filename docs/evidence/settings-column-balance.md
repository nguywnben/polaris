# Settings grouping and column balance

Verified on 2026-09-15.

Keep-alive now follows the connection settings in the right column, with its URL
full width and interval/current-URL action arranged compactly. Inference timeout
belongs to Storage and Connections. The redundant routing summary and its renderer
are removed; Models remains the sole routing editor. Only visible Settings keys
contribute to the metadata summary. All editable controls, validators, environment
locks, save scopes and server values are preserved. Retention and backup/restore
remain full width. The connection heading is updated in all 15 locale catalogs.

Verification:

- New placement/ownership tests fail before the move and pass afterward; all
  18 Settings/About contracts pass, including schema coverage with the explicit
  Models-owned routing keys and protection against routing writes from Settings.
- `tools/settings_ui_smoke.py` passes save failure/draft retention, successful
  synthetic saves of timeout and keep-alive, current-URL action, environment locks,
  system-only reset, password controls, load retry and unchanged routing state.
- The existing smoke was updated to the current surface: three password toggles
  (Code Assist is owned by Providers), no routing summary, and a reachable bottom
  save bar rather than the previous sticky-bar assumption.
- Light/dark at 320/360/768/1024/1440px: no horizontal overflow. At 1440px the
  independent-column height difference stays below 160px without forced heights.
  Desktop/light and phone/dark screenshots reviewed in `temp/settings-ui/`.
- Frontend locale audits, changed-file lint/format, JS syntax and diff checks pass.
- All mutations use a disposable backend with intercepted writes, not live data.
  No API/schema changes or test suppressions. Unrelated repository-wide baseline
  failures documented in `claude-platform-private-settings.md` remain outside scope.
