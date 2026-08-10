# `harness run` reuse and gap crosswalk

## Evidence boundary

This verdict is pinned to the committed live-driver reference and implementations read
by P1.1. The reference SHA-256 is
`9ff7eab9a5858581afe2b3ea149474ff3e9b25d1a894537975fb9f9b322d2b3f`;
`harness.run.journal` is
`522c299b480d75c5b4ae5438c0d50d9fe9ce3f828d9ebf57b375f166ef2f024f`;
the Task journal owner is
`82fee8b079d67863466efdb4e9b18c75deeecdfd7b0bdaa5456d8a280e940b8b`.
The live driver is a real incumbent and reuse donor, but it is not relabelled as a
durable supervisor.

## Ownership verdict

| Surface | Current live owner/behaviour | P1.1 verdict | Supervisor gap and later owner |
|:--|:--|:--|:--|
| phase queue and route gating | `harness.run.plan_reader`; explicit `Exec=plan-exec`, sequential queue | **reference/reuse**, do not copy statuses or route rules | P1.2 compiles immutable slices from Task Contract and preserves manual/provider-neutral routes |
| fresh worker lifecycle | `harness.run.worker`; one Claude process, timeout, bounded JSON result | **reuse pattern**, not implementation | P3 owns additive Codex/Claude adapters and durable process/session evidence |
| deterministic result gate | `harness.run.gate`; worker outcome + plan lint + Git topology + item fields | **reuse acceptance pattern**, not its exact table | P4 binds independent validation to frozen postimage and supervisor journal evidence |
| per-plan journal backstop | `harness.run.journal`; process-calls `task.journal`, driver writes only when worker cannot close | **reuse exactly at plan-history projection** | run WAL stays separate; accepted/recovered projection must not duplicate the worker row |
| wave summary | journal-derived GREEN/ATTENTION/RED, interventions, cost/duration when observed | **baseline/evidence donor** | P1.5/P4.5 own complete attempt denominators and unknown preservation |
| sequential one-writer default | driver launches one worker at a time | **preserve** | P1.2/P4.3 may allow isolated parallel work only with proved ownership and serialized integration |
| retry and resume | no retry; next manual invocation starts again from plan state | **gap** | P1.1 owns stable attempts, idempotency, verified replay and exact reconciliation |
| durable run folder | absent | **gap** | P1.1 owns immutable `run.json`, hash-chained `events.jsonl`, derived snapshot and lock |
| public-boundary WAL | no intent/observation fsync protocol around provider/Git/filesystem/bookkeeping | **gap** | P1.1 owns intent-before-effect and observation-before-acceptance ordering |
| chain/torn-write verification | per-plan journal is append-only but not a supervisor hash chain | **gap** | P1.1 rejects truncation, reorder, unknown schema/key and hash/sequence damage |
| postimage reconciliation | no exact pre/post/partial/third-state classifier | **gap** | P1.1/P4.2 prove no-rerun recovery and incident on unknown state |
| source/input drift | gate observes plan/Git outcome but no immutable per-attempt source bundle | **gap** | P1.2 freezes inputs; P1.1 refuses in-flight drift |
| orphan ownership | timeout result exists; durable child identity and restart reconciliation do not | **gap** | P1.1 defines fail-closed identity; P3.4 implements bounded process lifecycle |
| authority and budget decisions | remain in environment/plan command; driver makes no decisions | **preserve boundary** | P1.3/P1.5 own authority and budget; P1.1 records their outcomes only |
| provider parity | live wave drives Claude Code only | **gap without replacement** | P1.4/P3 define one neutral envelope plus additive provider adapters |

## Single-source rule

The prototype must not import `harness.run.journal` as its run WAL, copy Task journal
enums into `events.jsonl`, or infer recovery from plan status. It may process-call the
existing Task journal owner at the established terminal projection and may reuse the
live driver's sequential/fresh-process/gate patterns. Any proposal to move plan queue,
route, close, or per-plan history ownership into the supervisor is a contract conflict,
not a convenience refactor.

## Gap acceptance

This crosswalk is complete only while the independent P1.1 validator proves every row
above is present with one of `reference/reuse`, `reuse pattern`, `preserve`,
`preserve boundary`, or `gap`, and specifically proves the durability gaps
`exclusive_lock`, `hash_chain`, `intent_observation`, `atomic_snapshot`,
`exact_reconcile`, `source_drift`, `orphan_identity`, and `no_duplicate_projection`.
