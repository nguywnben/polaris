# Compose Update and Rollback Contract

Status: implemented and verified
Target: Production Self-Hosted R1 standalone Compose deployment

## Supported Boundary

The supported updater operates one `app` service from `deploy/docker-compose.yml`, optionally with
explicit Compose override files. It preserves the configured `DATA_VOLUME`, one worker, and one
replica. It does not manage Kubernetes, multiple replicas, external databases, or coordinated HA.

The workflow is host-driven and cross-platform through Python. Docker Compose remains the runtime
authority; the tool does not edit `.env`, Compose files, Git branches, or release tags.

## Update Contract

`python tools/compose_update.py update --target-image <version-or-digest>` performs these ordered
operations:

1. Verify Docker, Compose, the selected Compose files, the running `app` container, its health, and
   the configured volume without mutation.
2. Reject an untagged image or a floating tag such as `latest` or `edge`.
3. Pull a versioned registry reference, then resolve it to a local immutable image ID. An explicit
   digest or local image ID is inspected directly. Every subsequent Compose mutation uses the
   resolved image ID rather than the supplied tag.
4. Prompt for a backup passphrase without placing it in arguments, environment variables, logs, or
   the update record.
5. Create a consistent P1.4 encrypted `.ogb` archive from the running previous image and persist it
   atomically in a host recovery directory outside the application data volume.
6. Persist an update record containing the previous and target image IDs, backup path, Compose
   files, project identity, and current workflow state.
7. recreate only `app` with the target image ID and wait for Docker's `/ready` health check.
8. On success, retain the encrypted backup and update record for explicit operator rollback.

`--dry-run` performs only read-only preflight and prints the exact ordered plan. It never pulls an
image, prompts for a passphrase, creates files, stops/recreates a container, or restores data.

## Automatic Rollback Contract

If recreate fails, target health times out, or the operator interrupts after mutation begins, the
tool must:

1. stop the target `app` service;
2. run the previous image as an isolated one-off container with the same data volume;
3. restore the encrypted pre-update `.ogb` snapshot while the service is stopped;
4. recreate `app` from the previous immutable image ID;
5. require the previous image to become healthy; and
6. record either successful rollback or a bounded failure requiring operator action.

The restore passphrase is transferred over process standard input using a bounded binary frame. It
is never written to the update record. The one-off restore runs as the application's unprivileged
UID/GID and does not publish ports or start dependencies.

## Explicit Rollback Contract

`python tools/compose_update.py rollback --record <record.json>` validates the update record,
verifies that its backup is a regular `.ogb` file and that the active image matches the recorded
target, then executes the same stopped-service snapshot restore and immutable previous-image
recreate. A dry run displays the rollback plan without mutation.

## Recovery Artifacts

The default host directory is `~/.polaris/recovery`; operators may override it with
`--recovery-dir`. Archive and record creation is atomic and permission-restricted where the host
supports POSIX modes. Artifacts are retained until the operator explicitly removes them.

## Acceptance Evidence

- Unit contracts prove floating-reference rejection, dry-run non-mutation, secret-free command and
  record construction, and fail-closed record validation.
- A two-version isolated Compose rehearsal proves a healthy synthetic update.
- A forced unhealthy target proves automatic restoration of the previous image and encrypted state
  snapshot.
