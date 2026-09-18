# Console interface review — 2026-09-16

## Owner-authorized scope

Review and refine all console pages and nested workflows, including setup/login,
OAuth results, sidebar, provider workspaces, advanced settings/imports, credential
management, routing, quality policy, Playground, access keys, identities/sessions,
trace/audit/log views, backup/restore, confirmations, notifications and loading.
Use the existing compact monochrome Operate interface. Keep the approved 32px
single-line controls and existing provider/auth semantics. Preserve unrelated work.

## System

- Type roles: page 28px (24px narrow), workspace/dialog 20px, section 16px,
  subsection/body 14px, label/supporting copy 13px, metadata 12px. Google Sans
  with system sans fallbacks. Role sizes use rem; text and spacing remain readable
  with zoom. Weight and proximity distinguish headings from supporting text.
- Spacing: 4/8/12/16/24/32. Group related fields, put instructions near their
  controls, allow headers/actions to wrap. Keep the approved enclosing statistic
  borders. Retain content-sized cards, progressive disclosure and inline editing.
- States: truthful loading/empty/error/ready; skeletons for initial remote data,
  preserve rendered data during refresh, accessible busy state, no misleading
  zero/empty result before a request finishes. Buttons represent in-flight actions.
- Modal: readable title/body/actions, scrollable body on short screens, contained
  focus and inert background, safe initial focus, Escape and return focus.
- Theme: semantic text/border/background tokens, including state borders; retain
  synchronous palette changes and useful reduced-motion feedback.

## Bounded verification

- Baseline and final page matrix: 16 surfaces × 6 viewports × 2 themes = 192 each.
  Widths 360, 768, 844 landscape, 1024, 1440, 1920; add 320px in state tests.
- Additional bounded states: delayed/failing loads, disclosures and modal family
  coverage, long content, refresh retention, focus/confirmation/toast interaction.
- Existing page-specific synthetic browser journeys cover populated states and
  actions. Run each selected script once, rerun only failing slices after fixes.
- Inspect batched desktop/mobile captures; implement one correction batch, then
  confirm. Run affected contracts and the core suite for shared JS integration.
- All provider traffic is synthetic or blocked. No changes to real credentials,
  real model requests, Docker, commits or remote services.

## Baseline observations

- 192 empty-page combinations: no measured horizontal overflow, contrast/name/
  placeholder failures or page exceptions. This does not cover populated states.
- Section copy can be 11–12px while native dialog headings inherit 21px and custom
  dialogs use 17px; there is no common type-role vocabulary.
- Identity/access/about/activity data hosts start empty with aria-busy only;
  credential management replaces whole sections with plain loading text.
- Custom modal mounting traps Tab but does not make the background inert or lock
  background scroll. Confirmations initially focus the affirmative action.
- Semantic state borders contain light-theme hex colors. Reduced-motion uses a
  global near-zero duration override instead of targeting motion effects.
- Impeccable detector unavailable: engine 0.1.5 is not installed. Review uses skill
  guidance, source inspection and measured Chromium evidence. No certification.
