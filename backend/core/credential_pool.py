"""Credential pool write policy."""

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.credential_pool_mutation import (
    CredentialPoolMutation,
    CredentialPoolRecord,
    CredentialPoolWrite,
    normalize_pool_mode,
)
from core.provider_registry import (
    GOOGLE_ANTIGRAVITY,
    canonicalize_antigravity_credential_filename,
    get_credential_provider,
    get_static_credential_identity,
)
from core.storage_adapter import get_storage_adapter
from log import log


def _safe_filename(filename: str, fallback_prefix: str = "credential") -> str:
    basename = os.path.basename(str(filename or "").strip())
    if basename:
        return basename
    return f"{fallback_prefix}-{int(time.time())}.json"


def normalize_project_id(credential_data: Dict[str, Any]) -> str:
    project_id = credential_data.get("project_id") or credential_data.get("quota_project_id") or ""
    return str(project_id).strip().lower()


def normalize_credential_email(value: Any) -> str:
    return str(value or "").strip().lower()


def get_known_credential_email(credential_data: Dict[str, Any]) -> str:
    for key in ("user_email", "email", "account_email", "client_email"):
        email = normalize_credential_email(credential_data.get(key))
        if email:
            return email
    return ""


async def resolve_credential_email(credential_data: Dict[str, Any]) -> str:
    email = get_known_credential_email(credential_data)
    if email:
        return email
    if get_static_credential_identity(credential_data):
        return ""

    try:
        from core.google_oauth_api import Credentials, get_user_email

        credentials = Credentials.from_dict(credential_data)
        if not credentials:
            return ""
        return normalize_credential_email(await get_user_email(credentials))
    except Exception as e:
        log.warning(f"Unable to resolve credential email from token: {e}")
        return ""


