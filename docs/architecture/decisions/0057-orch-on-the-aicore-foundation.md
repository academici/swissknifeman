# ADR 0057: `orch` runs on the `aicore` foundation

## Status

Accepted

## Context

`orch` carried its own copies of the schema validator, the canonical digest and the model routing, and it found the
planner through a bridge folder of its own. The foundation (`aicore`) now holds the validator, the digest, the model
catalog and the error classes, and every module is required to depend on it explicitly.

## Decision

- **Dependency.** `unit.json` of `orch` requires `aicore`. `orch` code imports only the standard library, `orch` and
  `aicore`; `tests/test_boundaries.py` enforces it and also rejects the names of partner modules in the core.
- **Locator.** `aicore` is found by `AICORE_ROOT`, then `_vendor/aicore`, then the sibling folder, in Python and in bash.
- **Validator and digest.** `orch.schema` is a thin wrapper over the closed-profile validator of `aicore`;
  `contracts.canonical_digest` is computed by `aicore.util.digest`. Both were switched after a shadow comparison of the
  verdicts and bytes on every `exec/v1` fixture.
- **Models.** Models and effort come from the `aicore` model catalog (`--model-catalog FILE`). `ORCH_ROUTING` and
  `orch.py prepare --routing` are removed.
- **Errors.** Failure classes are the `error/v1` classes of `aicore`, referenced by optional fields of `exec/v1`.
- **Standalone.** `python3 scripts/ecosystem-units.py standalone orch` passes without the rest of the hub.

## Alternatives considered

- Keeping private copies: rejected, two validators drift and the golden verdicts of `orch` would depend on both.
- An optional dependency: rejected, `orch` has no working scenario without the foundation.

## Consequences

- Documents that were valid stay valid; only the diagnostics text may differ where the foundation words it differently.
- A change of the foundation validator is a change of the verdicts of `orch`; the golden cases of `orch` cover it.

## Supersedes

None.
