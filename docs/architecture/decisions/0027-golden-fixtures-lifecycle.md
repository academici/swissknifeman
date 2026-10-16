# ADR 0027: Golden fixtures: location, normalisation, lifecycle outside CI

## Status

Accepted

## Context

Behaviour has to be pinned before code moves, and the fixtures must survive merges from the main branch.

## Decision

`tests/golden/` in the hub root and `scripts/golden.py` (`capture`, `check`, `list`): CLI cases with normalised paths,
hashes and timestamps run in a sandbox, and generation is pinned by sha256 of generator outputs plus their own
`--check`. It is not a CI step but migration scaffolding. At the start of a stage, after merging the main branch, run
`check`; if main changed outputs, run `capture --reason` in a separate commit; a stage that moves code must pass
`check`; an intended behaviour change uses `capture --reason` in the same change. Their fate after the merge is
decided at the cutover.

## Alternatives considered

- A CI step on the main branch: rejected, the fixtures are temporary and would block ordinary changes.

## Consequences

- Behaviour preservation is checked byte-for-byte during the migration.
- Each recapture records the reason and the commit it came from.

## Supersedes

None.