def parse_credential_expiry(credential_data: Dict[str, Any]) -> Optional[datetime]:
    expiry = credential_data.get("expiry")
    if not expiry:
        return None

    try:
        if isinstance(expiry, datetime):
            parsed = expiry
        else:
            expiry_text = str(expiry).strip()
            if expiry_text.endswith("Z"):
                expiry_text = expiry_text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(expiry_text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _is_incoming_newer(incoming: Optional[datetime], existing: Optional[datetime]) -> bool:
    if incoming is None:
        return False
    if existing is None:
        return True
    return incoming > existing


def _best_expiry_key(item: Dict[str, Any]) -> tuple[datetime, int]:
    return (
        item["expiry"] or datetime.min.replace(tzinfo=timezone.utc),
        -item["index"],
    )


def _find_unique_filename(
    records: tuple[CredentialPoolRecord, ...],
    requested_filename: str,
    credential_data: Dict[str, Any],
) -> str:
    filename = _safe_filename(
        requested_filename, normalize_project_id(credential_data) or "credential"
    )
    stem, ext = os.path.splitext(filename)
    if not ext:
        ext = ".json"

    existing_names = {record.filename for record in records}
    if filename not in existing_names:
        return filename

    existing_data = next(
        (record.credential_data for record in records if record.filename == filename), None
    )
    if get_credential_provider(existing_data or {}) == get_credential_provider(
        credential_data
    ) and get_known_credential_email(existing_data or {}) == get_known_credential_email(
        credential_data
    ):
        return filename

    index = 2
    while True:
        candidate = f"{stem}-{index}{ext}"
        if candidate not in existing_names:
            return candidate
        index += 1


def _record_email(record: CredentialPoolRecord) -> str:
    return normalize_credential_email(record.user_email) or get_known_credential_email(
        record.credential_data
    )


def _plan_upsert(
    records: tuple[CredentialPoolRecord, ...],
    filename: str,
    credential_data: Dict[str, Any],
    *,
    email: str,
    static_identity: str,
    is_antigravity: bool,
) -> CredentialPoolMutation:
    if static_identity:
        matches = [
            record
            for record in records
            if get_static_credential_identity(record.credential_data) == static_identity
        ]
        if not matches:
            target_filename = _find_unique_filename(records, filename, credential_data)
            return CredentialPoolMutation(
                writes=(CredentialPoolWrite(target_filename, credential_data, None),),
                deletes=(),
                result={
                    "action": "created",
                    "stored": True,
                    "filename": target_filename,
                    "email": None,
                    "identity": static_identity,
                    "message": "API key added to the provider pool.",
                },
            )
        keep = min(matches, key=lambda item: item.rotation_order)
        updated = dict(credential_data)
        if keep.credential_data.get("created_at") and not updated.get("created_at"):
            updated["created_at"] = keep.credential_data["created_at"]
        deleted = [record.filename for record in matches if record.filename != keep.filename]
        return CredentialPoolMutation(
            writes=(CredentialPoolWrite(keep.filename, updated, None),),
            deletes=tuple(deleted),
            result={
                "action": "updated",
                "stored": True,
                "filename": keep.filename,
                "email": None,
                "identity": static_identity,
                "deleted_duplicates": deleted,
                "message": "The existing API key credential was revalidated and updated.",
            },
        )

    incoming = dict(credential_data)
    incoming_expiry = parse_credential_expiry(incoming)
    if email:
        incoming["user_email"] = email
    if is_antigravity:
        filename = canonicalize_antigravity_credential_filename(filename, incoming, email=email)
    if not email:
        target_filename = _find_unique_filename(records, filename, incoming)
        return CredentialPoolMutation(
            writes=(CredentialPoolWrite(target_filename, incoming, None),),
            deletes=(),
            result={
                "action": "created",
                "stored": True,
                "filename": target_filename,
                "email": None,
                "message": "Credential added to the pool. Email was not available, so duplicate detection was skipped.",
            },
        )

    provider = get_credential_provider(incoming)
    matches = [
        record
        for record in records
        if get_credential_provider(record.credential_data) == provider
        and _record_email(record) == email
    ]
    if not matches:
        target_filename = _find_unique_filename(records, filename, incoming)
        return CredentialPoolMutation(
            writes=(CredentialPoolWrite(target_filename, incoming, email),),
            deletes=(),
            result={
                "action": "created",
                "stored": True,
                "filename": target_filename,
                "email": email,
                "incoming_expiry": incoming_expiry.isoformat() if incoming_expiry else None,
                "message": "Credential added to the pool.",
            },
        )

    ranked = [
        {
            "record": record,
            "expiry": parse_credential_expiry(record.credential_data),
            "index": record.rotation_order,
        }
        for record in matches
    ]
    best = max(ranked, key=_best_expiry_key)
    keep = best["record"]
    deleted = [record.filename for record in matches if record.filename != keep.filename]
    if _is_incoming_newer(incoming_expiry, best["expiry"]):
        return CredentialPoolMutation(
            writes=(CredentialPoolWrite(keep.filename, incoming, email),),
            deletes=tuple(deleted),
            result={
                "action": "replaced",
                "stored": True,
                "filename": keep.filename,
                "email": email,
                "incoming_expiry": incoming_expiry.isoformat() if incoming_expiry else None,
                "existing_expiry": best["expiry"].isoformat() if best["expiry"] else None,
                "deleted_duplicates": deleted,
                "message": "Credential replaced because the new expiry is later.",
            },
        )
    return CredentialPoolMutation(
        writes=(),
        deletes=tuple(deleted),
        result={
            "action": "skipped",
            "stored": False,
            "filename": keep.filename,
            "email": email,
            "incoming_expiry": incoming_expiry.isoformat() if incoming_expiry else None,
            "existing_expiry": best["expiry"].isoformat() if best["expiry"] else None,
            "deleted_duplicates": deleted,
            "message": "Credential was not added because the pool already has the same email with an equal or later expiry.",
        },
    )


async def upsert_credential_by_email(
    filename: str,
    credential_data: Dict[str, Any],
    mode: str = "code_assist",
) -> Dict[str, Any]:
    """Store one credential per account or API-key identity."""
    storage_adapter = await get_storage_adapter()
    mode = normalize_pool_mode(mode)
    is_antigravity = (
        mode == "primary" and get_credential_provider(credential_data) == GOOGLE_ANTIGRAVITY
    )
    static_identity = get_static_credential_identity(credential_data)
    email = "" if static_identity else await resolve_credential_email(credential_data)
    return await storage_adapter.mutate_credential_pool(
        mode,
        lambda records: _plan_upsert(
            records,
            filename,
            credential_data,
            email=email,
            static_identity=static_identity,
            is_antigravity=is_antigravity,
        ),
    )


async def deduplicate_credentials_by_account_email(mode: str = "code_assist") -> Dict[str, Any]:
    """Remove duplicate credentials by account email or API-key fingerprint."""
    storage_adapter = await get_storage_adapter()
    mode = normalize_pool_mode(mode)

    def planner(records: tuple[CredentialPoolRecord, ...]) -> CredentialPoolMutation:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        no_email_count = 0
        total_count = 0

        for record in records:
            total_count += 1
            filename = record.filename
            credential_data = record.credential_data
            static_identity = get_static_credential_identity(credential_data or {})
            email = _record_email(record)
            provider_id = get_credential_provider(credential_data or {})
            identity = static_identity or (f"email:{provider_id}:{email}" if email else "")
            if not identity:
                no_email_count += 1
                continue

            grouped.setdefault(identity, []).append(
                {
                    "filename": filename,
                    "data": credential_data or {},
                    "expiry": parse_credential_expiry(credential_data or {}),
                    "index": record.rotation_order,
                    "email": email or None,
                    "identity": identity,
                }
            )

        deleted_count = 0
        groups = []

        for identity, items in grouped.items():
            if len(items) < 2:
                continue

            keep_item = max(items, key=_best_expiry_key)
            deleted_files = []

            for item in items:
                if item["filename"] == keep_item["filename"]:
                    continue
                deleted_files.append(item["filename"])
                deleted_count += 1

            groups.append(
                {
                    "email": keep_item.get("email"),
                    "identity": identity,
                    "kept_file": keep_item["filename"],
                    "kept_expiry": keep_item["expiry"].isoformat() if keep_item["expiry"] else None,
                    "deleted_files": deleted_files,
                    "duplicate_count": len(deleted_files),
                }
            )

        if deleted_count:
            credential_label = "credential" if deleted_count == 1 else "credentials"
            log.info(
                f"Deduplicated {deleted_count} {credential_label} in the {mode} pool "
                "by account identity."
            )

        return CredentialPoolMutation(
            writes=(),
            deletes=tuple(filename for group in groups for filename in group["deleted_files"]),
            result={
                "deleted_count": deleted_count,
                "kept_count": total_count - deleted_count,
                "total_count": total_count,
                "unique_emails_count": sum(
                    1 for identity in grouped if identity.startswith("email:")
                ),
                "unique_identities_count": len(grouped),
                "no_email_count": no_email_count,
                "duplicate_groups": groups,
            },
        )

    return await storage_adapter.mutate_credential_pool(mode, planner)


upsert_credential_by_project_id = upsert_credential_by_email
deduplicate_credentials_by_project_id = deduplicate_credentials_by_account_email
