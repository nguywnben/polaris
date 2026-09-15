"""Bounded Kiro OAuth network boundary. Never return upstream error descriptions."""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from core.httpx_client import http_client
from core.kiro import KiroError
from core.kiro_credentials import normalize_oauth

SOCIAL_BASE = "https://prod.us-east-1.auth.desktop.kiro.dev"


async def auth_request(url: str, body: dict) -> tuple[int, dict]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port
        or not (
            parsed.hostname == "prod.us-east-1.auth.desktop.kiro.dev"
            or re.fullmatch(
                r"oidc\.(?:us|eu|ap|ca|sa|me|af|il|mx)-(?:[a-z]+-)?[a-z]+-\d\.amazonaws\.com",
                parsed.hostname or "",
            )
        )
    ):
        raise KiroError("Invalid Kiro authorization endpoint.")
    try:
        async with http_client.get_client(
            timeout=20.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream(
                "POST", url, json=body, headers={"Accept": "application/json"}
            ) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 65536:
                        raise KiroError("Kiro authorization response exceeded the size limit.", 502)
                    content.extend(chunk)
                payload = json.loads(content)
                if not isinstance(payload, dict):
                    raise ValueError
                return response.status_code, payload
    except (httpx.HTTPError, OSError):
        raise KiroError("Unable to reach the Kiro authorization service.", 502) from None
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, KiroError):
            raise
        raise KiroError("Kiro returned an invalid authorization response.", 502) from None


def token_credential(data: dict, tokens: dict) -> dict:
    for camel, snake in (
        ("accessToken", "access_token"),
        ("refreshToken", "refresh_token"),
        ("expiresIn", "expires_in"),
    ):
        if camel in tokens and snake in tokens and tokens[camel] != tokens[snake]:
            raise KiroError("Kiro returned conflicting authorization credentials.", 502)
    access = tokens.get("accessToken") or tokens.get("access_token")
    seconds = tokens.get("expiresIn", tokens.get("expires_in", 3600))
    if not access or type(seconds) is not int or not 1 <= seconds <= 86400:
        raise KiroError("Kiro returned incomplete authorization credentials.", 502)
    updated = {
        **data,
        "access_token": access,
        "refresh_token": tokens.get("refreshToken")
        or tokens.get("refresh_token")
        or data.get("refresh_token", ""),
        "expiry": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
    }
    if tokens.get("profileArn"):
        updated["profile_arn"] = tokens["profileArn"]
    try:
        return {**data, **normalize_oauth(updated)}
    except ValueError:
        raise KiroError("Kiro returned invalid authorization credentials.", 502) from None


async def refresh_credential(data: dict) -> dict:
    credential = normalize_oauth(data)
    refresh = credential["refresh_token"]
    if not refresh:
        raise KiroError("Kiro OAuth session cannot be renewed. Sign in again.", 401)
    if credential["auth_method"] == "idc":
        url = f"https://oidc.{credential['token_region']}.amazonaws.com/token"
        body = {
            "clientId": credential["client_id"],
            "clientSecret": credential["client_secret"],
            "refreshToken": refresh,
            "grantType": "refresh_token",
        }
    else:
        url, body = SOCIAL_BASE + "/refreshToken", {"refreshToken": refresh}
    status, tokens = await auth_request(url, body)
    if status != 200 or tokens.get("error"):
        code = (
            401
            if tokens.get("error") in {"invalid_grant", "invalid_client"} or status in {401, 403}
            else 502
        )
        raise KiroError(
            "Kiro OAuth session could not be renewed. Check the connection or sign in again.", code
        )
    return token_credential({**data, **credential}, tokens)
