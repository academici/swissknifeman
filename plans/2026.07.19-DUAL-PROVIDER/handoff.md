# HANDOFF — 2026-07-21 — after P4.5

**Next:** close: task:plan-close 2026.07.19-DUAL-PROVIDER P4

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | skills.repository · command.filesystem-read/write · command.git-read/write |
| Context | cold-start — phase gate |
| Суть | Один terminal validation/close retry на repair tree, затем fresh Audit P4 attempt 2. |

```text
$ task:plan-close 2026.07.19-DUAL-PROVIDER P4

RETRY AFTER RED G04: repair commit cd654a4
RUN ONCE: full task/skiller validation, worktree-local registry check, docs/release assessment
THEN: fresh independent task:plan-audit 2026.07.19-DUAL-PROVIDER P4 (attempt 2)
DO NOT START: P5+, FOREMAN/fleet, live/user config or root adapters
```

**Done:** Audit P4 attempt 1 remains append-only RED. Bounded owning-seam repair replaced
raw canonical Codex runtime copies with deterministic self-contained runtime projections,
preserved source identity/hash, added fail-closed unsafe-literal validation and regenerated
only task-owned Codex artifacts/locks through the existing renderer/apply seam.

**Remaining:** run the single terminal P4 validation/close retry, mark P4.5/phase terminal
only from that evidence, then launch fresh independent Audit P4 attempt 2. P5 stays unopened.

**Focused evidence:** `test_codex_command_adapter` + `test_provider_command_parity` GREEN;
all 11 generated runtimes have zero exact canonical copies and zero Claude model/slash/
session-route/Workflow execution literals; statuses/item-field sentinels, two-run identity,
P2 lock lifecycle/cache containment and all-noop second apply remain GREEN. Immediate
Claude routing/adapter consumers are GREEN; full validation was not rerun in repair.

**Sources of truth:** `phases/P4.md` historical Audit P4 block and current Phase Handoff;
`packages/task/lib/task/command_render.py`; generated `packages/task/adapters/codex/**`;
`artifacts/P4-command-parity-conformance.md`; frozen D84 contract.

**Open risks:** none inside the bounded repair seam. G04 remains unsatisfied until the
single terminal close retry and fresh independent Audit P4 attempt 2 are literal GREEN.

**Scope boundary:** P5 remains unopened. Canonical task commands, Claude plugin/goldens,
frozen D84, root `.agents`, external plans, fleet and live/user configuration are untouched.
