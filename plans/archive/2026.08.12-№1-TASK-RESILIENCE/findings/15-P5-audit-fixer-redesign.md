# P5 audit-fixer redesign evidence — 2026-08-13

## Owner requirement

The owner requires phase audit to fix safe in-scope deviations itself while execution context is
fresh. A bounded phase must not enter a routine chain of separate audit, design, development and
second-audit sessions. Complexity is not terminal evidence; the agent must continue digging until
acceptance is green or an actual authority, safety, or public/frozen-contract boundary is proved.
RAG:— (owner-grounded: `brief/01-refinements.md`, 2026-08-13 audit-fixer refinement).

## Current repository behavior

1. `packages/task/commands/plan-audit.md:7-10` makes phase audit read-only for product files.
2. `packages/task/commands/plan-audit.md:168-177` implements two audits with a separate bounded
   repair run between them, then an owner incident at the audit cap.
3. `packages/task/commands/plan-audit.md:243-256` permits only one Markdown audit block plus one
   phase-level audit journal event; item states are left for another command.
4. The pre-P5.2 revision of `packages/task/commands/plan-audit.md` routed ordinary non-GREEN
   findings to a fresh `plan-exec`/`plan-run` root. The current replacement at
   `packages/task/commands/plan-audit.md:307-312` forbids that chain.
5. `packages/task/lib/task/plan_item_state.py:27-36,120-149` excludes `plan-design` from execution
   position and treats observations as status-neutral. Therefore a repaired spec cannot itself
   clear a historical `🔴 Blocked`; only a later execution event does. The current P5.2 carrier
   demonstrates that transient contradiction.
6. `packages/task/lib/task/plan_gates.py:236-288` correctly requires audit for non-green terminal
   items and material/full-review candidates, while `phase_close_gate()` accepts only matching
   `audit-green`. These candidate and close invariants remain useful.
7. P5.2 product commit `f0538e2f` passed its focused candidate/owner-decision matrix, but the
   downstream provider renderer owned by P5.3 failed and the execution was terminalized as a
   cross-package block (`journal.jsonl`, terminal P5.2 run `19b20367…`). This is a
   producer/consumer ordering signal, not proof that the P5.2 product is blocked.

All findings are repository- or owner-grounded. No external fact class is load-bearing.

## Design implications

- Preserve the fresh independent audit root, stable candidate fingerprint, snapshot-bound close,
  exact validation and generated-carrier ownership.
- Expand the audit command from reviewer-only to assurance owner: detect, cluster by root seam,
  repair, validate, commit, regenerate affected plan state, rebuild the candidate and only then
  emit its terminal verdict.
- An `🟠` item or a newly found in-scope defect is mandatory repair input, not permission to
  preserve debt. Out-of-scope observations do not color the phase verdict.
- Same-fingerprint failure changes tactic first; one `isolated-child-return` may advise the same
  root after a repeat or new material risk. It does not create another owner-facing command.
- A terminal non-GREEN verdict requires actual-impact evidence and the continue-first block gate;
  test volume, multi-file work, generator drift, dirty unrelated paths and difficulty are not
  terminal classes.
- Keep P5.2 focused validation independent of P5.3 generated projections. P5.3 consumes the
  canonical change, regenerates every provider/docs carrier through its owner and runs aggregate
  package validation. A not-yet-run consumer is `dependency-not-ready`, not a producer block.
