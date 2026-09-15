"""Validation for configurable Google OAuth and provider API base URLs."""

from __future__ import annotations

from urllib.parse import SplitResult, urlsplit, urlunsplit

TRUSTED_GOOGLE_OAUTH_ORIGINS = {
    "oauth_url": "https://oauth2.googleapis.com",
    "google_apis_url": "https://www.googleapis.com",
}


def _parse_base_url(value: str, *, setting_name: str) -> SplitResult:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"Google setting '{setting_name}' must not be empty.")
    if "\\" in normalized or any(character.isspace() for character in normalized):
        raise ValueError(f"Google setting '{setting_name}' contains invalid URL characters.")

    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"Google setting '{setting_name}' is not a valid URL.") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"Google setting '{setting_name}' must use HTTP or HTTPS.")
    if not parsed.hostname:
        raise ValueError(f"Google setting '{setting_name}' must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"Google setting '{setting_name}' must not include URL credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"Google setting '{setting_name}' must not include a query or fragment.")

    return parsed._replace(
        scheme=parsed.scheme.lower(), netloc=parsed.netloc, query="", fragment=""
    )


def normalize_google_oauth_base_url(value: str, *, setting_name: str) -> str:
    """Return a trusted Google origin for a secret-bearing OAuth request."""
    trusted_origin = TRUSTED_GOOGLE_OAUTH_ORIGINS.get(setting_name)
    if trusted_origin is None:
        raise ValueError(f"Google OAuth setting '{setting_name}' is not supported.")

    parsed = _parse_base_url(value, setting_name=setting_name)
    trusted = urlsplit(trusted_origin)
    if (
        parsed.scheme != "https"
        or parsed.hostname.lower() != trusted.hostname
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(
            f"Google setting '{setting_name}' must use the trusted Google HTTPS origin "
            f"{trusted_origin}."
        )
    return trusted_origin


def normalize_google_api_base_url(value: str, *, setting_name: str) -> str:
    """Normalize an HTTP(S) API base while retaining explicit proxy customization."""
    parsed = _parse_base_url(value, setting_name=setting_name)
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
