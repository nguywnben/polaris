"""Provider-neutral credential input validation."""

from fastapi import HTTPException


def validate_credential_filename(filename: str) -> str:
    """Validate a credential storage key before it reaches a backend or log entry."""
    value = str(filename or "")
    invalid = (
        not value
        or len(value) > 255
        or not value.lower().endswith(".json")
        or value in {".", ".."}
        or any(character in value for character in ("/", "\\", "\x00", "\r", "\n"))
    )
    if invalid:
        raise HTTPException(status_code=400, detail="Invalid credential file name.")
    return value
