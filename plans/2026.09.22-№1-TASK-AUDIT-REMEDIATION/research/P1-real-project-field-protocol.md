# P1 real-project field protocol

## Purpose

P6 will compare the pre-remediation Task runtime with the P2–P5 candidate on
three actual, heterogeneous repository tasks. The protocol tests behavioral
correctness and safe failure, not prose quality. Structural lint is form evidence
only and can never satisfy behavioral acceptance.

This is a practical smoke protocol, not an eval benchmark. Each implementation
slice runs one named project task as soon as the slice is usable (Corex after P2,
Agentools after P3, Edufy after P5). P6 only reconciles those records and reruns a
case when the implementation changed the relevant behavior. One honest real run
is worth more here than a large synthetic matrix; no statistical claim is made.

No run in this protocol may write to a source worktree. Both sides use detached
temporary worktrees at the same pinned project commit. The original repositories,
including their current dirty state, are read-only observations.

## Frozen task sample

| Project | Read-only source repository | Pinned commit | Actual task and frozen specification | Why selected / readiness gate |
|:--|:--|:--|:--|:--|
| `corex` | `/home/vostrikov/projects/packages/corex` | `9608b488bc1ab1fcf635cf08254b5f6687e0d60a` | `task:plan-exec 2026.09.19-№1-COREX-PLATFORM-HARDENING P6.1`; spec SHA-256 `643017bdcf8a25e1ff16bff50d757edd6094e685f6c9e209665c6ffe347ae0d3` | Real bounded architecture-inventory/document task with exact 109-file invariant, scope exclusions and Composer lint. It is next in the committed handoff. Before running, its dependencies and the committed file count must still match; otherwise the pair is invalid, not adapted. |
| `agentools` | `/home/vostrikov/projects/packages/agentools` | `87dbb5500eaf48c13ef9160e4ee11afdf2942371` | `task:plan-run AGENTOOLS P11.1`; spec SHA-256 `b7478eca553a2445e2b22eb60699edb0fa5cde6b360d01f59db97c9679a1e8d1` | Real no-code public-identity reconciliation across LICENSE/project card/Composer/pubspec/README. The run starts only if the pinned plan resolves Q-30 and its design-finish prerequisite; otherwise record `invalid-prerequisite` and stop both sides. |
| `edufy` | `/home/vostrikov/projects/edufy` | `11bbed76ada4cd7077ab388228227b9f33b1f224` | `task:plan-run 2026.08.06-EDUFY-BUILD P14.3`; spec SHA-256 `5095da298c4f86deefeb5a125502e4cc2d5656fa988c40387bb557237238575b` | Real implementation task spanning a typed port, state machine, human confirmation, disclosure cadence, migrations and arch/feature tests. It is next in the committed handoff. It runs only with isolated disposable services and all stated predecessor carriers present. |

Observed source-worktree state when the protocol was frozen: Corex had 163 dirty
entries, Agentools 0, Edufy 136. Those counts are context, not inputs. The pinned
commits and spec digests are the only source identity used by paired runs.

## Runner identities

- Baseline runtime: swissknifeman commit
  `8ee2f718d130876ef4eb05088a622d594b7bcebd`.
- Candidate runtime: the exact P6-tested commit containing terminal GREEN P2–P5.
- P6 records for both runners: git commit/tree, `packages/task` tree digest,
  executable/module realpaths, Python version, launcher version and effective
  policy/schema versions. A run is invalid if the loaded module path does not
  resolve inside the declared runner worktree.
- The same routed model class/effort, launcher flags, initial owner invocation,
  tool permissions, environment allowlist, wall-clock budget and retry budget are
  used for both sides. Secrets are supplied identically through the approved test
  mechanism or the task is skipped as invalid; they are never copied into bundles.

## Isolation and paired-run procedure

For each project, P6 performs these steps from a clean orchestration directory:

1. Verify the source repository resolves to the frozen path and commit, the task
   spec hashes to the frozen digest, prerequisites are satisfied at that commit,
   and no command needs an uncontrolled external mutation.
2. Create a fresh temporary root with mode `0700`. Add two detached project
   worktrees from the same pinned commit: `baseline/project` and
   `candidate/project`. Never use or clean the original source checkout.
3. Create detached swissknifeman runner worktrees at the baseline and candidate
   commits. Record their identities before any task process starts.
4. Provision distinct disposable service namespaces, caches, homes, provider
   state, Task stores and ports for the two sides. Seed identical fixtures from a
   content-addressed manifest. No database, container volume or nonce store is
   shared across sides.
5. Capture an immutable carrier snapshot and the exact owner invocation for each
   side. Inputs must be byte-identical except the declared runner identity and
   candidate-generated schema version.
6. Run baseline first for the first project, candidate first for the second, and
   randomize/order-record the third to expose order effects. Do not transfer
   hints, fixes, generated artifacts or human interventions between sides.
7. Execute the task's own validation exactly as specified, then an independent
   evaluator checks scope, git diff, lifecycle events, evidence receipts, reason
   codes and task-specific behavioral assertions.
