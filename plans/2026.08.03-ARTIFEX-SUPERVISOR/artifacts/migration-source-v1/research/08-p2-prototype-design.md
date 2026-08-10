# P2 plan-local prototype design

## Sources and execution gate

This synthesis uses `findings/06-p2-runtime-recon-2026-08-03.md`, `research/01`–`05`,
`research/07-p1-contract-freeze-design.md`, and the planned P1 contracts/case banks named in
`plan.md` §7. P1 is not executed: P2 implementation is forbidden until P0 and P1 are terminal,
all five P1 validators are green, and `validate-contract-set.py` verifies the pinned contract
manifest. Missing future files are preconditions, not evidence. RAG:— (repo-grounded plan state).

## Candidate layout and ownership

The prototype stays below `artifacts/supervisor/` and is imported only with an explicit
plan-local `PYTHONPATH`. It does not create a package CLI or edit `packages/**`/`core/**`.

| Item | Owns | Reuses | Produces for |
|:--|:--|:--|:--|
| P2.1 | `artifex.compiler`: pinned plan/phase read, Task Contract cross-check, immutable slice compilation | `harness run --dry-run --json`, `task.task_contract build`, frozen `slice-manifest-v1` | P2.2–P2.5, P3 |
| P2.2 | `artifex.store`: run identity, strict hash-chain JSONL, lock, replay, derived snapshot | `supervisor-run-v1`; Python stdlib only | P2.3–P2.5, P4 |
| P2.3 | `artifex.authority`: total AUTO/AUTO-FIX/OWNER evaluator and attention records | frozen P0/P1 authority cases and policy | P2.4–P2.5, P4–P5 |
| P2.4 | `artifex.scheduler`: dependencies, budgets, activity boundary and circuit breakers | P2.1–P2.3 plus frozen worker/economy contracts | P2.5, P3–P5 |
| P2.5 | plan-local CLI/report and aggregate manifest/verifier | P2.1–P2.4 | P3 adapter integration and P4 fault work |

Each item owns one module and its tests. Shared fixture construction is frozen in P2.1 and later
items extend data, not its plan parser. The phase is a strict P2.1→P2.5 chain; no workflow or
parallel authoring carrier is legal. RAG:— (repo-grounded dependency graph and plan-protocol
orchestration criterion).

## Process boundaries and no-duplicate-SSOT rule

P2.1 never imports private Harness/Task parsers. It invokes the worktree-local Harness dry-run and
Task Contract compiler as JSON subprocesses, verifies both outputs agree on route/item identity,
then applies only the missing frozen `slice-manifest-v1` rules. `drivable` remains Harness's
Claude-wave decision and is not Artifex authority. Artifex may compile a `manual` item only when
the P1 contract and run mandate allow it; provider dispatch remains absent until P3.

The candidate never stores a second plan status. Run state is supervisor state; canonical item
status remains in plan-protocol. A slice manifest pins plan/item/contract/mandate/source hashes and
is immutable after dispatch. Replan may supersede only pending manifests and preserves both hashes.

## Durable activity boundary

`events.jsonl` is the only recovery authority. Every record has closed schema/version, sequence,
previous hash and recomputed record hash. Appends occur under one non-blocking POSIX `flock`, then
flush→fsync→close→reopen/tail verification. A malformed/truncated/reordered/unknown record refuses
the whole replay; no tolerant reader or repair-by-snapshot path exists.

`snapshot.json` and `owner-queue.json` are derived caches. Publication is complete temp write,
flush/fsync, `os.replace`, then an explicitly observed parent-directory-fsync attempt. Unsupported
directory durability is recorded as a capability limitation; it cannot make the journal green or
be described as physical power-loss proof. Locking, atomic publication and durability remain three
separate claims. RAG:✅ Python 3.12 API boundaries in
`findings/06-p2-runtime-recon-2026-08-03.md`.

## Scheduler and provider boundary

P2's scheduler accepts only typed requests/observations conforming to `worker-envelope-v1`.
Production provider launch is structurally unavailable: the default activity port returns the
closed `provider_unavailable`/capability refusal before a dispatch intent. Tests may inject a
deterministic fake activity, but candidate code contains no Codex/Claude argv or parser.

