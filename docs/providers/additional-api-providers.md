# Additional API-key providers

Open **Providers**, select a provider, enter its key and required connection
fields, then save. Browse the credential pool and explicitly test a model before
sending production traffic. A model catalog may be public: successful discovery
does not prove that the key is valid or has inference permissions. Model tests
send a small request and may incur vendor charges.

| Provider | Required authentication | Credential-specific advanced settings |
| --- | --- | --- |
| Kimi API Platform | Moonshot API key | Official Moonshot API endpoint |
| Kiro | Kiro API key | Runtime region; optional profile ARN |
| Cloudflare Workers AI | API token and Account ID | Cloudflare management API root |
| NVIDIA NIM | NVIDIA API key | Hosted NVIDIA inference endpoint |
| OpenCode | API key and explicit Zen/Go plan | Plan-specific OpenCode endpoint |
| Poolside Platform | Platform API key | Poolside inference endpoint |
| Kimchi Coding | API/service key | Kimchi OpenAI-compatible endpoint |
| Kilo | API key | Gateway endpoint; optional organization ID |

Empty endpoint fields use official defaults. Endpoint overrides are limited to
trusted vendor HTTPS hosts; this is not a generic arbitrary-proxy feature.
Cloudflare account IDs and Kilo organization IDs belong to their own keys.
OpenCode Zen and Go remain separate credential contexts. Kimi API Platform is
not the Kimi Coding subscription endpoint.

Keys are stored with the existing credential storage protections. They are never
returned by the configuration editor. Leave an existing key blank to keep it;
changing the endpoint/account/plan requires a new discovery check. JSON/ZIP
imports use the same validation and require an explicit provider identifier.
Exported credential archives contain secrets and must be protected accordingly.

## Scope and limitations

- These integrations use API keys only: no vendor OAuth, CLI execution, token
  scraping, automatic refresh, or invented quota displays.
- Text, supported image inputs and function tools pass through the existing
  gateway routing and streaming pipeline. Unsupported request semantics fail
  explicitly instead of silently changing the request. Only one response
  candidate per request is supported by this integration boundary.
- OpenCode selects the vendor-native protocol by supported model family. Native
  Gemini preserves its reasoning history; reasoning-history round trips through
  other OpenCode protocols are not supported in this first integration.
- Kiro direct HTTP transport and Kimchi metadata discovery are based on the
  supplied reference implementations, not stable public API promises. Kiro
  requires an explicit terminal event and rejects truncated binary streams.
  Kiro reasoning/signature history is not supported.
- Usage is taken from vendor responses, never invented. Kimchi streaming usage
  availability depends on the upstream response; optional usage-request support
  was not verified. Model availability, plans, billing and permissions remain
  controlled by each vendor.
- Verification uses mocked transports and disposable browser fixtures. No live
  account credential or paid inference was used during implementation.

Source links and implementation acceptance criteria are recorded in
[the integration specification](../specs/provider-expansion-2026-09.md).
