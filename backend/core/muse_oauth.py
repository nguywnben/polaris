"""Muse Code's verified device grant and inference-key boundary.

Device contract: official Muse Code launcher, https://api.meta.ai/muse-launcher.sh.
Key contract: official CLI 1.3.0 and authorized live probes on 2026-09-16; see
docs/providers/muse-code-research-2026-09-16.md. No conventional refresh grant is
advertised. Re-minting an inference key is distinct from refreshing an OAuth token.
"""

import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx
from core.httpx_client import http_client

CLIENT_ID = "1031625952748946"
DEVICE_ENDPOINT = "https://auth.meta.com/oidc/device/authorization/"
TOKEN_ENDPOINT = "https://auth.meta.com/oidc/device/token/"
KEY_ENDPOINT = "https://api.meta.ai/muse-code/key"
API_BASE = "https://api.meta.ai/v1"
AUTH_ENDPOINTS = frozenset({DEVICE_ENDPOINT, TOKEN_ENDPOINT, KEY_ENDPOINT})
USER_AGENT = "Polaris/0.1 (Muse Code integration)"
MAX_RESPONSE_BYTES = 65536


class MuseOAuthError(ValueError):
    """Safe error details; vendor descriptions and credential values are omitted."""

    def __init__(self, message: str, status_code: int = 502, code: str = "invalid_response"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _secret(value) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 8192
        or any(not 33 <= ord(c) <= 126 for c in value)
    ):
        raise MuseOAuthError("Muse Code returned invalid credentials.")
    return value


def _integer(value, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise MuseOAuthError("Muse Code returned invalid authorization metadata.")
    return value


async def _request(url: str, body: dict, *, access_token: str | None = None) -> tuple[int, dict]:
    if url not in AUTH_ENDPOINTS or (access_token is not None) != (url == KEY_ENDPOINT):
        raise MuseOAuthError("Invalid Muse Code authorization endpoint.", 400)
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    arguments = {"data": body}
    if access_token is not None:
        headers["Authorization"] = "Bearer " + _secret(access_token)
        arguments = {"json": body}
    try:
        async with http_client.get_client(
            timeout=20.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream("POST", url, headers=headers, **arguments) as response:
                if 300 <= response.status_code < 400:
                    raise MuseOAuthError("Muse Code authorization redirects are not accepted.")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise MuseOAuthError(
                            "Muse Code authorization response exceeded the size limit."
                        )
                    content.extend(chunk)
                payload = json.loads(content)
                if not isinstance(payload, dict):
                    raise ValueError
                return response.status_code, payload
    except (httpx.HTTPError, OSError):
        raise MuseOAuthError("Unable to reach the Muse Code authorization service.") from None
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, MuseOAuthError):
            raise
        raise MuseOAuthError("Muse Code returned an invalid authorization response.") from None


def _verification_url(value, user_code: str | None = None) -> str:
    try:
        if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
            raise ValueError
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "auth.meta.com"
            or parsed.path != "/oauth/device/"
            or parsed.fragment
        ):
            raise ValueError
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        if query != ({"code": [user_code]} if user_code else {}):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise MuseOAuthError("Muse Code returned an invalid authorization link.") from None


async def start_device_authorization() -> dict:
    status, data = await _request(DEVICE_ENDPOINT, {"client_id": CLIENT_ID})
    if status != 200 or data.get("error"):
        raise MuseOAuthError("Unable to start Muse Code login.")
    code = data.get("user_code")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", code):
        raise MuseOAuthError("Muse Code returned an invalid device code.")
    return {
        "device_code": _secret(data.get("device_code")),
        "user_code": code,
        "verification_uri": _verification_url(data.get("verification_uri")),
        "verification_uri_complete": _verification_url(data.get("verification_uri_complete"), code),
        "expires_in": _integer(data.get("expires_in"), 1, 86400),
        "interval": _integer(data.get("interval", 5), 1, 600),
    }


async def exchange_device_token(device_code: str) -> dict:
    """Perform exactly one exchange; the owner-bound caller enforces the interval."""
    status, data = await _request(
        TOKEN_ENDPOINT,
        {
            "client_id": CLIENT_ID,
            "device_code": _secret(device_code),
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )
    errors = {
        "authorization_pending": "Muse Code login has not been approved yet.",
        "slow_down": "Wait before checking Muse Code login again.",
        "expired_token": "Muse Code login expired. Start a new login.",
        "access_denied": "Muse Code login was declined.",
    }
    code = data.get("error")
    if isinstance(code, str) and code in errors:
        raise MuseOAuthError(errors[code], 400, code)
    if status != 200 or code or data.get("token_type") != "Bearer":
        raise MuseOAuthError("Unable to complete Muse Code login.")
    result = {"access_token": _secret(data.get("access_token"))}
    if "expires_in" in data:
        result["oauth_expires_at"] = int(time.time()) + _integer(data["expires_in"], 1, 31536000)
    return result


def subscription_label(value) -> str | None:
    """Bound optional upstream display metadata without inventing a plan."""
    if not isinstance(value, str) or not value.isprintable():
        return None
    value = value.strip()
    if not 1 <= len(value) <= 128 or value.casefold() in {
        "unknown",
        "not_applicable",
        "n/a",
        "none",
    }:
        return None
    return value


def subscription_usage(value) -> dict | None:
    """Keep valid server windows in epoch seconds; missing usage is not zero."""
    try:
        if not isinstance(value, dict):
            return None
        result = {"observed_at": int(time.time())}
        tier = subscription_label(value.get("tier"))
        if tier:
            result["tier"] = tier
        for name in ("window", "weekly"):
            block = value.get(name)
            if not isinstance(block, dict):
                return None
            result[name] = {
                "used_percent": _integer(block.get("used_percent"), 0, 100000),
                "resets_at": _integer(block.get("resets_at"), 0, 253402300799),
            }
            if name == "window":
                result[name]["window_duration_mins"] = _integer(
                    block.get("window_duration_mins"), 1, 525600
                )
        return result
    except MuseOAuthError:
        return None


async def mint_key(access_token: str) -> dict:
    """Obtain the account's inference key without switching to pay-as-you-go."""
    status, data = await _request(KEY_ENDPOINT, {}, access_token=access_token)
    if status == 401:
        raise MuseOAuthError(
            "Muse Code session is no longer valid. Sign in again.", 401, "reauthorization_required"
        )
    if status != 200 or data.get("error"):
        raise MuseOAuthError("Unable to obtain a Muse Code inference key.")
    if data.get("is_subs_active") is not True or data.get("require_payment") is not False:
        raise MuseOAuthError(
            "An active Muse Code subscription is required.", 403, "subscription_required"
        )
    if data.get("base_url") != API_BASE:
        raise MuseOAuthError("Muse Code returned an unsupported API endpoint.")
    email = data.get("user_email")
    if (
        not isinstance(email, str)
        or not 3 <= len(email) <= 320
        or "@" not in email
        or any(c.isspace() or not c.isprintable() for c in email)
    ):
        raise MuseOAuthError("Muse Code returned incomplete account information.")
    return {
        "provider": "muse_code",
        "credential_type": "oauth",
        "access_token": _secret(access_token),
        "api_key": _secret(data.get("api_key")),
        "base_url": API_BASE,
        "account_id": hashlib.sha256(email.casefold().encode()).hexdigest(),
        "subscription_plan": subscription_label(data.get("subs_tier_name")),
        "subscription_usage": subscription_usage(data.get("subs_usage")),
    }
