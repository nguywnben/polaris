"""Offline, selected-provider imports using the pool's bounded archive reader."""

from pathlib import PurePosixPath

from core.pool_import import (
    MAX_POOL_ENTRY_BYTES,
    PoolImportError,
    _parse_archive_payload,
    extract_pool_archive,
    reserve_import_budget,
)
from core.provider_registry import get_static_credential_identity
from core.provider_store import store_extended_credential
from fastapi import UploadFile


async def import_provider_files(provider: str, files: list[UploadFile]) -> dict:
    if not files:
        raise PoolImportError("Select at least one credential file to import.")
    if len(files) > 100:
        raise PoolImportError("Import supports a maximum of 100 files.")

    candidates, results = [], []
    budget = {"entries": 0, "bytes": 0}
    # Validate the whole bounded batch before the first write. Per-entry format
    # errors are reported independently; aggregate resource violations abort it.
    for upload in files:
        name = PurePosixPath(str(upload.filename or "").replace("\\", "/")).name
        if name.lower().endswith(".zip"):
            found, errors = await extract_pool_archive(upload, variant=provider, budget=budget)
            candidates.extend(found)
            results.extend(errors)
        elif name.lower().endswith(".json"):
            content = await upload.read(MAX_POOL_ENTRY_BYTES + 1)
            if len(content) > MAX_POOL_ENTRY_BYTES:
                raise PoolImportError("Credential file exceeds the 2 MB entry limit.")
            reserve_import_budget(budget, 1, len(content))
            try:
                payload = _parse_archive_payload(content, name, variant=provider)
                candidates.append({"source_filename": name, "payload": payload})
            except PoolImportError as exc:
                results.append({"status": "error", "source_filename": name, "message": str(exc)})
        else:
            raise PoolImportError("Use a JSON file or ZIP archive.")

    seen = set()
    for candidate in candidates:
        identity = get_static_credential_identity(candidate["payload"])
        result = {"source_filename": candidate["source_filename"], "provider": provider}
        if identity in seen:
            result.update(
                status="skipped",
                action="skipped",
                message="Duplicate API key in this archive was skipped.",
            )
        else:
            try:
                saved = await store_extended_credential(candidate["payload"], [], file_import=True)
                action = saved.get("action", "created")
                result.update(
                    status="skipped" if action == "skipped" else "success",
                    action=action,
                    filename=saved["filename"],
                    message=(
                        "Duplicate API key was skipped; the existing credential was kept unchanged."
                        if action == "skipped"
                        else "Credential imported. Inference access is not verified."
                    ),
                )
                if action != "skipped":
                    result.update(model_count=0, validation_status="unverified")
                seen.add(identity)
            except Exception:
                result.update(
                    status="error",
                    action="failed",
                    message="Provider credential could not be stored.",
                )
        results.append(result)

    for result in results:
        result.setdefault("filename", result["source_filename"])
        result.setdefault("action", "failed")
        result.setdefault("provider", provider)
    return {
        "uploaded_count": sum(item["status"] == "success" for item in results),
        "error_count": sum(item["status"] == "error" for item in results),
        "skipped_count": sum(item["status"] == "skipped" for item in results),
        "total_count": len(results),
        "results": results,
        "message": "Credential import completed.",
    }
