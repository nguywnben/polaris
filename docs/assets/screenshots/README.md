# Console preview provenance

Captured on 2026-09-18 from Polaris's current application pages, using Chromium at
1600 × 1100, English UI, and the browser's light/dark color-scheme preference.
All 15 READMEs share these theme-aware Dashboard and Credentials screenshots.

The source is a new SQLite corpus created by `tools/seed_demo_database.py --full`,
served by `tools/demo_preview.py` on loopback. This developer entry point rejects
non-synthetic credentials and blocks outbound IO. The images contain only fictional
accounts (`example.invalid`), demo keys and synthetic usage; no operator database,
real account or production authentication material was used.

The application DOM, CSS, labels and API responses were not altered for the capture.
Screenshots show the actual viewport rather than a composite or an edited mockup.
Checks covered loaded headings/cards, the selected theme, no horizontal page overflow
and no uncaught page errors. Both themes were visually inspected before committing.

To refresh, create a new demo directory (never reuse operator state), start the
offline preview, complete setup with a demo-only password, and capture `/dashboard`
and `/credentials` after their data has loaded. Preserve the existing dimensions and
filenames so every locale and theme continues to resolve the same assets.
