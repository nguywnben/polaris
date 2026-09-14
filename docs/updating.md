# Updating and Rolling Back Compose

Polaris R1 supports an immutable-image update workflow for the canonical standalone SQLite
Compose deployment. The workflow performs preflight, encrypted backup, image replacement, health
verification, and automatic rollback as one operation. It does not support Docker `run`, external
databases, Kubernetes, multiple workers, or multiple replicas.

## Before You Begin

1. Choose an exact release such as `0.1.0-beta.1` or a registry digest. The updater rejects untagged
   images, `latest`, and `edge`.
2. Keep the same root `.env`, Compose files, project name, and `DATA_VOLUME` used by the running
   deployment. Preflight compares the rendered environment and `HOST_PORT` with the active
   container and fails before mutation when they differ. It never copies container secrets back to
   the host.
3. Store the backup passphrase in a password manager. It is prompted through the terminal and is
   never accepted as an argument, stored in the recovery record, or logged.
4. Ensure the host recovery directory has enough free space. Its default is
   `~/.polaris/recovery`, outside the Docker data volume.

If the release also changes the maintained Compose files, fetch and select that exact release
before the dry run; do not update from a floating branch:

```bash
git fetch --tags
git switch --detach v<version>
```

The ignored `.env` remains in the checkout. Review `git status` before switching when the checkout
contains local source changes.

## 1. Run the Read-Only Plan

From the repository root on Linux/macOS:

```bash
python3 tools/compose_update.py update \
  --target-image nguywnben/polaris:<version> \
  --dry-run
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/compose_update.py update `
  --target-image nguywnben/polaris:<version> `
  --dry-run
```

Add the same project name used at installation when Compose cannot derive it from the current
directory:

```text
--project-name <existing-project-name>
```

For an advanced deployment, repeat `--compose-file` in the same order used to start it:

```bash
python3 tools/compose_update.py update \
  --target-image nguywnben/polaris:<version> \
  --compose-file deploy/docker-compose.yml \
  --compose-file deploy/compose.advanced.yml \
  --dry-run
```

Dry-run checks Docker/Compose availability, the selected files, project topology, current health,
effective environment, published port, image identity, and named data volume. It does not pull,
prompt, create a file, or change a container.

## 2. Perform the Update

Repeat the accepted command without `--dry-run`:

```bash
python3 tools/compose_update.py update \
  --target-image nguywnben/polaris:<version>
```

The tool then:

1. pulls the versioned reference and resolves it to an immutable local image ID;
2. creates a consistent encrypted `.ogb` backup from the running previous image;
3. atomically writes the archive and a checksum-bound JSON recovery record on the host;
4. recreates only the `app` service using the resolved image ID; and
5. waits up to 90 seconds for Docker's `/ready` health check.

Use `--health-timeout <10-600>` only when slower hardware requires it. A successful update prints
`Result: updated` and the recovery-record path. Open the console and verify a normal inference
request before removing any old recovery artifact.

Exit status is part of the automation contract:

| Exit | Meaning |
| --- | --- |
| `0` | Dry-run accepted, update completed, or explicit rollback completed |
| `1` | Preflight/update/rollback could not complete; read the safe diagnostic and recovery record |
| `2` | Target update failed, but automatic image and snapshot rollback completed successfully |

`--passphrase-stdin` exists only for controlled non-interactive rehearsal. Do not pipe a literal
secret from shell history in production.

## Automatic Rollback

If target recreate fails, health times out, or the operator interrupts after replacement begins,
the updater stops `app`, restores the encrypted snapshot through a one-off unprivileged container,
recreates `app` with the previous immutable image ID, and requires it to become healthy. The same
named volume is supplied explicitly throughout the operation.

`Result: rolled_back_after_failed_update` means the failed target did not remain active and the
previous image plus pre-update state were recovered. The non-zero exit prevents automation from
mistaking recovery for a successful update.

If the result is `rollback_failed`, leave the recovery archive and JSON record in place. Do not
delete or recreate the named volume. Correct the reported Docker/Compose/storage problem, then run
the explicit rollback below.

## Explicit Rollback

Use the record printed by the successful update:

```bash
python3 tools/compose_update.py rollback \
  --record ~/.polaris/recovery/update-<timestamp>-<id>.json \
  --dry-run

python3 tools/compose_update.py rollback \
  --record ~/.polaris/recovery/update-<timestamp>-<id>.json
```

PowerShell accepts the same arguments with
`.\.venv\Scripts\python.exe tools/compose_update.py`. The record is authoritative for the previous
and target image IDs, Compose file list, project name, named volume, archive location, and archive
checksum. Rollback fails closed if the active image is unrelated, the record is malformed, or the
encrypted archive changed.

After rollback, verify:

```bash
docker compose -f deploy/docker-compose.yml ps
curl -fsS http://127.0.0.1:4283/health
curl -fsS http://127.0.0.1:4283/ready
```

Open the console, sign in again, and verify routing, providers, access keys, usage totals, and one
inference request. Restore-related session reauthentication is expected.

## Recovery Artifact Retention

Keep the newest known-good `.ogb` and matching update JSON somewhere protected outside the live
Docker volume until the updated version has been verified. The tool never prunes recovery points
because it cannot decide which operator checkpoint is safe to delete. Remove obsolete pairs
manually after checking free space and retaining the recovery point required by your policy.
