# ADR-002: Secure First Run and Enforce Single-Worker Operation

- Status: Accepted
- Date: 2026-07-12

## Context

An unconfigured instance previously allowed the first browser that reached the setup endpoint to establish the console password. That is convenient on localhost but unsafe when a new container is immediately exposed on a public VPS. The service also accepted `WORKERS` values greater than one even though credential reservations, cooldowns, sessions, and usage counters were not coordinated across processes.

## Decision

Direct setup through a loopback client and loopback host remains token-free. A loopback browser reaching a host-published container through the Docker bridge is also treated as local transport, while token access still follows the client-address boundary. Every remote setup request must present a strong, operator-configured `SETUP_TOKEN` of at least 24 characters. The process does not generate or print this secret. The token is useful only while no console password exists.

Before owner creation, a first-run preflight verifies durable configuration writes, the effective console address, HTTPS and secure-cookie expectations, setup-token policy, and existing installation state. Its resumable checkpoint contains only a schema version and completion marker. Owner creation is serialized and accepts a bounded unique passphrase of 12–256 characters.

The 1.x runtime accepts exactly one worker and one application replica. MongoDB and PostgreSQL remain optional storage backends, but they do not imply horizontal-scaling support. A future multi-worker design must provide distributed credential reservations, cooldown state, session invalidation, and centralized usage aggregation before this restriction is relaxed.

## Consequences

- A public first deployment cannot be claimed by an unauthenticated visitor who does not possess the bootstrap token.
- Local development keeps its existing setup flow.
- Remote operators must set a strong `SETUP_TOKEN` before startup; secrets are not recoverable from logs.
- Fresh, resumed, configured, and invalid setup states each expose one next action without including credentials.
- Invalid scale-out configurations fail early with an actionable message.
- Horizontal scaling is deferred rather than represented as production-ready prematurely.
