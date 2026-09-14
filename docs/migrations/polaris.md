# Migrating to Polaris

Polaris is the new public name and distribution identity of the project formerly published as
Omni Gateway. The application protocol, persisted credentials, encryption domains, and existing
client keys remain compatible during the rename.

## Public coordinates

Use these coordinates for new installations and updates:

- Repository: `https://github.com/nguywnben/polaris`
- Docker Hub: `nguywnben/polaris`
- GitHub Container Registry: `ghcr.io/nguywnben/polaris`
- Compose data volume for new installations: `polaris-data`

The former Docker Hub and GHCR coordinates continue to receive the same image tags during the
migration window. New automation should move to the Polaris coordinates now.

## Upgrade an existing Compose installation

Existing installations must keep using their current `omni-gateway-data` volume unless the data is
copied deliberately. Set the volume explicitly before switching image coordinates:

```dotenv
IMAGE=nguywnben/polaris:1.5.0
DATA_VOLUME=omni-gateway-data
```

Then follow the normal encrypted backup, update, health-check, and rollback procedure in
[Updating and rollback](../updating.md). Changing only the image coordinate does not rewrite stored
credentials or configuration.

## Stable compatibility identifiers

The following identifiers intentionally remain unchanged in this migration because changing them
in place would invalidate clients or persisted security state:

- API keys continue to use the `sk-ogw-` prefix.
- The virtual model alias remains `omway`.
- Existing environment contracts such as `OMNI_RUNTIME_MODE` remain accepted.
- Cryptographic domains, backup format identifiers, browser storage keys, and database defaults
  retain their existing values.

These are compatibility contracts, not the current product name. A future removal would require a
separate versioned migration with dual-read support and an announced deprecation window.

## Rollback

Rollback uses the previous immutable image reference and the same explicit data volume. Do not
delete or rename the volume as part of a rollback. Repository redirects and legacy image aliases
allow older automation to keep resolving while operators migrate.
