"""Internal stdin-only backup entry point for stopped-service Compose recovery."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from core.portable_backup import (
    MAX_BACKUP_UPLOAD_BYTES,
    BackupError,
    PortableBackupService,
    RestoreConflictPolicy,
)

MAX_PASSPHRASE_BYTES = 4096


class BackupCliInputError(ValueError):
    """The private stdin frame is malformed or outside its resource limits."""


def _read_exact(stream, size: int) -> bytes:
    value = stream.read(size)
    if len(value) != size:
        raise BackupCliInputError("Input frame is incomplete.")
    return value


def _read_frame(*, include_archive: bool) -> tuple[str, bytes]:
    stream = sys.stdin.buffer
    secret_size = int.from_bytes(_read_exact(stream, 4), "big")
    if not 1 <= secret_size <= MAX_PASSPHRASE_BYTES:
        raise BackupCliInputError("Input frame passphrase size is invalid.")
    try:
        passphrase = _read_exact(stream, secret_size).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise BackupCliInputError("Input frame passphrase encoding is invalid.") from exc
    archive = stream.read(MAX_BACKUP_UPLOAD_BYTES + 1)
    if include_archive:
        if not archive or len(archive) > MAX_BACKUP_UPLOAD_BYTES:
            raise BackupCliInputError("Input frame archive size is invalid.")
    elif archive:
        raise BackupCliInputError("Create input frame contains unexpected trailing data.")
    return passphrase, archive


def _service() -> PortableBackupService:
    credentials_dir = Path(os.getenv("CREDENTIALS_DIR", "backend/data/creds")).resolve()
    return PortableBackupService(
        credentials_dir / "credentials.db",
        credentials_dir=credentials_dir,
    )


async def _run(operation: str) -> None:
    passphrase, archive = _read_frame(include_archive=operation == "restore")
    service = _service()
    if operation == "create":
        artifact = await service.create_backup(passphrase)
        sys.stdout.buffer.write(artifact.content)
        sys.stdout.buffer.flush()
        return
    await service.restore(
        archive,
        passphrase,
        conflict_policy=RestoreConflictPolicy.REPLACE,
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "restore"))
    options = parser.parse_args(arguments)
    try:
        asyncio.run(_run(options.operation))
    except (BackupError, BackupCliInputError, OSError) as exc:
        print(f"Backup CLI failed ({type(exc).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
