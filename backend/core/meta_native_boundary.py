"""Bind trusted native Meta replay to the canonical request checked by policies.

The process-local seal cannot be reconstructed by a JSON caller. Fingerprints
ensure masking, compression or later history edits cannot leave a stale native
prompt that bypasses the policy-visible canonical mirror.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json

_RESERVED = "_polaris_meta_"
_FIELDS = {"_polaris_meta_responses", "_polaris_meta_seal", "_polaris_meta_fingerprint"}
_MAX_BYTES = 16 * 1024 * 1024


class MetaNativeBoundaryError(ValueError):
    """Safe error for an untrusted or policy-modified native request."""

    status_code = 400


class _ReplaySeal:
    def __deepcopy__(self, memo):
        return self


_SEAL = _ReplaySeal()
_PROVIDER_SEALS = {"meta": _SEAL, "muse_code": _ReplaySeal()}


def _reserved(request):
    return {key for key in request if isinstance(key, str) and key.startswith(_RESERVED)}


def _fingerprint(request, native):
    try:
        mirror = {key: value for key, value in request.items() if not key.startswith("_")}
        encoded = json.dumps(
            {"canonical": mirror, "native": native},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > _MAX_BYTES:
            raise ValueError("over limit")
    except (AttributeError, ValueError, TypeError, RecursionError, UnicodeError):
        raise MetaNativeBoundaryError("Invalid native Meta request boundary.") from None
    return hashlib.sha256(encoded).hexdigest()


def seal_native_request(canonical: dict, native: dict, *, provider: str = "meta") -> dict:
    """Called only by trusted ingress after validating and constructing its mirror."""
    if (
        provider not in _PROVIDER_SEALS
        or not isinstance(canonical, dict)
        or not isinstance(native, dict)
        or _reserved(canonical)
    ):
        raise MetaNativeBoundaryError("Invalid native Meta request boundary.")
    result = copy.deepcopy(canonical)
    payload = copy.deepcopy(native)
    result["_polaris_meta_fingerprint"] = _fingerprint(result, payload)
    result["_polaris_meta_responses"] = payload
    result["_polaris_meta_seal"] = _PROVIDER_SEALS[provider]
    return result


def validate_native_request(request: dict, provider: str) -> dict | None:
    """Fail closed before transport if replay is forged, detached or cross-provider."""
    if not isinstance(request, dict):
        raise MetaNativeBoundaryError("Invalid native Meta request boundary.")
    fields = _reserved(request)
    if not fields:
        return None
    native = request.get("_polaris_meta_responses")
    fingerprint = request.get("_polaris_meta_fingerprint")
    if (
        fields != _FIELDS
        or provider not in _PROVIDER_SEALS
        or request.get("_polaris_meta_seal") is not _PROVIDER_SEALS.get(provider)
        or not isinstance(native, dict)
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
    ):
        raise MetaNativeBoundaryError("Untrusted native Meta request boundary.")
    if not hmac.compare_digest(fingerprint, _fingerprint(request, native)):
        raise MetaNativeBoundaryError(
            "Native Meta replay was changed by request policy processing."
        )
    return native
