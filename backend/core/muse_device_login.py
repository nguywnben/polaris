"""Explicit, owner-bound Muse Code login using encrypted single-use flow state."""

import asyncio
import hashlib
import hmac
import json
import time

from core.device_authorization_coordination import (
    DeviceAuthorizationError,
    get_device_authorization_service,
)
from core.muse_code import discover_minted_models
from core.muse_oauth import (
    MuseOAuthError,
    exchange_device_token,
    mint_key,
    start_device_authorization,
)
from core.provider_store import store_extended_credential

_INVALID_FLOW = "Muse Code login expired or is unavailable. Start a new login."


def _owner(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _encode(state: dict) -> bytes:
    return json.dumps(state, ensure_ascii=True, separators=(",", ":")).encode()


async def start_login(token: str, *, credential_label: str = "") -> dict:
    if not isinstance(credential_label, str) or len(credential_label) > 128:
        raise MuseOAuthError("Invalid credential label.", 400)
    device = await start_device_authorization()
    expires = min(device["expires_in"], 900)
    if expires < 60:
        raise MuseOAuthError("Muse Code login expires too soon. Start a new login.")
    state = {
        "owner": _owner(token),
        "credential_label": credential_label.strip(),
        "device_code": device["device_code"],
        "interval": device["interval"],
        "next_check": time.time() + device["interval"],
    }
    try:
        flow = await get_device_authorization_service().create(
            _encode(state),
            ttl_seconds=expires,
            provider="muse_code",
        )
    except DeviceAuthorizationError:
        raise MuseOAuthError("Unable to start Muse Code login.", 503) from None
    return {
        "flow_id": flow,
        "verification_uri": device["verification_uri_complete"],
        "user_code": device["user_code"],
        "expires_in": expires,
        "interval": device["interval"],
        "status": "pending",
    }


async def _claim(token: str, flow_id: str):
    service = get_device_authorization_service()
    try:
        claim = await service.claim(flow_id, lease_seconds=60, provider="muse_code")
    except DeviceAuthorizationError:
        raise MuseOAuthError(_INVALID_FLOW, 409, "invalid_flow") from None
    try:
        state = json.loads(claim.payload)
        if not hmac.compare_digest(state.get("owner", ""), _owner(token)):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        await service.release(claim)
        raise MuseOAuthError(_INVALID_FLOW, 404, "invalid_flow") from None
    return service, claim, state


async def cancel_login(token: str, flow_id: str) -> dict:
    service, claim, _state = await _claim(token, flow_id)
    await service.consume(claim)
    return {"success": True, "status": "cancelled"}


async def complete_login(token: str, flow_id: str) -> dict:
    """One explicit check/save, never a polling task or automatic OAuth completion."""
    service, claim, state = await _claim(token, flow_id)
    consumed = False
    try:
        if time.time() < state["next_check"]:
            return {"status": "pending", "interval": state["interval"]}
        state["next_check"] = time.time() + state["interval"]
        # Finish before the lease ends so a concurrent owner request cannot replay
        # the exchange or save. Storage retries retain the captured one-use grant.
        remaining = min(45, await service.lease_remaining_seconds(claim) - 2)
        if remaining <= 0:
            raise MuseOAuthError(_INVALID_FLOW, 409, "expired_token")
        async with asyncio.timeout(remaining):
            if "tokens" not in state and "credential" not in state:
                state["tokens"] = await exchange_device_token(state["device_code"])
                state.pop("device_code", None)
                if len(_encode(state)) > 8192:
                    await service.consume(claim)
                    consumed = True
                    raise MuseOAuthError("Muse Code credentials exceeded the size limit.")
            if "credential" not in state:
                state["credential"] = {
                    **await mint_key(state["tokens"]["access_token"]),
                    **state["tokens"],
                    "credential_label": state["credential_label"],
                }
                state.pop("tokens", None)
                if len(_encode(state)) > 8192:
                    await service.consume(claim)
                    consumed = True
                    raise MuseOAuthError("Muse Code credentials exceeded the size limit.")
            models = await discover_minted_models(state["credential"])
            saved = await store_extended_credential(state["credential"], models)
            await service.consume(claim)
            consumed = True
        return {
            "success": True,
            "status": "complete",
            "credential_saved": True,
            "provider": "muse_code",
            "provider_variant": "muse_code",
            "filename": saved["filename"],
            "credential_action": saved["action"],
            "model_count": len(models),
            "connection_test_required": True,
            "message": "Credential saved. Open the credential pool and test a model to check inference access.",
        }
    except MuseOAuthError as exc:
        if exc.code in {"authorization_pending", "slow_down"}:
            if exc.code == "slow_down":
                state["interval"] = min(state["interval"] + 5, 600)
            state["next_check"] = time.time() + state["interval"]
            return {"status": "pending", "interval": state["interval"]}
        if exc.code in {
            "expired_token",
            "access_denied",
            "subscription_required",
            "reauthorization_required",
        }:
            await service.consume(claim)
            consumed = True
        raise
    except TimeoutError:
        raise MuseOAuthError("Muse Code login check timed out. Try again.", 504) from None
    finally:
        if not consumed:
            await asyncio.shield(service.release(claim, payload=_encode(state)))
