# PB5 — Console and Language Quality

Date: 2026-09-12

PB5 applies one production-level presentation contract across the 11 primary console destinations
and all 13 page fragments. Existing shared spacing, compact badge, responsive, feedback, and
translation primitives were already healthy, so the task changed only proven inconsistencies.

The Models priority explanation and both AI Quality safety explanations are now inline field copy
instead of one-line cards or visually separate note sections. About no longer renders empty support
tiers, so the retired Experimental surface does not occupy space when the runtime advertises no
experimental capability. Contract tests preserve balanced select padding, visible label spacing,
compact badges, and the prohibition on horizontal page scrollers and standalone advisory panels.

English and Vietnamese remain the only maintainer-curated documentation languages. Thirteen stale
community README snapshots were removed because they still advertised retired Redis and Helm paths
and could not be semantically guaranteed. This does not remove console localization: all 15 console
catalogs remain present, every key remains complete, and community locales continue to fall back to
English for missing messages.

Verification:

- 112 focused console, localization, accessibility, and product-inventory tests passed.
- All four localization audits passed; all 1,268 referenced keys resolve in every console locale.
- The maintained browser smoke passed 9/9 critical journeys with no console or page errors.
- The responsive/accessibility sweep passed all 11 routes at 360, 768, 1024, and 1440 pixels.
- Keyboard navigation passed for the primary sidebar and provider selector tablist.
- PB5 reduces the working tree by 7,447 net lines before this evidence/checklist update.
