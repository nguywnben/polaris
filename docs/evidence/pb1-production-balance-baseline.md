# PB1 — Production Balance Baseline

Date: 2026-09-12

PB1 restored the current branch to the previously accepted production contracts before any
topology simplification. It did not change the frozen R1 compatibility fixture.

- Removed the accidental strict-extra schema change from `VirtualModelPoolUpdateRequest`; the
  endpoint again accepts the exact R1 OpenAPI contract.
- Formatted the committed console feedback contract test instead of relaxing the format gate.
- The focused compatibility/model-routing run passed all 33 tests.
- The complete fast gate passed lint, format, compilation, suite partition, recursive JavaScript,
  strict YAML, shell syntax, and whitespace.

The workstream proceeds to PB2 with a truthful green baseline.
