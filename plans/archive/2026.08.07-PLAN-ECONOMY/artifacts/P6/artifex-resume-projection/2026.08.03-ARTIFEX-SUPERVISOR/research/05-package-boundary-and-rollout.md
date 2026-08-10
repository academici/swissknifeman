# Package boundary and rollout

## Current decision

Do not create `packages/artifex/` during the experiment. The repository canon names five independent
capability packages, the root router has a closed public group set, and speculative work belongs in
roadmap. A plan-local prototype can prove the operational contract without prematurely changing any
of those public surfaces.

## Prototype ownership

- Implementation: `plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/supervisor/`.
- Run data: plan-local `runs/`, excluded/redacted according to P1 privacy contract; only minimized
  fixtures/evidence are committed.
- Existing live packages are read/used through public APIs or subprocesses; no package file changes
  until P6.1 selects an approved home.

## P6.1 decision matrix

| Outcome | Consequence |
|:--|:--|
| P5 NO-GO | Preserve findings/evidence, move remaining concept back to roadmap, no live package or CLI. |
| GO, only plan lifecycle mechanics | Prefer extending `task` plugin internals/commands; no standalone `task` CLI and no root `task` group. |
| GO, provider environment/launch mechanics dominate | Extend Harness behind its package CLI, preserving provider adapters and root thin routing. |
| GO, genuinely independent public capability | Propose `packages/artifex/` and exact root CLI change as an explicit Owner/canon decision before implementation. |

Shared primitives belong in `core/` only after two live consumers are demonstrated. Analyst consumes
traces/reports but does not own scheduling. mAInd receives summaries but does not own transactional state.

## Rollout shape after GO

1. Freeze chosen ownership and public compatibility contracts.
2. Move/rewrite plan-local code into the approved home with no duplicate implementation.
3. Regenerate provider projections through their owners; preserve additive parity.
4. Introduce opt-in, bounded pilot profile; never always-on context without measured budget verdict.
5. Keep kill switch, old manual plan execution and run-data downgrade/rollback procedure.
6. Run package, aggregate docs, registry, release and independent security/recovery audits.

## Explicitly deferred product surfaces

Messenger remote approval, desktop UI, remote hosts, fleet scheduling and unbounded nested agents are
not v1 prerequisites. A local CLI plus deterministic report is sufficient to prove the system.

RAG:— (repository architecture/speculative-work/provider-parity canons; productization fork is staged, not unresolved).
