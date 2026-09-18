# Docker-run backup, update and recovery

Applies to the [guided Docker installation](docker-install.md), not Compose. These are
Linux/Bash commands for an administrator. Replace names consistently if you installed with
a custom `--name`. This is a manual maintenance path, not an automatic updater.

## Stop or start without deleting data

```bash
docker stop polaris
docker start polaris
```

Do not remove `polaris-data` or use volume-pruning commands to troubleshoot Polaris.

## Consistent offline backup

Stop Polaris while archiving SQLite and the other data files. Keep the old image ID so a
later rollback does not rely on a mutable tag. Run these commands in a private directory:

```bash
(
  set -e
  umask 077
  backup="polaris-data-$(date +%Y%m%d-%H%M%S).tar.gz"
  old_image=$(docker inspect --format '{{.Image}}' polaris)
  docker stop polaris
  trap 'docker start polaris >/dev/null' EXIT
  docker run --rm --network none --read-only --entrypoint tar \
    --mount type=volume,src=polaris-data,dst=/data,readonly \
    "$old_image" -czf - -C /data . > "$backup"
  tar -tzf "$backup" >/dev/null
  printf 'Backup: %s\nOld image: %s\n' "$backup" "$old_image"
)
```

The subshell stops on failure and attempts to restart Polaris even if archiving fails.
Confirm Polaris is running afterward; a failed archive is not a backup. The file contains credentials and other
secrets in **unencrypted** form: permissions are restricted by `umask`, not encryption.
Keep it private and use encrypted storage before copying it off the machine. Do not commit
or attach it to support tickets. For an encrypted application export, use the console backup
feature; the offline archive additionally preserves the complete Docker volume.

## Manual update with rollback isolation

Make and validate the backup above first. This procedure is for an installation whose owner
account has already been created. Read the target release's migration notes. Do not infer
that restoring a database upgraded by a new version is safe for an older version.

1. Pull the intended version and retain `old_image` and the backup. Do not use `latest` as
   a substitute for choosing a target version. Set the `old_image` and `backup` shell variables
   to the exact values printed by the backup command (its subshell does not export them).

   ```bash
   read -r -p 'Target image (explicit version or digest): ' target_image
   docker pull "$target_image" && new_image=$(docker image inspect --format '{{.Id}}' "$target_image")
   ```

   Continue only if the pull and inspection succeed. The replacement below uses that
   exact `new_image` ID, not a hardcoded old tag.
2. Stop `polaris` and take a **fresh** backup if any data changed after the earlier backup.
3. Restore that archive into a **new** volume, not over the original. Confirm the target
   name is unused with `docker volume ls` before creating it:

   ```bash
   docker volume create polaris-next-data
   docker run --rm -i --network none --read-only --entrypoint tar \
     --mount type=volume,src=polaris-next-data,dst=/data \
     "$old_image" -xzf - -C /data < "$backup"
   ```

   Only restore your own trusted archive. Root extraction preserves the numeric ownership
   needed by the non-root application. Treat backup files from other people as untrusted.

4. Preserve the stopped original container:

   ```bash
   docker rename polaris polaris-before-update
   ```

5. Set `port_binding` and `http_policy` to the original installation's settings. These
   defaults retain local-only access; for an existing public HTTP deployment whose risks
   you accept, use `0.0.0.0:4283:4283` and `true`. Preserve any additional custom settings.
   The owner already exists in the restored data, so no setup token or password override
   is passed:

   ```bash
   port_binding=127.0.0.1:4283:4283
   http_policy=false
   docker run -d --name polaris --restart unless-stopped --init --read-only \
     --stop-timeout 45 --publish "$port_binding" \
     --env "SETUP_ALLOW_INSECURE_HTTP=$http_policy" \
     --env HOST=0.0.0.0 --env PORT=4283 --env WORKERS=1 \
     --env POLARIS_RUNTIME_MODE=standalone --env POLARIS_REPLICA_COUNT=1 \
     --mount type=volume,src=polaris-next-data,dst=/app/backend/data \
     --tmpfs /tmp:rw,noexec,nosuid,size=64m --security-opt no-new-privileges:true \
     --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
     "${new_image:?Select and pull the target image first}"
   ```

   Never copy a preconfigured `PANEL_PASSWORD` over your stored owner without understanding
   its precedence.
6. Wait for `healthy`, sign in with the existing password, and verify configuration and
   credential counts. Do not delete the original container or volume until satisfied.

To roll back **before sending real traffic to the new version**, stop the new container,
preserve it under an unused name, and start the old one:

```bash
docker stop polaris
docker rename polaris polaris-update-failed
docker rename polaris-before-update polaris
docker start polaris
```

The original container still uses the untouched original volume and old image ID. Data
written only to the new volume will not be present after rollback; reconcile it before
rolling back a version already in use. Keep both volumes until recovery is confirmed.

## Recovery after losing a container

If `polaris-data` still exists, the data is not lost. Use the manual Docker command with
that **verified original** volume, the intended compatible image and the previous access
policy. When an owner already exists, omit setup-token generation; log in normally. If setup
was never completed, generate a fresh setup code as in the manual installation example.

If the original volume is unavailable, restore a trusted backup into a new named volume as
above and run against that volume. Do not overwrite surviving data to test a recovery.
