# Install Polaris with Docker — no repository clone

This guide applies to the refreshed Polaris 1.0.0 with the guided installer and HTTP
setup option. An earlier image with the same version does not contain this flow;
check the source revision and digest in the [release](https://github.com/nguywnben/polaris/releases/tag/v1.0.0).
The installer pulls the image and rejects incompatible images before creating data.
It does not update or reset an existing installation.

## Choose your operating system

You do not need Git, Python, Compose, a domain name, or a manually edited `.env` file.
You **do** need a running local Linux/amd64 Docker engine and permission to use it:

- **Linux x86_64/VPS:** install [Docker Engine](https://docs.docker.com/engine/install/).
- **Windows x86_64:** install and open [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/),
  select Linux containers, and wait for the engine to be running. Use Windows PowerShell 5.1
  or PowerShell 7, not Command Prompt. Windows Server is not this Desktop path.
- **macOS Intel:** the Bash entry point requires [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/).
  Native Mac verification is **pending**; this is not a claim of tested macOS support.
- **Apple Silicon/other ARM64:** native ARM64 images are not published. The guided
  installer refuses these engines; see the [support matrix](installation.md#support-matrix).

If Docker is missing or stopped, the installer stops with guidance. It does not install
Docker, grant privileges, change execution policies, or modify firewalls automatically.
Docker access is privileged: only run installation code from a source you trust.

The script validates the Docker engine, not every host configuration. Verification covers
Docker Desktop's Linux/amd64 engine and an owner-authorized Ubuntu 24.04 x86_64 VPS,
not macOS or ARM64. See the recorded test environment in
[installer verification](evidence/guided-docker-install-2026-09-18.md) and
[PowerShell verification](evidence/one-command-install-2026-09-19.md).

### Linux / macOS Intel (Bash)

Run this on the machine where
Polaris will live (on a VPS, inside your SSH/Termius session). Use a directory where
`polaris-install.sh` is not an existing file you want to preserve:

```bash
curl -fsSL https://raw.githubusercontent.com/nguywnben/polaris/v1.0.0/deploy/scripts/docker-install.sh -o polaris-install.sh && bash polaris-install.sh
```

To inspect before execution, run only the download portion first, read the saved script,
then run `bash polaris-install.sh`. If Docker requires sudo, run the reviewed saved script
with `sudo bash polaris-install.sh`. A failed download must not be executed.

### Windows (PowerShell)

**Source-ready, not published yet:** the new PowerShell entry point is not in the existing
`v1.0.0` tag. The following is a release-command template, **not a currently usable download**.
Replace `RELEASE_TAG` only after a release containing this file has been published:

```powershell
& ([scriptblock]::Create((Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/nguywnben/polaris/RELEASE_TAG/deploy/scripts/docker-install.ps1' -ErrorAction Stop)))
```

This downloads the complete script before parsing/executing it; HTTP/download errors stop
execution. It still runs remote code, so read the script at that exact release first if
you want to inspect it. No permanent execution-policy change is needed. Follow your
organization's policy if script execution is restricted; do not disable its controls.

Developers can test the current checkout now (read the file first):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\docker-install.ps1 -Local
```

Here `Bypass` applies only to that new PowerShell process, not the machine/user policy;
see [Microsoft's execution-policy documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies).
When script-file execution is already allowed, use `& .\deploy\scripts\docker-install.ps1`.
Omit `-Local` for the guided questions. Do not reuse an existing container or volume name.

### What happens next

The installer asks two plain-language questions:

1. **This computer or VPS?** This computer is the default and only binds to `127.0.0.1`.
   For VPS access, enter the public IPv4 address or hostname shown by your cloud provider.
   Local mode explicitly permits HTTP inside that loopback-only deployment, because
   Docker can hide the original client address. A loopback Host header alone is not trusted.
2. **Accept HTTP risks?** For public HTTP, type `YES` after reading the warning. Enter cancels.
   HTTP does not encrypt passwords, setup codes, cookies, or API traffic. HTTPS is recommended;
   this installer does not configure certificates or a reverse proxy for you.

It downloads the image, creates persistent storage, starts Polaris, and waits for readiness.
Then it prints the address and a private setup code. Open that address, paste the code, and
create your owner password on the web. The code is not your login password; do not share it
or screenshots of the terminal. An unknown visitor cannot claim the owner without this code.

The container is called `polaris`; its data volume is `polaris-data`. Data survives container
restarts. Docker must itself start on host boot; the container uses `unless-stopped`, so one
you deliberately stop stays stopped. See [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/).

On a VPS, open `http://YOUR_PUBLIC_IP:4283`, **not** `127.0.0.1` on your laptop. If it is
unreachable, allow TCP 4283 in the cloud security rules and check the host firewall. The
installer does not alter firewall rules. Opening a port makes the service reachable; it
does not encrypt HTTP traffic.

## Existing installation or interrupted setup

The installer refuses existing container/volume names. It is not an updater and never
deletes, overwrites, or automatically starts an existing installation. For a separate test
instance, use both a different name and an unused port:

```bash
bash polaris-install.sh --local --name polaris-test --port 14283
```

PowerShell equivalent (with the reviewed script saved locally):

```powershell
& .\docker-install.ps1 -Local -Name polaris-test -Port 14283
```

If a start fails, the container and data are retained. Resolve the reported problem first
(for example, another application occupying port 4283), then:

```bash
docker logs --tail 50 polaris
docker start polaris
docker inspect --format '{{.State.Health.Status}}' polaris
```

Wait for `healthy`. If you lost the initial setup code, a Docker administrator can retrieve
it privately from the running container:

```bash
docker exec polaris python -c 'import os; print(os.environ["SETUP_TOKEN"])'
```

On Windows PowerShell 5.1, use this quoting instead:

```powershell
docker exec polaris python -c "import os; print(os.environ['SETUP_TOKEN'])"
```

This intentionally displays a secret to the administrator, not application logs. If setup
is already complete, sign in with your owner password instead. Do not reset or delete the
volume to solve a login problem. If only a volume remains after interrupted creation, stop
and use the recovery guide; a reinstall must not assume it is empty.

## Advanced and development use

The installer is optional. Run `bash polaris-install.sh --help` to see explicit options.
`--public-host HOST --accept-insecure-http` is the noninteractive equivalent of accepting
the HTTP warning; it is never enabled by default. `--wait-seconds` changes the readiness
deadline (1–900 seconds). The installer uses the local Docker daemon, not remote contexts.
PowerShell uses `-Help`, `-PublicHost HOST -AcceptInsecureHttp`, `-WaitSeconds`,
`-Name`, `-Port`, `-Image` and `-Pull always|never` for the same choices.

To test a source checkout without changing a release tag/image:

```bash
docker build -f deploy/Dockerfile -t polaris-install-test:local .
bash deploy/scripts/docker-install.sh --local --image polaris-install-test:local --pull never --name polaris-test --port 14283
```

People who want to customize Polaris can still clone the repository and use
[the Python development workflow](../README.md#local-development), build their own image, or
use [Docker Compose](installation.md). No source-run or Compose functionality is removed.

### Manual Docker command

Equivalent local-only container settings, for operators who prefer Docker commands directly.
Use a fresh installation only; inspect existing `polaris` / `polaris-data` resources first.
Do not reuse an unknown existing volume. `od` and `tr` are standard Linux utilities.

```bash
docker pull nguywnben/polaris:1.0.0
export SETUP_TOKEN="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
docker run -d --name polaris --restart unless-stopped --init --read-only \
  --stop-timeout 45 -p 127.0.0.1:4283:4283 \
  -e SETUP_TOKEN -e SETUP_ALLOW_INSECURE_HTTP=true \
  -e HOST=0.0.0.0 -e PORT=4283 -e WORKERS=1 \
  -e POLARIS_RUNTIME_MODE=standalone -e POLARIS_REPLICA_COUNT=1 \
  --mount type=volume,src=polaris-data,dst=/app/backend/data \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m --security-opt no-new-privileges:true \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  nguywnben/polaris:1.0.0
printf 'Setup code: %s\n' "$SETUP_TOKEN"
unset SETUP_TOKEN
```

For public HTTP, deliberately change the bind to `0.0.0.0:4283:4283` and retain the HTTP
option `true` **only after accepting the risks above**, using the updated image. The direct Docker
command does not perform the installer's compatibility/readiness/collision checks. Follow
the health check above before opening the web setup page. Docker documents these standard
[container options](https://docs.docker.com/reference/cli/docker/container/run/).

## Backup, updating and recovery

See [Docker-run maintenance](docker-maintenance.md). The existing encrypted automated
[Compose updater](updating.md) applies to Compose installations only. Do not run it against
an installer-created container, and do not rerun the installer as an update command.
