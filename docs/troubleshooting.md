# Production Troubleshooting

Use this guide for the supported single-machine, one-worker, one-replica Docker Compose deployment.
Start with observation, preserve recovery options, and change only one documented setting at a
time. Coordinated state, multiple workers, multiple replicas, and Kubernetes are outside this
production support path.

## First five minutes

Run these commands from the release checkout that owns the deployment:

```text
docker compose -f deploy/docker-compose.yml ps
curl --fail http://127.0.0.1:4283/health
curl --fail http://127.0.0.1:4283/ready
docker compose -f deploy/docker-compose.yml logs --tail 200 app
```

`GET /health` confirms that the process can answer HTTP. `GET /ready` also checks required
application dependencies and is the deployment decision signal. Record the HTTP status, UTC time,
image ID, and any displayed `X-Request-ID`. Do not publish cookies, API keys, provider credentials,
setup tokens, passwords, authorization headers, or raw prompts and responses.

**Do not delete the data volume.** A volume deletion is not a repair step. Before any storage or
version change, create and verify an encrypted backup using
[Backup and Restore](backup-and-restore.md).

## Setup, login, and local recovery

- If Setup appears unexpectedly, stop and verify that the expected named volume is mounted. Do not
  create a second owner over an unexplained empty data path.
- If the owner password is rejected, confirm the browser is using the current host and HTTPS policy,
  then use the documented local-owner recovery flow. Recovery remains available when optional OIDC
  is unavailable.
- A process restart intentionally invalidates browser sessions in the supported standalone mode.
  Sign in again; durable identities, bindings, and settings must remain.
- Repeated failures may trigger bounded throttling. Wait for the response's retry guidance instead
  of restarting repeatedly or weakening authentication controls.

## Provider and routing failures

Open **Pool** and run the provider-specific connection diagnostic. Then inspect **Models** for route
eligibility and cooldown reasons and **Activity** for the request ID. A provider can be reachable
while a credential lacks model entitlement, quota, or a required authentication capability.

Do not paste raw upstream errors into an issue. Record the safe diagnostic category, provider/auth
variant, model alias, gateway request ID, status code, retry guidance, and whether fallback was
attempted. Test one credential before applying a mixed-provider bulk action.

## Slow requests or resource pressure

Check Dashboard latency, active requests, recent errors, container CPU/memory, and Activity for the
same time window. Confirm that the host is not running the amd64 image under unexpected emulation.
Token compression is quality-aware and configurable; use AI Quality preview before changing its
threshold or disabling it for a virtual key/request. Never treat truncation of system instructions,
tools, or the latest user turn as an acceptable performance fix.

## Storage and readiness failures

If `/health` succeeds but `/ready` fails, inspect the bounded application log and the selected
storage mode. SQLite is Core, PostgreSQL is Advanced, and MongoDB is Compatibility. Do not switch
backends during an incident without the documented migration and verified recovery artifact.
Preserve the current `.env`, image ID, release checkout, and named volume until the cause is known.

## Update failure and explicit rollback

Use the dry-run-first [Update and Rollback](updating.md) workflow. Its **Explicit rollback** restores
the previously recorded immutable image and encrypted pre-update snapshot, then verifies `/ready`.
Do not improvise a downgrade by copying database files or pulling `latest`.

## Redacted support bundle

Collect only the following after reviewing every file for secrets:

1. `docker version`, `docker compose version`, and Linux engine OS/architecture;
2. release tag, application version from About, and immutable image ID;
3. sanitized Compose configuration with all secret values replaced by `<redacted>`;
4. `/health` and `/ready` status plus UTC timestamps;
5. the smallest relevant bounded log window and request IDs; and
6. exact reproduction steps, expected result, actual result, and whether rollback succeeded.

Never include `.env`, the data volume, database files, encrypted-backup passphrases, browser storage,
credentials, cookies, tokens, authorization headers, or prompt/response bodies. When reporting an
issue, use the repository's security policy for vulnerabilities and the normal issue template for
redacted operational defects.
