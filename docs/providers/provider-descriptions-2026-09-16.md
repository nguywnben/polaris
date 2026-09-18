# Provider product descriptions

Provider cards and workspace headers share a product-focused description in all
15 console locales. Each description identifies the product and its purpose;
authentication badges identify connection methods, and form copy explains steps.
These are product introductions, not a claim that Polaris exposes every feature
of the upstream IDE, CLI, inference service or developer platform.

The catalog distinguishes coding tools from developer model platforms, including
Grok Build / SpaceXAI Console, Codex / OpenAI Platform, Claude Code / Claude Platform,
and Muse Code / Meta Model API. Model gateways such as OpenCode and Kilo mention
their model services. Descriptions avoid prices, quotas, specific model versions,
benchmark claims and authentication instructions.

## Source notes

Product scope was checked against official documentation on 2026-09-16. Descriptions
are original summaries rather than marketing excerpts.

| Providers | Product reference |
| --- | --- |
| Google Antigravity | [Product overview](https://antigravity.google/) — agents, editor and terminal |
| Google AI Studio | [Quickstart](https://ai.google.dev/gemini-api/docs/ai-studio-quickstart) — Gemini experiments and app prototyping |
| Grok Build | [Coding agent overview](https://docs.x.ai/build/overview) — code exploration and terminal workflows |
| SpaceXAI Console | [Grok API](https://docs.x.ai/overview) — developer access to Grok models |
| Codex | [OpenAI developer documentation](https://developers.openai.com/codex/) — coding workflows |
| OpenAI Platform | [API overview](https://developers.openai.com/api/docs/overview) — models for applications and agents |
| Claude Code | [Overview](https://code.claude.com/docs/en/overview) — codebase, file and command workflows |
| Claude Platform | [Claude introduction](https://platform.claude.com/docs/en/intro) — language, reasoning and coding |
| Ollama | [Product overview](https://ollama.com/) — local and cloud models |
| Kimi API Platform | [Quickstart](https://platform.kimi.ai/docs/overview) — Kimi model platform |
| Kiro | [Product overview](https://kiro.dev/) — specification-driven development |
| Cloudflare Workers AI | [Overview](https://developers.cloudflare.com/workers-ai/) — managed serverless inference |
| NVIDIA NIM | [Developer overview](https://developer.nvidia.com/nim) — optimized GPU inference services |
| OpenCode | [Agent](https://opencode.ai/), [Zen](https://opencode.ai/docs/zen/), [Go](https://opencode.ai/docs/go/) — coding agent and model services |
| Poolside Platform | [Overview](https://docs.poolside.ai/get-started/overview), [Platform introduction](https://poolside.ai/blog/introducing-the-poolside-platform) — enterprise software engineering |
| Kimchi Coding | [Inference overview](https://docs.kimchi.dev/docs/model-apis-overview) — distinction between the coding agent and hosted model service |
| Kilo | [Gateway](https://kilo.ai/docs/gateway), [Product overview](https://kilo.ai/) — coding agents and unified model access |
| Meta Model API / Muse Code | [API overview](https://dev.meta.ai/docs/getting-started/overview/), [Muse Code](https://dev.meta.ai/docs/muse-code) — model platform versus terminal assistant; the text fetch returned a shell, so scope also follows the previously recorded rendered-documentation and CLI evidence in [Muse research](muse-code-research-2026-09-16.md) |
| GroqCloud | [Overview](https://console.groq.com/docs/overview) — low-latency inference hardware |
| DeepSeek Platform | [API documentation](https://api-docs.deepseek.com/) — conversation, reasoning and coding models |
| Mistral AI Studio | [Documentation](https://docs.mistral.ai/) — model experimentation and application development |
| Cerebras Cloud | [Inference overview](https://inference-docs.cerebras.ai/) — wafer-scale inference hardware |

## Verification

Locale audits check coverage. `tools/provider_entry_smoke.py` checks 23 unique
descriptions per locale and card/header parity. `tools/extended_providers_smoke.py`
checks catalog sizing, uncropped text, search, pagination, responsive layouts and
provider form regressions using disposable data. No provider credentials, vendor
requests, authentication protocols or deployment settings are changed by this copy update.

Verification passed: both browser scripts, 13 focused onboarding/Muse UI tests,
all three locale audits, JavaScript syntax and Python lint/format checks. Desktop
light and 320px dark catalog captures were visually reviewed. The Kiro description
is no longer overwritten when legacy authentication translations are reapplied.
