# Guided Docker installer verification — 2026-09-18

No push, image/tag publication or release occurred in this verification round.
The initial local-only record is preserved below; the owner subsequently authorized
installation and final verification on the selected test VPS.

## Final candidate and native Ubuntu rehearsal

Runtime revision: `fec038866acae3cea26d259048493713e0ddb205`.
Local image: `polaris-final:fec0388`, version metadata `1.0.0` (not a published tag).
Image ID: `sha256:0ac3f25bbfc5b371b135ea801287a7857031b58a0f93a6bae48143870d0b00c5`.
Exported image archive SHA-256, checked before loading on the VPS:
`6b12110df38ee6b5abb1468f2f7ca331cc757bb5e27197b710b2961cebf02638`.
These are a local image ID and archive checksum, not a registry manifest digest.

- The guided installer was rehearsed on the owner-authorized Ubuntu 24.04 x86_64
  VPS; public access was explicitly selected. Docker is enabled at host boot and
  Polaris uses `unless-stopped`. No host reboot or unrelated service changes were made.
- Final update stopped the old container, archived its named volume offline, restored
  into a new volume, and started the new immutable image. The original stopped
  container, original volume and mode-restricted archive remain available for rollback.
  The archive is private but not encrypted; it must not be published or shared.
- External `/ready` and setup status passed. Public HTTP shows the opt-in warning;
  correct setup code passed preflight and an incorrect code was rejected. The actual
  owner's account remains uncreated; the original setup code is unchanged.
- A separate native Linux container with synthetic credentials passed
  `backend/tests/runtime_smoke.py` both at fresh setup and after restart. This checks
  owner login and authenticated application routes without claiming the real account.
  Graceful stop exited with code 0; only the label-verified smoke container and volume
  were removed. The actual updated Polaris container was also restarted and returned
  healthy, with its original setup code preserved and owner creation still pending.
- The final local-image Docker smoke passed setup, restart persistence, offline
  backup, restored-volume replacement and original-volume rollback. This does not
  establish arbitrary future cross-version downgrade safety.
- Canonical release gate passed: 2,330 core tests (22 existing optional storage skips),
  all 15 locales, dependency audit, configuration/compatibility checks, 9/9 browser
  journeys and 600/600 routine requests (p95 99.696 ms; dashboard 749.578 ms).
- Setup UI passed at 320/768/1440 pixels in light/dark Chromium, including empty,
  filled and cleared password-eye spacing. Physical Android behavior still needs
  owner confirmation; Chromium emulation is not device certification.
- Independent review approved the transport-policy fix: a remote peer cannot bypass
  HTTPS by supplying a loopback Host header; guided local Docker's explicit HTTP
  option is coupled to loopback-only publication. Public HTTP still requires consent.

Local logs: `temp/release-final-fec0388.log`, `temp/docker-final-fec0388.log`,
`temp/setup-ui-final-fec0388.log`. These logs are local artifacts, not repository files.
GitHub CI has not run on this unpushed candidate. Exact-source CI and actual
published-digest installation remain required after renewed publication approval.
The documentation-only handoff additionally passed 27 install/product/release contract
tests and `release_preflight.py --tag v1.0.0`; it does not change the tested runtime.

## Initial local checkpoint (historical)

## Environment and scope

Windows host, Git Bash, Docker Desktop Linux/x86_64 engine; locally built image
`polaris-install-test:local`, using the pinned base and locked dependencies in
`deploy/Dockerfile`. The image is not the previously published 1.0.0 artifact.
This demonstrates real container behavior, not a fresh native Ubuntu/VPS installation
or macOS/ARM64 certification. Native Linux interactive installation remains a release check.

## Runtime checks

`python tools/docker_install_smoke.py` passed against unique, isolated resources:

- Installer generated a private setup code, bound to loopback and waited for health.
- Wrong setup code rejected; owner created; authenticated API access succeeded.
- Restart preserved the owner login and application API key.
- A stopped-volume tar backup restored into a separate volume with working ownership.
- Replacement container retained the login and key; original-volume rollback worked.
- Generated setup code was absent from container stdout logs.
- Test cleanup verified names and ownership labels and removed only its own test data.

The replacement rehearsal uses the same locally built application image on the restored
volume. It verifies the replacement/recovery mechanism, not cross-version database downgrade
compatibility; future releases must test their own migrations.

`python tools/http_setup_smoke.py` passed default remote-HTTP rejection, explicit opt-in,
wrong-code rejection, setup, cookie properties, logout/login, and repeat-setup rejection.

## Automated checks

- Installer subprocess tests use a fake Docker executable to cover input validation,
  HTTP consent, missing/unreachable Docker, unsupported engine/architecture, remote contexts,
  incompatible images, pull failures, existing resources, creation races, startup errors,
  health timeouts, and local-image selection. No live daemon is used by unit tests.
- Install-support and product-surface tests check configuration and all 15 READMEs.
- Fast quality gate covers Python lint/format/compile, test inventory, recursive frontend
  syntax, deployment YAML, shell syntax and whitespace.
- Full core regression: 2,327 tests completed in 505.974 seconds, OK with 22 existing
  conditional skips (`temp/simple-docker-core.log`, local only). The subsequently added
  volume-race and all-README storage regressions were verified in focused runs:
  11 installer tests and 18 install-support/product-inventory tests passed.
- Independent review identified and verified fixes for volume-creation races, cleanup
  guards under optimized Python, and explicit target-image selection in update instructions.

## Before publication (updated)

- Native Linux/amd64 interactive installation and external reachability were completed
  on the owner-authorized test VPS as recorded above. This is not macOS/ARM64 coverage.
- Publish only with owner approval, matching the reviewed installer and image. The old
  release does not contain this flow; do not advertise its download command as ready yet.
- Retain the existing Compose path and its separate update/rollback contract.
