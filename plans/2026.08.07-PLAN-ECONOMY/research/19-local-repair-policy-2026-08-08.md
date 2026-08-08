# Local repair before design — synthesis

Sources: owner refinement dated 2026-08-08; `findings/20-local-repair-boundary-2026-08-08.md`;
existing adaptive ladder in `research/17-session-continuity-adaptive-review-2026-08-08.md`.

## Decision

A failed validation or a contradictory declaration is an observation, not automatically a terminal
workflow state. The executor classifies it before emitting `🔴 Blocked`:

1. `repair-now` — first occurrence; root cause and minimal edit are deterministic; exact changed paths
   are named by the current item or are this plan's bookkeeping; validation is available in the same
   session; no hard boundary is crossed. Record the observation and repair in the journal, then
   rerun the affected validation without a cold start.
2. `isolated-review` — repeated fingerprint, ambiguous cause, or an independence-sensitive verdict.
   The root executor retains control and receives a bounded result.
3. `plan-design` or owner gate — a semantic choice, public or released contract, authority/security,
   irreversible/destructive action, cross-package/cross-repository effect, incompatible acceptance,
   or a repair that cannot be bounded and validated locally.

The existing D124 remains the default. Its blanket frozen-contract trigger is refined only for a
literal collision among unpublished, intra-plan contract copies when one already accepted decision
selects the value, no implementation has consumed the wrong value, all copies are synchronized in
one repair, and the normal validations remain green.

## P2.7 application

The `.closed.md` spelling is already selected by D34/D77 and all implementation-facing P2/P3/P6
specifications. `.closure.md` occurs only in the package projection and the plan-owned frozen
registry/read-path copies. The repair is therefore local, deterministic and reversible by Git; the
implementation of the closure generator remains P2.7 work and is not pre-approved beyond its existing
Scope Included.

## Non-goals

This is not a general authorization to edit frozen contracts in place. A new semantic path, a runtime
consumer already depending on a value, a versioned public contract, or a change outside the current
item remains a design/authority decision.

## Проверка (verification status)

- RAG: see `findings/20-local-repair-boundary-2026-08-08.md`.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: —.
- Обходки/[POSSIBLE-DEFECT]: —.
