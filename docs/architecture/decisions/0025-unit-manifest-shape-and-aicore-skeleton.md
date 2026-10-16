# ADR 0025: Shape of unit.json and the aicore skeleton

## Status

Accepted

## Context

The manifest must be introduced before `aicore` has code and before `task` is renamed, and the closed schema profile of the
hub validator cannot express maps with arbitrary keys.

## Decision

`packages/aicore` starts with only `unit.json` and `schemas/{unit,check-result}/v1`. The manifest is marked
`"$schema": "urn:swissknifeman:aicore:unit:v1"`, and sets such as `requires` are arrays of objects (`unit`,
`range`), not maps. The id equals the folder and the import package; `task` keeps id `task` until the rename;
`artifex` is `retired` in `configs/ecosystem-units.json` and has no manifest. `version` is not edited by hand in
two places: the check requires equality with the existing carrier (`package.json`, `plugin.json` or `__version__`)
listed in `configs/ecosystem-units.json`. `unit.json` becomes the source when the plugin is generated from it. The
validator is the closed profile of `orch.schema`, called from the hub script until `aicore` has its own.

## Alternatives considered

- Put the manifest schema in `scripts/` or `configs/` of the hub: rejected, it belongs to the foundation.

## Consequences

- Modules pass manifest checks today without moving code.
- The field list is documented in `contracts.md` and the schema.

## Supersedes

None.
