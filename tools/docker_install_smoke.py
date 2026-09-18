"""Verify the guided installer and offline recovery using only fresh, owned Docker resources."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from quality_gate import _bash_executable

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Synthetic-Docker-Install-Owner-2026"


def docker(*args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(["docker", *args], input=data, capture_output=True, timeout=180)
    if result.returncode:
        # Do not echo full arguments/environment: they may contain an operator secret.
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_ready(client: httpx.Client) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if client.get("/ready").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise AssertionError("Isolated smoke container did not become ready")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="polaris-install-test:local")
    options = parser.parse_args()
    run_id = uuid.uuid4().hex[:12]
    name = f"polaris-install-smoke-{run_id}"
    clone = f"{name}-restored"
    port = free_port()
    containers = {name, clone}
    volumes = {f"{name}-data", f"{clone}-data"}
    image_id = docker("image", "inspect", "--format", "{{.Id}}", options.image).decode().strip()
    try:
        print("Installing an isolated local container...", flush=True)
        result = subprocess.run(
            [
                _bash_executable(),
                "deploy/scripts/docker-install.sh",
                "--local",
                "--name",
                name,
                "--port",
                str(port),
                "--image",
                options.image,
                "--pull",
                "never",
            ],
            cwd=ROOT,
            env={**os.environ, "MSYS_NO_PATHCONV": "1"},
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(f"Installer failed: {result.stderr}")
        match = re.search(r"Setup code: ([a-f0-9]{64})", result.stdout)
        assert match, "Installer must display a generated setup code"
        token = match[1]
        state = json.loads(docker("inspect", name))[0]
        assert state["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
        assert state["HostConfig"]["ReadonlyRootfs"] is True
        assert state["HostConfig"]["PortBindings"]["4283/tcp"][0]["HostIp"] == "127.0.0.1"
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10
        ) as client:
            assert client.get("/api/auth/setup/status").json()["setup_required"] is True
            assert (
                client.post("/api/auth/setup/preflight", json={"setup_token": "wrong"}).status_code
                == 403
            )
            payload = {"setup_token": token, "password": PASSWORD, "confirm_password": PASSWORD}
            assert (
                client.post("/api/auth/setup/preflight", json={"setup_token": token}).status_code
                == 200
            )
            assert client.post("/api/auth/setup", json=payload).status_code == 200
            original_keys = client.get("/api/auth/keys").json()
            docker("restart", name)
            wait_ready(client)
            assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
            assert client.get("/api/auth/keys").json() == original_keys
            print("Setup, owner login and restart persistence passed.", flush=True)

            # Follow the documented stopped-volume tar backup, without writing secrets to disk.
            docker("stop", name)
            archive = docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "tar",
                "--mount",
                f"type=volume,src={name}-data,dst=/data,readonly",
                image_id,
                "-czf",
                "-",
                "-C",
                "/data",
                ".",
            )
            assert archive.startswith(b"\x1f\x8b")
            docker("volume", "create", "--label", f"io.polaris.smoke={run_id}", f"{clone}-data")
            docker(
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "tar",
                "--mount",
                f"type=volume,src={clone}-data,dst=/data",
                image_id,
                "-xzf",
                "-",
                "-C",
                "/data",
                data=archive,
            )
            del archive
            docker(
                "run",
                "-d",
                "--name",
                clone,
                "--label",
                f"io.polaris.smoke={run_id}",
                "--restart",
                "unless-stopped",
                "--init",
                "--read-only",
                "--stop-timeout",
                "45",
                "--publish",
                f"127.0.0.1:{port}:4283",
                "--env",
                "HOST=0.0.0.0",
                "--env",
                "PORT=4283",
                "--env",
                "WORKERS=1",
                "--env",
                "POLARIS_RUNTIME_MODE=standalone",
                "--env",
                "POLARIS_REPLICA_COUNT=1",
                "--mount",
                f"type=volume,src={clone}-data,dst=/app/backend/data",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "--security-opt",
                "no-new-privileges:true",
                image_id,
            )
            wait_ready(client)
            client.cookies.clear()
            assert client.get("/api/auth/setup/status").json()["setup_required"] is False
            assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
            assert client.get("/api/auth/keys").json() == original_keys
            docker("stop", clone)
            docker("start", name)
            wait_ready(client)
            client.cookies.clear()
            assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
            assert client.get("/api/auth/keys").json() == original_keys
            assert token.encode() not in docker("logs", name)
            print(
                "Offline backup, restored-volume replacement and original-volume rollback passed.",
                flush=True,
            )
    finally:
        # Only remove exact random names created by this run after verifying ownership labels.
        for resource, targets in (("container", containers), ("volume", volumes)):
            for target in targets:
                inspected = subprocess.run(
                    ["docker", resource, "inspect", target], capture_output=True, timeout=30
                )
                if inspected.returncode:
                    continue
                item = json.loads(inspected.stdout)[0]
                labels = (item["Config"] if resource == "container" else item).get("Labels") or {}
                if not target.startswith(f"polaris-install-smoke-{run_id}"):
                    raise RuntimeError("Refusing cleanup: unexpected resource name")
                if not (
                    labels.get("io.polaris.install") == "guided"
                    or labels.get("io.polaris.smoke") == run_id
                ):
                    raise RuntimeError("Refusing cleanup: ownership label does not match")
                if resource == "container":
                    docker("container", "rm", "--force", target)
                else:
                    docker("volume", "rm", target)
        print("Disposed only this run's isolated test containers and volumes.", flush=True)


if __name__ == "__main__":
    main()
