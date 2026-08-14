# P7 design lint admission defect — 2026-08-13

## Reproduction

After the stable P7 carriers, generated views and first bundle were materialized, both the
worktree-local and marketplace-resolved commands returned the same result:

```text
python3 packages/task/scripts/plan-lint.py plans/2026.08.12-№1-TASK-RESILIENCE
→ 29 ERROR / 3 WARN
```

`--baseline HEAD --gate new` could not classify the delta because the plan exists only under
`plans/archive/` at HEAD while the working index moves it to the active path. The command
therefore failed closed and reported baseline unavailable. No product implementation or
historical carrier rewrite was performed in the design root. RAG:— (repo-grounded: observed
command output, current Git index).

After the spec-only downstream declaration was corrected and the P7.0 bundle regenerated, the
final design-root rerun reports `28 ERROR / 3 WARN`: all 28 errors are the two historical-policy
classes below, while the new P7 structure, handoff and runnable bundle add no diagnostic of their
own. This is the acceptance RED assigned to P7.0, not a skipped green check. RAG:—
(repo-grounded: final observed lint output).

## Error classes

1. 25 terminal journal events dated 2026-08-13 are rejected as
   `TERMINAL_EVIDENCE_REQUIRED`, although they predate the new writer/reducer policy and were
   valid terminal evidence of already closed P0–P6.
2. Latest Audit P3/P4/P5 blocks are ERROR and P0/P1/P2 are WARN because a date-only
   `AUDIT_TERMINAL_POLICY_CANON_DATE = 2026-08-13` treats same-day historical blocks as if they
   were authored under the new provider-neutral Semantic Next contract.
3. A downstream record error named producer P6.2/consumer P7.2 because the initial P7.2
   Required Reads declared target implementation/test paths historically produced by P6.2. The
   spec was corrected in design: target Files do not need to masquerade as predecessor Inputs.

## Classification

This is an in-scope bootstrap acceptance defect, not an authority or plan-history failure. The
correct repair is forward-compatible activation in the linter with tests proving both historical
readability and new-event fail-closed enforcement. Rewriting append-only journal, generated state
or closed audit prose is forbidden. The repair owns only current lint modules/tests and is isolated
as manual P7.0 because ordinary `task:plan-run` preflight is the failing seam. RAG:—
(repo-grounded: `journal.py::validate_append_policy`, `terminal_policy.py`,
`plan_lint_checks/{common,parsing}.py`, plan-protocol historical compatibility).

## Required post-repair evidence

- focused `test_plan_lint_policy` green with historical/new boundary cases;
- full active-plan lint exits 0 without changing P0–P6 bytes;
- conflict lint exits 0;
- P7.0 journal/state/handoff generated only after the linter accepts the plan.

The append-only P7 design journal note counts the five ordinary routed product items P7.1–P7.5.
P7.0 is the subsequently isolated manual bootstrap item, so it is additional to that count rather
than a rewrite of the recorded design event. RAG:— (repo-grounded: append-only journal policy,
D32 and this reproduction).
