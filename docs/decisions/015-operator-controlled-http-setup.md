# ADR-015: Operator-Controlled HTTP Setup

- Status: Accepted
- Date: 2026-09-18
- Amends: ADR-002 transport policy only

## Context

Self-hosted operators may choose direct IP-based HTTP access without TLS. The default remote
setup HTTPS requirement prevents that choice even when the operator accepts the transport risk.

## Decision

Keep HTTPS as the recommendation and default remote setup requirement. Only the server owner
can opt in using the environment-only boolean `SETUP_ALLOW_INSECURE_HTTP=true`. Neither request
parameters nor browser controls can change that policy. The console reports a warning, not a
secure-transport success, and explains interception/tampering risks before secrets are entered.

The exception affects initial setup only. Strong setup-token verification, owner password
validation, storage durability, cookie compatibility and origin protection remain unchanged.
Do not force insecure cookies on HTTPS or trust proxy headers just to make HTTP work.

Local transport requires both a loopback host and a loopback client under the existing
proxy-trust policy. A loopback Host header alone is not evidence of local access.
When Docker NAT hides the client, HTTP requires the same explicit server-side flag.
The guided installer's local mode sets it only while enforcing a loopback-only published
port; its public mode still requires the operator's HTTP confirmation. Manual Docker and
Compose users configure this explicitly. No private-subnet heuristic grants local trust.

## Consequences

- Operators can knowingly complete remote HTTP setup with no domain or TLS prerequisite.
- HTTP exposes credentials and sessions to on-path attackers; opt-in does not make it secure.
- Reverting the flag does not block HTTP login after setup; secure the listener separately.
- No database migration, version bump, tag rewrite or publication is part of this change.
