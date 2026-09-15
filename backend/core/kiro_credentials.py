"""Canonical Kiro OAuth credentials; exported metadata is never authorization."""

import hashlib
import json
import re
from datetime import datetime, timezone


def _field(data, *names, required=False):
    values = {data[name] for name in names if isinstance(data.get(name), str) and data[name]}
    if any(data.get(name) is not None and not isinstance(data[name], str) for name in names):
        raise ValueError("Invalid Kiro credential field.")
    if len(values) > 1 or (required and not values):
        raise ValueError("Kiro credential fields are missing or conflicting.")
    value = next(iter(values), "")
    if value and (len(value) > 16384 or not value.isascii() or any(c.isspace() for c in value)):
        raise ValueError("Invalid Kiro credential field.")
    return value


def normalize_oauth(data):
    if data.get("api_key") or data.get("credential_type") not in (None, "", "oauth"):
        raise ValueError("Import one Kiro authentication method at a time.")
    access = _field(data, "access_token", "accessToken")
    refresh = _field(data, "refresh_token", "refreshToken")
    if not access and not refresh:
        raise ValueError("Kiro OAuth requires an access or refresh token.")
    method = _field(data, "auth_method", "authMethod").lower() or (
        "idc" if data.get("client_id") or data.get("clientId") else "social"
    )
    method = {"builder-id": "idc", "builder_id": "idc", "iam": "idc"}.get(method, method)
    if method not in {"social", "idc"}:
        raise ValueError("Unsupported Kiro OAuth authentication method.")
    region = _field(data, "region") or "us-east-1"
    if region not in {"us-east-1", "eu-central-1"}:
        raise ValueError("Kiro runtime region must be us-east-1 or eu-central-1.")
    result = {
        "provider": "kiro",
        "credential_type": "oauth",
        "auth_method": method,
        "region": region,
        "access_token": access,
        "refresh_token": refresh,
    }
    if method == "idc":
        result["client_id"] = _field(data, "client_id", "clientId", required=True)
        result["client_secret"] = _field(data, "client_secret", "clientSecret", required=True)
        token_region = (
            _field(
                data,
                "token_region",
                "tokenRegion",
                "sso_region",
                "ssoRegion",
                "idc_region",
                "idcRegion",
            )
            or region
        )
        if not re.fullmatch(r"(?:us|eu|ap|ca|sa|me|af|il|mx)-(?:[a-z]+-)?[a-z]+-\d", token_region):
            raise ValueError("Invalid Kiro OAuth region.")
        result["token_region"] = token_region
    arn = _field(data, "profile_arn", "profileArn")
    if arn:
        if not re.fullmatch(
            rf"arn:aws:codewhisperer:{region}:\d{{12}}:profile/[A-Za-z0-9_-]{{1,128}}", arn
        ):
            raise ValueError("Kiro profile ARN must match the selected runtime region.")
        result["profile_arn"] = arn
    expiries = set()
    for name in ("expiry", "expires_at", "expiresAt"):
        expiry = data.get(name)
        if expiry in (None, ""):
            continue
        try:
            if type(expiry) in (int, float):
                parsed = datetime.fromtimestamp(
                    expiry / 1000 if expiry >= 1e12 else expiry, timezone.utc
                )
            elif isinstance(expiry, str) and len(expiry) <= 64:
                parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            else:
                raise ValueError
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            expiries.add(parsed.astimezone(timezone.utc).isoformat())
        except (ValueError, OverflowError, OSError):
            raise ValueError("Invalid Kiro OAuth expiration time.") from None
    if len(expiries) > 1:
        raise ValueError("Conflicting Kiro OAuth expiration times.")
    if expiries:
        result["expiry"] = expiries.pop()
    fingerprint = _field(data, "account_fingerprint")
    if fingerprint and not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValueError("Invalid Kiro account fingerprint.")
    result["account_fingerprint"] = (
        fingerprint
        or hashlib.sha256(
            json.dumps(
                [
                    method,
                    region,
                    result.get("token_region"),
                    result.get("client_id"),
                    arn,
                    refresh or access,
                ]
            ).encode()
        ).hexdigest()
    )
    return result
