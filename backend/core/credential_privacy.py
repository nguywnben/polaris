"""Privacy projections for account identity; never apply these to stored credentials."""

import hashlib
import hmac
import re

_EMAIL_IN_TEXT = re.compile(r"[^\s<>\(\)\"',;:@/\\]+@[^\s<>\(\)\"',;:@/\\]+")


def mask_account_email(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if not _EMAIL_IN_TEXT.fullmatch(value):
        return "***"
    local, domain = value.rsplit("@", 1)
    if "***" in local:
        return value
    visible = (
        f"{local[:2]}***{local[-2:]}"
        if len(local) > 4
        else f"{local[:1] if len(local) > 2 else ''}***"
    )
    return f"{visible}@{domain}"


def mask_email_text(value: object) -> object:
    """Preserve ordinary custom labels, but not addresses embedded in them."""
    if not isinstance(value, str):
        return value
    return _EMAIL_IN_TEXT.sub(lambda match: mask_account_email(match.group()) or "***", value)


def credential_account_email(content: dict, state: dict) -> str | None:
    for value in (content.get("user_email"), content.get("email"), state.get("user_email")):
        if isinstance(value, str) and _EMAIL_IN_TEXT.fullmatch(value.strip()):
            return value.strip()
    return None


CREDENTIAL_REFERENCE_PREFIX = "credref-v1-"
_REFERENCE_DOMAIN = b"polaris/credential-reference/v1\x00"
_FILENAME_FIELDS = frozenset(
    {
        "filename",
        "file_path",
        "selected_filename",
        "filenames",
        "file",
        "files",
        "credential_name",
        "credential_file",
        "credential_filename",
        "source_filename",
        "kept_file",
        "deleted_files",
        "deleted_duplicates",
        "existing_env_files",
    }
)
_DIAGNOSTIC_FIELDS = frozenset(
    {"message", "messages", "credential_message", "error", "error_messages", "detail", "reason"}
)


def private_credential_filename(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.lower().endswith(".json")
        and not any(character in value for character in ("/", "\\", "\x00", "\r", "\n"))
        and ("@" in value or value.startswith(CREDENTIAL_REFERENCE_PREFIX))
    )


def credential_reference(filename: str, key: bytes) -> str:
    """Stable opaque display ID, not an authorization token or storage key."""
    if not private_credential_filename(filename):
        return filename
    if type(key) is not bytes or len(key) != 32:
        raise ValueError("Credential reference key is unavailable.")
    digest = hmac.digest(key, _REFERENCE_DOMAIN + filename.encode("utf-8"), hashlib.sha256).hex()
    return f"{CREDENTIAL_REFERENCE_PREFIX}{digest}.json"


def project_credential_references(
    value: object, key: bytes, *, field: str = "", diagnostic: bool = False
) -> object:
    """Project only inventory keys/fields and free-text diagnostics; never mutate input."""
    diagnostic = diagnostic or field in _DIAGNOSTIC_FIELDS
    if isinstance(value, dict):
        return {
            credential_reference(name, key): project_credential_references(
                item, key, field=name, diagnostic=diagnostic
            )
            for name, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            project_credential_references(item, key, field=field, diagnostic=diagnostic)
            for item in value
        ]
    if isinstance(value, str):
        if field in _FILENAME_FIELDS:
            if private_credential_filename(value):
                return credential_reference(value, key)
            # Import source descriptions can contain archive paths or mode prefixes.
            return mask_email_text(value)
        if field in {"user_email", "email", "account_email", "credential_label"} or diagnostic:
            return mask_email_text(value)
    return value
