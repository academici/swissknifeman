# Session continuity and adaptive review — design synthesis

Sources: owner refinements in `brief/01-refinements.md`; external verification in
`findings/19-session-continuity-and-adaptive-review-2026-08-08.md`; existing return-loop design in
`research/06-p4-loop-limiter-design.md`; repository session provenance in P6.2/D91.

## 1. Problem statement

The current protocol conflates three different operations: refreshing reviewer context, routing a
review to a stronger model, and abandoning the executor session. On an escalation this can cause two
cold starts: one for audit/research and one for the item retry. Each cold start re-resolves the same
plan state and delays feedback even when the defect is a small deterministic local miss.

## 2. Target execution ladder

| Observed condition | Action | Context/model | Durable result |
|:--|:--|:--|:--|
| First occurrence of a deterministic, reproducible failure inside the item's declared Scope/Files; no protected/frozen/public-contract, security, destructive, irreversible, cross-package, rule-conflict, unclear-architecture or unclear-acceptance trigger | `local-fix` | same root executor session and its legal route | validation evidence + fingerprint occurrence |
| Second occurrence of the same durable fingerprint, ambiguous root cause, independence-sensitive verdict, or any risk trigger above | `isolated-review` | fresh bounded reviewer context; model/effort selected independently; root waits and then resumes | schema-valid verdict + evidence ids + reviewer actor/route |
| Third occurrence of the same fingerprint (`same_return_max = 2` exhausted), authority/frozen-contract change, or unresolved owner decision | `owner-gate` | park only the subject; resume the same logical run when possible | DecisionRequest/response + continuation token/state |
| Measured root-context exhaustion, runtime/provider cannot perform nested/resumable execution, or whole-plan independent audit | `cold-start-root` | new root session | cold-start handoff + exact scope payload |

`RAG:—` for the numeric ladder: it reuses this plan's fingerprint and cap contracts. `RAG:✅` for
the manager/specialist topology and selective use of subagents: `findings/19-…` R23–R24.

## 3. Scoped-review capsule

The reviewer remains the existing `auditor` reader; no fifth reader is added. Two profiles are
distinguished:

- `scoped-review`: exact plan/item identity, applicable rules and decisions, declared bundle,
  committed diff/commit ids, raw validation evidence, current fingerprint slice and prior attempted
  resolutions. It excludes the executor transcript, chain-of-thought, self-evaluation, unrelated
  item history, and plan-wide history unless explicitly linked.
- `full-audit`: the existing auditor path for phase/plan conformance, including primary history.

The reviewer returns a compact schema-valid finding/verdict. It never becomes the owner of the root
run and cannot silently broaden scope. Actor independence and model route are recorded separately.

## 4. Allocation to plan items

| Owner item | Obligation added |
|:--|:--|
| `2026.08.07-PLAN-ECONOMY P1.5` | freeze two auditor profiles without adding a reader; preserve executor path and root continuity semantics |
| `2026.08.07-PLAN-ECONOMY P4.3` | freeze the `local-fix → isolated-review → owner-gate` ladder against the durable fingerprint/cap |
| `2026.08.07-PLAN-ECONOMY P4.4` | implement deterministic triage and prove no audit is emitted for a first local failure |
| `2026.08.07-PLAN-ECONOMY P4.5–P4.6` | freeze/implement the scoped capsule, actor independence, one-verdict rule, and return-to-root behavior |
| `2026.08.07-PLAN-ECONOMY P5.1` | freeze provider-neutral continuation identity in DecisionRequest before P5.4 implements it |
| `2026.08.07-PLAN-ECONOMY P5.4` | persist subject pause and continuation identity so an owner response resumes the same logical run |
| `2026.08.07-PLAN-ECONOMY P6.1–P6.3` | project the ladder into commands, session provenance, and isolated model-judgement interface |
| `2026.08.07-PLAN-ECONOMY P6.5` | replace automatic plan-step cold-start doctrine with the three-axis context policy |
| `2026.08.07-PLAN-ECONOMY P6.7–P6.8` | predeclare and execute canaries that count root restarts and repeated reads for all four ladder branches |

## 5. Acceptance invariants

1. A first eligible local failure produces zero reviewer calls and zero root-session changes.
2. A repeated identical fingerprint produces exactly one isolated reviewer record and zero root
   restarts; execution resumes the prior root run.
3. A stronger reviewer route does not imply a root route change.
4. An isolated reviewer receives only the scoped capsule and returns only the declared schema.
5. A hard boundary creates one cold-start handoff with an exact reason; it is never inferred merely
   from the words `blocked`, `escalated`, `audit`, or `research`.
6. The owner gate remains fail-closed and cannot be bypassed by a local fix or reviewer verdict.

## 6. Rejected alternatives

- Always audit the first failure: pays isolation and re-read overhead before evidence of ambiguity.
- Never isolate: loses independent review and stronger routing on high-risk or repeated failures.
- Transfer root ownership to the reviewer: creates the second cold start when execution resumes.
- Let the reviewer verdict lower counters or gates: violates the already-designed monotonicity
  invariant of P4.5.
