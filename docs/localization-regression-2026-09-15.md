# Polaris localization and field hints — 2026-09-15

## Scope

The owner expanded localization from curated English/Vietnamese plus compatibility locales
to complete contextual interface copy for all 15 existing languages: English, Simplified and
Traditional Chinese, German, Spanish, French, Indonesian, Italian, Japanese, Korean,
Portuguese, Russian, Thai, Turkish, and Vietnamese. No locale or runtime dependency was added.

The 13 completion files contain 5,312 reviewed translation entries. Shared field hints cover
all 15 languages. Exact provider instructions cover 44 workflows/help messages; they preserve
PKCE, device-code steps, callback URLs, per-key validation, local token storage, and import
deduplication details instead of reducing them to generic guidance.

## Implementation

- Load per-language completion maps after legacy catalogs and Identity aliases, then synchronize
  the actual `MESSAGE_CATALOGS` used by `t()` and the English-source lookup.
- Add an exact provider-copy catalog. Explicitly keyed labels and attributes are excluded from
  automatic raw-copy translation so repeated language changes do not restore stale text.
- Add 58 static and four dynamic text-field placeholders. Keep labels, values, validation,
  password-only authentication, and secret lifetimes unchanged. OAuth secret hints stay populated
  after configuration loads; dynamic provider hints retain their matching translation key.
- Use font weight 400 for input/textarea placeholders and disabled empty select prompts.
  Checkboxes, radios, file/date controls do not support text placeholders and keep their labels.
- Keep exact product names, protocol identifiers, example URLs, and filesystem paths untranslated.

New content lives in per-locale files and a small provider-copy module rather than further
expanding the already-large i18n implementation. The existing source dictionaries remain for
compatibility; no framework, authentication, persistence, or provider behavior was changed.

## Verification

- Strict runtime-catalog audit: 1,712 effective English keys across 15 locales, including 1,287
  statically referenced keys. Require nonblank translations, interpolation-token multiset parity,
  no ordinary multiword English fallback, and exact provider-help resolution.
- HTML, JavaScript, and management-API localization audits pass. Backend messages cover all
  15 languages with matching interpolation fields.
- 94 focused unit/contract tests pass. The 28-test provider/i18n/placeholder subset also passes
  after synchronizing dynamic provider placeholder keys.
- Critical Chromium journeys: 9/9 pass, plus 11 routes at 360/768/1024/1440 pixels and keyboard checks.
- `tools/localization_ui_smoke.py` exercises 15 languages on setup/login and 11 console routes
  at 360-dark and 1440-light, plus the virtual-key dialog. It checks field hints, font weight,
  overflow, unresolved keys, repeated provider language switching, and exact provider instructions.
  OAuth callback responses are checked for all 15 language attributes and no-store headers;
  this matrix does not claim a separate visual review of every callback translation.
- Browser tests use disposable storage, synthetic credentials, and blocked external requests.
  No real provider login, billable inference, or operator secret is used.
- The final 15-locale browser matrix passed after both runtime fixes, with no page errors,
  placeholder mismatches, provider-instruction mismatches, or horizontal overflow.

## Review and limits

Language-group agents reviewed contextual wording and interpolation independently of integration.
Integration review checked precedence, stale automatic translations, escaped dynamic attributes,
unchanged secret handling, and bounded iteration over shipped catalogs. Placeholder labels are
supplementary, not replacements for accessible field names.

These are automated checks and editorial reviews, not native-speaker certification, a guarantee
against every possible wording defect, or a production-release certification. Technical identifiers
and user/provider-generated content are not machine-translated. Changes are local to `develop`;
this task does not publish a release or push to a remote repository.
