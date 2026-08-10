# Audit 8 owner/generator reconciliation — 2026-08-04

## Inputs and boundary

- Audit input: `plan.md` → last `## Audit design — 2026-08-04`, pass 8, F1–F4.
- Owner input: `brief/16-audit8-owner-carriers-and-execution.md`.
- Repository input: worktree-local Harness CLI and
  `packages/harness/lib/harness/instructions.py`; no package/root/generated write was run.

RAG:— (repo-grounded: named files and read-only CLI observations on 2026-08-04).

## Exact Harness write contract

The bare command `packages/harness/bin/harness instructions` prints help and exits without
planning or applying projections. The public write contract is:

1. `instructions plan` computes ordered target actions without mutation;
2. `instructions apply --authorize <ordered writable target paths>` refuses unless the supplied
   paths equal the computed non-NOOP create/update actions in exact `target_path` order;
3. `apply_plan` writes those targets and then writes
   `.swissknifeman/provider-artifacts.lock.json` as the plan's `next_lock`;
4. `instructions check` re-derives the projections and must report clean targets and lock
   provenance.

Therefore the lock is an owner-scoped mutation but is not an `--authorize` target. Once the
Artifex scope exists, its exact two-target authorization order is
`packages/artifex/AGENTS.md,packages/artifex/CLAUDE.md`. The existing root scope's exact order is
`AGENTS.md,CLAUDE.md`. RAG:— (repo-grounded:
`packages/harness/lib/harness/instructions.py::apply_instructions`,
`core/provider/lock.py::ArtifactPlan` and `apply_plan`).

## Authority reconciliation

D86 covers `packages/artifex/**` and D87 covers the finite root router/generated outputs, but
neither grants mutation of their Harness-owned source/test inventory or the shared lock. The owner
has now supplied two separate finite grants before their consumers:

- `G-OWNER-P3.8-HARNESS-INSTRUCTIONS` for the exact P3.8 Harness Artifex source/test/lock set;
- `G-OWNER-P6.2-HARNESS-ROOT-INSTRUCTIONS` for the exact P6.2 Harness root
  source/test/lock set.

The shared catalog, fixtures, tests and lock intentionally occur in both grants because P3.8 and
P6.2 produce different generations at different times. The grant does not merge those generations
or permit one item to consume the other's future authority. RAG:— (owner/repo-grounded:
`brief/16-audit8-owner-carriers-and-execution.md`; D86/D87; generation chain D89).

## Durable package-cwd continuation

P3.8 crosses an instruction-owner boundary and a package-owner boundary. The safe continuation is
not an ambient `cd`: stage 1 commits only its exact Harness sources, generated package guides and
shared lock after `check` is green; then a full Codex launch starts at `packages/artifex` with the
item's implementation/high route, never approval, danger-full-access, and a prompt that re-reads
the plan, P3.8, both generated guides and the stage-1 commit before package-runtime writes. The
restart is a continuation of P3.8, not a second item or permission to repeat stage 1.
RAG:— (repo-grounded: root Codex launch/package-scope canons and P3.8 two-owner boundary).

## P3.7 validation ownership

`probe-adapters.py` writes provider smoke JSON beneath its `--output-dir`. P3.7 owns only the Task
test, so rerunning the P3.6 command against the committed P3.6 output directory would mutate a
foreign item scope. P3.7 can preserve the intended fan-in by:

- requiring the committed P3.6 carrier paths clean before and after validation;
- running any fresh real probe only under a `mktemp -d` output directory and deleting it;
- running `validate-adapters.py` and parity validation read-only against the committed P3.6
  outputs.

No P3.6 historical field or output ownership changes. RAG:— (repo-grounded:
`phases/P3.md` P3.6/P3.7 and `artifacts/P3/probe-adapters.py`).

## Verdict

F1–F4 have a non-conflicting design repair: two owner carriers, one executable generator/restart
contract and one temp-isolated/read-only validation contract. No item, generated target, hook or
terminal history needs mutation in the design session.
