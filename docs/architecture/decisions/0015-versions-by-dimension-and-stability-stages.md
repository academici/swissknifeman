# ADR 0015: Versions by dimension and stability stages

## Status

Accepted

## Context

One SemVer number cannot express module, manifest, schema, protocol and capability compatibility.

## Decision

Versions are kept separately: module version (SemVer, `version` in `unit.json`), manifest version (`$schema` of
`unit.json`), contract version (`.../v<N>`: a minor change adds only optional fields, a major change creates a new
directory), protocol version (`protocol` min and max for bridges and external plugins) and capability version
(`id@N`). Stability stages: `development`, `alpha`, `beta`, `rc`, `stable`, `deprecated`. For every contract the
policy records how many past majors a consumer reads, what a producer writes, who upcasts, the deprecation window,
behaviour on unknown fields and the migration fixtures. `unit.json` declares `requires` as ranges and `provides`
with versions; the module check verifies the ranges.

## Alternatives considered

- A single SemVer per module: rejected, it hides contract and protocol changes.

## Consequences

- The policy per contract is in `contracts.md`.
- The rule matches the existing `exec/v1` practice.

## Supersedes

None.
