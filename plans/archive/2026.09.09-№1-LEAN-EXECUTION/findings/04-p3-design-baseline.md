# P3 design baseline — 2026-09-09

RAG:— (local source, preserved incident carriers and preflight observations).

## Preflight

- Route evidence matched the exact invocation and repository cwd: `gpt-5.6-sol/high`, class
  `frontier`, source `provider-thread-state`.
- `codex doctor --json`, corrected `packages/maind/bin/maind health --cwd`, and
  `packages/harness/bin/harness doctor` were green. The first mAInd probe supplied a value after the
  boolean `--cwd` flag and failed as a procedural input error; the corrected local-CLI invocation
  was green.
- Initial plan-lint was green with one optional warning for absent `index.md`.
- The worktree already contained owner roadmap removals and this untracked plan directory; P3 design
  preserves that baseline and changes only this plan's carriers.

## Current seams

- `phase_audit_policy()` derives first-audit admission from `Routing.Review`, non-green history and
  item count. It has no `Phase Assurance | v1` input, so a fully evidenced isolated multi-item phase
  cannot declare direct-close eligibility and a historical `full` row remains a perpetual trigger.
  RAG:— (repo-grounded: packages/task/lib/task/plan_gates.py:342-398;
  artifacts/source-roadmap/2026.08.14-phase-assurance-contract.md).
- `_phase_reviews()` manually consumes every pipe row remaining in `## 3. Routing`. A second mapping
  table in that section can therefore invalidate the executable table instead of being ignored by
  one header-bounded parser. RAG:— (repo-grounded: packages/task/lib/task/plan_gates.py:287-330;
  artifacts/source-roadmap/2026.08.14-insiders-p6-routing-candidate-repro.md).
- `terminal-evidence/v1` binds only spec SHA and `{carrier,status,evidence_ids}` rows. It cannot prove
  command/input/product/tool/route identity, risk class, duration or reuse lifetime, so audit cannot
  safely distinguish reusable deterministic evidence from a live gate. RAG:— (repo-grounded:
  packages/task/lib/task/terminal_policy.py:39-129;
  artifacts/source-roadmap/2026.08.14-repeat-audit-evidence-reuse-budget.md).
- `phase_close_gate()` compares one aggregate fingerprint and returns bare `PHASE_AUDIT_STALE` on
  mismatch. Although item-state projection metadata is already excluded, the product tree still
  hashes every declared `Files` path, including audit-owned journal/view/handoff carriers, and no
  persisted field-level impact/dependency closure exists. RAG:— (repo-grounded:
  packages/task/lib/task/plan_gates.py:182-270,486-542;
  packages/task/lib/task/plan_item_state.py:123-140;
  artifacts/source-roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md).
- `plan_downstream.discover_consumers()` derives edges from exact path intersection and executes
  consumer Validation, but it does not yet own a reusable phase-wide evidence graph or explicit
  spec/product/closure anchors. RAG:— (repo-grounded:
  packages/task/lib/task/plan_downstream.py:104-163).

## Design verdict

Use one candidate lineage and four ordered ownership seams: assurance/impact policy, shared Routing
parsing, validation receipts, then anchor/dependency closure and audit finalization. Preserve live
checks as live, keep legacy plans on a conservative first-baseline path, and never infer `full` from
an unclassifiable diff. No external fact class or RAG retrieval is required for P3.
