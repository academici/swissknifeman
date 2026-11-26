# ADR 0043: Validator profile with patternProperties and a schema compatibility check

## Status

Accepted

## Context

Dictionaries keyed by identifiers (ADR 0040) cannot be written in the closed validator profile, and contract changes
within a major version were reviewed by eye.

## Decision

- **Profile.** `aicore.util.schema` accepts `patternProperties` and `propertyNames` with the semantics of draft 2020-12:
  a property is covered when it is listed or matches a pattern, every matching schema applies, `propertyNames` checks
  names only and does not widen coverage (issue code `property_name`). Patterns of contracts are anchored.
- **References.** `load_contract` loads neighbouring aicore contracts named by `$ref`
  (`urn:swissknifeman:aicore:<contract>:v<N>`); `common/v1` holds the shared `$defs`.
- **Compatibility.** `aicore schema compat [--base REF] [--json]` (`aicore.util.schemacompat`) compares the working tree
  with a git reference inside one major version by backward-compatibility rules (22 kinds of change). What cannot be
  proven (`pattern`, `oneOf`) counts as breaking. A breaking change is an error for contracts at `beta` or above and a
  warning below; a bad reference exits with 2.

## Alternatives considered

- A full JSON Schema library: rejected, modules stay stdlib-only (ADR 0032).
- Compare by hand in review: rejected, it misses narrowed enums and new `required`.

## Consequences

- A contract may reference shared definitions and may hold a dictionary.
- A `beta` contract cannot change incompatibly by accident; the conservative rules can flag a harmless change, which is
  then a reviewed exception.

## Supersedes

Refines ADR 0016.
