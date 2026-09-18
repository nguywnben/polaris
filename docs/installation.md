# Canonical Installation

This is the single production installation path for Polaris R1. It runs the supported
standalone topology—one application worker and one replica—through Docker Compose with SQLite in
one named volume. Do not add Redis, an external database, or the advanced override during the
first installation.

This guide targets `1.0.0`. Run the release download/pull commands only after the
matching Polaris tag and images are published. For an unpublished source checkout,
follow the [1.0.0 publication checklist](releases/1.0.0-preparation.md), build a unique
local image and override `IMAGE`. Historical tags are archived separately and are not
substitutes for the new release. Use matching `v1.0.0`/`1.0.0` versions below, not
`latest` or `edge`.

## 1. Check the host

All canonical hosts need Git, an unused TCP port (4283 by default), and Docker Compose v2 with a
running Linux container engine:

```text
docker version
docker compose version
docker info --format '{{.OSType}}/{{.Architecture}}'
```

The final command must report a Linux engine. Apply the host-specific prerequisite before
continuing:

- **Windows:** run Docker Desktop with its WSL2 backend and Linux containers. `wsl --status`
  should report default version 2. Docker Desktop does not require a separately installed Ubuntu
  distribution for this Compose path.
- **Linux:** install Docker Engine and the Docker Compose v2 plugin. Use an account authorized to
  access the Docker daemon, or consistently prefix the Docker commands with `sudo`.
- **macOS:** install and start Docker Desktop. The data volume lives inside Docker Desktop's Linux
  virtual machine. See the architecture limitation and manual check below before relying on an
  Apple Silicon host.

## 2. Download one release

Use a release tag so the checked-out Compose file and the image version stay reproducible:

```text
git clone --branch v1.0.0 --depth 1 https://github.com/nguywnben/polaris.git
cd polaris
```

If the repository already exists, check out the intended release in a clean working tree instead
of copying deployment files between versions.

## 3. Create the minimal configuration

On Linux or macOS:

```text
cp deploy/compose.env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item deploy/compose.env.example .env
```

The template pins the image, host port, and data-volume name. For interactive setup on the same
machine, leave `API_KEY`, `PANEL_PASSWORD`, and `SETUP_TOKEN` empty. Before an unconfigured console
can be reached through a non-loopback host, set a unique `SETUP_TOKEN` of at least 24 characters,
or set a unique 12–256 character `PANEL_PASSWORD` for non-interactive bootstrap. Never commit the
populated `.env` file.

## 4. Start and wait for readiness

Validate the rendered model before Docker changes anything, pull the pinned release, then wait for
the storage-aware readiness probe:

```text
docker compose -f deploy/docker-compose.yml config --quiet
docker compose -f deploy/docker-compose.yml pull
docker compose -f deploy/docker-compose.yml up --detach --wait --wait-timeout 60
docker compose -f deploy/docker-compose.yml ps
```

Check readiness without exposing a secret:

```text
curl --fail http://127.0.0.1:4283/ready
```

In PowerShell, use `Invoke-WebRequest http://127.0.0.1:4283/ready` if `curl` is unavailable. If the
service is not ready, inspect only this deployment with
`docker compose -f deploy/docker-compose.yml logs app`; do not delete the data volume.

## 5. Complete first-run setup

Open `http://127.0.0.1:4283/` on the host running Docker. Complete the displayed preflight and
create the local owner with a unique 12–256 character passphrase. For a remote host, first provide
HTTPS through a trusted reverse proxy or use a secure tunnel; enter the configured setup token
when prompted. The application never generates or prints that token.

### Explicit HTTP opt-in for a remote host

HTTPS is recommended, but a domain name is not a Polaris requirement. If the server owner
accepts unencrypted access, set `SETUP_ALLOW_INSECURE_HTTP=true` in the root `.env` together
with a strong `SETUP_TOKEN`. Recreate the container to apply environment changes:

```text
docker compose --env-file .env -f deploy/docker-compose.yml up --detach --wait
```

