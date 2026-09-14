"""Safely update or roll back the supported Polaris Compose service."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_FILE = ROOT / "deploy" / "docker-compose.yml"
DEFAULT_RECOVERY_DIR = Path.home() / ".polaris" / "recovery"
MAX_BACKUP_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_DIGEST_REFERENCE = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
_VERSION_REFERENCE = re.compile(
    r"^(?P<name>(?:[^\s/@]+/)*[^\s/:@]+):"
    r"(?P<tag>v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$"
)
_RECORD_FIELDS = frozenset(
    {
        "format",
        "version",
        "operation_id",
        "created_at",
        "status",
        "target_reference",
        "previous_image_id",
        "target_image_id",
        "backup_path",
        "backup_sha256",
        "compose_files",
        "project_name",
        "data_volume",
        "failure",
    }
)
_RECORD_STATUSES = frozenset(
    {
        "prepared",
        "updated",
        "rolled_back_after_failed_update",
        "rolled_back_by_operator",
        "rollback_failed",
    }
)


class UpdateError(RuntimeError):
    """A safe, operator-actionable update workflow failure."""


class UpdateRollbackError(UpdateError):
    """The update failed and automatic rollback could not be completed."""


@dataclass(frozen=True, slots=True)
class RuntimeState:
    container_id: str
    image_id: str
    healthy: bool


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    status: str
    actions: tuple[str, ...]
    record_path: Path | None = None


@dataclass(slots=True)
class UpdateRecord:
    format: str
    version: int
    operation_id: str
    created_at: str
    status: str
    target_reference: str
    previous_image_id: str
    target_image_id: str
    backup_path: str
    backup_sha256: str
    compose_files: list[str]
    project_name: str
    data_volume: str
    failure: str


class UpdateRuntime(Protocol):
    def preflight(self) -> RuntimeState: ...

    def context(self) -> dict[str, object]: ...

    def resolve_image(self, reference: str) -> str: ...

    def create_backup(self, container_id: str, passphrase: str) -> bytes: ...

    def deploy(self, image_id: str) -> None: ...

    def wait_healthy(self, timeout_seconds: int) -> bool: ...

    def stop(self) -> None: ...

    def restore(self, image_id: str, passphrase: str, archive: bytes) -> None: ...


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_failure(exc: BaseException) -> str:
    return "operator_interrupt" if isinstance(exc, KeyboardInterrupt) else type(exc).__name__


def validate_image_reference(reference: str) -> None:
    """Require a digest, local image ID, or semantic-version container tag."""

    if not isinstance(reference, str) or not reference or reference != reference.strip():
        raise UpdateError("Target image reference is empty or contains surrounding whitespace.")
    if _IMAGE_ID.fullmatch(reference) or _DIGEST_REFERENCE.fullmatch(reference):
        return
    if _VERSION_REFERENCE.fullmatch(reference) is None:
        raise UpdateError(
            "Target image must use a semantic version tag, registry digest, or local image ID."
        )


def validate_effective_configuration(
    service: object,
    container_environment: dict[str, str],
    published_ports: set[str],
) -> None:
    """Fail before mutation when the current shell would recreate a different deployment."""

    if not isinstance(service, dict) or not isinstance(service.get("environment"), dict):
        raise UpdateError("Effective Compose app configuration is invalid.")
    expected_environment = {
        str(key): "" if value is None else str(value)
        for key, value in service["environment"].items()
    }
    if any(container_environment.get(key) != value for key, value in expected_environment.items()):
        raise UpdateError(
            "Effective Compose environment differs from the active container; restore the same "
            ".env or shell values before updating."
        )
    ports = service.get("ports")
    if not isinstance(ports, list):
        raise UpdateError("Effective Compose port configuration is invalid.")
    expected_ports = {
        str(port.get("published"))
        for port in ports
        if isinstance(port, dict)
        and str(port.get("target")) == "4283"
        and port.get("protocol", "tcp") == "tcp"
    }
    if not expected_ports or expected_ports != published_ports:
        raise UpdateError(
            "Effective Compose host port differs from the active container; restore the same "
            "HOST_PORT before updating."
        )


def _encode_stdin_frame(passphrase: str, archive: bytes = b"") -> bytes:
    secret = passphrase.encode("utf-8")
    if not secret or len(secret) > 4096:
        raise UpdateError("Backup passphrase encoding is outside the supported size boundary.")
    return len(secret).to_bytes(4, "big") + secret + archive


class RecoveryStore:
    """Persist encrypted archives and workflow records atomically outside the data volume."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().absolute()

    def _prepare(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise UpdateError("Recovery directory is not a safe directory.")
        if os.name != "nt":
            self.root.chmod(0o700)

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def create(
        self,
        *,
        archive: bytes,
        target_reference: str,
        previous_image_id: str,
        target_image_id: str,
        context: dict[str, object],
    ) -> tuple[Path, UpdateRecord]:
        if not archive or len(archive) > MAX_BACKUP_BYTES:
            raise UpdateError("Encrypted backup is empty or exceeds the supported size boundary.")
        self._prepare()
        operation_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
        )
        backup_path = self.root / f"pre-update-{operation_id}.ogb"
        record_path = self.root / f"update-{operation_id}.json"
        self._write_atomic(backup_path, archive)
        record = UpdateRecord(
            format="polaris-compose-update",
            version=1,
            operation_id=operation_id,
            created_at=_utc_timestamp(),
            status="prepared",
            target_reference=target_reference,
            previous_image_id=previous_image_id,
            target_image_id=target_image_id,
            backup_path=str(backup_path),
            backup_sha256=hashlib.sha256(archive).hexdigest(),
            compose_files=[str(value) for value in context["compose_files"]],
            project_name=str(context["project_name"]),
            data_volume=str(context["data_volume"]),
            failure="",
        )
        self.save(record_path, record)
        return record_path, record

    def save(self, path: Path, record: UpdateRecord) -> None:
        content = (
            json.dumps(
                asdict(record), ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2
            ).encode("ascii")
            + b"\n"
        )
        self._write_atomic(path, content)

    @staticmethod
    def load(path: Path) -> UpdateRecord:
        candidate = Path(path).expanduser().absolute()
        if candidate.is_symlink() or not candidate.is_file() or candidate.suffix != ".json":
            raise UpdateError("Update record is missing or unsafe.")
        if not 0 < candidate.stat().st_size <= MAX_RECORD_BYTES:
            raise UpdateError("Update record size is invalid.")
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise UpdateError("Update record is unreadable or invalid.") from exc
        if not isinstance(payload, dict) or set(payload) != _RECORD_FIELDS:
            raise UpdateError("Update record fields are invalid.")
        if payload["format"] != "polaris-compose-update" or payload["version"] != 1:
            raise UpdateError("Update record format is unsupported.")
        if payload["status"] not in _RECORD_STATUSES or not isinstance(payload["failure"], str):
            raise UpdateError("Update record workflow state is invalid.")
        if not _IMAGE_ID.fullmatch(str(payload["previous_image_id"])) or not _IMAGE_ID.fullmatch(
            str(payload["target_image_id"])
        ):
            raise UpdateError("Update record image identities are invalid.")
        validate_image_reference(str(payload["target_reference"]))
        compose_files = payload["compose_files"]
        if (
            not isinstance(compose_files, list)
            or not compose_files
            or not all(isinstance(value, str) and value for value in compose_files)
        ):
            raise UpdateError("Update record Compose context is invalid.")
        record = UpdateRecord(**payload)
        archive_path = Path(record.backup_path).expanduser().absolute()
        if archive_path.is_symlink() or not archive_path.is_file() or archive_path.suffix != ".ogb":
            raise UpdateError("Recorded encrypted backup is missing or unsafe.")
        if not 0 < archive_path.stat().st_size <= MAX_BACKUP_BYTES:
            raise UpdateError("Recorded encrypted backup size is invalid.")
        archive = archive_path.read_bytes()
        if hashlib.sha256(archive).hexdigest() != record.backup_sha256:
            raise UpdateError("Recorded encrypted backup checksum does not match.")
        return record


