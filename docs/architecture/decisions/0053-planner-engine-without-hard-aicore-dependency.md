# ADR 0053: The planner engine runs without aicore; aicore is reached through `planner.integration`

## Status

Accepted

## Context

`plan.py` also runs from the Claude Code plugin cache, where no sibling `aicore` exists, and the engine was pure
standard library. The foundation ([ADR 0004](0004-aicore-foundation-and-generalisation-boundary.md)) offers layered
configuration, events, overlays, external plugins and the model catalog
([ADR 0031](0031-model-catalog-in-aicore.md)). A hard dependency would break installs from the cache.

## Decision

- **Stdlib core.** `lib/planner/plan/` imports no aicore and runs on Python 3.9. Every call to aicore goes through
  the package `planner.integration` (`config`, `events`, `overlays`, `plugins`, `models`); the projection renderer is
  the only other place that imports aicore.
- **Locator.** aicore is found by one Python locator in this order: `AICORE_ROOT`, `<planner>/_vendor/aicore`,
  `<planner>/../aicore`. `scripts/test-aicore-locator.py` keeps it in step with the shell locator.
- **Quiet degradation.** Without aicore the configuration is the schema defaults plus the `plan.settings` layer, no
  events are emitted, overlay blocks are empty and external checks are skipped. `plan.py config show` prints
  `aicore: unavailable`; nothing fails.
- **Own validator.** The plan validator stays in the engine because the engine must work without aicore; a parity test
  compares its verdicts with `aicore.util.schema` on the `plan/v1` fixtures.
- **Model catalog snapshot.** The class and effort selectors in `configs/command-routing.json` are a snapshot of the
  aicore catalog, written by the projection renderer and verified by `--check`. `start` reads the snapshot, so it
  needs no aicore; the former parity test became a generation check.
- Projection rendering needs aicore and no longer imports the old `core` package.

## Alternatives considered

- A hard dependency on aicore (exit with an error when absent): rejected, it breaks installs from the plugin cache.
- Vendoring aicore into planner: rejected, how aicore is delivered after the split is a separate decision.

## Consequences

- Users of the cache have no events and no configuration layers until the registry of installed modules exists.
- The validator and the catalog snapshot are two copies kept honest by tests, not by import.

## Supersedes

None. Refines the validator and catalog decisions of [ADR 0030](0030-shared-contracts-digest-error-capability-catalog.md)
and [ADR 0031](0031-model-catalog-in-aicore.md): planner keeps its validator and a generated catalog snapshot.
