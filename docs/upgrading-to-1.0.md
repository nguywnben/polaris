# Upgrading to Polaris 1.0

Version 1.0.0 establishes the stable API, configuration, storage, and container-channel baseline. Upgrade a disposable copy first when moving an existing beta deployment.

## Before Upgrading

1. Stop write traffic to the existing instance.
2. Back up the entire persistent data directory, including credentials, SQLite data, configuration, usage records, and logs.
3. Record the currently running image tag and digest so rollback does not depend on a mutable tag.
4. Validate the backup by listing or extracting it on another machine.

For the documented Docker layout:

```bash
sudo tar -C /opt -czf "polaris-backup-$(date +%Y%m%d-%H%M%S).tar.gz" polaris
sudo docker inspect --format='{{.Image}}' polaris
```

## Breaking Changes from 0.x

### Environment Variables

Rename beta variables before starting 1.0.0:

| Removed beta variable | 1.0 variable |
| --- | --- |
| `PASSWORD` | `PANEL_PASSWORD` |
| `CLIENT_ID` | `ANTIGRAVITY_CLIENT_ID` |
| `CLIENT_SECRET` | `ANTIGRAVITY_CLIENT_SECRET` |
| `API_URL` | `ANTIGRAVITY_API_URL` |
| `USER_AGENT` | `ANTIGRAVITY_USER_AGENT` |
| `OAUTH_PROXY_URL` | `OAUTH_URL` |
| `GOOGLEAPIS_PROXY_URL` | `GOOGLE_APIS_URL` |
| `RESOURCE_MANAGER_API_URL` | `RESOURCE_MANAGER_URL` |
| `SERVICE_USAGE_API_URL` | `SERVICE_USAGE_URL` |
| `ANTIGRAVITY_STREAM2NOSTREAM` | `STREAM_TO_NONSTREAM` |
| `ANTIGRAVITY_SWITCH_CREDENTIAL` | `SWITCH_CREDENTIAL_ENABLED` |

`PASSWORD` stops startup when it is the only configured console password. Other removed aliases are ignored with a migration warning. Stored beta password and OAuth client keys are migrated automatically on first successful startup.

### Management Routes

Replace every `/api/creds/...` call with `/api/credentials/...`. The beta alias is removed and returns `404` in 1.0.0.

### External Storage

Configure no more than one of `MONGODB_URI` and `POSTGRESQL_URI`. When an explicitly configured external database cannot initialize, startup now fails instead of silently creating or using local SQLite. This prevents operators from writing to an unintended database.

### Runtime Topology

Keep `WORKERS=1` and run one application replica. External databases do not coordinate credential reservations, cooldowns, sessions, or usage aggregation across processes.

### Container Channels

- `1.0.0` is the immutable release tag for this version.
- `latest` tracks the newest stable release.
- `edge` tracks verified builds from `main` and can contain unreleased changes.

Production deployments should pin a version tag or image digest. Use `latest` only when automatically adopting future stable releases is intentional.

## Upgrade Procedure

```bash
sudo docker pull nguywnben/polaris:1.0.0
sudo docker stop polaris
sudo docker rm polaris
```

Recreate the container with the same persistent mounts and canonical environment variables. Then verify:

```bash
curl --fail http://127.0.0.1:4283/health
curl --fail http://127.0.0.1:4283/ready
sudo docker logs --tail 200 polaris
```

Sign in to the console, confirm the credential count, refresh the provider model catalog, and send one request through each SDK surface used by your clients.

## Rollback

Stop and remove the 1.0.0 container, restore the data-directory backup, and recreate the previous container by its recorded digest. Do not run two versions against the same writable data directory at the same time.
