# Additional providers and connection settings

Open **Providers**, select a provider, enter its key and required connection
fields, then save. Kiro also offers the OAuth methods listed below. Open
**Credentials** and explicitly test a model before
sending production traffic. A model catalog may be public: successful discovery
does not prove that the key is valid or has inference permissions. Model tests
send a small request and may incur vendor charges.

On multi-column screens, catalog cards share the measured height of the complete
catalog, including cards on other pages or outside the current search. Headings,
descriptions and capability rows remain aligned without truncating translations.
The measurement updates when content, fonts or available width change; on narrow
single-column screens each card grows naturally with its own content.

| Provider | Required authentication | Credential-specific advanced settings |
| --- | --- | --- |
| [Meta Model API](meta-model-api.md) | Model API key | Official Meta API endpoint |
| Kimi API Platform | Moonshot API key | Official Moonshot API endpoint |
| Kiro | Browser OAuth (Google/GitHub); AWS device login; optional API key | Per-method runtime region; AWS token region/start URL; API-key profile ARN |
| Cloudflare Workers AI | API token and Account ID | Cloudflare management API root |
| NVIDIA NIM | NVIDIA API key | Hosted NVIDIA inference endpoint |
| OpenCode | API key and explicit Zen/Go plan | Plan-specific OpenCode endpoint |
| Poolside Platform | Platform API key | Poolside inference endpoint |
| Kimchi Coding | API/service key | Kimchi OpenAI-compatible endpoint |
| Kilo | API key | Gateway endpoint; optional organization ID |
| GroqCloud | Groq API key | Groq API endpoint |
| DeepSeek Platform | Platform API key | DeepSeek API endpoint |
| Mistral AI Studio | Studio API key | Mistral API endpoint |
| Cerebras Cloud | Cloud API key | Cerebras API endpoint |

Empty endpoint fields use official defaults. Endpoint overrides are limited to
trusted vendor HTTPS hosts; this is not a generic arbitrary-proxy feature.
Cloudflare account IDs and Kilo organization IDs belong to their own keys.
OpenCode Zen and Go remain separate credential contexts. Kimi API Platform is
not the Kimi Coding subscription endpoint.

Keys are stored with the existing credential storage protections. They are never
returned by the configuration editor. Leave an existing key blank to keep it;
changing the endpoint/account/plan requires a new discovery check.

Each provider has an inline JSON/ZIP import panel with a downloadable JSON
example. The example never contains the key entered in the form. Imports on this
page are constrained to the selected provider: a missing provider identifier is
inferred from that selection, but a conflicting provider or OAuth export is rejected.
Cloudflare files must include `account_id`; OpenCode files can specify `plan`.
Use the downloadable examples or exported Polaris credentials.
These imports validate file structure and connection fields offline, save no
archive-supplied model catalog, and remain marked as imported without verification.
Open **Credentials** in the sidebar to discover models and explicitly test inference. Mixed-provider
archives belong in the **Credentials** import workflow and require explicit identifiers.
Reimporting the same key and connection context skips it atomically: the existing
model catalog, label and operational state stay unchanged. Failed files remain
selected for correction and retry; each entry reports its own result.

Advanced fields belong to the API-key form above them; they are saved with that
key, not as global provider defaults. Reset only clears the connection draft,
without clearing the entered key or altering any stored credential. Existing
credentials are edited in **Credentials**. Switching OpenCode plans selects the
corresponding endpoint, including in the existing-credential editor.
Exported credential archives contain secrets and must be protected accordingly.

## Scope and limitations

- Kiro supports the browser/AWS OAuth methods listed above and token renewal;
  completing a new login still requires an explicit user action. The other
  integrations in this table use API keys. None executes vendor CLIs, scrapes
  account tokens, or invents quota displays.
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
See [the four API-platform guide](api-platforms.md) for their endpoints, catalog
filters and reasoning compatibility limits.
