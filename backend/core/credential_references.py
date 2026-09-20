"""Resolve console-only credential IDs after authorization, without renaming storage."""

import base64
import binascii
import re

from core.credential_privacy import (
    CREDENTIAL_REFERENCE_PREFIX,
    credential_reference,
    private_credential_filename,
)
from core.credential_validation import validate_credential_filename
from fastapi import HTTPException

_REFERENCE_PATTERN = re.compile(r"credref-v1-[0-9a-f]{64}\.json")


async def credential_reference_key(storage=None) -> bytes:
    # Reuse the high-entropy durable root, with a separate HMAC domain. Unlike a
    # password-derived or process-random key this survives restarts and workers.
    if storage is None:
        from core.storage_adapter import get_storage_adapter

        storage = await get_storage_adapter()
    encoded = await storage.get_config("_internal_session_master_key_v1", None)
    try:
        if type(encoded) is not str or len(encoded) != 44:
            raise ValueError
        key = base64.b64decode(encoded, altchars=b"-_", validate=True)
        if len(key) != 32 or base64.urlsafe_b64encode(key).decode("ascii") != encoded:
            raise ValueError
        return key
    except (ValueError, binascii.Error):
        raise HTTPException(
            status_code=503, detail="Credential references are unavailable."
        ) from None


async def resolve_credential_reference(value: str, *, mode: str) -> str:
    """Call inside authenticated handlers, with a validated internal mode."""
    resolved = await resolve_credential_references([value], mode=mode)
    return validate_credential_filename(resolved[0])


async def resolve_credential_references(values: list[str], *, mode: str) -> list[str]:
    """Resolve a batch with one inventory read; ordinary invalid inputs stay with its planner."""
    if mode not in {"primary", "code_assist"}:
        raise ValueError("Credential reference mode must be normalized.")
    aliases = set()
    for value in values:
        if value.startswith(CREDENTIAL_REFERENCE_PREFIX):
            if not _REFERENCE_PATTERN.fullmatch(value):
                raise HTTPException(status_code=404, detail="Credential does not exist.")
            aliases.add(value)
        elif private_credential_filename(value):
            # Do not offer an email-guessing existence oracle on ordinary routes.
            raise HTTPException(status_code=404, detail="Credential does not exist.")
    if not aliases:
        return list(values)
    from core.storage_adapter import get_storage_adapter

    storage = await get_storage_adapter()
    key = await credential_reference_key(storage)
    matches = {}
    for filename in await storage.list_credentials(mode=mode):
        if not private_credential_filename(filename):
            continue
        reference = credential_reference(filename, key)
        if reference in aliases:
            if reference in matches:
                raise HTTPException(status_code=404, detail="Credential does not exist.")
            matches[reference] = validate_credential_filename(filename)
    if aliases != matches.keys():
        raise HTTPException(status_code=404, detail="Credential does not exist.")
    return [matches.get(value, value) for value in values]
