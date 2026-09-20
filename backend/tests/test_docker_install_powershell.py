"""PowerShell guided-install subprocess tests; Docker is replaced by a shell fake."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy/scripts/docker-install.ps1"
SHELLS = list(dict.fromkeys(filter(None, (shutil.which("pwsh"), shutil.which("powershell")))))

HARNESS = r"""
$global:FakeAnswers = New-Object System.Collections.Queue
if ($env:FAKE_ANSWERS) {
    (ConvertFrom-Json $env:FAKE_ANSWERS) | ForEach-Object { $global:FakeAnswers.Enqueue($_) }
}
function Read-Host {
    param([string]$Prompt)
    if ($global:FakeAnswers.Count) { return $global:FakeAnswers.Dequeue() }
    Microsoft.PowerShell.Utility\Read-Host $Prompt
}
function Get-Command {
    [CmdletBinding()]
    param([string]$Name)
    if ($Name -eq 'docker' -and $env:FAKE_NO_DOCKER -eq '1') { return }
    Microsoft.PowerShell.Core\Get-Command $Name -ErrorAction SilentlyContinue
}
function docker {
    $global:LASTEXITCODE = 0
    $line = $args -join ' '
    Add-Content -LiteralPath $env:FAKE_LOG -Value $line
    switch -Wildcard ($line) {
        'info --format*' {
            if ($env:FAKE_INFO_EXIT) { $global:LASTEXITCODE = 1 }
            if ($env:FAKE_ENGINE) { $env:FAKE_ENGINE } else { 'linux/x86_64' }
        }
        'context inspect*' {
            if ($env:FAKE_ENDPOINT) { $env:FAKE_ENDPOINT } else { 'npipe:////./pipe/docker_engine' }
        }
        'container ls*' { $env:FAKE_CONTAINER }
        'volume ls*' { $env:FAKE_VOLUME }
        'pull *' { if ($env:FAKE_PULL_EXIT) { $global:LASTEXITCODE = 1 } }
        'image inspect*' { 'sha256:fixture-image' }
        'run --rm*' { if ($env:FAKE_CAPABILITY_EXIT) { $global:LASTEXITCODE = 1 } }
        'volume create*' {
            $global:FakeOwner = ($args | Where-Object { $_ -like 'io.polaris.install-id=*' }).Substring(22)
            'polaris-data'
        }
        'volume inspect*' {
            $owner = if ($env:FAKE_VOLUME_RACE) { 'another-install' } else { $global:FakeOwner }
            @(@{Labels = @{'io.polaris.install-id' = $owner}}) | ConvertTo-Json -Compress
        }
        'create *' {
            Set-Content -LiteralPath $env:FAKE_SECRET -Value $env:SETUP_TOKEN
            if ($env:FAKE_CREATE_EXIT) { $global:LASTEXITCODE = 1 } else { 'fixture-container' }
        }
        'start *' { if ($env:FAKE_START_EXIT) { $global:LASTEXITCODE = 1 } }
        'inspect --format*' {
            if ($env:FAKE_HEALTH) { $env:FAKE_HEALTH } else { 'healthy' }
        }
        default { throw "Unexpected fake Docker operation: $line" }
    }
}
$parameters = @{}
(ConvertFrom-Json $env:FAKE_PARAMETERS).PSObject.Properties | ForEach-Object {
    $parameters[$_.Name] = $_.Value
}
$code = 0
try {
    if ($env:FAKE_SCRIPTBLOCK) {
        & ([scriptblock]::Create((Get-Content -LiteralPath $env:INSTALLER -Raw))) @parameters
    } else { & $env:INSTALLER @parameters }
} catch { [Console]::Error.WriteLine($_.Exception.Message); $code = 1 }
finally { Set-Content -LiteralPath ($env:FAKE_SECRET + '.restored') -Value $env:SETUP_TOKEN }
exit $code
"""


class PowerShellDockerInstallerTests(unittest.TestCase):
    def run_installer(self, parameters=None, **settings):
        self.assertTrue(SHELLS, "PowerShell is required for installer contract tests")
        self.assertTrue(INSTALLER.is_file(), "PowerShell guided installer must exist")
        results = []
        for shell in SHELLS:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                log, secret = root / "docker.log", root / "token"
                harness = root / "harness.ps1"
                harness.write_text(HARNESS, encoding="utf-8")
                env = {
                    **os.environ,
                    "INSTALLER": str(INSTALLER),
                    "FAKE_LOG": str(log),
                    "FAKE_SECRET": str(secret),
                    "FAKE_PARAMETERS": json.dumps(parameters or {}),
                    "DOCKER_HOST": "",
                    "DOCKER_CONTEXT": "",
                    "SETUP_TOKEN": "synthetic-prior-environment",
                    **settings,
                }
                result = subprocess.run(
                    [
                        shell,
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(harness),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=25,
                    cwd=ROOT,
                )
                restored = secret.with_suffix(".restored")
                self.assertTrue(restored.exists(), result.stderr)
                self.assertEqual(
                    restored.read_text(encoding="utf-8-sig").strip(), env["SETUP_TOKEN"]
                )
                results.append(
                    (
                        result,
                        log.read_text(encoding="utf-8-sig") if log.exists() else "",
                        secret.read_text(encoding="utf-8-sig").strip() if secret.exists() else "",
                    )
                )
        return results

    def test_local_install_matches_bash_security_and_secret_transport(self):
        for result, commands, token in self.run_installer({"Local": True}):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertRegex(token, r"^[a-f0-9]{64}$")
            self.assertIn(token, result.stdout)
            self.assertNotIn(token, commands + result.stderr)
            self.assertIn("http://127.0.0.1:4283", result.stdout)
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

    def test_public_access_requires_explicit_consent(self):
        for result, commands, _ in self.run_installer({"PublicHost": "192.0.2.10"}):
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("HTTP", result.stdout + result.stderr)
            self.assertNotIn("create ", commands)
        for result, commands, _ in self.run_installer(
            {"PublicHost": "192.0.2.10", "AcceptInsecureHttp": True, "Port": 14283}
        ):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("http://192.0.2.10:14283", result.stdout)
            self.assertIn("--publish 0.0.0.0:14283:4283", commands)

    def test_invalid_arguments_and_noninteractive_prompt_do_not_mutate(self):
        for parameters in (
            {},
            {"Local": True, "PublicHost": "192.0.2.10"},
            {"Port": 0},
            {"Port": 65536},
            {"Name": "../data"},
            {"PublicHost": "host;bad"},
            {"Image": "bad image"},
            {"WaitSeconds": 0},
            {"Unknown": True},
            {"Name": "polaris\n"},
            {"Image": "polaris:test\n"},
            {"PublicHost": "localhost\n"},
        ):
            with self.subTest(parameters=parameters):
                arguments = (
                    {"Local": True, **parameters}
                    if parameters and "PublicHost" not in parameters
                    else parameters
                )
                for result, commands, _ in self.run_installer(arguments):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("create ", commands)
                    if parameters:
                        self.assertEqual(commands, "")

    def test_guided_questions_default_local_and_require_public_confirmation(self):
        for answers, binding in (
            ([""], "127.0.0.1"),
            (["2", "192.0.2.10", "YES"], "0.0.0.0"),
        ):
            for result, commands, _ in self.run_installer(FAKE_ANSWERS=json.dumps(answers)):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"--publish {binding}:4283:4283", commands)
        for answers in (["2", "192.0.2.10", "NO"], ["unexpected"]):
            for result, commands, _ in self.run_installer(FAKE_ANSWERS=json.dumps(answers)):
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("create ", commands)

    def test_prerequisite_failures_do_not_create_resources(self):
        for settings in (
            {"FAKE_NO_DOCKER": "1"},
            {"FAKE_INFO_EXIT": "1"},
            {"FAKE_ENGINE": "linux/arm64"},
            {"FAKE_ENGINE": "windows/amd64"},
            {"FAKE_ENDPOINT": "ssh://remote"},
            {"FAKE_PULL_EXIT": "1"},
            {"FAKE_CAPABILITY_EXIT": "1"},
            {"DOCKER_HOST": "tcp://remote:2375"},
            {
                "FAKE_ENDPOINT": "ssh://remote",
                "DOCKER_CONTEXT": "remote",
                "DOCKER_HOST": "unix:///local",
            },
        ):
            with self.subTest(settings=settings):
                for result, commands, _ in self.run_installer({"Local": True}, **settings):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("create ", commands)

    def test_existing_resources_and_concurrent_volume_claim_are_preserved(self):
        for settings in (
            {"FAKE_CONTAINER": "polaris"},
            {"FAKE_VOLUME": "polaris-data"},
            {"FAKE_VOLUME_RACE": "1"},
        ):
            for result, commands, _ in self.run_installer({"Local": True}, **settings):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("preserved", result.stderr.lower())
                self.assertNotRegex(commands, r"(?m)^(?:create |start |(?:volume |container )?rm )")
                if settings.get("FAKE_VOLUME_RACE"):
                    self.assertNotIn("docker start polaris", result.stdout + result.stderr)

    def test_partial_failure_keeps_data_and_explains_recovery(self):
        for settings in (
            {"FAKE_CREATE_EXIT": "1"},
            {"FAKE_START_EXIT": "1"},
            {"FAKE_HEALTH": "unhealthy"},
            {"FAKE_HEALTH": "starting"},
        ):
            for result, commands, _ in self.run_installer(
                {"Local": True, "WaitSeconds": 1}, **settings
            ):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("preserved", (result.stdout + result.stderr).lower())
                self.assertNotIn("Ready:", result.stdout)
                self.assertNotRegex(commands, r"(?m)^(?:volume |container )?rm ")
                if settings.get("FAKE_CREATE_EXIT"):
                    self.assertNotIn("docker start polaris", result.stdout + result.stderr)
                    self.assertIn("did not create", result.stdout)

    def test_local_image_and_help_do_not_pull(self):
        for result, commands, _ in self.run_installer(
            {"Local": True, "Pull": "never", "Image": "polaris-test:local"}
        ):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("pull ", commands)
        for result, commands, _ in self.run_installer({"Help": True}):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(commands, "")

    def test_complete_download_scriptblock_uses_the_same_install_path(self):
        for result, commands, token in self.run_installer({"Local": True}, FAKE_SCRIPTBLOCK="1"):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ready: http://127.0.0.1:4283", result.stdout)
            self.assertRegex(token, r"^[a-f0-9]{64}$")
            self.assertNotIn(token, commands)


if __name__ == "__main__":
    unittest.main()