The scheduler selects dependency-ready slices, writes durable intent before invoking an activity,
records the bounded observation, then runs schema/scope/authority/validation predicates before an
acceptance event. One write lane is always enforced. A ready set may expose at most two concurrent
read-only/worktree-isolated slices for P3/P4 adapters, but P2 does not execute them concurrently.
Budget exhaustion, repeated finding identity, unknown state, source drift and failed rollback stop
the lane and create OWNER/incident evidence rather than a retry loop.

## CLI contract

The plan-local command is:

```text
PYTHONPATH=plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/supervisor \
python3 -m artifex --repo-root . --plan-dir plans/<ID> --runs-root plans/<ID>/runs <command>
```

Closed commands are `start`, `status`, `resume`, `reconcile`, `stop`, and `report`. Mutating
commands require explicit run/phase/mandate inputs as applicable and take the writer lock;
read-only commands stream-verify before reporting. Every command emits one bounded JSON envelope
and stable exit/reason code. Paths are resolved below explicit roots; symlink/path escape, foreign
run identity and ambient-default mutation refuse before write. `start` in P2 can compile and create
a ready run but cannot dispatch a real provider.

## Alternatives rejected

1. Importing `harness.run.plan_reader` would bind the candidate to a private Python seam; its
   documented worktree-local dry-run JSON is the narrower experiment boundary.
2. Parsing plan Markdown again would create a third carrier beside plan-lint/Task Contract.
3. Reusing tolerant `core.io.read_ndjson_iter` could skip the exact corruption recovery must catch.
4. SQLite/Temporal or a new dependency would violate the prototype/dependency gate and obscure the
   measured value of the control loop.
5. Adding provider argv in P2 would mix durable-core proof with P3's empirical provider boundary.
6. A phase workflow would either violate the strict dependency chain or create the second scheduler
   the experiment is meant to evaluate.

RAG:— (repo-grounded alternatives against current owners and frozen plan decisions).

## Ecosystem-core pre-mortem

| Failure after 6–12 months | Early signal | Mitigation | Owner |
|:--|:--|:--|:--|
| Plan parser and canonical Task reader drift | same item has different route/hash in two outputs | subprocess cross-check; any mismatch refuses compilation | P2.1 |
| Corrupt tail silently disappears | replay count changes without a named invalid record | strict streaming parser and mutation tests; snapshot never repairs | P2.2 |
| Lock is mistaken for durability | concurrent test passes while crash cut loses tail | separate lock/append/replace capability evidence and P4 crash matrix | P2.2/P4.1 |
| AUTO evaluator becomes allow-all or block-all | P1 positive/negative cases no longer partition results | run frozen independent case bank plus mutation counterexamples | P2.3 |
| Retry widens scope or weakens acceptance | attempt hash differs or finding identity resets | immutable hashes, stable identity, bounded budget and OWNER on mismatch | P2.3/P2.4 |
| P2 accidentally launches a live provider | provider argv/parser appears before P3 or a test needs credentials | no-provider default port; source scanner and explicit refusal smoke test | P2.4/P2.5 |
| CLI mutates foreign paths | resolved target escapes explicit repo/runs root or crosses symlink | containment/lstat checks before every mutation and temp-repo tests | P2.5 |
| Aggregate tests certify their own expected values | evaluator derives expected outcomes from implementation | frozen P1 cases remain independent; aggregate manifest recomputes hashes | P2.3/P2.5 |

## Stop condition

P2 design is ready when all five items name exact modules/tests, terminal P1 gates, finite reads,
independent validation and manual implementation/high routes; the P3 contract can consume the
terminal candidate without provider semantics leaking backward. P2 execution is ready only after
P1.5's aggregate contract set is terminal and green.

## Проверка (verification status)

- RAG: Python 3.12 exact API class checked through official docs via Perplexity Web ×1 after a
  Context7 version miss; same-day provider/durable sources from `findings/01` remain the source for
  already-frozen architecture. Local Harness/Task/Core boundaries were read directly.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: filesystem-specific power-loss durability remains P4 empirical
  evidence; exact provider dispatch remains P0.3/P3, deliberately outside P2.
- Обходки/[POSSIBLE-DEFECT]: none; `stale-source` Codex hook projections remain a named environment
  defect and no P2 item repairs them.