Then open `http://YOUR_PUBLIC_IP:4283/` (or your configured host port). The host port must be
published and permitted by the host/cloud firewall. Setup displays an HTTP warning even after
the checks pass. **HTTP does not encrypt setup tokens, passwords, session cookies, API keys
or other traffic; an on-path attacker can read or modify it.** Only enable this option after
accepting that risk. Do not enable trusted proxy headers for a directly exposed HTTP listener.

The option defaults to `false`, is controlled only by the server environment, and relaxes only
the initial setup HTTPS check. It does not bypass the setup token, password policy, durable
storage check, authentication, or origin protection. Keep `PANEL_COOKIE_SECURE` in automatic
mode for direct HTTP; explicitly requiring secure cookies still prevents HTTP setup. HTTPS
continues to require secure cookies even when the option is enabled.

To return to HTTPS, configure TLS and trusted proxy handling as appropriate, change the option
back to `false`, and recreate the container. **The flag is not a post-setup HTTP access firewall**:
restrict or close the public HTTP listener separately. Do not delete the data volume.

The setup flow creates the public API key once and displays it for the operator. Store it in a
password manager; do not put it in source control or screenshots.

Gemini-compatible clients may send that key as the `key` query parameter on `/v1beta/*`. Prefer
`x-goog-api-key` or `Authorization: Bearer` whenever the client supports headers. If a reverse
proxy is present, configure its access log to omit query strings on these routes so the
compatibility credential is not retained in URLs.

## 6. Verify authenticated operation

Sign in with the owner passphrase and open `http://127.0.0.1:4283/dashboard`. A completed install
must satisfy all of these checks:

- `/ready` returns a successful status;
- the Dashboard loads after authentication without returning to Setup;
- the Settings page reports the standalone one-worker runtime; and
- after `docker compose -f deploy/docker-compose.yml restart`, the same owner can sign in and the
  installation remains configured.

Keep the `.env` file, the named volume, and the release tag together in the operator record. Use
the [encrypted backup and restore guide](backup-and-restore.md) before moving data and the
[health-checked update guide](updating.md) before changing versions. Use the
[production troubleshooting guide](troubleshooting.md) before changing configuration or storage
in response to an incident.

## Support matrix

The machine-readable source for this table is `deploy/install-support.json`.

| Host path | Tier | Evidence | Production status |
| --- | --- | --- | --- |
| Windows + Docker Desktop + WSL2, Linux containers | Core | Local clean-install rehearsal | Supported for `linux/amd64` |
| Linux + Docker Engine + Compose v2 | Core | Required Ubuntu CI Compose smoke | Supported for `linux/amd64` |
| macOS + Docker Desktop | Core equivalent | Manual checklist below | Intel/amd64 requires the manual check; Apple Silicon native ARM64 is not published |

The published production image platform is **`linux/amd64`**. **`linux/arm64` is not published**:
the locked provider dependency stack does not yet have equivalent build and runtime evidence.
Running the amd64 image through Apple Silicon emulation is a compatibility path, may be slower,
and does not establish native ARM64 support.

### Remaining macOS manual check

On an Intel Mac, or an Apple Silicon Mac explicitly accepting amd64 emulation, run sections 1–6
unchanged and record:

1. `docker info` engine OS/architecture and `docker compose version`;
2. successful `config --quiet`, pull, and `up --wait` exit codes;
3. `/ready` response plus authenticated Dashboard access;
4. successful sign-in and retained configuration after `docker compose restart`; and
5. `docker compose down` without `--volumes`, followed by `up --wait` and another authenticated
   sign-in.

Until that record exists for the release, macOS is documented as an equivalent Compose host with
a required operator check, not as independently CI-verified.

## Non-canonical paths

The native Python installers and launchers in `deploy/scripts`, direct `docker run`, Render, and
Zeabur are compatibility paths. They may help development, migration, or community deployments,
but they do not receive the complete production install/update/rollback evidence. Kubernetes is
outside the product boundary. These alternatives must not be used
to infer support for another architecture, multiple workers, or multiple replicas.

To stop the canonical service while preserving data:

```text
docker compose -f deploy/docker-compose.yml down
```

Do not add `--volumes` unless permanent deletion of the named application data is intentional and
an independently verified encrypted backup exists.
