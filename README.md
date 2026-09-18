<div align="center">
  <h1>
    <img src="frontend/assets/logo.png" alt="Polaris Logo" width="48" height="48" style="vertical-align: middle;" /> <span style="vertical-align: middle;">Polaris</span>
  </h1>
  <p><b>Universal AI Router & Unified Multi-Provider Gateway for AI Coding Tools</b></p>

  <p>
    <a href="https://github.com/nguywnben/polaris/releases"><img src="https://img.shields.io/github/v/release/nguywnben/polaris?style=flat-square&color=blue" alt="Release"></a>
    <a href="https://github.com/nguywnben/polaris/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nguywnben/polaris?style=flat-square&color=green" alt="License"></a>
    <a href="https://github.com/nguywnben/polaris/actions"><img src="https://img.shields.io/github/actions/workflow/status/nguywnben/polaris/ci.yml?branch=main&style=flat-square&label=CI" alt="CI Status"></a>
    <a href="https://hub.docker.com/r/nguywnben/polaris"><img src="https://img.shields.io/docker/pulls/nguywnben/polaris?style=flat-square&logo=docker" alt="Docker Pulls"></a>
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 | 3.14">
    <img src="https://img.shields.io/badge/console-15%20languages-orange?style=flat-square" alt="Console: 15 languages">
  </p>

  <p>
    <a href="#supported-providers"><b>🌐 Supported Providers</b></a> •
    <a href="#core-capabilities"><b>⚡ Capabilities</b></a> •
    <a href="#deployment"><b>🐳 Docker Deployment</b></a> •
    <a href="#sdk-surfaces"><b>🔌 SDK Setup</b></a> •
    <a href="docs/architecture.md"><b>📖 Architecture</b></a>
  </p>

  <p>
    <b>README · 15 languages:</b><br>
    <b>English</b> • <a href="docs/locales/README.vi.md">Tiếng Việt</a> • <a href="docs/locales/README.zh-CN.md">中文（简体）</a> • <a href="docs/locales/README.zh-TW.md">中文（繁體）</a> • <a href="docs/locales/README.ja.md">日本語</a> • <a href="docs/locales/README.ko.md">한국어</a> • <a href="docs/locales/README.es.md">Español</a> • <a href="docs/locales/README.fr.md">Français</a> • <a href="docs/locales/README.de.md">Deutsch</a> • <a href="docs/locales/README.it.md">Italiano</a> • <a href="docs/locales/README.pt.md">Português</a> • <a href="docs/locales/README.ru.md">Русский</a> • <a href="docs/locales/README.id.md">Bahasa Indonesia</a> • <a href="docs/locales/README.th.md">ภาษาไทย</a> • <a href="docs/locales/README.tr.md">Türkçe</a>
  </p>
</div>

---

The console supports 15 languages. English and Vietnamese receive semantic review; the other 13
community locales are compatibility translations and fall back to English when a message is absent.

This README is available in **15 languages** with the same functional scope. Linked technical guides retain their original document language. README translations are separate from the console's localization support policy.

A universal AI router for coding tools. Polaris provides smart auto-fallback, token-aware request cleanup, usage visibility, and seamless format translation so local agents, IDE assistants, and automation scripts can use free and premium LLM capacity through one stable API surface.

> **Product boundary:** Polaris is production-ready for self-hosting by one person or
> a trusted team. The supported production topology is one application worker and one replica;
> Docker Compose, local-owner access, SQLite, provider routing, and the documented SDK routes form
> the core profile. PostgreSQL, OIDC team access, reverse-proxy operation, and external telemetry
> are advanced opt-ins. MongoDB and non-curated locales are compatibility surfaces. Coordinated
> multi-replica operation and Kubernetes deployment are outside the product boundary. See
> the [Production Self-Hosted R1 specification](docs/specs/production-self-hosted.md).

## Why Polaris

Modern coding workflows often mix clients and providers: OpenAI-compatible tools, Gemini-native SDKs, Anthropic-style agents, Google-backed credentials, and experimental model routes. Polaris sits between those clients and model backends so each tool can keep speaking the format it already understands while the gateway handles routing, retries, request cleanup, and response normalization.

## Core Capabilities

- Smart auto-fallback: reserves credentials per request, spreads concurrent traffic, tracks every attempt for fair rotation, and routes around recent failures, cooldowns, rate limits, and exhausted capacity.
- Token-aware cleanup: normalizes payloads and trims only oversized conversation prefixes at safe turn boundaries while preserving system instructions, tool definitions, and recent context.
- Format translation: accepts OpenAI Chat Completions and Responses, Gemini native requests, and Anthropic Messages, then translates requests and streaming responses across formats.
- Credential orchestration: manages OAuth accounts and provider API keys with health state, cooldown tracking, verification, deduplication, and provider-aware fallback.
- Credential-level model routing: keeps a separate capability catalog for each credential, so one account's entitlement cannot send a request to another account that does not expose the selected model.
- Route health memory: records model-not-found responses at credential scope and exposes the affected routes for recovery from the Models page.
- Streaming resilience: supports SSE streaming, pseudo-streaming for clients that require streamed output, and anti-truncation retries for long generations.
- Routing strategies: balanced, provider priority, weighted random, least latency, and lowest cost credential selection.
- Virtual API keys: scoped client keys with daily and monthly USD budgets, per-minute request and token limits, expiry, and model allowlists.
- Cost ledger: estimated USD cost per call from a maintained model pricing table, aggregated on the dashboard and in Prometheus metrics.
- Guardrails: optional pre-call prompt-injection blocking, keyword filtering, and PII masking before requests leave the gateway.
- Response caching: optional exact-match caching of deterministic requests to reduce latency and provider spend.
- Observability: Prometheus `/metrics` endpoint and optional Langfuse trace export alongside the built-in usage dashboard.
- Control panel: ships with a web console for credentials, logs, configuration, usage, and version information.

