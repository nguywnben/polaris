# Modal dismissal policy — 2026-09-19

## Scope

Classify existing console dialogs by whether an incidental dismissal could discard
input, interrupt a workflow, or lose a one-time secret. This is a local UI change;
it does not deploy to Oracle, publish an image, or change provider credentials.

| Category | Existing dialogs | Dismissal |
| --- | --- | --- |
| Read-only | Informational messages, quota/details messages, virtual-key usage, trace detail, audit detail | Outside click/touch, Escape, or Close |
| Explicit action | Prompt, confirmation, Identity create/confirm, credential management/edit, model test, virtual-key create/edit/one-time secret | Close/Cancel or the dialog's successful action; outside and Escape do not dismiss |

Navigation and the existing pagehide secret cleanup are unchanged. No X icon is
introduced. Opening focus, focus trapping, nested-dialog inertness, and returning
focus to the trigger are preserved.

## Implementation

- Shared dismissal policy in `frontend/js/ui/notifications.js`; custom dialogs
  default to explicit action and read-only callsites opt into outside dismissal.
- Native dialogs register the same policy. Native dialog padding is not treated
  as the backdrop, and dragging from content onto the backdrop does not close it.
- Listener cleanup follows modal unmount; existing request cancellation and
  secret-clearing callbacks remain the authoritative close paths.
- Updated older smoke tests that intentionally assumed Escape closed all forms.
  Updated the interface-state smoke to inspect every Identity fact skeleton,
  matching the prior layout change instead of assuming a single skeleton.

## Verification

- Red first: the new explicit-dismissal regression reproduced Identity create
  closing on Escape before implementation.
- Green: `modal_initial_focus_smoke.py` — nine explicit modal paths at desktop
  and mobile widths, draft retention, keyboard focus, informational outside/touch
  and Escape dismissal.
- Green: `trace_dialog_smoke.py` — five widths, themes, explicit Close, outside
  click, drag protection, Escape, focus return, scrolling and forced colors.
- Green: `credential_management_smoke.py`, `interface_states_smoke.py`,
  `identity_ui_smoke.py`, `form_interaction_smoke.py`, `access_ui_smoke.py`, and
  `activity_ui_smoke.py`; usage and audit details explicitly cover outside/Escape.
- Green: `modal_loading_smoke.py` at 1440/1024/768/360px, including closing
  delayed-request dialogs through their supported dismissal paths.
- Green: 73 unittest cases across Identity, access virtual-key frontend,
  control-panel assets, and UI feedback contracts.
- Green: Ruff format/check for changed Python files, Node syntax checks for
  changed JavaScript, and `git diff --check`.

All browser checks use isolated localhost storage and synthetic records. No real
keys, provider requests, production storage, or Oracle service were touched.
