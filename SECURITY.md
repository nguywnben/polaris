# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| Latest `1.x` release | Yes |
| `main` / `edge` development builds | Best effort |
| `0.x` beta releases | No |
| Older `1.x` releases | Upgrade to the latest release |

## Reporting Vulnerabilities

Report suspected vulnerabilities through a [private GitHub security advisory](https://github.com/nguywnben/polaris/security/advisories/new). Do not open a public issue for active secrets, credential exposure, authentication bypasses, or deployment compromise.

Include the affected version or commit, deployment topology, reproduction steps, impact, and any proposed mitigation. Remove real credentials and personal data from evidence. This is a personal open-source project, so response times are best effort; reports are normally acknowledged within 72 hours.

After a fix is available, coordinate public disclosure through the advisory. Credit is provided unless the reporter prefers to remain anonymous.

## Operational Baseline

- Use a unique `PANEL_PASSWORD` for the management console.
- Use a separate `API_KEY` beginning with `sk-ogw-` for client traffic.
- Keep the service behind TLS when exposed outside localhost.
- Keep `MAX_REQUEST_BODY_MB` bounded and configure an equal or lower request-body limit at the reverse proxy.
- Protect the bootstrap token printed for remote first-run setup, or preconfigure `PANEL_PASSWORD` for non-interactive deployment.
- Restrict browser cross-origin access with `CORS_ORIGINS`.
- Preserve `Host` and trust forwarded headers only when a controlled reverse proxy overwrites them.
- Run exactly one worker and one application replica for the 1.x series, regardless of storage backend.
- Protect the credential volume or external database with least-privilege access and platform-level encryption at rest. Provider tokens and API keys must remain retrievable by the router and are not application-encrypted.
- Never commit `.env`, credential JSON files, database files, or logs.
- Rotate credentials immediately if GitHub or another scanner reports a public leak.