## Console Preview

Screenshots use fictional data from an isolated offline demo.

### Dashboard

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshots/dashboard-dark.png" />
  <img src="docs/assets/screenshots/dashboard-light.png" alt="Polaris dashboard" />
</picture>

### Credentials

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshots/credentials-dark.png" />
  <img src="docs/assets/screenshots/credentials-light.png" alt="Polaris credentials" />
</picture>

## Supported Providers

Polaris currently exposes **23 providers** in the catalog. The table describes each connection method and service; available models depend on the individual credential.

| Provider | Connection method | Service / scope |
| :--- | :--- | :--- |
| <img src="frontend/assets/providers/google-antigravity.png" width="18" height="18" valign="middle" /> **Google Antigravity** | OAuth (Google) | Google Code Assist |
| <img src="frontend/assets/providers/google-ai-studio.png" width="18" height="18" valign="middle" /> **Google AI Studio** | API key | Gemini / Gemma |
| <img src="frontend/assets/providers/grok-build.png" width="18" height="18" valign="middle" /> **Grok Build** | OAuth (PKCE) | Grok Build |
| <img src="frontend/assets/providers/spacexai-console.png" width="18" height="18" valign="middle" /> **SpaceXAI Console** | API key | xAI API |
| <img src="frontend/assets/providers/codex.png" width="18" height="18" valign="middle" /> **Codex / ChatGPT** | OAuth (device code) | Codex Responses |
| <img src="frontend/assets/providers/openai-platform.png" width="18" height="18" valign="middle" /> **OpenAI Platform** | API key | OpenAI API |
| <img src="frontend/assets/providers/claude-code.png" width="18" height="18" valign="middle" /> **Claude Code** | OAuth (PKCE) | Anthropic Messages |
| <img src="frontend/assets/providers/claude-platform.png" width="18" height="18" valign="middle" /> **Claude Platform** | API key | Anthropic API |
| <img src="frontend/assets/providers/ollama.png" width="18" height="18" valign="middle" /> **Ollama** | Endpoint; optional API key | Local / self-hosted |
| <img src="frontend/assets/providers/cerebras-cloud.png" width="18" height="18" valign="middle" /> **Cerebras Cloud** | API key | Cerebras API |
| <img src="frontend/assets/providers/cloudflare.png" width="18" height="18" valign="middle" /> **Cloudflare Workers AI** | API token + Account ID | Workers AI |
| <img src="frontend/assets/providers/deepseek-platform.png" width="18" height="18" valign="middle" /> **DeepSeek Platform** | API key | DeepSeek API |
| <img src="frontend/assets/providers/groqcloud.png" width="18" height="18" valign="middle" /> **GroqCloud** | API key | Groq API |
| <img src="frontend/assets/providers/kilo.png" width="18" height="18" valign="middle" /> **Kilo** | API key; optional organization ID | Kilo Gateway |
| <img src="frontend/assets/providers/kimchi.png" width="18" height="18" valign="middle" /> **Kimchi Coding** | API / service key | Kimchi Coding API |
| <img src="docs/assets/providers/kimi-api-platform.svg" width="18" height="18" valign="middle" /> **Kimi API Platform** | API key | Moonshot API |
| <img src="frontend/assets/providers/kiro.png" width="18" height="18" valign="middle" /> **Kiro** | Browser OAuth / AWS device login / API key | Kiro |
| <img src="frontend/assets/providers/muse-code.png" width="18" height="18" valign="middle" /> **Muse Code** | OAuth (Meta device code) | `muse-code/` |
| <img src="frontend/assets/providers/meta-model-api.png" width="18" height="18" valign="middle" /> **Meta Model API** | API key | Meta API |
| <img src="frontend/assets/providers/mistral-ai-studio.png" width="18" height="18" valign="middle" /> **Mistral AI Studio** | API key | Mistral API |
| <img src="frontend/assets/providers/nvidia.png" width="18" height="18" valign="middle" /> **NVIDIA NIM** | API key | Hosted NVIDIA inference |
| <img src="frontend/assets/providers/opencode.png" width="18" height="18" valign="middle" /> **OpenCode** | API key + Zen/Go plan | OpenCode Zen / Go |
| <img src="frontend/assets/providers/poolside-platform.png" width="18" height="18" valign="middle" /> **Poolside Platform** | API key | Poolside API |

Clients use Polaris's shared [SDK surfaces](#sdk-surfaces). Adapters handle protocol translation, streaming and fallback within each model's supported capabilities; unsupported request semantics produce explicit errors.

Connection settings belong to the provider or credential on **Providers**, not System Settings. See the [connection guide and limitations](docs/providers/additional-api-providers.md), [four API-platform guide](docs/providers/api-platforms.md), and [Meta Model API guide](docs/providers/meta-model-api.md). Muse Code and Meta Model API are separate providers with distinct credentials and model namespaces.

## Architecture

```text
client tools
  OpenAI SDKs | Google GenAI SDKs | Anthropic SDKs | IDE integrations
        |
        v
Polaris
  authentication -> format translation -> token-aware cleanup -> routing -> fallback -> streaming
        |
        v
provider adapters
  Google | xAI | OpenAI | Anthropic | Kiro | Muse Code | Meta | Ollama | other API platforms
```

The public API stays stable while provider-specific adapters evolve behind Polaris.

## Repository Structure

