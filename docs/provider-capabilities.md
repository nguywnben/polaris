# Provider Capability Contract

Polaris exposes one server-owned capability matrix for every provider and authentication
variant advertised by the production self-hosted console. The management API and credential UI
must use this matrix instead of provider-name conditionals.

## API

### Settings ownership

Provider-specific configuration is edited on **Providers**, never in System Settings.
Existing storage keys and environment overrides are preserved; moving an editor does not
reset credentials or configuration.

- Antigravity owns its OAuth client, inference endpoint, client identity headers and
  per-account credit-use controls. Pool shows credit state but does not edit it.
- Grok Build owns `xai_oauth_api_url` and its OAuth issuer/client. SpaceXAI Console owns
  `xai_api_url`. Their shared HTTP User-Agent is operator-only configuration.
- Claude Code owns its OAuth settings (`code` reset scope). Its legacy API endpoint
  and User-Agent overrides remain operator-only (`shared` reset scope, retained for
  API compatibility). Claude Platform owns `claude_platform_api_url` and
  `claude_platform_user_agent` with a separate `platform` reset scope. Validation,
  imports, model discovery and inference all use these private Platform values.
  Saving or resetting either provider does not modify the other provider's values.
  Platform now defaults to the official API and `polaris/claude-platform`; deployments
  that previously customized the shared endpoint must set the Platform override
  explicitly. Old settings and credentials are retained, but no longer inherited.
- Shared Google OAuth/user-info endpoints and the separate legacy Code Assist settings
  are operator-only, not visible provider settings. `GET/POST /api/providers/google/config` uses the existing config
  keys. Reset requires `?scope=shared` or `?scope=compatibility`; blank client secrets
  preserve the configured secret. This is not a new advertised provider variant.
- `stream_to_nonstream` and `switch_credential_enabled` affect the primary routing pool,
  not just Antigravity, and are edited once in System Settings.

### Operator-only settings

The console hides shared Google, xAI and Claude editors and their navigation links.
Legacy Code Assist controls are also hidden; they are not Antigravity-specific settings.
Only provider-specific advanced controls are presented. A provider with no separate
advanced controls has no empty advanced-settings disclosure.

This is a presentation change, not deletion or a security boundary. Stored values,
runtime defaults, environment overrides and authenticated management APIs are retained.
Hidden editors remain inert to user interaction, even after family configuration loads.
There is no new Code Assist enable/disable switch: `COMPATIBILITY_MODE` controls AI
quality behavior and must not be used to expose the legacy editor.

For exceptional deployments, set these variables in the application's environment
(for Docker Compose, explicitly forward them in the app service's `environment`):

| Scope | Environment variables |
| --- | --- |
| Shared Google OAuth/account lookup | `OAUTH_URL`, `GOOGLE_APIS_URL` |
| Legacy Code Assist | `CODE_ASSIST_ENDPOINT`, `CODE_ASSIST_CLIENT_ID`, `CODE_ASSIST_CLIENT_SECRET`, `RESOURCE_MANAGER_URL`, `SERVICE_USAGE_URL` |
| Grok Build / SpaceXAI Console | `XAI_USER_AGENT` |
| Claude Code only | `ANTHROPIC_API_URL`, `CLAUDE_USER_AGENT` |

Restart/recreate the process or container after changing its environment. Normal
deployments should keep defaults. Existing saved values remain effective when no
environment override is supplied; do not reset them just because the editor is hidden.

Google OAuth/user-info destinations are restricted to the trusted Google origins before
credentials can be sent; redirects are not followed. Claude authorization/token URLs use
the same validation at save and runtime. Claude token responses preserve 429/5xx as
transient errors instead of classifying them as invalid credentials.

If an older deployment customized Google OAuth/user-info hosts, restore their official
Google origins before authorization or refresh. Use the outbound proxy setting for network
access instead. Existing values are not silently rewritten, but unsafe destinations are now
rejected. This is an intentional security tightening in the pre-1.0 configuration contract.

### Native imports and proxy bypass

The importer recognizes native Codex `tokens`, Claude Code `claudeAiOauth`, and Grok
account containers, as well as canonical Polaris credentials and supported CLIProxy xAI
exports. Ambiguous provider/type declarations are rejected. JWT claims are unverified
metadata hints only, not proof of identity. Existing size and ZIP-entry limits still apply.
Offline Codex/Grok imports are marked as imported without provider verification; use the
Pool's explicit verification/model test before relying on them. The provenance notice
describes the import, not the outcome of a later test, and does not change routing eligibility.

The shared HTTP client honors explicitly configured `no_proxy` (preferred) or `NO_PROXY`
for GET, POST and streaming requests. Supported rules include comma-separated exact
hosts/domain suffixes, optional ports, literal IP/CIDR and `*`. There is no implicit local
network bypass or DNS lookup. For local Ollama, set a precise rule such as
`NO_PROXY=localhost,127.0.0.1,host.docker.internal` in the runtime environment if needed.
Direct and proxied requests keep separate connection pools.

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
| Claude Code | OAuth | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | All | Yes | Yes | Yes |
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
- `quota` is provider-specific rather than a synthetic universal balance: Google Antigravity
  reports model windows, Grok Build reports billing periods, Codex reports account rate-limit
  windows, and Claude Code reports subscription usage windows. Claude Platform, OpenAI Platform,
  SpaceXAI Console, Google AI Studio, and Ollama do not advertise quota because their credential
  APIs do not expose an equivalent account view.
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

Claude Code subscription usage is fetched on demand from the account endpoint used by current
Claude Code clients. That endpoint can rate-limit and is not a documented public Anthropic API, so
Polaris caches successful snapshots and 429 responses for three minutes, parses both known
response shapes, and returns a sanitized temporary error instead of repeatedly probing upstream.
