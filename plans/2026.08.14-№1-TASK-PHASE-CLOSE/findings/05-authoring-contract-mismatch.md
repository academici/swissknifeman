# Environment finding — authoring projection vs layout-v2 lint

**Дата:** 2026-08-14
**Статус:** observed, worked around without bypass.
**Evidence:** RAG:— (local command output).

Installed `task:plan-design` runtime and the plan-protocol snippet instructed the designer to put
`Version`, `## 6. Update Log` and `## Обсуждение` into `plan.md`. Worktree-local
`python3 packages/task/scripts/plan-lint.py plans/2026.08.14-№1-TASK-PHASE-CLOSE` rejected all three:

- `Version` lives only in generated `status.md`;
- `Update Log` is outside the closed layout-v2 core;
- `## Обсуждение` is forbidden in favor of other durable carriers.

The machine gate is authoritative. The plan removed those fields/sections; model provenance remains
in Meta and `journal.jsonl`, while the resolved fingerprint trade-off is preserved in
`research/01-slice-a-design.md` and D3. No gate was skipped or described as green.

Owning-source repair is deliberately not added to Slice A implementation scope: this design task
records the mismatch; a Task authoring/projection maintenance change must reconcile it at its owner.
