# Owner refinement — automatic agent continuation

**Date:** 2026-07-20

The root agent must orchestrate the active master plan without asking the owner to relay routine
launch blocks:

1. After each terminal item, phase close or audit, automatically start a fresh subagent for the
   next executable roadmap step, grounded from committed plan/handoff/Required Reads.
2. Sequentially dependent items run one subagent at a time. Do not introduce a Workflow script or
   parallel fan-out where the next item consumes the previous item's deliverables.
3. The on-disk launch block remains a recovery/cold-start carrier; presenting it is not a reason
   to stop orchestration.
4. Stop and ask the owner only at an explicit Owner Approval gate, a new-authority boundary or a
   genuinely unresolved blocker after safe in-scope remediation is exhausted.
5. Environment/tooling failures follow D56: disclose quality impact, repair immediately when safe,
   re-run affected checks, then continue automatically.
6. Audit regressions trigger an automatic fix-forward loop: return to the owning item/phase,
   apply formal reopen rules when needed, commit the repair separately, repeat validation and
   independent audit, then resume the roadmap. Escalate only a frozen-contract change,
   authority expansion or genuine owner-level fork.
