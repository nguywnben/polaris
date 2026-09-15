# Empty-state interface consistency — 2026-09-15

## Scope

Reviewed all 14 page surfaces: setup, login, dashboard, providers, pool, models,
ai-quality, playground, access, identity, activity, config, about, and OAuth callback.
Activity was also checked separately in audit/security and runtime-log views.

The disposable runtime starts without providers, credentials, virtual keys, routes,
or request traffic. Creating its synthetic owner naturally produces a session and
an `auth.setup` audit event. No user data or saved configuration is used or changed.

## Shared rules retained and corrected

- Preserve the compact monochrome administration UI, existing sidebar order, page
  hierarchy, spacing, content-sized sections, and purposeful empty-state actions.
  Empty data is not filled with invented metrics or decorative panels.
- Resolve brand contrast centrally in `foundation.css`, including sidebar, mobile
  header, setup, and login. Provider artwork keeps its provider-specific handling.
- Secondary text and information badges use shared theme tokens with sufficient
  measured contrast on their respective surfaces; placeholders remain weight 400.
- Keep compact desktop buttons. At the existing 960px drawer breakpoint, use 44px
  minimum heights for standard buttons and fields, including compact selects,
  endpoint-copy actions, and in-field visibility controls. Icons remain visually
  small; larger click targets do not need larger artwork.
- Treat an open mobile drawer as modal navigation: background main content is inert,
  Tab/Shift+Tab stay inside, Escape returns to the menu trigger, and navigation or
  resizing to desktop removes the modal state. Reuse the existing focus helper.
- Native and custom dialogs use the same theme overlay token. Preserve non-editable
  initial focus, Cancel without a duplicate X, and toast layering without field focus.
- Recent-activity header actions wrap without overlapping their description. When
  empty dashboard metrics stack vertically, separators also change direction.

## Evidence and reproduction

`tools/design_consistency_smoke.py` records DOM measurements and full-page images
at 360px and 1440px. Its full matrix measures 16 surfaces × 6 viewports × 2 themes:
**192 combinations** at 360×800, 768×1024, 844×390, 1024×768, 1440×900, and 1920×1080.
This includes phone landscape, portrait tablet, desktop, and wide desktop.

```powershell
.venv/Scripts/python.exe tools/design_consistency_smoke.py --stage review --strict
# Recheck only a failing surface:
.venv/Scripts/python.exe tools/design_consistency_smoke.py --stage focused --only dashboard --strict
# Optional contact sheets, using a Python runtime with Pillow:
python tools/design_contact_sheets.py temp/design-consistency/review
```

The before pass reproduced invisible dark logos, escaped drawer focus, small
phone/tablet controls, and secondary/badge contrast below the threshold. The after
matrix found no horizontal overflow, JavaScript exceptions, missing field names,
missing/bold placeholders, or measured text-contrast failures. A remaining tablet
role-select override was corrected and rechecked on setup/playground (24 cases).
The initial setup measurement was stabilized by waiting for resize rendering before
measuring, without lowering assertions. Dashboard header overlap found during image
review was corrected and rechecked separately (12 cases).

Regression checks also cover all nine critical browser journeys, the existing
11-route/four-width sweep, seven modal entry paths, native/custom toast layering,
and the navigation, asset, feedback, password-form, and localization unit contracts.
An old provider-card snapshot expected a 154px minimum and 42px logo even though
HEAD already used content sizing and a 32px logo; its assertions now protect the
existing layout rather than restoring obsolete sizing.

The selected unit contracts pass (65 tests), as do lint and formatting for the
changed Python files. The repository-wide task gate stops at its format stage:
23 other, unchanged Python files need formatting. This pre-existing formatting
debt was not mixed into the UI change, and the full task gate is not reported green.

## Limits

This is a bounded Chromium desktop-browser audit, not a WCAG certification or a
claim about every browser, populated dataset, or operating-system zoom setting.
The visual matrix uses Vietnamese, reduced motion, and blocks external HTTPS,
including remote fonts, so it also verifies the fallback-font layout. The existing
localization contracts cover catalog completeness separately; this is not a new
visual pass through all 15 languages. Disabled controls and non-text icons are not
part of the text-contrast calculation. Checkbox/radio and inline-link targets are
not subject to the generic 44px field-height assertion.

No release, remote push, provider request, or persistent-data migration is included.
