# P0.1 baseline selection policy

## Selection order

These rules were written before candidate rows were adjudicated. A source is eligible only when
it is a committed plan journal, a committed minimized acceptance report, or a sanitized
machine-local run report whose aggregate fields can be inspected without copying prompts,
transcripts, secrets, chain-of-thought, or environment data.

For every candidate, apply the gates in this order:

1. identify exactly one lane: `manual`, `workflow`, or `harness-run`;
2. require a stable `source_anchor` and classify the evidence as `committed`, `machine_local`, or
   `synthetic`;
3. require repository/source, plan or run, provider/model class, effort, scope, and validation
   comparability keys; a missing key is recorded in `unknown_reason`, never imputed;
4. require an explicit acceptance outcome and acceptance-contract hash; unmatched scope, route,
   or validation is `ineligible` rather than pooled;
5. classify the row as `measured`, `synthetic`, `baseline_pending`, or `ineligible`;
6. numeric token, cost, turn, duration, retry, and owner-intervention values may be copied only
   from structured provider/run evidence. Missing measurements remain `null` with a non-empty
   `unknown_reason`; `null` is never treated as zero.

## Matched-work eligibility

A future Artifex result is matched to an incumbent row only when all of these values are equal:

- repository/source anchor and plan or fixture identity;
- provider plus model class and effort;
- normalized slice scope hash;
- validation/acceptance hash;
- accepted terminal outcome.

The normalized comparison unit is one accepted non-synthetic slice. Synthetic fixture evidence
can test mechanics and schema but cannot satisfy the five battle-wave floor or an economic GO.
Committed journals without structured token/cost fields remain useful for reliability and owner-
intervention history, but are `baseline_pending` for economy.

## Lane semantics

- `manual` means an owner/coordinator launches and interprets individual plan items. A
  `plan-run` journal row is manual unless a non-null driver `run_id` proves otherwise.
- `workflow` means a named Workflow run. A sequence of `resumeFromRunId` calls is one iterative
  run, not multiple independent matched baselines; historical free-prose telemetry without a
  sanitized structured source is not promoted to a numeric baseline.
- `harness-run` means the committed exec-wave driver. It is both an incumbent baseline and a
  reuse donor, never relabelled as Workflow. Driver-written journal lines are owner interventions;
  worker self-close lines are not.

## Adjudication

Candidate adjudication is recorded in `baseline-catalog.json`; the evidence inventory and reuse
verdict are recorded in `findings/P0-baseline-observations-2026-08-03.md` after applying the rules
above.
