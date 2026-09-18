# Release Checklist

Use this checklist when preparing a tagged Polaris release.

For the new `1.0.0` line, complete the [version-reset publication checklist](releases/1.0.0-preparation.md)
first. Existing legacy tag/image names must not silently be reused. Undated release notes
are intentionally rejected by `python tools/release_preflight.py --tag v1.0.0` before image publication.

## Automated Gates

- Inspect the immutable release plan with `python tools/quality_gate.py release --dry-run` and resolve
  every `pending` entry through its existing owner task.
- Run the single local command `python tools/quality_gate.py release` on the candidate commit.
- Confirm its release-blocking routine completed through
  `python tools/reliability_profile.py --profile routine --verify` (120 seconds at 5 RPS).
- Confirm the required CI application, Chromium browser, and container smoke jobs passed for the
  same commit.
- Regenerate `requirements.lock` and confirm that `git diff --exit-code requirements.lock` is clean.
- Confirm the CI container smoke test builds the image and completes setup, login, management API, and invalid-key checks.
- Confirm public authentication, validation, upstream, and pre-stream errors match the OpenAI, Anthropic, and Google GenAI envelopes.
- Confirm every public response includes a bounded `X-Request-ID`.
- Confirm oversized fixed-length and chunked requests return `413` in the selected SDK envelope.

The separately listed optional storage and provider suites are not release gates. Report their
latest result under their own classification only; an unavailable external environment cannot
change the production result.

### Optional soak

For a major release or when investigating memory growth, run the preserved ten-minute profile with
`python tools/reliability_profile.py --profile soak --verify`. It is useful supplementary evidence,
not a release blocker for routine personal or trusted-team deployments.

## Manual Provider Checks

These real-provider checks are optional evidence because they require external accounts and quotas.
Core provider behavior is release-blocking through deterministic contracts instead.

- Add one Google Antigravity credential through OAuth and complete a message test.
- Add one Google AI Studio key and complete a message test.
- Add one Grok Build credential through OAuth and complete a message test.
- Open the Grok Build credential quota view and confirm monthly usage is displayed.
- Add one SpaceXAI Console key and complete a message test.
- Add one Codex account through device OAuth, confirm its account model catalog, and complete a message test.
- Add one OpenAI Platform key, confirm its account model catalog, and complete a message test.
- Add one Claude Code account through PKCE OAuth and complete a message test.
- Add one Claude Platform key, confirm its account model catalog, and complete a message test.
- Add one local Ollama endpoint and one protected or remote endpoint when available; confirm model discovery and complete a message test.
- Refresh the model catalog and route `polaris` through at least one compatible model from every configured provider type.
- Configure two credentials from the same provider with different model catalogs; confirm a fixed model uses only compatible credentials and that one credential's model-not-found response does not disable the route for the other credential.
- Remove one entry from **Unavailable Model Routes**, revalidate its credential, and confirm the route becomes eligible again without changing unrelated provider routes.
- Send one non-streaming and one streaming request through each supported SDK surface.
- Confirm token usage, provider attribution, fallback, cooldown, and context-compression metrics update.
- Export the pool, restore it into a clean disposable instance, and verify deduplication results.
- Exercise the console in a real browser at desktop and mobile widths; verify every page, modal, form, navigation action, and empty/error state without console errors or horizontal page overflow.

## Deployment Checks

- Test the exact `linux/amd64` image on a clean host with persistent credential and log mounts.
- Confirm remote first-run setup rejects missing/weak tokens and accepts a strong operator-configured `SETUP_TOKEN` without printing it in application or container logs.
- Put the service behind TLS and verify secure cookies and forwarded-header configuration.
- Back up the persistent data directory before upgrading an existing instance.
- Record the previous image digest for rollback.
- Confirm a stable version tag publishes `latest` and semantic-version tags. A prerelease tag must
  publish only its prerelease semantic tag, while a default-branch build publishes `edge` without
  moving `latest`.
- When upgrading a beta deployment, perform the documented [1.0 upgrade](upgrading-to-1.0.md) against a copy of the existing data.

## Release Steps

1. Move completed entries from `Unreleased` to the target version in `CHANGELOG.md`.
2. Confirm `DEFAULT_APPLICATION_VERSION` matches the release tag.
3. Rebase on `origin/main` and rerun every automated gate.
4. Tag the verified commit with an annotated `vX.Y.Z` or `vX.Y.Z-prerelease` tag.
5. Let GitHub Actions publish the container and verify its digest.
6. Confirm GitHub Actions created the release from the matching changelog section before announcing it.
7. Pull the published image by digest, rerun liveness/readiness and SDK smoke checks, and record the digest in the release notes or deployment record.
