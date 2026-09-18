# Guided Docker installer verification — 2026-09-18

Local preparation only. No image/tag/release was published and no VPS was modified.

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

## Before publication

- Complete a fresh Linux/amd64 host rehearsal including the interactive terminal prompts
  and external reachability through the operator's cloud firewall.
- Publish only with owner approval, matching the reviewed installer and image. The old
  release does not contain this flow; do not advertise its download command as ready yet.
- Retain the existing Compose path and its separate update/rollback contract.
