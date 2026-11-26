# ADR 0012: Dependency policy

Status: proposed
Date: 2026-10-25

## Context
Legacy "stdlib only" produced a vendored TOML parser, an own validator and a byte-copied validator; a commercial
product with PostgreSQL and HTTP needs a few libraries.

## Decision
Allowed runtime libraries: psycopg[binary,pool], jsonschema+referencing, starlette, uvicorn, httpx, keyring
(optional extra). Each is used only in its layer (see engineering standards §3) and recorded in
`docs/dependencies.md` with purpose, layer and alternative. Versions are pinned through `uv.lock`. Forbidden
without a new ADR: ORM, pydantic/attrs/msgspec, DI frameworks, async frameworks in core, brokers, telemetry SDKs.

## Alternatives considered
- Stdlib only: rejected for v2.
- Free choice per item: rejected — dependency sprawl.

## Consequences
Small, auditable dependency tree.

## Compatibility
n/a.

## Verification
Architecture test checks third-party imports against an allowlist per layer.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

### GenAI semantic conventions (I-12.3)

SKM uses a dependency-free projection of the [OpenTelemetry GenAI v0.1.0 conventions](https://github.com/open-telemetry/semantic-conventions-genai/releases/tag/v0.1.0).
The runtimes module owns the mapping from recorded runtime observations and reported usage to
agent invocation attributes. The projection is metadata-only and runs without a tracer, exporter
or collector. SKM retains the existing dependency allowlist. Adopting an SDK or adding a telemetry
export path requires a separate ADR.
