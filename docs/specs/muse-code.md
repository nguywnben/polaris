# Muse Code direct OAuth provider

Status: the user approved the five-stage direct-integration plan on 2026-09-16.
Direct Windows OAuth and key minting are verified; an HTTP success is not vendor certification.
This is a separate user-authorized provider extension, not a reopening of R1/R2.

## Objective and acceptance

Add `muse_code` / **Muse Code**, separate from `meta` / Meta Model API, without
requiring a CLI subprocess, Linux bridge, VPS or new runtime dependency. Use the
existing `muse-code.png` asset. Do not activate the provider until its authentication,
storage, transport and management contracts pass their tests.

1. Verify device authorization, explicit token exchange, inference-key minting and
   credential lifecycle against the official installed CLI and live Meta endpoints.
   Record what is observed rather than inventing refresh grants or expiry periods.
2. Verify direct HTTP login from Windows. Browser approval remains a user action.
3. Provide a consistent OAuth workspace: Muse precedes Meta Model API in the catalog;
   the authorization URL uses the existing clickable link card with a Copy button.
   Show the device code and explicit Save action, with expiry/retry handling but no
   separate Cancel or Open page button. Requesting a fresh link invalidates the old
   flow. No automatic completion, background polling or navigation away from the form.
   Catalog badges show connection methods only. The device code is a compact,
   selectable label/value row. Advanced settings expose only the supported optional
   credential display name, applied on the next login-link request; OAuth/API
   endpoints remain pinned, with no invented client or subscription settings.
4. Persist credentials through existing encrypted storage and permission checks;
   support bounded JSON/ZIP imports and sample files without exposing real secrets.
   Neither imported catalogs nor arbitrary upstream URLs are trusted.
5. Reuse verified Meta model transport only where semantics match, preserving
   streaming, function calls, cancellation and usage. Do not silently downgrade
   unsupported tool choices, select Contributor, or fall back to a pay-as-you-go
   credential. Limit discovery to compatible text models.
6. Display subscription windows only from validated server observations. Unknown
   values are not zero. Subscription expiry/payment requirements produce actionable
   errors, not an automatic purchase or switch to another billing mode.
7. Match existing controls, light/dark themes, 360/768/1024/1440 widths and all 15
   console locales. Do not add provider settings to unrelated pages.

## Verified and unresolved protocol

Evidence: [research record](../providers/muse-code-research-2026-09-16.md).
The official launcher supplies the client ID and device endpoints. Live Windows
device authorization, user-approved token exchange, key minting and catalog access
returned HTTP 200 without a CLI or VPS dependency.
On Linux, `POST https://api.meta.ai/muse-code/key` with OAuth Bearer authentication
and an empty JSON object returned the already-saved inference key, expected API
base, subscription eligibility and usage windows. Repeated requests returned the
same key. No key expiry was advertised by that response.

The token response has no refresh token or expiry. Key minting likewise advertises
no expiry. Unknown: long-term session lifetime and key rotation/revocation behavior.
Reauthorization is the safe terminal path; no invented refresh endpoint or retry loop.
Meta documents subscription credentials for Muse Code CLI use; this adapter must
not claim official third-party support or a billing guarantee.

Public model IDs use the `muse-code/` namespace. It is stripped only at the trusted
upstream boundary. Ordinary Meta API credentials cannot claim these IDs, and Muse
accounts cannot claim raw Meta IDs. Native Responses replay is bound to its provider
family; mixed Meta/Muse candidates are rejected before dispatch.

## Structure and code style

Python/FastAPI with the existing `httpx==0.28.1` network wrapper; vanilla JS/CSS
frontend. No dependency or persistent schema change is planned.

- `backend/core/muse_oauth.py`: fixed-origin, bounded authorization transport.
- Provider credential/coordination modules: explicit owner-bound login and storage.
- Existing provider registry, runtime, management and quota integration points.
- `backend/tests/test_muse_*.py`: synthetic secrets and HTTP transport fixtures.
- Existing frontend provider components/locales and browser smoke tooling.

Use small async functions and sanitized exceptions, matching neighboring adapters:

```python
async def mint_key(access_token: str) -> dict:
    """Validate a server response; never return its raw error description."""
    ...
```

## Commands and testing

Run from the repository root:

```powershell
.venv/Scripts/python.exe -m unittest backend.tests.test_muse_oauth
.venv/Scripts/python.exe -m backend.tests --suite core
.venv/Scripts/python.exe tools/quality_gate.py fast
node tools/i18n-audit.mjs
.venv/Scripts/python.exe tools/backend-i18n-audit.py
.venv/Scripts/python.exe tools/extended_providers_smoke.py --capture
```

Write failing tests first. Cover malicious origins/redirects, oversized/malformed
responses, pending/slow-down/denial/expiry, owner isolation, replay/concurrent save,
secret redaction, subscription/payment gating, model filtering and native replay.
Keep the repository's changed-code coverage threshold. Full integration and browser
gates apply before declaring the provider complete. Live inference requires a fresh
explicit allowance; previous three-call allowance is exhausted.

## Boundaries

Always: TLS validation, fixed intended origins, no credential-bearing redirects,
bounded requests, encrypted storage, manual login completion, truthful capability
reporting and preservation of existing data.

Ask first: more live inference, CLI bridge/service, new dependency/schema, paid
subscription changes or deployment changes. Commit/push/Docker updates are not part
of this implementation request.

Never: log/copy real tokens into source, forge a CLI identity, bypass access checks,
silently alter billing/model/tool semantics, or treat a partial test as readiness.