class ComposeUpdater:
    """Coordinate immutable-image update and snapshot-backed rollback."""

    def __init__(
        self,
        runtime: UpdateRuntime,
        recovery_store: RecoveryStore,
        *,
        passphrase_provider: Callable[[bool], str],
        health_timeout: int = 90,
    ) -> None:
        if not 10 <= health_timeout <= 600:
            raise UpdateError("Health timeout must be between 10 and 600 seconds.")
        self.runtime = runtime
        self.store = recovery_store
        self.passphrase_provider = passphrase_provider
        self.health_timeout = health_timeout

    @staticmethod
    def _update_actions(target_reference: str) -> tuple[str, ...]:
        return (
            "preflight Docker, Compose, active image, health, and data volume",
            f"resolve {target_reference} to an immutable image ID; pull versioned registry refs",
            "create encrypted backup in the host recovery directory",
            "write a prepared update record",
            "recreate only the app service from the resolved target image ID",
            "wait for the target /ready health check",
            "on failure: stop app, restore the encrypted snapshot, deploy the previous image ID, "
            "and require healthy state",
        )

    def update(self, target_reference: str, *, dry_run: bool = False) -> WorkflowResult:
        validate_image_reference(target_reference)
        state = self.runtime.preflight()
        if not state.healthy:
            raise UpdateError("The current app must be healthy before an update can begin.")
        actions = self._update_actions(target_reference)
        if dry_run:
            return WorkflowResult("dry_run", actions)

        target_image_id = self.runtime.resolve_image(target_reference)
        if not _IMAGE_ID.fullmatch(target_image_id):
            raise UpdateError("Docker returned an invalid target image identity.")
        if target_image_id == state.image_id:
            raise UpdateError("Target image is already the active immutable image.")
        passphrase = self.passphrase_provider(True)
        archive = self.runtime.create_backup(state.container_id, passphrase)
        record_path, record = self.store.create(
            archive=archive,
            target_reference=target_reference,
            previous_image_id=state.image_id,
            target_image_id=target_image_id,
            context=self.runtime.context(),
        )
        try:
            self.runtime.deploy(target_image_id)
            if not self.runtime.wait_healthy(self.health_timeout):
                raise UpdateError("Target image did not become healthy before the timeout.")
        except (Exception, KeyboardInterrupt) as exc:
            return self._automatic_rollback(record_path, record, passphrase, archive, exc)

        record.status = "updated"
        self.store.save(record_path, record)
        return WorkflowResult("updated", actions, record_path)

    def _automatic_rollback(
        self,
        record_path: Path,
        record: UpdateRecord,
        passphrase: str,
        archive: bytes,
        cause: BaseException,
    ) -> WorkflowResult:
        record.failure = _safe_failure(cause)
        try:
            self.runtime.stop()
            self.runtime.restore(record.previous_image_id, passphrase, archive)
            self.runtime.deploy(record.previous_image_id)
            if not self.runtime.wait_healthy(self.health_timeout):
                raise UpdateRollbackError("Previous image did not become healthy after rollback.")
        except Exception as rollback_exc:
            record.status = "rollback_failed"
            self.store.save(record_path, record)
            raise UpdateRollbackError(
                f"Update failed and rollback did not complete; recovery record: {record_path}"
            ) from rollback_exc
        record.status = "rolled_back_after_failed_update"
        self.store.save(record_path, record)
        return WorkflowResult(
            record.status, self._update_actions(record.target_reference), record_path
        )

    def rollback(self, record_path: Path, *, dry_run: bool = False) -> WorkflowResult:
        record = self.store.load(record_path)
        state = self.runtime.preflight()
        if state.image_id != record.target_image_id:
            raise UpdateError("The active image does not match the target image in this record.")
        actions = (
            "validate the update record and encrypted backup checksum",
            "stop the app service",
            "restore the encrypted pre-update snapshot with the previous image",
            "recreate app from the previous immutable image ID",
            "require the previous image to become healthy",
        )
        if dry_run:
            return WorkflowResult("dry_run", actions, Path(record_path))
        passphrase = self.passphrase_provider(False)
        archive = Path(record.backup_path).read_bytes()
        self.runtime.stop()
        try:
            self.runtime.restore(record.previous_image_id, passphrase, archive)
            self.runtime.deploy(record.previous_image_id)
            if not self.runtime.wait_healthy(self.health_timeout):
                raise UpdateRollbackError("Previous image did not become healthy after rollback.")
        except Exception as exc:
            record.status = "rollback_failed"
            record.failure = _safe_failure(exc)
            self.store.save(Path(record_path), record)
            raise
        record.status = "rolled_back_by_operator"
        record.failure = ""
        self.store.save(Path(record_path), record)
        return WorkflowResult(record.status, actions, Path(record_path))


