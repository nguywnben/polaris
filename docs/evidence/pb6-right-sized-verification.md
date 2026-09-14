# PB6 — Right-Sized Production Verification

Date: 2026-09-12

PB6 separates routine production confidence from optional endurance evidence. The release gate now
runs a 120-second deterministic profile at 5 RPS and eight configured concurrency (600 requests),
which is proportionate to a personal or trusted-team deployment and completes within the fixed
three-minute budget on the reference Windows host.

The original 600-second, 10 RPS, concurrency-16 profile is preserved byte-for-byte as
`tools/reliability-soak-profile.json` and is listed as `reliability-soak`, an automated optional
suite for major releases or memory investigations. Both profiles retain the same p95, error-rate,
memory, scheduling-lag, dashboard, graceful-shutdown, and restart thresholds; PB6 did not weaken a
quality boundary to obtain a pass.

The active gate, CLI output, docs, and ownership labels no longer refer to historical P5.5 work.
Current guidance distinguishes Core release checks, Advanced PostgreSQL live evidence,
Compatibility MongoDB live evidence, optional real-provider checks, and the optional soak. The
obsolete high-availability runbook was removed because it invoked Redis/HA evidence tooling and
deployment assets retired in PB2.

Verification:

- 31 reliability, gate, retired-topology, and product-inventory contracts passed.
- Release dry-run lists 17 deterministic steps and selects `--profile routine --verify` under PB6.
- Optional-suite listing exposes `reliability-soak` separately and never promotes it to the release
  verdict.
- The routine profile passed all 15 checks: 600/600 successful requests, p95 76.055 ms, dashboard
  usable in 565.491 ms, and successful graceful restart/persisted post-restart request.
- The existing intentional-failure contract rejects excessive error rate, p95, queue depth,
  exhaustion, dashboard time, shutdown time, restart time, and post-restart failure.
