# PB4 — Core Correctness Normalization

Date: 2026-09-12

PB4 removes the remaining project-owned Pydantic v1 configuration surface and tightens only the
failure boundaries named by the fixed plan. Six protocol models and the AI Quality update model now
use `ConfigDict`; the compatibility-only `BaseModel.dict()` fallback is gone because the locked
runtime is Pydantic 2. Importing the affected modules with Pydantic deprecations promoted to errors
passes, and the maintainability inventory reports no Pydantic deprecation site.

Startup, shutdown, selected-storage initialization, credential import/export, response-cache
fallback, cooldown parsing, and nested stream cleanup now emit bounded error types instead of
silently swallowing failures or interpolating raw exception detail. Expected malformed cooldown
data is caught by typed parser exceptions. The redundant callers around that bounded parser were
removed. Authentication/OIDC boundaries continue to translate unexpected failures into their
existing sanitized typed errors rather than exposing provider or identity details.

Implementation diff before this evidence/checklist update: 14 files, 99 additions and 67
deletions. This task intentionally does not attempt a global rewrite of every storage/provider
exception boundary.

Verification:

- 107 focused lifecycle, storage selection, stream settlement, guardrail/cache, routing model,
  OpenAI Responses, cross-protocol, and AI Quality tests passed.
- Regression tests prove startup/shutdown/storage/stream cleanup logs exclude injected secret text
  while retaining an observable error type.
- The compatibility snapshot remains unchanged at 18 public inference and 126 management
  operations.
- The fast quality gate passed lint, format, compilation, the 195-module Core manifest, recursive
  JavaScript syntax, strict YAML, shell syntax, and whitespace.