class DockerComposeRuntime:
    """Subprocess adapter for the canonical one-service Compose deployment."""

    def __init__(self, compose_files: list[Path], project_name: str = "") -> None:
        if not compose_files:
            raise UpdateError("At least one Compose file is required.")
        self.compose_files = [path.expanduser().resolve() for path in compose_files]
        self.project_name = project_name
        self.data_volume = ""

    def _compose(self) -> list[str]:
        command = ["docker", "compose"]
        if self.project_name:
            command.extend(("--project-name", self.project_name))
        for path in self.compose_files:
            command.extend(("--file", str(path)))
        return command

    def _environment(self, image_id: str = "") -> dict[str, str]:
        environment = dict(os.environ)
        if image_id:
            environment["IMAGE"] = image_id
        if self.data_volume:
            environment["DATA_VOLUME"] = self.data_volume
        return environment

    @staticmethod
    def _run(
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                input=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            raise UpdateError(f"Required command is unavailable: {command[0]}") from exc
        if completed.returncode:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise UpdateError(f"Command failed ({command[0]}): {detail or 'no diagnostic output'}")
        return completed

    def _inspect(self, container_id: str, template: str) -> str:
        result = self._run(["docker", "inspect", "--format", template, container_id])
        return result.stdout.decode("utf-8", errors="strict").strip()

    def preflight(self) -> RuntimeState:
        for path in self.compose_files:
            if path.is_symlink() or not path.is_file():
                raise UpdateError(f"Compose file is missing or unsafe: {path}")
        self._run(["docker", "version", "--format", "{{.Server.Version}}"])
        self._run(["docker", "compose", "version", "--short"])
        rendered = self._run(
            [*self._compose(), "config", "--format", "json"], environment=self._environment()
        )
        try:
            compose = json.loads(rendered.stdout.decode("utf-8", errors="strict"))
            service = compose["services"]["app"]
        except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise UpdateError("Effective Compose app configuration is invalid.") from exc
        result = self._run([*self._compose(), "ps", "--quiet", "app"])
        containers = result.stdout.decode("utf-8", errors="strict").split()
        if len(containers) != 1:
            raise UpdateError("Exactly one running Compose app container is required.")
        container_id = containers[0]
        image_id = self._inspect(container_id, "{{.Image}}")
        if not _IMAGE_ID.fullmatch(image_id):
            raise UpdateError("Active container image identity is invalid.")
        health = self._inspect(container_id, "{{if .State.Health}}{{.State.Health.Status}}{{end}}")
        try:
            configured_environment = json.loads(self._inspect(container_id, "{{json .Config.Env}}"))
            if not isinstance(configured_environment, list):
                raise TypeError
            environment = {
                key: value
                for entry in configured_environment
                if isinstance(entry, str) and "=" in entry
                for key, value in [entry.split("=", 1)]
            }
            network_ports = json.loads(
                self._inspect(container_id, "{{json .NetworkSettings.Ports}}")
            )
            bindings = network_ports.get("4283/tcp", [])
            published_ports = {
                str(binding["HostPort"])
                for binding in bindings or []
                if isinstance(binding, dict) and binding.get("HostPort")
            }
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise UpdateError("Active container environment metadata is invalid.") from exc
        validate_effective_configuration(service, environment, published_ports)
        if environment.get("POSTGRESQL_URI") or environment.get("MONGODB_URI"):
            raise UpdateError("Compose update recovery supports the SQLite state backend only.")
        if (
            environment.get("WORKERS") != "1"
            or environment.get("POLARIS_RUNTIME_MODE") != "standalone"
            or environment.get("POLARIS_REPLICA_COUNT") != "1"
        ):
            raise UpdateError("Compose update recovery requires the supported standalone topology.")
        volume = self._inspect(
            container_id,
            '{{range .Mounts}}{{if eq .Destination "/app/backend/data"}}{{.Type}}|{{.Name}}{{end}}{{end}}',
        )
        try:
            volume_type, volume_name = volume.split("|", 1)
        except ValueError as exc:
            raise UpdateError("The canonical application data volume is not mounted.") from exc
        if volume_type != "volume" or not volume_name:
            raise UpdateError("Updates require the canonical named application data volume.")
        self.data_volume = volume_name
        if not self.project_name:
            self.project_name = self._inspect(
                container_id, '{{index .Config.Labels "com.docker.compose.project"}}'
            )
        if not self.project_name:
            raise UpdateError("Compose project identity is unavailable.")
        return RuntimeState(container_id, image_id, health == "healthy")

    def context(self) -> dict[str, object]:
        if not self.project_name or not self.data_volume:
            raise UpdateError("Compose runtime preflight has not completed.")
        return {
            "compose_files": [str(path) for path in self.compose_files],
            "project_name": self.project_name,
            "data_volume": self.data_volume,
        }

    def resolve_image(self, reference: str) -> str:
        validate_image_reference(reference)
        if not _IMAGE_ID.fullmatch(reference):
            self._run(["docker", "pull", reference])
        result = self._run(["docker", "image", "inspect", "--format", "{{.Id}}", reference])
        image_id = result.stdout.decode("utf-8", errors="strict").strip()
        if not _IMAGE_ID.fullmatch(image_id):
            raise UpdateError("Docker returned an invalid image identity.")
        return image_id

    def create_backup(self, container_id: str, passphrase: str) -> bytes:
        result = self._run(
            [
                "docker",
                "exec",
                "--interactive",
                "--user",
                "10001:10001",
                container_id,
                "python",
                "backend/backup_cli.py",
                "create",
            ],
            stdin=_encode_stdin_frame(passphrase),
        )
        if not result.stdout or len(result.stdout) > MAX_BACKUP_BYTES:
            raise UpdateError("Container produced an invalid encrypted backup size.")
        return result.stdout

    def deploy(self, image_id: str) -> None:
        if not _IMAGE_ID.fullmatch(image_id):
            raise UpdateError("Refusing to deploy a non-immutable image identity.")
        self._run(
            [*self._compose(), "up", "--detach", "--no-deps", "--force-recreate", "app"],
            environment=self._environment(image_id),
        )

    def wait_healthy(self, timeout_seconds: int) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                result = self._run([*self._compose(), "ps", "--quiet", "app"])
                container_id = result.stdout.decode("utf-8", errors="strict").strip()
                if container_id:
                    health = self._inspect(
                        container_id, "{{if .State.Health}}{{.State.Health.Status}}{{end}}"
                    )
                    if health == "healthy":
                        return True
                    if health == "unhealthy":
                        return False
            except UpdateError:
                pass
            time.sleep(2)
        return False

    def stop(self) -> None:
        self._run([*self._compose(), "stop", "app"], environment=self._environment())

    def restore(self, image_id: str, passphrase: str, archive: bytes) -> None:
        if not _IMAGE_ID.fullmatch(image_id):
            raise UpdateError("Refusing to restore with a non-immutable image identity.")
        self._run(
            [
                *self._compose(),
                "run",
                "--rm",
                "--no-deps",
                "--user",
                "10001:10001",
                "--entrypoint",
                "python",
                "app",
                "backend/backup_cli.py",
                "restore",
            ],
            environment=self._environment(image_id),
            stdin=_encode_stdin_frame(passphrase, archive),
        )


def _passphrase_from_terminal(confirm: bool) -> str:
    passphrase = getpass.getpass("Backup passphrase: ")
    if confirm and passphrase != getpass.getpass("Confirm backup passphrase: "):
        raise UpdateError("Backup passphrases do not match.")
    return passphrase


def _passphrase_from_stdin(_confirm: bool) -> str:
    value = sys.stdin.readline()
    if not value:
        raise UpdateError("No backup passphrase was provided on standard input.")
    return value.rstrip("\r\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("update", "rollback"))
    parser.add_argument("--target-image", default="")
    parser.add_argument("--record", type=Path)
    parser.add_argument(
        "--compose-file",
        action="append",
        type=Path,
        dest="compose_files",
        help="Compose file; repeat for overrides (default: deploy/docker-compose.yml).",
    )
    parser.add_argument("--project-name", default="")
    parser.add_argument("--recovery-dir", type=Path, default=DEFAULT_RECOVERY_DIR)
    parser.add_argument("--health-timeout", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--passphrase-stdin",
        action="store_true",
        help="Read one passphrase line from stdin for non-interactive rehearsal.",
    )
    return parser


def _runtime_from_options(options: argparse.Namespace) -> DockerComposeRuntime:
    if options.command == "update" and not options.target_image:
        raise UpdateError("update requires --target-image")
    if options.command == "rollback" and options.record is None:
        raise UpdateError("rollback requires --record")
    if options.command == "rollback":
        record = RecoveryStore.load(options.record)
        recorded_files = [Path(value) for value in record.compose_files]
        requested_files = [path.expanduser().resolve() for path in options.compose_files or []]
        if requested_files and requested_files != [path.resolve() for path in recorded_files]:
            raise UpdateError("Rollback Compose files must match the recovery record.")
        if options.project_name and options.project_name != record.project_name:
            raise UpdateError("Rollback project name must match the recovery record.")
        runtime = DockerComposeRuntime(recorded_files, record.project_name)
        runtime.data_volume = record.data_volume
        return runtime
    return DockerComposeRuntime(
        options.compose_files or [DEFAULT_COMPOSE_FILE], options.project_name
    )


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    provider = _passphrase_from_stdin if options.passphrase_stdin else _passphrase_from_terminal
    try:
        updater = ComposeUpdater(
            _runtime_from_options(options),
            RecoveryStore(options.recovery_dir),
            passphrase_provider=provider,
            health_timeout=options.health_timeout,
        )
        if options.command == "update":
            result = updater.update(options.target_image, dry_run=options.dry_run)
        else:
            result = updater.rollback(options.record, dry_run=options.dry_run)
    except UpdateError as exc:
        print(f"Update workflow failed: {exc}", file=sys.stderr)
        return 1
    for index, action in enumerate(result.actions, 1):
        print(f"{index}. {action}")
    if result.record_path is not None:
        print(f"Recovery record: {result.record_path}")
    print(f"Result: {result.status}")
    return 2 if result.status == "rolled_back_after_failed_update" else 0


if __name__ == "__main__":
    raise SystemExit(main())
