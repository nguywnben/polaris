"""Kiro portal/PKCE login, using the existing encrypted, expiring flow store.

Callbacks only capture an authorization code. Only the initiating, authenticated
owner can exchange it and save credentials. No new localhost listener is needed.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit

from core.device_authorization_coordination import (
    DeviceAuthorizationBusyError,
    DeviceAuthorizationError,
    get_device_authorization_service,
)
from core.kiro import KiroError
from core.kiro_oauth import SOCIAL_BASE, auth_request, token_credential
from core.provider_store import store_extended_credential

_INVALID = "Kiro login expired or is unavailable. Start a new login."


def _encode(state):
    payload = json.dumps(state, ensure_ascii=True, separators=(",", ":")).encode()
    if len(payload) > 8192:
        raise KiroError(_INVALID, 502)
    return payload


def _origin(value):
    parsed = urlsplit(value)
    if (
        len(value) > 256
        or parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in value)
    ):
        raise KiroError(_INVALID, 400)
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise KiroError(_INVALID, 400)
    return f"{parsed.scheme}://{parsed.netloc}"


async def start_login(token, *, callback_origin, region="us-east-1"):
    origin = _origin(callback_origin)
    if region not in {"us-east-1", "eu-central-1"}:
        raise KiroError(_INVALID, 400)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state = {
        "kind": "browser",
        "owner": hashlib.sha256(token.encode()).hexdigest(),
        "verifier": verifier,
        "origin": origin,
        "region": region,
    }
    service = get_device_authorization_service()
    flow = await service.create(_encode(state), ttl_seconds=600, provider="kiro")
    return {
        "flow_id": flow,
        "expires_in": 600,
        "interval": 2,
        "authorization_url": "https://app.kiro.dev/signin?"
        + urlencode(
            {
                "state": flow,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "redirect_uri": origin,
                "redirect_from": "KiroIDE",
            }
        ),
    }


async def _claim(flow_id, token=None):
    service = get_device_authorization_service()
    try:
        claim = await service.claim(flow_id, lease_seconds=60, provider="kiro")
    except DeviceAuthorizationBusyError:
        raise
    except DeviceAuthorizationError:
        raise KiroError(_INVALID, 409) from None
    state = json.loads(claim.payload)
    if state.get("kind") != "browser" or (
        token is not None
        and not hmac.compare_digest(
            state.get("owner", ""), hashlib.sha256(token.encode()).hexdigest()
        )
    ):
        await service.release(claim)
        raise KiroError(_INVALID, 404)
    return service, claim, state


async def accept_callback(callback_url, *, token=None, flow_id=None):
    if len(callback_url) > 6144 or any(ord(c) < 33 for c in callback_url):
        raise KiroError(_INVALID, 400)
    parsed = urlsplit(callback_url)
    origin = _origin(f"{parsed.scheme}://{parsed.netloc}")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=24)
    params = dict(pairs)
    if (
        len(params) != len(pairs)
        or ("login_option" in params and "loginOption" in params)
        or parsed.fragment
        or parsed.path not in {"/oauth/callback", "/signin/callback"}
        or not params.get("state")
        or (flow_id is not None and params["state"] != flow_id)
    ):
        raise KiroError(_INVALID, 400)
    service, claim, state = await _claim(params["state"], token)
    try:
        if origin != state["origin"] or state.get("callback") or state.get("credential"):
            raise KiroError(_INVALID, 409)
        option = params.get("login_option", params.get("loginOption", "")).lower()
        code = params.get("code", "")
        if len(code) > 4096 or not code.isascii() or any(ord(c) < 33 for c in code):
            raise KiroError(_INVALID, 400)
        error = (
            "denied"
            if params.get("error")
            else ("unsupported_method" if option not in {"google", "github"} else "")
        )
        if not code and not error:
            raise KiroError(_INVALID, 400)
        state["callback"] = {"code": code, "option": option, "path": parsed.path, "error": error}
        return {"status": "received"}
    finally:
        await asyncio.shield(service.release(claim, payload=_encode(state)))


async def cancel_login(token, flow_id):
    service, claim, _state = await _claim(flow_id, token)
    await service.consume(claim)
    return {"status": "cancelled"}


async def complete_login(token, flow_id):
    service, claim, state = await _claim(flow_id, token)
    consumed = False
    try:
        callback = state.get("callback")
        if not callback and not state.get("credential"):
            return {"status": "pending", "interval": 2}
        if callback and callback["error"]:
            await service.consume(claim)
            consumed = True
            return {"status": "error", "reason": callback["error"]}
        if not state.get("credential"):
            try:
                status, tokens = await auth_request(
                    SOCIAL_BASE + "/oauth/token",
                    {
                        "code": callback["code"],
                        "code_verifier": state["verifier"],
                        "redirect_uri": state["origin"]
                        + callback["path"]
                        + "?"
                        + urlencode({"login_option": callback["option"]}),
                    },
                )
                if status != 200 or tokens.get("error"):
                    raise KiroError(_INVALID, 502)
                tokens = tokens.get("data", tokens)
                if not isinstance(tokens, dict):
                    raise KiroError(_INVALID, 502)
                credential = token_credential(
                    {
                        "provider": "kiro",
                        "credential_type": "oauth",
                        "auth_method": "social",
                        "region": state["region"],
                    },
                    tokens,
                )
                if not credential.get("refresh_token"):
                    raise KiroError(_INVALID, 502)
                state["credential"] = credential
                state.pop("callback", None)
                state.pop("verifier", None)
                _encode(state)
            except BaseException:
                # A timed-out exchange may already have spent the one-use code.
                await asyncio.shield(service.consume(claim))
                consumed = True
                raise
        saved = await store_extended_credential(state["credential"], [])
        await service.consume(claim)
        consumed = True
        return {
            "status": "complete",
            "credential_saved": True,
            "credential_action": saved["action"],
            "filename": saved["filename"],
            "connection_test_required": True,
        }
    finally:
        if not consumed:
            await asyncio.shield(service.release(claim, payload=_encode(state)))