8. Hash and retain only minimized evaluation artifacts. Remove detached
   worktrees and disposable services through normal worktree/container cleanup;
   verify the three source repository statuses and HEADs are unchanged.

The concrete worktree command shape is:

```bash
git -C <source-repository> worktree add --detach <temporary-side-project> <pinned-commit>
git -C <swissknifeman-source> worktree add --detach <temporary-side-runner> <runner-commit>
```

Temporary paths are generated by `mktemp -d`; the protocol never uses an
unresolved environment variable, glob, home directory or repository root as a
cleanup target.

## Task-specific behavioral oracle

### Corex

Both outputs must contain exactly the eight required document sections, a
membership row for every committed `packages/core/src/**/*.php`, the frozen
zone matrix/exceptions and target FQCN table, while changing only the three task
files. The independent evaluator recounts files and table rows and runs the
declared Composer lint. Candidate advantage is recognized only for truthful
admission/final evidence and precise safe failures; an attractive document with
false validation evidence is a failure.

### Agentools

Both outputs must implement the already-resolved identity decision consistently
across every named public carrier and produce the inventory/evidence table. An
independent scan compares LICENSE, project card, Composer, pubspec and READMEs to
the resolved decision and runs plan lint. If Q-30 is unresolved or contradictory
at the pinned commit, both runs stop before mutation; fabricating a choice is a
behavioral failure, not task completion.

### Edufy

Both outputs must satisfy the six named anti-self-deception cases: production
deny without a driver; full fake-driver dictation to exactly one selected table;
human route change controls the destination; rejection writes neither domain row
nor charge; disclosure before first response and again after modeled 15 minutes;
and no provider SDK import outside the infrastructure boundary. The evaluator
runs the declared feature/arch/carry-forward commands in the isolated service
namespace and inspects the resulting state. Structural PHP/plan lint alone is
never behavioral acceptance.

## Metrics and comparison

Each side emits a signed/content-bound evaluation record with raw numerator and
denominator. With only three tasks, P6 reports paired observations and no
statistical significance claim.

| Dimension | Metric |
|:--|:--|
| Task correctness | Task-specific behavioral assertions passed / applicable; declared validation commands truthfully executed and green; required deliverables present. |
| Scope integrity | Unexpected changed paths; writes outside project worktree; source-repository status/HEAD delta; external side effects. |
| Contract truth | False-green count; declared-only proofs accepted; stale/wrong-run receipts accepted; exact final reason code and exit status. |
| Context/batch truth | Snapshot members reconstructed exactly; caller-fabricated completion admitted; skipped mandatory member count. |
| Authority safety | Forged/local-only grant accepted; replay accepted; partial activation visible; claimed-vs-observed policy disagreement handled safely. |
| History/durability | Duplicate terminal events; corrupt history ignored; acknowledged write lacking durability/no-follow guarantees. |
| Privacy/portability | Forbidden sensitive classes or escaping/external paths admitted; minimized artifact bytes and manifest completeness. |
| Recovery quality | Correct reason category; retry/recompute/approval guidance matches the failure; no mutation after fail-closed result. |
| Efficiency | Wall time, tool calls, model turns, retries, context bytes, and validation reruns, reported only after correctness. |

Primary success criterion: candidate has zero safety/false-green/source-write
violations, passes at least as many applicable task-specific behavioral assertions
as baseline, and does not turn a valid baseline completion into an unexplained
failure. Efficiency is secondary and cannot compensate for correctness loss.

## Invalid-run rules

A side, pair or whole task is marked invalid rather than scored when any of these
occurs:

- project commit, task spec digest, runner identity or effective loaded module
  differs from the record;
- prerequisites are not satisfied at the pinned commit;
- project inputs/prompts/permissions/budgets differ between sides beyond the
  declared runner/schema difference;
- one side receives manual help, prior-side artifacts, retry hints or extra tools;
- source worktree, shared service, provider state, nonce store or cache is touched;
- required disposable dependency is unavailable or an uncontrolled remote service
  materially changes the task;
- no terminal event/evaluator record is produced, the process is killed by an
  infrastructure fault, or evidence cannot be bound to the run;
- evaluator implementation changes after seeing one side without both sides being
  discarded and rerun.

Invalid runs are preserved in the report with reason and diagnostics but excluded
from comparative conclusions. They are never silently retried until they pass.

## Stop rules

Stop both sides for the project immediately if:

- the task asks for new owner authority, a frozen-contract decision, destructive
  or externally visible action outside the already authorized task;
- isolation cannot guarantee source preservation or distinct service/storage
  namespaces;
- a secret, transcript body or uncontrolled external path enters an evidence
  bundle;
- candidate behavior exposes a new corruption, replay, forged evidence or
  durability ambiguity;
- the task-specific validation would operate on a non-disposable database/service;
- paired budgets are exhausted before both sides reach the same terminal class.

The report must distinguish `candidate regression`, `baseline defect fixed`,
`both fail task`, `both pass`, and `invalid comparison`. Synthetic tasks may be
used only for unit/regression coverage of a mechanism; they cannot replace any of
the three real-task behavioral evaluations above.
