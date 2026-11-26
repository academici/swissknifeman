# ADR 0011: JSON Schema is the source of truth for contracts

Status: proposed
Date: 2026-10-25

## Context
Hand-maintained types next to schemas drift; legacy generated types only for two packages.

## Decision
Contracts (command/query DTOs, API bodies, events, settings sections, documents) are JSON Schema Draft 2020-12
files under `src/skm/schemas/` with `$id = urn:skm:<module>:<kind>:v<major>`. `make gen` generates Python types
(frozen dataclasses for DTOs, TypedDict for raw documents) and TypeScript types; generated files carry a schema
hash header and must not be edited. Validation uses the `jsonschema` library. Within a major version input schemas may gain optional fields. Closed output schemas (`result`, `view`,
`event`) require a new major for new properties; extensible outputs carry additions in their open `extensions`
field. Compatibility checks are the offline comparison in [`tools/schema_check.py`](../../tools/schema_check.py) and [`tools/schema_comparison.py`](../../tools/schema_comparison.py), ported from legacy `schemacompat`.

## Alternatives considered
- Pydantic models as the source: rejected — a second rule source next to schemas.
- Keep the legacy stdlib validator: rejected — it lacks `anyOf`, `allOf`, `if/then`, `format`.

## Consequences
Every boundary change starts with a schema diff.

## Compatibility
Legacy digest/v1 canonical JSON algorithm and its vectors are ported unchanged for content digests.

## Verification
`make schema-check` fails on drift or incompatible change.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E33 forbids handwritten generated DTOs in P00. E38 pins the supported code-generation profile and preserves the full runtime schema.