```text
backend/       FastAPI composition root, routing core, translators, storage, and tests
frontend/      Management console markup, styles, scripts, and provider assets
deploy/        Container definitions, platform manifests, and operating-system scripts
docs/          Architecture notes and maintained project assets
.github/       CI, dependency automation, and contribution templates
```

See [Architecture](docs/architecture.md) for module boundaries, request flow, state ownership, and current release constraints.

## Deployment

For a guided Linux/amd64 installation without cloning the repository or editing `.env`,
see [Simple Docker installation](docs/docker-install.md): one installer command, an explicit
HTTP choice for VPS access, then create your password on the web. **This flow is prepared
locally and requires the matching updated installer/image to be published first.** Manual
Docker, Compose and source development remain available; Docker-run uses its own
[backup/update procedure](docs/docker-maintenance.md), not the Compose updater.

Docker Compose is the canonical production deployment path for the supported single-machine,
single-worker profile. Follow the [Canonical installation guide](docs/installation.md) from host
checks through the first authenticated Dashboard; its
[Installation support matrix](docs/installation.md#support-matrix) records the verified Windows,
Linux, macOS, and architecture status without implying unsupported ARM64 coverage.

The default profile needs no external service and stores all application data in the
`polaris-data` named volume. Its minimal environment template targets `1.0.0`. Install using
matching published Polaris tags and images; for an unpublished source checkout, follow the
[release preparation checklist](docs/releases/1.0.0-preparation.md) and build a separate local image. Production
updates use the encrypted, health-checked [Compose update and rollback guide](docs/updating.md).
External storage, Team access, proxy, guardrails, cache, and telemetry remain opt-in through
`deploy/compose.advanced.yml` after the base installation is healthy.

The [Polaris identifier contract](docs/migrations/polaris.md) lists the canonical names used by
clients, operators, storage, telemetry, and automation. Pre-release builds are intentionally not
supported through compatibility aliases.

For diagnosis and safe recovery, use the [Production troubleshooting guide](docs/troubleshooting.md).
It starts with health and readiness checks, preserves the data volume, and records the exact
information needed for a redacted support bundle.

Compatibility-only native scripts under `deploy/scripts`, Render, and Zeabur
do not carry the full install/update/rollback evidence of the canonical path. The production image
is published for `linux/amd64`; native `linux/arm64` publication remains paused until the complete
locked dependency stack has equivalent build and runtime evidence.

### Local Development

Use the Python workflow when developing or debugging the gateway locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

Open the control panel at:

```text
http://127.0.0.1:4283
```

Local development uses the same first-run setup screen as the Docker deployment.

## Configuration

Polaris reads configuration from environment variables first, then stored configuration, then defaults.
The complete [generated configuration reference](docs/reference/configuration.md) identifies every
field's type, Basic/Advanced/Experimental group, Settings owner, and whether it applies live,
requires restart, or is environment-only. Startup rejects malformed values with the exact variable
name; likely misspelled `POLARIS_*` variables produce a warning.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address. |
| `PORT` | `4283` | HTTP port. |
| `HOST_PORT` | `4283` | Host-side port used only by Docker Compose. |
| `WORKERS` | `1` | Supported worker count. This release accepts one only. |
| `POLARIS_RUNTIME_MODE` | `standalone` | Runtime mode. This release supports `standalone` only. |
| `POLARIS_REPLICA_COUNT` | `1` | Declared application replica count. The current release accepts one only. |
| `CORS_ORIGINS` | empty | Comma-separated browser origins allowed to call the API cross-origin. Leave empty for same-origin console usage. |
| `CORS_ORIGIN_REGEX` | empty | Optional regex for managed dynamic browser origins. |
| `API_KEY` | generated automatically | Preferred key for public client API requests. Must start with `sk-polaris-`. |
| `PANEL_PASSWORD` | empty until setup | Password for the web control panel. |
| `SETUP_TOKEN` | empty | Required before remote first-run setup; use a unique value of at least 24 characters. It is never generated or printed by the application. Direct localhost setup does not require it. |
| `SETUP_ALLOW_INSECURE_HTTP` | `false` | Opt in to remote HTTP setup only after accepting unencrypted credentials and sessions. HTTPS is recommended; a strong setup token is still required. |
| `PANEL_SESSION_TTL_SECONDS` | `86400` | Web console session lifetime in seconds. |
| `PANEL_COOKIE_SECURE` | automatic | Set `true` to require HTTPS-only panel cookies. Leave empty to detect HTTPS through `X-Forwarded-Proto`. |
| `PANEL_LOGIN_WINDOW_SECONDS` | `300` | Login rate-limit window in seconds. |
| `PANEL_LOGIN_MAX_ATTEMPTS` | `10` | Failed login attempts allowed per client within the rate-limit window. |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | `10000` | Maximum client addresses retained by the in-memory login limiter. |
| `MAX_REQUEST_BODY_MB` | `64` | Maximum HTTP request body size in MiB. Oversized SDK requests return the native protocol error envelope. |
| `TRUST_PROXY_HEADERS` | `false` | Accept client/protocol forwarding headers only from a trusted reverse proxy that overwrites them. |
| `CREDENTIALS_DIR` | `./backend/data/creds` | Credential storage directory. In Docker, persist `/app/backend/data/creds` with a host volume. |
| `CODE_ASSIST_ENDPOINT` | `https://cloudcode-pa.googleapis.com` | Code Assist backend endpoint. |
| `ANTIGRAVITY_API_URL` | `https://daily-cloudcode-pa.googleapis.com` | Google Antigravity backend endpoint. |
| `PROXY` | empty | Optional HTTP, HTTPS, or SOCKS proxy. |
| `RETRY_429_ENABLED` | `true` | Enable bounded retries for rate limits and transient upstream failures. The legacy name is retained for configuration compatibility. |
| `RETRY_429_MAX_RETRIES` | `5` | Maximum retry attempts for transient upstream failures. |
| `RETRY_429_INTERVAL` | `1` | Base delay between transient retries in seconds. |
| `AUTO_DISABLE` | `false` | Disable credentials after configured hard failures. |
| `AUTO_DISABLE_ERROR_CODES` | `403` | Comma-separated hard-failure status codes. |
| `ROUTING_STRATEGY` | `balanced` | Credential selection policy: `balanced`, `priority`, `weighted`, `least_latency`, or `lowest_cost`. |
| `PREFERRED_PROVIDER` | empty | Provider preferred by the `priority` strategy, such as `google_antigravity` or `google_ai_studio`. |
| `UPSTREAM_TIMEOUT_SECONDS` | `300` | Provider inference timeout, bounded between 5 and 900 seconds. |
| `RESPONSE_CACHE_ENABLED` | `false` | Cache deterministic (temperature 0) non-streaming responses in memory. |
| `RESPONSE_CACHE_TTL_SECONDS` | `300` | Response cache entry lifetime in seconds. |
| `RESPONSE_CACHE_MAX_ENTRIES` | `1000` | Maximum responses held by the in-memory cache. |
| `GUARDRAILS_ENABLED` | `false` | Enable the pre-call guardrails pipeline. |
| `GUARDRAILS_PII_MASKING_ENABLED` | `true` | Mask emails, card numbers, and API keys in outbound request text. |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | `true` | Reject prompt-injection attempts with HTTP 400. |
| `GUARDRAILS_BLOCKED_KEYWORDS` | empty | Comma-separated case-insensitive keywords that block a request. |
| `PRICING_SYNC_ENABLED` | `true` | Refresh the public LiteLLM model-price catalog in the background; the last valid snapshot remains usable offline. |
| `PRICING_SYNC_INTERVAL_HOURS` | `24` | Price-catalog refresh interval, bounded between 1 and 168 hours. |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3` | Maximum continuation attempts for anti-truncation streaming. |
| `TOKEN_COMPRESSION_ENABLED` | `true` | Compress oversized conversation history before provider routing. |
| `TOKEN_COMPRESSION_THRESHOLD` | `32000` | Estimated input-token threshold that activates compression. |
| `TOKEN_COMPRESSION_TARGET` | `24000` | Estimated input-token target after compression. Must be lower than the threshold. |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | `4` | Minimum number of recent user turns retained during compression. |
| `COMPATIBILITY_MODE` | `false` | Converts system messages for clients/models that reject them. |
| `RETURN_THOUGHTS_TO_FRONTEND` | `true` | Include model reasoning fields when available. |
| `MONGODB_URI` | empty | Selects the compatibility-only MongoDB storage path. |
| `POSTGRESQL_URI` | empty | Selects optional Advanced PostgreSQL storage. |
| `CODE_ASSIST_CLIENT_ID` | bundled desktop client | Optional override for the Code Assist OAuth client ID. |
| `CODE_ASSIST_CLIENT_SECRET` | bundled desktop client | Optional override for the Code Assist OAuth client secret. |
| `ANTIGRAVITY_CLIENT_ID` | bundled desktop client | Optional override for the Google Antigravity OAuth client ID. It can also be managed from the Providers page. |
| `ANTIGRAVITY_CLIENT_SECRET` | bundled desktop client | Optional override for the Google Antigravity OAuth client secret. Configure it through env or the Providers page when the upstream client changes. |
| `GOOGLE_AI_STUDIO_API_URL` | `https://generativelanguage.googleapis.com` | Optional Google AI Studio Generative Language API endpoint override. |
| `XAI_API_URL` | `https://api.x.ai/v1` | Optional SpaceXAI Console API endpoint override for API-key credentials. It can also be managed from the Providers page. |
| `XAI_OAUTH_API_URL` | `https://cli-chat-proxy.grok.com/v1` | Optional Grok Build OAuth subscription endpoint override. |
| `XAI_OAUTH_ISSUER` | `https://auth.x.ai` | Optional Grok Build OAuth issuer override. Only HTTPS hosts under `x.ai` are accepted by the console. |
| `XAI_CLIENT_ID` | bundled public client | Optional override for the Grok Build PKCE OAuth client ID. |
| `XAI_USER_AGENT` | `grok-cli/polaris` | Optional shared HTTP User-Agent override for Grok Build OAuth and SpaceXAI Console API requests. |
| `OPENAI_API_URL` | `https://api.openai.com/v1` | Optional OpenAI Platform API endpoint override. It can also be managed from the Providers page. |
| `CODEX_API_URL` | `https://chatgpt.com/backend-api/codex` | Optional Codex inference and account-model endpoint override. |
| `CODEX_USAGE_URL` | `https://chatgpt.com/backend-api/wham/usage` | Optional Codex account rate-limit endpoint override. |
| `CODEX_AUTH_BASE` | `https://auth.openai.com` | Optional Codex device-authorization service override. |
| `CODEX_CLIENT_ID` | bundled public client | Optional override for the Codex device OAuth client ID. |
| `CODEX_USER_AGENT` | Codex CLI-compatible value | Optional User-Agent override for Codex requests. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1` | Operator-level Messages API endpoint override for Claude Code. |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | `https://claude.ai/oauth/authorize` | Optional Claude Code PKCE authorization endpoint override. Only Anthropic and Claude hosts are accepted by the console. |
| `CLAUDE_OAUTH_TOKEN_URL` | `https://api.anthropic.com/v1/oauth/token` | Optional Claude Code token endpoint override. Only Anthropic and Claude hosts are accepted by the console. |
| `CLAUDE_CLIENT_ID` | bundled public client | Optional override for the Claude Code PKCE OAuth client ID. |
| `CLAUDE_USER_AGENT` | `claude-cli/polaris` | Operator-level User-Agent override for Claude Code requests. |
| `CLAUDE_PLATFORM_API_URL` | `https://api.anthropic.com/v1` | Separate Claude Platform endpoint, configurable from Providers. |
| `CLAUDE_PLATFORM_USER_AGENT` | `polaris/claude-platform` | Separate Claude Platform User-Agent, independent of Claude Code. |
| `ANTIGRAVITY_USER_AGENT` | `antigravity/cli/1.0.1 windows/amd64` | Optional Google Antigravity protocol User-Agent override. |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | `antigravity` | Optional payload-level Google Antigravity userAgent override. |
| `PROMETHEUS_EXPORT_ENABLED` | `false` | Explicitly enables authenticated `GET /metrics` export. |
| `METRICS_TOKEN` | empty | Bearer token of at least 32 UTF-8 bytes required when Prometheus export is enabled. |
| `OTEL_EXPORT_ENABLED` | `false` | Explicitly enables content-free aggregate OTLP/HTTP metrics export. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | HTTPS OpenTelemetry collector endpoint; credentials in URLs are rejected. |
| `OTEL_EXPORT_INTERVAL_SECONDS` | `60` | Aggregate export interval, bounded to 15–300 seconds. |
| `LANGFUSE_PUBLIC_KEY` | empty | Enables Langfuse trace export together with the secret key. |
| `LANGFUSE_SECRET_KEY` | empty | Langfuse secret key for trace export. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse ingestion endpoint. |
| `LOG_LEVEL` | `info` | Runtime log level. |
| `LOG_MAX_MB` | `10` | Maximum active log file size before rotation. |
| `LOG_BACKUP_COUNT` | `3` | Number of rotated log files retained. |
| `LOG_FILE` | `./backend/data/logs/polaris.log` | File log destination. In Docker, persist `/app/backend/data/logs` with a host volume. |

### Compression controls

The global AI Quality policy is authoritative. A virtual key may only inherit it or disable
compression through `PATCH /api/virtual-keys/{key_id}/quality-policy` with its current revision:

```json
{"expected_revision": 3, "compression": "disabled"}
```

Use `"inherit"` to remove that restriction. A single authenticated inference request can also set
`x-polaris-compression: off`; omit the header or use `inherit` for the effective global/key behavior.
Neither a key nor a request can re-enable globally disabled compression or make compression more
aggressive. Compression only removes a safe history prefix and fails open to the uncompressed
payload when token estimation or structural invariants cannot be proven. Token counts are estimates;
the provider tokenizer remains authoritative.

## SDK Surfaces

Polaris is designed around the standard URL behavior of the official Python SDKs. Configure each client exactly as shown below; the gateway does not require non-standard duplicated path prefixes.

The examples use the virtual model `polaris`. Configure its ordered provider-model fallback on the Models page first, or replace it with a concrete model ID.

### OpenAI Python SDK

Use `/v1` as the OpenAI base URL. The SDK appends `/chat/completions`.

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:4283/v1", api_key="sk-polaris-...")

response = client.chat.completions.create(
    model="polaris",
    messages=[{"role": "user", "content": "Explain this repository in one paragraph."}],
)
```

The same client can use the OpenAI Responses API:

```python
response = client.responses.create(
    model="polaris",
    instructions="Be concise.",
    input="Explain this repository in one paragraph.",
)

print(response.output_text)
```

Responses compatibility supports text, image inputs, non-streaming function tools, and SSE text streaming. OpenAI-hosted built-in tools, stored response history, and streaming function calls are rejected explicitly because Polaris does not execute, persist, or silently discard those OpenAI-specific behaviors.

### Anthropic Python SDK

Use the gateway origin as the Anthropic base URL. The SDK appends `/v1/messages`.

```python
from anthropic import Anthropic

client = Anthropic(base_url="http://127.0.0.1:4283", api_key="sk-polaris-...")

response = client.messages.create(
    model="polaris",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Draft a commit message."}],
)
```

### Google GenAI Python SDK

Use the gateway origin as the Google GenAI base URL. The SDK appends its default model route, such as `/v1beta/models/{model}:generateContent`.

```python
from google import genai
from google.genai import types

client = genai.Client(
    http_options={
        "base_url": "http://127.0.0.1:4283",
    },
    api_key="sk-polaris-...",
)

response = client.models.generate_content(
    model="polaris",
    contents="Write a small Python function.",
    config=types.GenerateContentConfig(
        system_instruction="You are a helpful assistant.",
    ),
)
```

### Supported Routes

Polaris exposes SDK-compatible routes without a product namespace:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/messages`
- `GET /v1/models`
- `GET /v1beta/models`
- `POST /v1beta/models/{model}:generateContent`
- `POST /v1beta/models/{model}:streamGenerateContent`
- `POST /v1beta/models/{model}:countTokens`
- `POST /vertex/v1/chat/completions`
- `POST /vertex/v1/models/{model}:generateContent`

Authentication, request-validation, routing, upstream, and pre-stream failures use the native error envelope for the selected SDK surface. Every HTTP response includes `X-Request-ID`; clients may supply a safe identifier in that header for end-to-end correlation. Rate-limited and temporarily unavailable responses preserve `Retry-After` when the upstream provides it.

## Model Features

The Models page builds the virtual model `polaris` from models discovered across enabled provider credentials. Arrange its members in priority order once, then use `polaris` from any supported SDK. Polaris balances healthy credentials that support the first model and continues through the configured model order when that model is unavailable. Concrete provider model IDs remain available for clients that need deterministic model selection. Saving an empty selection disables `polaris` without affecting provider credentials.

Model discovery is provider-aware: a shared model can be backed by multiple providers, while provider-specific models only use compatible credentials. Each verified credential stores its own provider catalog, and the router gives declared credential support priority over generic provider inference. Refreshing the catalog rechecks current provider availability; unavailable selections remain visible in the configuration until they are restored or removed.

When an upstream returns `404` for a concrete model, Polaris records an unavailable route for that credential and model rather than suppressing the entire provider. The route is temporarily avoided immediately and remains visible under **Unavailable Model Routes** until it is removed or the credential is revalidated. This prevents one account's subscription or regional entitlement from affecting other accounts at the same provider. If no enabled credential declares or can infer support for a requested concrete model, the gateway returns a clear no-compatible-credential error instead of sending the request to a random provider.

Polaris recognizes feature prefixes and suffixes in model names:

- `fake-streaming/{model}` or the configured pseudo-streaming prefix for clients that require SSE output.
- `streaming-anti-truncation/{model}` or the configured anti-truncation prefix for long-form streaming recovery.
- Thinking suffixes such as `-high`, `-medium`, `-low`, `-minimal`, and `-max` for supported Gemini-family models.
- Search suffixes such as `-search` for models that support Google Search grounding.

Provider adapters normalize these feature names before sending upstream requests.

## Usage and Cost Visibility

Polaris records provider-attempt volume, success rate, credential attribution, provider-reported token usage, estimated context-compression savings, and an estimated USD cost per call. Retries and failovers are separate provider attempts, while request traces preserve the final logical request outcome. Token totals distinguish normal input, cache reads, cache writes, output, and reasoning when the provider reports them; the dashboard identifies successful attempts whose usage was not reported instead of treating missing usage as an exact zero. Dashboard periods and chart buckets use fixed clock boundaries in the browser's current timezone, so refreshing at a different minute does not shift the reporting buckets. The one-day view covers the current local calendar day and labels its hourly buckets from 00:00 through 23:00. At startup and every 24 hours by default, the gateway refreshes the public [LiteLLM model-price catalog](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json), validates direct OpenAI, Anthropic, Gemini, and xAI entries, and atomically caches the last valid snapshot. A failed refresh never blocks inference. Override or extend any price by placing a `model_pricing.json` file in the credentials directory; manual prices take precedence and are expressed in USD per one million tokens. Aggregates are available on the dashboard, per virtual key through the `/api/virtual-keys` management API, and through Prometheus `/metrics`. Compression savings and costs remain estimates because provider tokenizers and billing rules are authoritative.

Virtual API keys let one gateway serve multiple clients under separate limits. Each key carries optional daily and monthly USD budgets enforced from the cost ledger, requests-per-minute and tokens-per-minute sliding windows, an expiry timestamp, and a model allowlist with glob patterns. Keys are stored as SHA-256 hashes; the plaintext secret is shown exactly once at creation time.

## Credential Workflow

1. Start Polaris.
2. Open `http://YOUR_SERVER_IP:4283` on a VPS, or `http://127.0.0.1:4283` for local development.
3. Complete the first-run checks and create the console owner password. For remote setup, configure a unique `SETUP_TOKEN` of at least 24 characters before startup and enter it on the setup screen; alternatively preconfigure `PANEL_PASSWORD`.
4. Add an account, API key, or Ollama connection from the Providers page.
5. Open **Credentials** (`/credentials`) to verify credentials and monitor cooldown/error state.
6. Point your coding tool to one of the API surfaces above.

When adding a Google Antigravity credential, Google redirects the browser to `http://localhost:4283/callback` after sign-in. On a local machine, Polaris shows an OAuth success page. On a VPS, that `localhost` address belongs to the user's browser machine, so the page may not load; copy the full URL from the browser address bar, return to the Providers page, paste it into `Callback URL`, and click `Save credential`.

Google AI Studio uses API-key authentication instead of OAuth. Add a key from the Providers page; Polaris validates it against Google's model catalog, stores it as a provider credential, and routes compatible Gemini or Gemma requests through it. The smart router can fall back between AI Studio and Google Antigravity for shared Gemini models while keeping provider-specific models on compatible credentials.

Google AI Studio batch import accepts JSON files and ZIP archives containing JSON files. A JSON document may contain one key, an `api_keys` array, or an array of key objects:

```json
{
  "provider": "google_ai_studio",
  "api_keys": [
    "YOUR_FIRST_API_KEY",
    "YOUR_SECOND_API_KEY"
  ]
}
```

File import is offline: Polaris checks the JSON/ZIP structure, stores new keys as `unverified`, and skips duplicate or existing keys without contacting Google. Imported model lists are not trusted. Malformed entries are reported without exposing key values. Use the explicit credential verification/model-discovery action afterwards; use **Test model** separately to check inference access (which can consume quota or incur charges).

Grok Build supports PKCE OAuth credentials, while SpaceXAI Console supports API keys. SpaceXAI Console keys are validated against the SpaceXAI Console API model catalog before storage. For Grok Build OAuth, Polaris generates an authorization link; after authorization, copy the code displayed on the Grok Build authorization page and paste it into the Grok Build OAuth form. Access tokens are refreshed automatically when a refresh token is available, and both credential types expose only models declared by their respective current catalogs. The Credentials page can retrieve monthly credit usage and, when xAI provides it, weekly usage for Grok Build OAuth accounts. This account-level billing view is not available for SpaceXAI Console API keys.

Codex uses OpenAI's device authorization flow. Generate a device code from the Providers page, open the displayed verification URL, enter the code, finish sign-in, and return to check authorization. Polaris stores the account-scoped model catalog returned by Codex, refreshes OAuth access tokens when needed, and sends compatible requests through the Codex Responses transport. OpenAI Platform uses API-key authentication; keys are validated through the account model catalog before being saved to Credentials. Both products support JSON and ZIP import with provider-specific validation and deduplication.

Claude Code uses Anthropic's PKCE OAuth flow. Generate an authorization link, finish authorization, then paste the returned authorization code into the Providers page. Claude Platform accepts Anthropic API keys. Both products discover the models exposed to each credential, use the Anthropic Messages transport, refresh Claude Code access tokens when possible, and support validated JSON or ZIP import.

Muse Code uses Meta device authorization. In **Providers → Muse Code**, get the sign-in link, approve the displayed device code with Meta, then return and choose **Save credential**. Polaris connects directly; it does not require the Muse CLI, Linux, or a VPS. Models use the `muse-code/` prefix. Advanced settings allow an optional credential display name. Credentials can show the provider-reported plan, session and weekly usage windows, reset times, and observation time. Missing usage is unavailable, not an assumed 100% remaining. Refresh rechecks subscription eligibility and obtains an inference key with the existing OAuth session; if that session is no longer valid, sign in again.

Kiro supports Google/GitHub browser OAuth, AWS device authorization, and an optional API-key path. Advanced fields depend on the selected method: runtime region, AWS token region/start URL, or API-key profile ARN. See the [connection guide](docs/providers/additional-api-providers.md) for provider-specific settings.

Ollama connections are configured per endpoint and may include an optional bearer API key for protected or cloud servers. Polaris discovers models through `/api/tags` and routes inference through `/api/chat`. When Polaris runs in Docker, `localhost` refers to the container itself; use a host-gateway address or another network-reachable Ollama endpoint.

Credential imports and Google Antigravity batch imports accept archives up to 10 MB, at most 500 files, individual credential files up to 2 MB, and at most 25 MB of uncompressed data. Google AI Studio, OpenAI, Anthropic, and Ollama provider imports use stricter limits of 2 MB per imported file, 200 JSON entries, and 5 MB of uncompressed data.

The **Credentials** page (`/credentials`) groups connected accounts and API keys by provider. Each credential's management dialog shows its identity, models, status, and provider-supported actions. OAuth providers can report different quota windows, per-model limits, plans, or credit controls; unavailable information is shown as unavailable. API keys do not imply access to account email, subscription, or billing data.

`Download ZIP` exports credentials, and `Import ZIP` imports mixed-provider archives using provider-specific identification and validation. OAuth identity and API-key fingerprints are deduplicated within their provider and connection context. Unsupported or malformed entries are reported individually. Validation and discovery depend on the provider; an imported credential or visible model catalog does not by itself prove inference access. Use **Test model** for an explicit inference check, which may consume allowance or incur charges.

Credential archives contain secrets. A credential ZIP is not a full application backup: use the encrypted SQLite backup/restore workflow in **Settings** to transfer supported application data and configuration.

Google Antigravity credentials use `google-antigravity-{account_fingerprint}.json`, where the fingerprint is derived from the normalized account email without exposing it. Google AI Studio credentials use `google-ai-studio-{key_fingerprint}.json`, Grok Build OAuth credentials use `grok-{account_fingerprint}.json`, SpaceXAI Console credentials use `xai-console-{key_fingerprint}.json`, Codex credentials use `openai-codex-{account_fingerprint}.json`, OpenAI Platform credentials use `openai-platform-{key_fingerprint}.json`, Claude Code credentials use `claude-code-{account_fingerprint}.json`, Claude Platform credentials use `claude-platform-{key_fingerprint}.json`, and Ollama connections use `ollama-{connection_fingerprint}.json`. Legacy `provider_*.json` and `xai-grok-*.json` credentials remain compatible and are exported with canonical names.

Credential mode names:

- `code_assist`: standard Code Assist credentials.
- `provider`: provider backend credentials.

## Storage

Single-instance deployments use SQLite-backed storage in the application data directory.
Compose and the Docker installer persist all of `/app/backend/data` in the `polaris-data`
named volume. Manual `docker run` deployments must also persist the entire data directory:
mounting only `creds` and `logs` does not preserve SQLite and configuration.

SQLite is the Core storage authority and the recommended production default. PostgreSQL is an
Advanced option for operators who manage their own database lifecycle. MongoDB is retained as a
Compatibility path for existing deployments. It reads and writes MongoDB directly and does not
require or use Redis:

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=polaris
```

```bash
POSTGRESQL_URI=postgresql://user:password@localhost:5432/polaris
```

External storage does not make the runtime horizontally scalable. Production deployments
must run one worker and one replica. Configure either MongoDB or PostgreSQL, not both; an explicit
external-database initialization failure stops startup rather than silently falling back to SQLite.
Portable encrypted backup/restore supports SQLite only, and R1 does not provide a supported live
cross-backend migration command. See [Storage support and recovery](docs/storage.md) before selecting
an external backend.

Environment credential import is available from the control panel. Set one of the following variables to raw JSON or use the matching `_B64` variant for base64-encoded JSON:

```bash
CODE_ASSIST_CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
CREDENTIALS_JSON='{"token":"...","refresh_token":"...","client_id":"...","client_secret":"...","project_id":"..."}'
```

The payload can be a single credential object, an array, or `{ "credentials": [...] }`.

## Development

This section is for contributors and local debugging. Production deployments should use Docker with persistent host volumes.

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

Use [Quality gates](docs/quality-gates.md) to select task, phase, or release scope. Optional live
storage and provider checks are listed separately with
`python tools/quality_gate.py --list-suites`; they cannot change the production result.

Public SDK routes, console management routes, compatibility URLs, config migrations, stored schema
versions, and client examples are protected by the versioned
[compatibility contract](docs/compatibility.md).

Start the service after the checks pass:

```bash
python backend/main.py
```

The production baseline is Python 3.12, and CI currently verifies Python 3.12 and 3.14. See [Contributing](CONTRIBUTING.md) for the pull-request workflow and review expectations.

## Deployment Notes

- Never commit credential JSON files or `.env`.
- Use a dedicated `API_KEY` for client integrations and a separate `PANEL_PASSWORD` for console access.
- Restrict access to the persistent credential volume or external database and enable platform-level encryption at rest; provider tokens must remain retrievable by the router.
- Put Polaris behind a reverse proxy with TLS when reachable outside localhost.
- Configure the reverse proxy to preserve `Host` and pass `X-Forwarded-Proto`; set `PANEL_COOKIE_SECURE=true` when HTTPS termination is guaranteed.
- Set `TRUST_PROXY_HEADERS=true` only when the service is reachable exclusively through a trusted proxy that replaces `X-Forwarded-For` and `X-Forwarded-Proto`.
- Use `GET /health` for process liveness and `GET /ready` for storage-aware readiness checks.
- External telemetry is opt-in. Enable `PROMETHEUS_EXPORT_ENABLED` with a strong `METRICS_TOKEN`,
  or configure the aggregate-only OpenTelemetry exporter as documented in
  [Operational observability](docs/observability.md). Prompt and response content is never exported.
- The Docker image starts as root only long enough to repair mounted data-directory ownership, then runs the service as the unprivileged `gateway` user.
- Set `CORS_ORIGINS` to explicit trusted origins when browser clients need cross-origin access.
- Use the authenticated [encrypted backup and restore workflow](docs/backup-and-restore.md) before
  upgrading or moving a standalone SQLite deployment. Keep the archive and its passphrase outside
  the `polaris-data` volume.
- Docker image publishing uses the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets for Docker Hub, and the built-in `GITHUB_TOKEN` for GitHub Packages at `ghcr.io/nguywnben/polaris`. Set the optional `IMAGE_NAME` repository variable only when publishing to a custom Docker Hub image name.
- Keep `WORKERS=1` and one application replica for the 1.x series; external storage is not a substitute for distributed coordination.
- Use the canonical `/api/credentials` management routes. The beta `/api/creds` aliases were removed in 1.0.0.
- Follow [Upgrading to 1.0](docs/upgrading-to-1.0.md) before migrating a beta deployment.
- Follow the [update guide](docs/updating.md) when upgrading a deployed instance or rolling back a release.
- Follow the maintained [release checklist](docs/release-checklist.md) before tagging or promoting an image.
- Keep log retention and credential rotation policies aligned with your usage limits.
- Rotate credentials immediately if a repository or platform scanner reports a leaked secret.
- The Render Blueprint uses a paid service with a persistent disk. Render free services use ephemeral filesystems and are suitable only for disposable evaluation.

## Community and Project Health

- Read [Contributing](CONTRIBUTING.md) before opening a pull request.
- Report vulnerabilities through the private process in [Security Policy](SECURITY.md).
- Review [Changelog](CHANGELOG.md) for release-level changes.
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md) in all project spaces.

## Acknowledgements & Inspirations

Polaris stands on the shoulders of the open-source AI routing, telemetry, and gateway community. We express our gratitude to the creators and maintainers of these projects:

| Project | Description | Stars |
| :--- | :--- | :---: |
| [**songquanpeng / one-api**](https://github.com/songquanpeng/one-api) | Inspiration for multi-provider key management and web-based API aggregation | [![Stars](https://img.shields.io/github/stars/songquanpeng/one-api?style=flat-square&color=yellow)](https://github.com/songquanpeng/one-api) |
| [**router-for-me / CLIProxyAPI**](https://github.com/router-for-me/CLIProxyAPI) | Pioneering multi-format proxy and protocol translation layer for AI coding CLIs | [![Stars](https://img.shields.io/github/stars/router-for-me/CLIProxyAPI?style=flat-square&color=yellow)](https://github.com/router-for-me/CLIProxyAPI) |
| [**BerriAI / litellm**](https://github.com/BerriAI/litellm) | Standard-setting unified LLM proxy, load balancing, and fallback routing | [![Stars](https://img.shields.io/github/stars/BerriAI/litellm?style=flat-square&color=yellow)](https://github.com/BerriAI/litellm) |
| [**Portkey-AI / gateway**](https://github.com/Portkey-AI/gateway) | Ultra-fast AI gateway architecture, routing strategies, and resilient fallback patterns | [![Stars](https://img.shields.io/github/stars/Portkey-AI/gateway?style=flat-square&color=yellow)](https://github.com/Portkey-AI/gateway) |
| [**langfuse / langfuse**](https://github.com/langfuse/langfuse) | Open-source LLM engineering platform, tracing, observability, and metrics ingestion | [![Stars](https://img.shields.io/github/stars/langfuse/langfuse?style=flat-square&color=yellow)](https://github.com/langfuse/langfuse) |

## License

Polaris is released under the [MIT License](LICENSE).
