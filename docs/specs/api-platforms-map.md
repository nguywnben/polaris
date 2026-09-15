# API platform provider expansion

Status: scope and implementation approved by the owner on 2026-09-15. Execute sequentially; no delegated agents.

| Module | Responsibility | Depends on |
| --- | --- | --- |
| [groqcloud](api-platform-groqcloud.md) | GroqCloud API-key integration | Existing hosted-provider boundary |
| [deepseek-platform](api-platform-deepseek-platform.md) | DeepSeek Platform API-key integration | Existing hosted-provider boundary |
| [mistral-ai](api-platform-mistral-ai.md) | Mistral AI Studio API-key integration | Existing hosted-provider boundary |
| [cerebras-cloud](api-platform-cerebras-cloud.md) | Cerebras Cloud API-key integration | Existing hosted-provider boundary |

Build order: groqcloud → deepseek-platform → mistral-ai → cerebras-cloud.
Each module is a complete provider slice: transport, credential lifecycle, console and verification.
The existing 18 provider variants remain unchanged; the completed catalog will contain 22.
This owner-requested expansion does not reopen or renumber the completed production baseline.

No new OAuth flow, runtime dependency, database migration, or unrelated provider settings.
The owner subsequently approved updating the local Docker container on port 4283,
preserving its configuration and data volume. Remote push remains outside scope.

## Implementation checklist

- [x] Contract tests first: provider registration, trusted endpoints, isolated settings and chat catalogs.
- [x] GroqCloud transport and catalog filtering; preserve Groq streaming usage/error metadata.
- [x] DeepSeek Platform transport and tool reasoning history.
- [x] Mistral AI Studio transport, content chunks and paired wire tool IDs.
- [x] Cerebras Cloud transport using its documented Chat endpoint.
- [x] Console onboarding/import integration, PNG logos and descriptions in 15 locales.
- [x] Management, inference and import regression tests, including fragmented streams.
- [x] Browser matrix, locale audit, quality gate and core regression suite.
- [x] Review and document remaining live-account limitations.

Verification on 2026-09-15: the core suite passed 2,082 tests with 22 optional skips;
the quality gate and both locale audits passed. The disposable-browser smoke covered
22 catalog cards, 15 locales, 130 provider form viewport/theme cases and 39 import
cases. No real vendor API key or billable inference request was used.

Logos are local PNG assets only; the user-approved source SVG files were removed after rasterization.
