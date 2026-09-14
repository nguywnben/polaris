"""Contracts for the production self-hosted Compose update workflow."""

from __future__ import annotations

import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from tools.compose_update import (
    MAX_BACKUP_BYTES,
    ComposeUpdater,
    RecoveryStore,
    RuntimeState,
    UpdateError,
    validate_effective_configuration,
    validate_image_reference,
)


class FakeRuntime:
    def __init__(self, *, target_healthy: bool = True) -> None:
        self.current_image = "sha256:" + "1" * 64
        self.target_image = "sha256:" + "2" * 64
        self.target_healthy = target_healthy
        self.calls: list[tuple] = []

    def preflight(self) -> RuntimeState:
        self.calls.append(("preflight",))
        return RuntimeState(
            container_id="container-1",
            image_id=self.current_image,
            healthy=True,
        )

    def context(self) -> dict[str, object]:
        return {
            "compose_files": ["deploy/docker-compose.yml"],
            "project_name": "polaris-test",
            "data_volume": "polaris-test-data",
        }

    def resolve_image(self, reference: str) -> str:
        self.calls.append(("resolve_image", reference))
        return self.target_image

    def create_backup(self, container_id: str, passphrase: str) -> bytes:
        self.calls.append(("create_backup", container_id, passphrase))
        return b"encrypted-backup"

    def deploy(self, image_id: str) -> None:
        self.calls.append(("deploy", image_id))
        self.current_image = image_id

    def wait_healthy(self, timeout_seconds: int) -> bool:
        self.calls.append(("wait_healthy", timeout_seconds))
        if self.current_image == self.target_image:
            return self.target_healthy
        return True

    def stop(self) -> None:
        self.calls.append(("stop",))

    def restore(self, image_id: str, passphrase: str, archive: bytes) -> None:
        self.calls.append(("restore", image_id, passphrase, archive))


class ComposeUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        test_root = Path(os.environ["CREDENTIALS_DIR"]).parent
        test_root.mkdir(parents=True, exist_ok=True)
        self.recovery = test_root / f"compose-update-{uuid.uuid4().hex}"
        self.recovery.mkdir()
        self.addCleanup(shutil.rmtree, self.recovery, True)

    def test_target_reference_rejects_floating_or_untagged_images(self) -> None:
        for value in (
            "nguywnben/polaris",
            "nguywnben/polaris:latest",
            "nguywnben/polaris:edge",
            "latest",
        ):
            with self.subTest(value=value), self.assertRaises(UpdateError):
                validate_image_reference(value)

        validate_image_reference("nguywnben/polaris:1.5.0")
        validate_image_reference("localhost:5000/polaris:1.5.0")
        validate_image_reference("registry.example/polaris@sha256:" + "a" * 64)
        validate_image_reference("sha256:" + "b" * 64)

        for value in (
            "https://registry.example/polaris:1.5.0",
            "user@registry.example/polaris:1.5.0",
        ):
            with self.subTest(value=value), self.assertRaises(UpdateError):
                validate_image_reference(value)

    def test_preflight_rejects_environment_or_port_drift_without_exposing_values(self) -> None:
        service = {
            "environment": {"PANEL_PASSWORD": "rendered-secret", "WORKERS": "1"},
            "ports": [{"target": 4283, "published": "4297", "protocol": "tcp"}],
        }
        validate_effective_configuration(
            service,
            {"PANEL_PASSWORD": "rendered-secret", "WORKERS": "1"},
            {"4297"},
        )

        for environment, ports in (
            ({"PANEL_PASSWORD": "different-secret", "WORKERS": "1"}, {"4297"}),
            ({"PANEL_PASSWORD": "rendered-secret", "WORKERS": "1"}, {"4283"}),
        ):
            with self.assertRaises(UpdateError) as raised:
                validate_effective_configuration(service, environment, ports)
            self.assertNotIn("rendered-secret", str(raised.exception))
            self.assertNotIn("different-secret", str(raised.exception))

    def test_dry_run_is_read_only_and_does_not_request_a_passphrase(self) -> None:
        runtime = FakeRuntime()
        passphrase_calls = 0

        def passphrase_provider(_confirm: bool) -> str:
            nonlocal passphrase_calls
            passphrase_calls += 1
            return "not-used"

        updater = ComposeUpdater(
            runtime,
            RecoveryStore(self.recovery),
            passphrase_provider=passphrase_provider,
            health_timeout=45,
        )

        result = updater.update("nguywnben/polaris:1.5.0", dry_run=True)

        self.assertEqual(result.status, "dry_run")
        self.assertEqual(runtime.calls, [("preflight",)])
        self.assertEqual(passphrase_calls, 0)
        self.assertFalse(any(self.recovery.iterdir()))
        self.assertIn("create encrypted backup", " ".join(result.actions).lower())
        self.assertIn("restore", " ".join(result.actions).lower())

    def test_successful_update_records_immutable_images_and_encrypted_backup(self) -> None:
        runtime = FakeRuntime()
        updater = ComposeUpdater(
            runtime,
            RecoveryStore(self.recovery),
            passphrase_provider=lambda _confirm: "correct horse battery staple",
            health_timeout=45,
        )

        result = updater.update("nguywnben/polaris:1.5.0")

        self.assertEqual(result.status, "updated")
        self.assertIsNotNone(result.record_path)
        record = json.loads(result.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "updated")
        self.assertEqual(record["previous_image_id"], "sha256:" + "1" * 64)
        self.assertEqual(record["target_image_id"], "sha256:" + "2" * 64)
        self.assertNotIn("correct horse battery staple", json.dumps(record))
        backup = Path(record["backup_path"])
        self.assertEqual(backup.read_bytes(), b"encrypted-backup")
        self.assertEqual(
            runtime.calls,
            [
                ("preflight",),
                ("resolve_image", "nguywnben/polaris:1.5.0"),
                ("create_backup", "container-1", "correct horse battery staple"),
                ("deploy", "sha256:" + "2" * 64),
                ("wait_healthy", 45),
            ],
        )

    def test_failed_target_health_restores_snapshot_and_previous_image(self) -> None:
        runtime = FakeRuntime(target_healthy=False)
        updater = ComposeUpdater(
            runtime,
            RecoveryStore(self.recovery),
            passphrase_provider=lambda _confirm: "correct horse battery staple",
            health_timeout=30,
        )

        result = updater.update("nguywnben/polaris:1.5.0")

        self.assertEqual(result.status, "rolled_back_after_failed_update")
        record = json.loads(result.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "rolled_back_after_failed_update")
        self.assertEqual(runtime.current_image, "sha256:" + "1" * 64)
        self.assertEqual(
            runtime.calls[-4:],
            [
                ("stop",),
                (
                    "restore",
                    "sha256:" + "1" * 64,
                    "correct horse battery staple",
                    b"encrypted-backup",
                ),
                ("deploy", "sha256:" + "1" * 64),
                ("wait_healthy", 30),
            ],
        )

    def test_explicit_rollback_rejects_an_unrelated_active_image(self) -> None:
        runtime = FakeRuntime()
        store = RecoveryStore(self.recovery)
        updater = ComposeUpdater(
            runtime,
            store,
            passphrase_provider=lambda _confirm: "correct horse battery staple",
            health_timeout=30,
        )
        result = updater.update("nguywnben/polaris:1.5.0")
        runtime.current_image = "sha256:" + "3" * 64

        with self.assertRaisesRegex(UpdateError, "active image"):
            updater.rollback(result.record_path)

    def test_explicit_rollback_restores_only_a_checksum_verified_record(self) -> None:
        runtime = FakeRuntime()
        store = RecoveryStore(self.recovery)
        updater = ComposeUpdater(
            runtime,
            store,
            passphrase_provider=lambda _confirm: "correct horse battery staple",
            health_timeout=30,
        )
        result = updater.update("nguywnben/polaris:1.5.0")

        rolled_back = updater.rollback(result.record_path)

        self.assertEqual(rolled_back.status, "rolled_back_by_operator")
        self.assertEqual(runtime.current_image, "sha256:" + "1" * 64)
        record = json.loads(result.record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "rolled_back_by_operator")

    def test_explicit_rollback_rejects_a_tampered_backup_before_stopping(self) -> None:
        runtime = FakeRuntime()
        store = RecoveryStore(self.recovery)
        updater = ComposeUpdater(
            runtime,
            store,
            passphrase_provider=lambda _confirm: "correct horse battery staple",
            health_timeout=30,
        )
        result = updater.update("nguywnben/polaris:1.5.0")
        record = json.loads(result.record_path.read_text(encoding="utf-8"))
        Path(record["backup_path"]).write_bytes(b"tampered")
        calls_before_rollback = list(runtime.calls)

        with self.assertRaisesRegex(UpdateError, "checksum"):
            updater.rollback(result.record_path)

        self.assertEqual(runtime.calls, calls_before_rollback)

    def test_record_and_archive_resource_limits_fail_before_large_reads(self) -> None:
        runtime = FakeRuntime()
        store = RecoveryStore(self.recovery)
        updater = ComposeUpdater(
            runtime,
            store,
            passphrase_provider=lambda _confirm: "correct horse battery staple",
            health_timeout=30,
        )
        result = updater.update("nguywnben/polaris:1.5.0")
        record_path = result.record_path

        original_record = record_path.read_bytes()
        record_path.write_bytes(original_record + b" " * (70 * 1024))
        with self.assertRaisesRegex(UpdateError, "record size"):
            store.load(record_path)

        record_path.write_bytes(original_record)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        backup_path = Path(record["backup_path"])
        with backup_path.open("wb") as stream:
            stream.seek(MAX_BACKUP_BYTES)
            stream.write(b"x")
        with (
            patch.object(Path, "read_bytes", side_effect=AssertionError("large read")),
            self.assertRaisesRegex(UpdateError, "backup size"),
        ):
            store.load(record_path)


if __name__ == "__main__":
    unittest.main()
