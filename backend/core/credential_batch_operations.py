"""Bounded, secret-free planning state for credential batch operations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.credential_batch_coordination import (
    BatchIdempotencyConflictError,
    BatchIdempotencyInProgressError,
    BatchIdempotencyReplay,
    BatchIdempotencyReservation,
    CredentialBatchCapacityError,
    CredentialBatchCoordinationError,
    get_credential_batch_coordination_service,
)
from core.credential_validation import validate_credential_filename
from core.provider_registry import (
    credential_supports_operation,
    get_credential_provider_variant,
    get_credential_variant_capabilities,
)
from fastapi import HTTPException

BATCH_ACTION_OPERATIONS = {
    "enable": "toggle",
    "disable": "toggle",
    "delete": "delete",
    "enable_credit": "credit_mode",
    "disable_credit": "credit_mode",
}
BATCH_HIGH_VOLUME_THRESHOLD = 20
BATCH_ITEM_TIMEOUT_SECONDS = 5.0
BATCH_PREVIEW_TTL_SECONDS = 300


def batch_request_fingerprint(mode: str, action: str, filenames: list[str]) -> str:
    """Return a deterministic digest without retaining target names in coordination state."""
    serialized = json.dumps(
        {"mode": mode, "action": action, "filenames": filenames},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def batch_requires_preview(action: str, target_count: int) -> bool:
    return action == "delete" or target_count >= BATCH_HIGH_VOLUME_THRESHOLD


async def issue_batch_preview(fingerprint: str) -> str:
    try:
        return await get_credential_batch_coordination_service().issue_preview(fingerprint)
    except CredentialBatchCapacityError:
        raise HTTPException(
            status_code=429,
            detail="Credential batch capacity is temporarily exhausted.",
            headers={"Retry-After": "60"},
        ) from None
    except CredentialBatchCoordinationError:
        raise HTTPException(
            status_code=503,
            detail="Credential batch coordination is unavailable.",
        ) from None


async def preview_matches(token: str | None, fingerprint: str) -> bool:
    try:
        return await get_credential_batch_coordination_service().preview_matches(token, fingerprint)
    except CredentialBatchCoordinationError:
        raise HTTPException(
            status_code=503,
            detail="Credential batch coordination is unavailable.",
        ) from None


async def get_idempotent_response(
    key: str | None,
    fingerprint: str,
    *,
    reserve: bool = False,
) -> tuple[int, dict[str, Any]] | BatchIdempotencyReservation | None:
    if not key:
        return None
    try:
        service = get_credential_batch_coordination_service()
        result = (
            await service.reserve(key, fingerprint)
            if reserve
            else await service.lookup(key, fingerprint)
        )
        if isinstance(result, BatchIdempotencyReplay):
            return result.status_code, result.body
        return result
    except BatchIdempotencyConflictError:
        raise HTTPException(
            status_code=409,
            detail="The idempotency key is already bound to another batch request.",
        ) from None
    except BatchIdempotencyInProgressError:
        raise HTTPException(
            status_code=409,
            detail="The batch request for this idempotency key is still in progress.",
        ) from None
    except CredentialBatchCapacityError:
        raise HTTPException(
            status_code=429,
            detail="Credential batch capacity is temporarily exhausted.",
            headers={"Retry-After": "60"},
        ) from None
    except CredentialBatchCoordinationError:
        raise HTTPException(
            status_code=503,
            detail="Credential batch coordination is unavailable.",
        ) from None


async def store_idempotent_response(
    reservation: BatchIdempotencyReservation | None,
    status_code: int,
    body: dict[str, Any],
) -> None:
    if reservation is None:
        return
    await get_credential_batch_coordination_service().complete(reservation, status_code, body)


async def release_idempotency_reservation(
    reservation: BatchIdempotencyReservation | None,
) -> None:
    if reservation is None:
        return
    await get_credential_batch_coordination_service().release(reservation)


async def assert_idempotency_reservation(
    reservation: BatchIdempotencyReservation | None,
) -> None:
    if reservation is None:
        return
    await get_credential_batch_coordination_service().assert_owner(reservation)


async def build_batch_plan(
    storage_adapter: Any,
    action: str,
    filenames: list[str],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    """Re-evaluate targets and capabilities without mutating credential state."""
    operation = BATCH_ACTION_OPERATIONS[action]
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for target_index, raw_filename in enumerate(filenames):
        try:
            filename = validate_credential_filename(raw_filename)
        except HTTPException:
            results.append(_plan_item(target_index, None, operation, "invalid", "invalid_filename"))
            continue

        if filename in seen:
            results.append(
                _plan_item(target_index, filename, operation, "duplicate", "duplicate_target")
            )
            continue
        seen.add(filename)

        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            results.append(
                _plan_item(target_index, filename, operation, "not_found", "credential_not_found")
            )
            continue

        inferred_variant = get_credential_provider_variant(credential_data)
        capabilities = get_credential_variant_capabilities(inferred_variant)
        variant_id = capabilities.variant_id if capabilities else "unknown"
        operation_unsupported = (operation == "credit_mode" and mode != "primary") or (
            mode == "primary" and not credential_supports_operation(credential_data, operation)
        )
        if operation_unsupported:
            results.append(
                _plan_item(
                    target_index,
                    filename,
                    operation,
                    "unsupported",
                    "credential_operation_unsupported",
                    variant_id,
                )
            )
            continue

        item = _plan_item(target_index, filename, operation, "eligible", "eligible", variant_id)
        item["credential_data"] = credential_data
        results.append(item)

    return results


def public_batch_plan(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "credential_data"} for item in results
    ]


def _plan_item(
    target_index: int,
    filename: str | None,
    operation: str,
    status: str,
    code: str,
    variant_id: str = "unknown",
) -> dict[str, Any]:
    return {
        "target_index": target_index,
        "filename": filename,
        "variant_id": variant_id,
        "operation": operation,
        "status": status,
        "code": code,
    }
