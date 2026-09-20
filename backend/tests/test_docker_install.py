"""Exercise the installer with an isolated fake Docker daemon, never a live deployment."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy/scripts/docker-install.sh"
BASH = shutil.which("bash") if os.name != "nt" else "C:/Program Files/Git/bin/bash.exe"

FAKE_DOCKER = r"""
command() {
    if [[ "${FAKE_NO_DOCKER:-0}" == 1 && "$*" == '-v docker' ]]; then return 1; fi
    builtin command "$@"
}
export -f command
docker() {
    printf '%s\n' "$*" >> "$FAKE_LOG"
    case "$1 $2" in
        'info --format') printf '%s\n' "${FAKE_ENGINE:-linux/x86_64}"; return "${FAKE_INFO_EXIT:-0}" ;;
        'context inspect') printf '%s\n' "${FAKE_ENDPOINT:-unix:///var/run/docker.sock}" ;;
        'container ls') printf '%s\n' "${FAKE_CONTAINER:-}" ;;
        'volume ls') printf '%s\n' "${FAKE_VOLUME:-}" ;;
        'pull '*) return "${FAKE_PULL_EXIT:-0}" ;;
        'image inspect') printf '%s\n' 'sha256:fixture-image' ;;
        'run --rm') return "${FAKE_CAPABILITY_EXIT:-0}" ;;
        'volume create')
            for arg in "$@"; do
                case "$arg" in io.polaris.install-id=*) printf '%s' "${arg#*=}" > "$FAKE_LOG.owner" ;; esac
            done
            printf '%s\n' 'polaris-data' ;;
        'volume inspect')
            if [[ "${FAKE_VOLUME_RACE:-0}" == 1 ]]; then printf 'another-install'; else cat "$FAKE_LOG.owner"; fi ;;
        'create '*)
            printf '%s' "$SETUP_TOKEN" > "$FAKE_SECRET"
            printf '%s\n' 'fixture-container-id' ;;
        'start '*) return "${FAKE_START_EXIT:-0}" ;;
        'inspect --format') printf '%s\n' "${FAKE_HEALTH:-healthy}" ;;
        *) printf 'Unexpected Docker operation: %s\n' "$*" >&2; return 90 ;;
    esac
}
export -f docker
bash "$INSTALLER" "$@"
"""


class DockerInstallerTests(unittest.TestCase):
    def run_installer(self, *args, **settings):
        self.assertTrue(INSTALLER.is_file(), "The standalone Docker installer must exist")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "docker.log"
            secret = root / "token"
            env = {
                **os.environ,
                "INSTALLER": INSTALLER.as_posix(),
                "FAKE_LOG": log.as_posix(),
                "FAKE_SECRET": secret.as_posix(),
                "DOCKER_HOST": "",
                "DOCKER_CONTEXT": "",
                **settings,
            }
            result = subprocess.run(
                [BASH, "-c", FAKE_DOCKER, "test-installer", *args],
                env=env,
                input="",
                capture_output=True,
                text=True,
                timeout=15,
                cwd=ROOT,
            )
            return (
                result,
                log.read_text() if log.exists() else "",
                secret.read_text() if secret.exists() else "",
            )

    def test_local_install_retains_hardening_and_protects_setup_secret(self):
        result, commands, token = self.run_installer("--local")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://127.0.0.1:4283", result.stdout)
        self.assertRegex(token, r"^[a-f0-9]{64}$")
        self.assertIn(token, result.stdout)
        self.assertNotIn(token, commands + result.stderr)
        for expected in (
            "--publish 127.0.0.1:4283:4283",
            "--restart unless-stopped",
            "--read-only",
            "--init",
            "--env SETUP_TOKEN",
            "--env SETUP_ALLOW_INSECURE_HTTP=true",
            "--mount type=volume,src=polaris-data,dst=/app/backend/data",
            "--security-opt no-new-privileges:true",
            "--log-opt max-size=10m",
            "--stop-timeout 45",
            "sha256:fixture-image",
        ):
            self.assertIn(expected, commands)

    def test_public_install_requires_explicit_http_consent(self):
        result, commands, _ = self.run_installer("--public-host", "192.0.2.10")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP", result.stderr + result.stdout)
        self.assertNotIn("create ", commands)

    def test_public_install_uses_entered_host_and_explicit_opt_in(self):
        result, commands, _ = self.run_installer(
            "--public-host", "192.0.2.10", "--accept-insecure-http", "--port", "14283"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://192.0.2.10:14283", result.stdout)
        self.assertIn("--publish 0.0.0.0:14283:4283", commands)
        self.assertIn("SETUP_ALLOW_INSECURE_HTTP=true", commands)
        self.assertIn("firewall", result.stdout)

    def test_invalid_options_fail_before_mutating_docker(self):
        for args in (
            ("--local", "--port", "0"),
            ("--local", "--port", "65536"),
            ("--local", "--name", "../data"),
            ("--public-host", "evil;touch bad", "--accept-insecure-http"),
            ("--local", "--public-host", "192.0.2.1"),
            ("--image",),
            ("--unknown",),
        ):
            with self.subTest(args=args):
                result, commands, _ = self.run_installer(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("create ", commands)

    def test_noninteractive_run_without_mode_explains_required_choice(self):
        result, commands, _ = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--local", result.stderr)
        self.assertNotIn("create ", commands)

    def test_existing_resources_are_not_overwritten_or_started(self):
        for setting in ({"FAKE_CONTAINER": "polaris"}, {"FAKE_VOLUME": "polaris-data"}):
            with self.subTest(setting=setting):
                result, commands, _ = self.run_installer("--local", **setting)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("preserved", result.stderr)
                self.assertNotIn("create ", commands)
                self.assertNotIn("start ", commands)
                self.assertNotRegex(commands, r"(?m)^(?:container |volume )?rm ")

    def test_volume_created_by_another_installer_is_not_mounted(self):
        result, commands, _ = self.run_installer("--local", FAKE_VOLUME_RACE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ownership", result.stderr)
        self.assertNotRegex(commands, r"(?m)^create ")
        self.assertNotIn("start ", commands)

    def test_engine_and_pull_failures_leave_no_data_resources(self):
        for setting in (
            {"FAKE_ENGINE": "linux/aarch64"},
            {"FAKE_ENGINE": "windows/x86_64"},
            {"FAKE_PULL_EXIT": "1"},
            {"FAKE_CAPABILITY_EXIT": "1"},
            {"FAKE_INFO_EXIT": "1"},
            {"FAKE_ENDPOINT": "ssh://another-host"},
            {"FAKE_NO_DOCKER": "1"},
            {
                "FAKE_ENDPOINT": "ssh://another-host",
                "DOCKER_CONTEXT": "remote",
                "DOCKER_HOST": "unix:///var/run/docker.sock",
            },
        ):
            with self.subTest(setting=setting):
                result, commands, _ = self.run_installer("--local", **setting)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("create ", commands)

    def test_failed_start_preserves_resources_and_gives_resume_instructions(self):
        result, commands, _ = self.run_installer("--local", FAKE_START_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("docker start polaris", result.stderr)
        self.assertIn("preserved", result.stderr)
        self.assertNotRegex(commands, r"(?m)^(?:container |volume )?rm ")
        self.assertNotIn("Ready:", result.stdout)

    def test_health_timeout_does_not_report_success_or_delete_data(self):
        result, commands, _ = self.run_installer(
            "--local", "--wait-seconds", "1", FAKE_HEALTH="starting"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("readiness", result.stderr)
        self.assertNotIn("Ready:", result.stdout)
        self.assertNotRegex(commands, r"(?m)^(?:container |volume )?rm ")

    def test_local_image_can_be_verified_without_pulling_published_release(self):
        result, commands, _ = self.run_installer(
            "--local", "--image", "polaris-install-test:local", "--pull", "never"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pull polaris", commands)
        self.assertIn("image inspect", commands)

    def test_missing_docker_points_to_official_host_instructions(self):
        result, commands, _ = self.run_installer("--local", FAKE_NO_DOCKER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("https://docs.docker.com/", result.stderr)
        self.assertEqual(commands, "")


if __name__ == "__main__":
    unittest.main()
