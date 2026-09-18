# Configuration Reference

> Generated from `backend/core/configuration_schema.py`; do not edit manually.

Values marked `secret` never expose a default through the Settings API.

| Variable | Group | Type | Default | Apply | Settings owner |
| --- | --- | --- | --- | --- | --- |
| `HOST` | basic | string | `0.0.0.0` | restart | system |
| `PORT` | basic | integer | `4283` | restart | system |
| `HOST_PORT` | basic | integer | `4283` | read_only | environment |
| `POLARIS_RUNTIME_MODE` | basic | string | `standalone` | read_only | environment |
| `POLARIS_REPLICA_COUNT` | basic | integer | `1` | read_only | environment |
| `WORKERS` | basic | integer | `1` | read_only | environment |
| `CORS_ORIGINS` | basic | csv | `(empty)` | read_only | environment |
| `CORS_ORIGIN_REGEX` | basic | string | `(empty)` | read_only | environment |
| `API_KEY` | basic | string / secret | `(empty)` | live | access |
| `PANEL_PASSWORD` | basic | string / secret | `(empty)` | live | access |
| `SETUP_TOKEN` | basic | string / secret | `(empty)` | read_only | environment |
| `SETUP_ALLOW_INSECURE_HTTP` | basic | boolean | `false` | read_only | environment |
| `PANEL_SESSION_TTL_SECONDS` | basic | integer | `86400` | read_only | environment |
| `PANEL_COOKIE_SECURE` | basic | boolean | `(empty)` | read_only | environment |
| `PANEL_LOGIN_WINDOW_SECONDS` | basic | integer | `300` | read_only | environment |
| `PANEL_LOGIN_MAX_ATTEMPTS` | basic | integer | `10` | read_only | environment |
| `PANEL_LOGIN_MAX_TRACKED_CLIENTS` | basic | integer | `10000` | read_only | environment |
| `MAX_REQUEST_BODY_MB` | basic | integer | `64` | read_only | environment |
| `TRUST_PROXY_HEADERS` | basic | boolean | `false` | read_only | environment |
| `OIDC_ENABLED` | advanced | boolean | `false` | read_only | environment |
| `OIDC_ISSUER` | advanced | string | `(empty)` | read_only | environment |
| `OIDC_CLIENT_ID` | advanced | string | `(empty)` | read_only | environment |
| `OIDC_CLIENT_SECRET` | advanced | string / secret | `(empty)` | read_only | environment |
| `OIDC_CLIENT_SECRET_FILE` | advanced | string / secret | `(empty)` | read_only | environment |
| `OIDC_REDIRECT_URI` | advanced | string | `(empty)` | read_only | environment |
| `OIDC_SCOPES` | advanced | space_list | `openid profile email` | read_only | environment |
| `OIDC_ID_TOKEN_SIGNING_ALGORITHMS` | advanced | csv | `RS256` | read_only | environment |
| `OIDC_SUBJECT_CLAIM` | advanced | string | `sub` | read_only | environment |
| `OIDC_USERNAME_CLAIM` | advanced | string | `preferred_username` | read_only | environment |
| `OIDC_DISPLAY_NAME_CLAIM` | advanced | string | `name` | read_only | environment |
| `OIDC_EMAIL_CLAIM` | advanced | string | `email` | read_only | environment |
| `OIDC_GROUPS_CLAIM` | advanced | string | `groups` | read_only | environment |
| `OIDC_ROLE_MAPPINGS` | advanced | json | `{}` | read_only | environment |
| `OIDC_ALLOWED_ENDPOINT_ORIGINS` | advanced | csv | `(empty)` | read_only | environment |
| `OIDC_ALLOWED_PRIVATE_HOSTS` | advanced | csv | `(empty)` | read_only | environment |
| `OIDC_CONNECT_TIMEOUT_SECONDS` | advanced | integer | `5` | read_only | environment |
| `OIDC_READ_TIMEOUT_SECONDS` | advanced | integer | `10` | read_only | environment |
| `OIDC_MAX_RESPONSE_BYTES` | advanced | integer | `262144` | read_only | environment |
| `OIDC_JWKS_TTL_SECONDS` | advanced | integer | `300` | read_only | environment |
| `OIDC_START_WINDOW_SECONDS` | advanced | integer | `300` | read_only | environment |
| `OIDC_START_MAX_ATTEMPTS` | advanced | integer | `20` | read_only | environment |
| `OIDC_START_MAX_TRACKED_CLIENTS` | advanced | integer | `10000` | read_only | environment |
| `CREDENTIALS_DIR` | basic | string | `./backend/data/creds` | restart | system |
| `MONGODB_URI` | advanced | string / secret | `(empty)` | read_only | environment |
| `MONGODB_DATABASE` | advanced | string | `polaris` | read_only | environment |
| `POSTGRESQL_URI` | advanced | string / secret | `(empty)` | read_only | environment |
| `CODE_ASSIST_CREDENTIALS_JSON` | advanced | json / secret | `(empty)` | read_only | environment |
| `CREDENTIALS_JSON` | advanced | json / secret | `(empty)` | read_only | environment |
| `CODE_ASSIST_CLIENT_ID` | advanced | string | `(empty)` | live | provider |
| `CODE_ASSIST_CLIENT_SECRET` | advanced | string / secret | `(empty)` | live | provider |
| `ANTIGRAVITY_CLIENT_ID` | advanced | string | `(empty)` | live | provider |
| `ANTIGRAVITY_CLIENT_SECRET` | advanced | string / secret | `(empty)` | live | provider |
| `ANTIGRAVITY_USER_AGENT` | advanced | string | `antigravity/cli/1.0.1 windows/amd64` | live | provider |
| `ANTIGRAVITY_PAYLOAD_USER_AGENT` | advanced | string | `antigravity` | live | provider |
| `PROXY` | basic | string | `(empty)` | live | system |
| `CODE_ASSIST_ENDPOINT` | advanced | string | `https://cloudcode-pa.googleapis.com` | live | provider |
| `ANTIGRAVITY_API_URL` | advanced | string | `https://daily-cloudcode-pa.googleapis.com` | live | provider |
| `GOOGLE_AI_STUDIO_API_URL` | advanced | string | `https://generativelanguage.googleapis.com` | live | provider |
| `XAI_API_URL` | advanced | string | `https://api.x.ai/v1` | live | provider |
| `XAI_OAUTH_API_URL` | advanced | string | `https://cli-chat-proxy.grok.com/v1` | live | provider |
| `XAI_OAUTH_ISSUER` | advanced | string | `https://auth.x.ai` | live | provider |
| `XAI_CLIENT_ID` | advanced | string | `(empty)` | live | provider |
| `XAI_USER_AGENT` | advanced | string | `grok-cli/polaris` | live | provider |
| `OAUTH_URL` | advanced | string | `https://oauth2.googleapis.com` | live | provider |
| `GOOGLE_APIS_URL` | advanced | string | `https://www.googleapis.com` | live | provider |
| `RESOURCE_MANAGER_URL` | advanced | string | `https://cloudresourcemanager.googleapis.com` | live | provider |
| `SERVICE_USAGE_URL` | advanced | string | `https://serviceusage.googleapis.com` | live | provider |
| `OPENAI_API_URL` | advanced | string | `https://api.openai.com/v1` | live | provider |
| `CODEX_API_URL` | advanced | string | `https://chatgpt.com/backend-api/codex` | live | provider |
| `CODEX_USAGE_URL` | advanced | string | `https://chatgpt.com/backend-api/wham/usage` | live | provider |
| `CODEX_AUTH_BASE` | advanced | string | `https://auth.openai.com` | live | provider |
| `CODEX_CLIENT_ID` | advanced | string | `app_EMoamEEZ73f0CkXaXp7hrann` | live | provider |
| `CODEX_USER_AGENT` | advanced | string | `codex_cli_rs/0.0.0 (Unknown 0; unknown)` | live | provider |
| `ANTHROPIC_API_URL` | advanced | string | `https://api.anthropic.com/v1` | live | provider |
| `CLAUDE_OAUTH_AUTHORIZE_URL` | advanced | string | `https://claude.ai/oauth/authorize` | live | provider |
| `CLAUDE_OAUTH_TOKEN_URL` | advanced | string | `https://api.anthropic.com/v1/oauth/token` | live | provider |
| `CLAUDE_CLIENT_ID` | advanced | string | `9d1c250a-e61b-44d9-88ed-5944d1962f5e` | live | provider |
| `CLAUDE_USER_AGENT` | advanced | string | `claude-cli/polaris` | live | provider |
| `CLAUDE_PLATFORM_API_URL` | advanced | string | `https://api.anthropic.com/v1` | live | provider |
| `CLAUDE_PLATFORM_USER_AGENT` | advanced | string | `polaris/claude-platform` | live | provider |
| `VERTEX_ANON_API_KEY` | advanced | string / secret | `(empty)` | read_only | environment |
| `AUTO_DISABLE` | advanced | boolean | `false` | live | system |
| `AUTO_DISABLE_ERROR_CODES` | advanced | integer_list | `403` | live | system |
| `RETRY_429_ENABLED` | advanced | boolean | `true` | live | system |
| `RETRY_429_MAX_RETRIES` | advanced | integer | `5` | live | system |
| `RETRY_429_INTERVAL` | advanced | number | `1` | live | system |
| `SWITCH_CREDENTIAL_ENABLED` | advanced | boolean | `true` | live | system |
| `ROUTING_STRATEGY` | basic | string | `balanced` | live | system |
| `PREFERRED_PROVIDER` | basic | string | `(empty)` | live | system |
| `UPSTREAM_TIMEOUT_SECONDS` | advanced | number | `300` | live | system |
| `RESPONSE_CACHE_ENABLED` | advanced | boolean | `false` | live | quality |
| `RESPONSE_CACHE_TTL_SECONDS` | advanced | integer | `300` | live | quality |
| `RESPONSE_CACHE_MAX_ENTRIES` | advanced | integer | `1000` | live | quality |
| `GUARDRAILS_ENABLED` | advanced | boolean | `false` | live | quality |
| `GUARDRAILS_PII_MASKING_ENABLED` | advanced | boolean | `true` | live | quality |
| `GUARDRAILS_INJECTION_DETECTION_ENABLED` | advanced | boolean | `true` | live | quality |
| `GUARDRAILS_BLOCKED_KEYWORDS` | advanced | csv | `(empty)` | live | quality |
| `PRICING_SYNC_ENABLED` | advanced | boolean | `true` | read_only | environment |
| `PRICING_SYNC_INTERVAL_HOURS` | advanced | integer | `24` | read_only | environment |
| `COMPATIBILITY_MODE` | advanced | boolean | `false` | live | quality |
| `RETURN_THOUGHTS_TO_FRONTEND` | advanced | boolean | `true` | live | quality |
| `STREAM_TO_NONSTREAM` | advanced | boolean | `true` | live | system |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | advanced | integer | `3` | live | quality |
| `TOKEN_COMPRESSION_ENABLED` | advanced | boolean | `true` | live | quality |
| `TOKEN_COMPRESSION_THRESHOLD` | advanced | integer | `32000` | live | quality |
| `TOKEN_COMPRESSION_TARGET` | advanced | integer | `24000` | live | quality |
| `TOKEN_COMPRESSION_MIN_RECENT_TURNS` | advanced | integer | `4` | live | quality |
| `LOG_LEVEL` | basic | string | `info` | live | system |
| `LOG_MAX_MB` | advanced | integer | `10` | live | system |
| `LOG_BACKUP_COUNT` | advanced | integer | `3` | live | system |
| `PROMETHEUS_EXPORT_ENABLED` | advanced | boolean | `false` | read_only | environment |
| `METRICS_TOKEN` | advanced | string / secret | `(empty)` | read_only | environment |
| `OTEL_EXPORT_ENABLED` | advanced | boolean | `false` | read_only | environment |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | advanced | string | `(empty)` | read_only | environment |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | advanced | string | `http/json` | read_only | environment |
| `OTEL_EXPORT_INTERVAL_SECONDS` | advanced | integer | `60` | read_only | environment |
| `OTEL_EXPORTER_OTLP_HEADERS` | advanced | string / secret | `(empty)` | read_only | environment |
| `LANGFUSE_PUBLIC_KEY` | advanced | string / secret | `(empty)` | read_only | environment |
| `LANGFUSE_SECRET_KEY` | advanced | string / secret | `(empty)` | read_only | environment |
| `LANGFUSE_HOST` | advanced | string | `https://cloud.langfuse.com` | read_only | environment |
| `LOG_FILE` | advanced | string | `./backend/data/logs/polaris.log` | read_only | environment |
| `KEEPALIVE_URL` | advanced | string | `(empty)` | live | system |
| `KEEPALIVE_INTERVAL` | advanced | integer | `60` | live | system |
