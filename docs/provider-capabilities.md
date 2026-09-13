# Provider Capability Contract

Omni Gateway exposes one server-owned capability matrix for every provider and authentication
variant advertised by the production self-hosted console. The management API and credential UI
must use this matrix instead of provider-name conditionals.

## API

`GET /api/providers/capabilities` returns schema version 2. The authenticated response contains:

- `providers`: routing-provider metadata retained from the provider catalog;
- `credential_variants`: the exact authentication variants and their supported operations and
  inference protocols;
- `operation_vocabulary`: every recognized operation, including compatibility aliases; and
- `inference_protocol_vocabulary`: every recognized public ingress protocol.

`GET /api/providers` remains the frozen v1 compatibility projection. New clients should use the
versioned capability route. An operation not listed for a variant is unsupported; clients must not
infer support from provider names, credential fields, or another variant of the same provider.

## Production matrix

| Provider variant | Authentication | Add | Verify | Test | Refresh | Re-auth | Edit | Quota | Models | Protocols | Disable | Export | Delete |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Google Antigravity | OAuth | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | All | Yes | Yes | Yes |
| Google AI Studio | API key | Yes | Yes | Yes | No | No | Yes | No | Yes | All | Yes | Yes | Yes |
| Grok Build | OAuth | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | All | Yes | Yes | Yes |
| SpaceXAI Console | API key | Yes | Yes | Yes | No | No | Yes | No | Yes | All | Yes | Yes | Yes |
| Codex | OAuth | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | All | Yes | Yes | Yes |
| OpenAI Platform | API key | Yes | Yes | Yes | No | No | Yes | No | Yes | All | Yes | Yes | Yes |
| Claude Code | OAuth | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes | All | Yes | Yes | Yes |
| Claude Platform | API key | Yes | Yes | Yes | No | No | Yes | No | Yes | All | Yes | Yes | Yes |
| Ollama | Connection | Yes | Yes | Yes | No | No | Yes | No | Yes | All | Yes | Yes | Yes |

`All` means the current normalized ingress families: `openai_chat_completions`,
`openai_responses`, `anthropic_messages`, `gemini_native`, and `vertex`. This declares routing
eligibility, not perfect field parity; field-level behavior is defined by the
[protocol translation contract](protocol-translation-contract.md) and its versioned golden corpus.

Operation meanings:

- `add` covers the variant-specific OAuth completion, API-key save, or Ollama connection flow.
- `verify` validates the credential, refreshes its available model metadata, and clears recorded
  errors without changing whether the credential is enabled or disabled.
- `test` sends the bounded model test exposed by the credential console.
- `refresh` means automatic OAuth token renewal during credential preparation or verification. It
  does not advertise a standalone refresh button.
- `reauthenticate` opens the matching provider authorization workspace for a managed OAuth
  credential. It is not offered for API keys, Ollama connections, or environment-owned entries.
- `edit` permits a managed credential to change its display name. API-key variants can additionally
  rotate the key through their native provider validator; Ollama can change its normalized endpoint
  and optional key after a connection check. OAuth secrets are never exposed or edited in place.
- `model_discovery` covers reading or refreshing the available model set.
- `disable` governs both disabling and re-enabling a stored credential.
- `toggle` is the v1 compatibility alias for `disable`; `refresh_identity`, `credit_mode`, and
  `preview_channel` remain compatibility vocabulary and are supported only where explicitly listed.

## Unsupported-operation contract

Single-credential routes reject an unsupported provider operation before provider network or
storage mutation work with HTTP 422:

```json
{
  "error": {
    "code": "credential_operation_unsupported",
    "message": "This operation is not supported for the credential variant.",
    "operation": "refresh",
    "variant_id": "openai_platform"
  },
  "diagnostic": {
    "schema_version": 1,
    "code": "provider_connection_unsupported_operation",
    "category": "unsupported_operation",
    "message": "This credential variant does not support the requested operation.",
    "remediation": "Choose an operation supported by this credential variant.",
    "retryable": false
  }
}
```

Unknown variants use `variant_id: "unknown"` and fail closed. Batch previews and executions use
the same registry, report the same code per unsupported item, and continue to evaluate
authorization, current state, environment locks, preview requirements, and idempotency separately.
The additive connection diagnostic is documented in `docs/provider-connection-diagnostics.md`.

Credential configuration reads return an allowlisted, secret-free projection. Configuration
writes retain the stable credential filename so usage history remains attached, reject duplicate
provider identities, and are included in the management audit stream. Entries materialized from
runtime environment variables are explicitly read-only in both the API and console.

## Adding or changing a provider

Update the variant in `backend/core/provider_registry.py`, add or update its table-driven matrix
case, and verify both the authenticated capability route and every affected operation route.
Capabilities must describe behavior that exists now; planned adapter work is not advertised.
