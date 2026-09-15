"""Owner-bound Kiro device grants using Polaris' encrypted flow coordinator."""

import asyncio
import hashlib
import hmac
import json
import math
import re
import time
from urllib.parse import urlsplit

from core.device_authorization_coordination import (
    DeviceAuthorizationError,
    get_device_authorization_service,
)
from core.kiro import KiroError
from core.kiro_oauth import SOCIAL_BASE, auth_request, token_credential
from core.provider_store import store_extended_credential

_REGION = re.compile(r"(?:us|eu|ap|ca|sa|me|af|il|mx)-(?:[a-z]+-)?[a-z]+-\d")
_INVALID_FLOW = "Kiro login expired or is unavailable. Start a new login."


def _owner(token: str) -> str:
    return hashlib.sha256(str(token).encode()).hexdigest()


def _encode(state: dict) -> bytes:
    return json.dumps(state, ensure_ascii=True, separators=(",", ":")).encode()


def _secret(data: dict, key: str) -> str:
    value = data.get(key)
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 4096
        or not value.isascii()
        or any(c.isspace() for c in value)
    ):
        raise KiroError("Kiro returned incomplete authorization credentials.", 502)
    return value


def _trusted_url(value: str, *, enterprise: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        allowed = (
            host.endswith(".awsapps.com")
            if enterprise
            else (
                host in {"app.kiro.dev", "view.awsapps.com"}
                or re.fullmatch(r"device\.sso\.[a-z0-9-]+\.amazonaws\.com", host)
            )
        )
        if (
            len(value) > 2048
            or any(ord(c) < 33 for c in value)
            or parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port
            or not allowed
        ):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise KiroError("Invalid Kiro authorization URL.") from None


async def start_login(
    token: str,
    *,
    method: str,
    region: str = "us-east-1",
    token_region: str = "us-east-1",
    start_url: str = "",
    credential_label: str = "",
) -> dict:
    if (
        method not in {"google", "github", "builder-id", "identity-center"}
        or region not in {"us-east-1", "eu-central-1"}
        or not _REGION.fullmatch(token_region)
    ):
        raise KiroError("Unsupported Kiro OAuth authentication method or region.")
    service = get_device_authorization_service()
    credential = {
        "provider": "kiro",
        "credential_type": "oauth",
        "region": region,
        "credential_label": credential_label,
    }
    if method in {"google", "github"}:
        credential["auth_method"] = "social"
        status, device = await auth_request(
            SOCIAL_BASE + "/oauth/device/authorization",
            {
                "clientId": "kiro-cli",
                "loginProvider": "Google" if method == "google" else "Github",
            },
        )
        divisor, expiry_key, interval_key = 1000, "expiresInMilliseconds", "intervalInMilliseconds"
    else:
        start_url = (
            "https://view.awsapps.com/start"
            if method == "builder-id"
            else _trusted_url(start_url, enterprise=True)
        )
        base = f"https://oidc.{token_region}.amazonaws.com"
        status, registration = await auth_request(
            base + "/client/register",
            {
                "clientName": "Polaris Kiro",
                "clientType": "public",
                "scopes": [
                    "codewhisperer:completions",
                    "codewhisperer:analysis",
                    "codewhisperer:conversations",
                ],
                "grantTypes": ["urn:ietf:params:oauth:grant-type:device_code", "refresh_token"],
                "issuerUrl": start_url,
            },
        )
        if status != 200:
            raise KiroError("Unable to start Kiro authorization. Try again.", 502)
        credential.update(
            auth_method="idc",
            token_region=token_region,
            client_id=_secret(registration, "clientId"),
            client_secret=_secret(registration, "clientSecret"),
        )
        status, device = await auth_request(
            base + "/device_authorization",
            {
                "clientId": credential["client_id"],
                "clientSecret": credential["client_secret"],
                "startUrl": start_url,
            },
        )
        divisor, expiry_key, interval_key = 1, "expiresIn", "interval"
    if status != 200 or device.get("error"):
        raise KiroError("Unable to start Kiro authorization. Try again.", 502)
    expires, interval = device.get(expiry_key, 300 * divisor), device.get(interval_key, 5 * divisor)
    if (
        type(expires) is not int
        or type(interval) is not int
        or expires < 60 * divisor
        or interval < divisor
        or interval > 60 * divisor
    ):
        raise KiroError("Kiro returned an invalid authorization response.", 502)
    expires, interval = min(expires // divisor, 900), math.ceil(interval / divisor)
    verification = _trusted_url(
        device.get("verificationUriComplete") or device.get("verificationUri", "")
    )
    code = _secret(device, "userCode")
    state = {
        "owner": _owner(token),
        "credential": credential,
        "device_code": _secret(device, "deviceCode"),
        "interval": interval,
        "next_poll": time.time() + interval,
    }
    try:
        flow = await service.create(_encode(state), ttl_seconds=expires, provider="kiro")
    except DeviceAuthorizationError:
        raise KiroError("Unable to start Kiro authorization. Try again.", 503) from None
    return {
        "flow_id": flow,
        "verification_uri": verification,
        "user_code": code,
        "expires_in": expires,
        "interval": interval,
        "status": "pending",
    }


async def _claim(token: str, flow_id: str):
    try:
        service = get_device_authorization_service()
        claim = await service.claim(flow_id, lease_seconds=60, provider="kiro")
    except DeviceAuthorizationError:
        raise KiroError(_INVALID_FLOW, 409) from None
    state = json.loads(claim.payload)
    if not hmac.compare_digest(state.get("owner", ""), _owner(token)):
        await service.release(claim)
        raise KiroError(_INVALID_FLOW, 404)
    return service, claim, state


async def cancel_login(token: str, flow_id: str) -> dict:
    service, claim, _state = await _claim(token, flow_id)
    await service.consume(claim)
    return {"success": True, "status": "cancelled"}


async def poll_login(token: str, flow_id: str) -> dict:
    service, claim, state = await _claim(token, flow_id)
    consumed = False
    try:
        credential = state["credential"]
        if not state.get("authorized"):
            if time.time() < state["next_poll"]:
                return {"status": "pending", "interval": state["interval"]}
            if credential["auth_method"] == "social":
                url, body = (
                    SOCIAL_BASE + "/oauth/device/poll",
                    {"clientId": "kiro-cli", "deviceCode": state["device_code"]},
                )
            else:
                url = f"https://oidc.{credential['token_region']}.amazonaws.com/token"
                body = {
                    "clientId": credential["client_id"],
                    "clientSecret": credential["client_secret"],
                    "deviceCode": state["device_code"],
                    "grantType": "urn:ietf:params:oauth:grant-type:device_code",
                }
            # Throttle retries even when the upstream fails transiently.
            state["next_poll"] = time.time() + state["interval"]
            status, tokens = await auth_request(url, body)
            error = tokens.get("error")
            if error in {"authorization_pending", "slow_down"}:
                if error == "slow_down":
                    state["interval"] = min(state["interval"] + 5, 60)
                state["next_poll"] = time.time() + state["interval"]
                return {"status": "pending", "interval": state["interval"]}
            if status != 200 or error:
                if status < 500 and status != 429:
                    await service.consume(claim)
                    consumed = True
                raise KiroError(
                    "Kiro authorization was not completed. Try again or start a new login.", 502
                )
            credential = token_credential(credential, tokens)
            if not credential.get("refresh_token"):
                raise KiroError("Kiro returned incomplete authorization credentials.", 502)
            state.update(credential=credential, authorized=True)
            state.pop("device_code", None)
            # Keep the captured grant within the encrypted coordinator's bound.
            # An oversized response must not leave a retryable one-use exchange.
            if len(_encode(state)) > 8 * 1024:
                await service.consume(claim)
                consumed = True
                raise KiroError("Kiro authorization credentials exceeded the size limit.", 502)
        # Save first; a retry after storage failure uses the captured credentials,
        # never exchanges the same one-use device grant again.
        saved = await store_extended_credential(credential, [])
        await service.consume(claim)
        consumed = True
        return {
            "success": True,
            "status": "complete",
            "credential_saved": True,
            "provider": "kiro",
            "provider_variant": "kiro",
            "filename": saved["filename"],
            "credential_action": saved["action"],
            "model_count": 0,
            "connection_test_required": True,
            "message": "Credential saved. Open the credential pool and test a model to check inference access.",
        }
    finally:
        if not consumed:
            await asyncio.shield(service.release(claim, payload=_encode(state)))
