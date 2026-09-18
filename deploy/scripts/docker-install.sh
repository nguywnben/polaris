#!/usr/bin/env bash
# Guided Docker installation. Advanced/manual paths: docs/installation.md.
set +x
set -euo pipefail

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
    printf '%s\n' \
        'Polaris Docker installer (requires a Linux amd64 Docker engine)' \
        'Interactive: bash docker-install.sh' \
        'Local:       bash docker-install.sh --local' \
        'VPS HTTP:    bash docker-install.sh --public-host YOUR_IP --accept-insecure-http' \
        'Options: --name NAME --port PORT --image IMAGE --pull always|never --wait-seconds N' \
        'No existing container or volume is replaced. HTTPS is recommended for remote access.'
}

prompt() {
    printf '%s' "$1" >&2
    IFS= read -r answer <&3 || fail 'No answer received; nothing will be exposed automatically.'
}

resume_help() {
    printf '%s\n' \
        "Existing resources are preserved. Inspect: docker logs --tail 50 $name" \
        "After resolving the error (for example, a port conflict): docker start $name" \
        "Retrieve the setup code privately after starting: docker exec $name python -c 'import os; print(os.environ[\"SETUP_TOKEN\"])'" >&2
}

main() {
    local name=polaris port=4283 image=nguywnben/polaris:1.0.0 pull=always
    local mode='' public_host='' consent=false wait_seconds=120 answer=''
    local bind=127.0.0.1 allow_http=false engine endpoint names volumes image_id token health install_id owner
    while (($#)); do
        case "$1" in
            --help|-h) usage; return ;;
            --local) [[ -z "$mode" ]] || fail 'Choose only one access mode.'; mode=local; shift ;;
            --accept-insecure-http) consent=true; shift ;;
            --public-host|--name|--port|--image|--pull|--wait-seconds)
                (($# >= 2)) || fail "Missing value for $1"
                case "$1" in
                    --public-host)
                        [[ -z "$mode" ]] || fail 'Choose only one access mode.'
                        mode=public; public_host=$2 ;;
                    --name) name=$2 ;;
                    --port) port=$2 ;;
                    --image) image=$2 ;;
                    --pull) pull=$2 ;;
                    --wait-seconds) wait_seconds=$2 ;;
                esac
                shift 2 ;;
            *) fail "Unknown option: $1 (use --help)" ;;
        esac
    done
    [[ "$name" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$ ]] || fail 'Invalid container name.'
    [[ "$port" =~ ^[0-9]{1,5}$ ]] || fail 'Port must be 1-65535.'
    port=$((10#$port))
    ((port >= 1 && port <= 65535)) || fail 'Port must be 1-65535.'
    [[ "$wait_seconds" =~ ^[0-9]{1,3}$ ]] || fail 'Wait must be 1-900 seconds.'
    wait_seconds=$((10#$wait_seconds))
    ((wait_seconds >= 1 && wait_seconds <= 900)) || fail 'Wait must be 1-900 seconds.'
    [[ "$image" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$ ]] || fail 'Invalid image reference.'
    [[ "$pull" == always || "$pull" == never ]] || fail 'Pull must be always or never.'

    if [[ -z "$mode" ]]; then
        { exec 3</dev/tty; } 2>/dev/null || fail 'Choose --local or --public-host IP --accept-insecure-http.'
        prompt 'Where will you use Polaris? [1] This computer (default) [2] VPS/public IP: '
        case "$answer" in
            ''|1) mode=local ;;
            2) mode=public; prompt 'VPS public IPv4 address or hostname (no http:// or port): '; public_host=$answer ;;
            *) fail 'Choose 1 or 2, then run the installer again.' ;;
        esac
    fi
    if [[ "$mode" == public ]]; then
        [[ "$public_host" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$ ]] || fail 'Enter an IPv4 address or hostname only.'
        printf '%s\n' 'WARNING: HTTP does not encrypt passwords, setup codes, sessions or API traffic.' \
            'Anyone able to intercept the connection can read them. HTTPS is recommended.' >&2
        if [[ "$consent" != true ]]; then
            { exec 3</dev/tty; } 2>/dev/null || fail 'Public HTTP requires --accept-insecure-http after understanding the warning.'
            prompt 'Allow public HTTP anyway? Type YES to accept, or press Enter to cancel: '
            [[ "$answer" == YES ]] || fail 'HTTP access declined. No container created.'
        fi
        bind=0.0.0.0; allow_http=true
    else
        public_host=127.0.0.1
        # Docker NAT can hide the loopback peer. This installer enforces the local
        # host-side bind, so HTTP is intentional; never infer this from Host headers.
        allow_http=true
    fi

    command -v docker >/dev/null 2>&1 || fail 'Install and start Docker, then run this installer again.'
    engine=$(docker info --format '{{.OSType}}/{{.Architecture}}') || fail 'Docker is unavailable. Start Docker and check your Docker permissions (sudo may be needed).'
    case "$engine" in linux/x86_64|linux/amd64) ;; *) fail "Unsupported engine: $engine. This release requires Linux amd64." ;; esac
    endpoint=${DOCKER_HOST:-}
    if [[ -n "${DOCKER_CONTEXT:-}" || -z "$endpoint" ]]; then
        endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}') || fail 'Cannot identify the Docker host.'
    fi
    case "$endpoint" in unix://*|npipe://*) ;; *) fail 'Use a local Docker daemon on the installation machine, not a remote Docker context.' ;; esac
    names=$(docker container ls --all --format '{{.Names}}') || fail 'Cannot list containers.'
    if printf '%s\n' "$names" | grep -Fxq "$name"; then
        resume_help
        fail "Container $name already exists; it is preserved. This installer is not an updater."
    fi
    volumes=$(docker volume ls --format '{{.Name}}') || fail 'Cannot list data volumes.'
    if printf '%s\n' "$volumes" | grep -Fxq "$name-data"; then
        fail "Volume $name-data already exists and is preserved. Follow the backup/recovery guide or choose a different --name for a separate installation."
    fi

    printf 'Preparing %s...\n' "$image"
    if [[ "$pull" == always ]]; then
        docker pull "$image" || fail 'Image download failed; no data volume created. Check the image version and network, then retry.'
    fi
    image_id=$(docker image inspect --format '{{.Id}}' "$image") || fail 'Image not available locally.'
    # Refuse the old published image rather than offering HTTP setup it cannot support.
    docker run --rm --network none --read-only --entrypoint python --workdir /app/backend "$image_id" \
        -c 'from pathlib import Path; raise SystemExit(0 if "SETUP_ALLOW_INSECURE_HTTP" in Path("core/panel/setup_preflight.py").read_text() else 1)' \
        || fail 'This image does not support the guided setup flow. Use a matching updated image; no data volume created.'
    token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n') || fail 'Cannot generate a secure setup code.'
    [[ "$token" =~ ^[a-f0-9]{64}$ ]] || fail 'Secure setup-code generation failed.'
    install_id=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n') || fail 'Cannot generate an installation identifier.'
    [[ "$install_id" =~ ^[a-f0-9]{32}$ ]] || fail 'Installation identifier generation failed.'
    export SETUP_TOKEN="$token"
    trap 'unset SETUP_TOKEN' EXIT

    docker volume create --label io.polaris.install=guided --label "io.polaris.install-id=$install_id" "$name-data" >/dev/null || fail 'Cannot create data volume.'
    # Volume creation is idempotent: another installer can win after the initial name check.
    owner=$(docker volume inspect --format '{{index .Labels "io.polaris.install-id"}}' "$name-data") || fail 'Cannot verify volume ownership; data preserved.'
    [[ "$owner" == "$install_id" ]] || fail 'Volume ownership changed during installation. Data preserved; no application started.'
    if ! docker create --name "$name" --label io.polaris.install=guided \
        --restart unless-stopped --init --read-only --stop-timeout 45 \
        --publish "$bind:$port:4283" \
        --env SETUP_TOKEN --env "SETUP_ALLOW_INSECURE_HTTP=$allow_http" \
        --env HOST=0.0.0.0 --env PORT=4283 --env WORKERS=1 \
        --env POLARIS_RUNTIME_MODE=standalone --env POLARIS_REPLICA_COUNT=1 \
        --mount "type=volume,src=$name-data,dst=/app/backend/data" \
        --tmpfs /tmp:rw,noexec,nosuid,size=64m --security-opt no-new-privileges:true \
        --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
        "$image_id" >/dev/null; then
        resume_help
        fail "Container creation failed. Volume $name-data is preserved; do not delete it without inspecting it."
    fi
    if ! docker start "$name" >/dev/null; then
        resume_help; fail 'Container could not start. Check for an occupied host port.'
    fi
    printf 'Waiting for readiness (up to %s seconds)...\n' "$wait_seconds"
    local deadline=$((SECONDS + wait_seconds))
    while ((SECONDS < deadline)); do
        health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$name") || {
            resume_help; fail 'Could not read readiness state.';
        }
        if [[ "$health" == healthy ]]; then
            printf '\nReady: http://%s:%s\nSetup code: %s\n' "$public_host" "$port" "$token"
            printf '%s\n' 'Open the address, paste the setup code, and create your owner password.' \
                'Keep this code private; it is not your login password. Do not share terminal screenshots.' \
                "Data volume: $name-data. Docker must start on host boot for automatic recovery."
            if [[ "$mode" == public ]]; then
                printf 'If the page cannot be reached, allow TCP %s in your cloud/host firewall. No firewall rules were changed.\n' "$port"
            fi
            return
        fi
        if [[ "$health" == unhealthy || "$health" == missing ]]; then
            resume_help; fail 'Container did not become ready. Check the logs before retrying.'
        fi
        sleep 1
    done
    resume_help; fail 'Timed out waiting for readiness. Data is preserved; inspect logs and health before opening the setup page.'
}

# Keep execution last so an incomplete download cannot start a partial installation.
main "$@"
