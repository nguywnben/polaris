# Modal and toast regression — 2026-09-15

## Contract

- A modal with a Cancel action does not also need a close icon. Identity creation was
  the duplicate; audit and trace detail dialogs retain their only close action.
- Notifications remain above native dialogs and custom modal overlays, including a
  notification already visible when a dialog opens.
- Notifications and validation feedback do not transfer focus into inputs, textareas,
  or selects. Normal modal entry, Tab navigation, and focus restoration are retained.

## Implementation

The shared notification host uses a manual popover to enter the browser top layer.
While a native modal is active, the host belongs to that dialog so its live region is
not outside the active modal's accessible subtree. Dialog toggle events restore the
notification's layer; dismissal returns the empty host to the document body.
The host has no autofocus, and a missing host is recreated rather than opening a
message modal. See the [MDN Popover API guide](https://developer.mozilla.org/en-US/docs/Web/API/Popover_API/Using).

Shared validation and explicit setup, quality, settings, and provider error/pending
paths no longer focus a field alongside a toast. Field error markers remain intact.
No authentication, authorization, persistence, or provider request policy changed.

## Evidence

- The new `tools/modal_toast_ui_smoke.py` first reproduced the duplicate close action,
  native-dialog layering failure, validation focus changes for three control types,
  and the missing-host modal fallback. It passes after the fix.
- Chromium checks cover all four native dialogs on their actual routes, a custom
  modal, input/textarea/select validation, toast-before-dialog ordering, toast timeout,
  missing-host recovery, unchanged focus, and Tab navigation.
- Desktop light (1440 px) and mobile dark (360 px) screenshots were inspected.
- 48 focused unit tests pass: identity, form validation, password forms, provider
  onboarding, quality policy, and settings/about.
- The existing browser smoke suite passes all 9 critical journeys and its responsive
  route checks. Ruff and whitespace checks pass.

The browser evidence is for the installed Chromium runtime. Firefox, Safari, and
older browsers without native Popover support were not certified by this run.
