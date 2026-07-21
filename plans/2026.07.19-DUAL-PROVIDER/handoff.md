# HANDOFF — 2026-07-21 — after P4

**Next:** audit-phase: task:plan-audit 2026.07.19-DUAL-PROVIDER P4

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | skills.repository · command.filesystem-read · command.git-read |
| Context | cold-start — plan-step |
| Суть | Fresh independent G04 Audit P4 attempt 2 on the post-repair closed tree; no P5 execution. |

```text
$ task:plan-audit 2026.07.19-DUAL-PROVIDER P4

Read AGENTS.md, CLAUDE.md, plan.md, handoff.md, phases/P4.md, the frozen
root/contracts/provider-command-routing-contract.md, P4 contribution/conformance artifacts,
P4.1–P4.5 commits, repair `cd654a4` and terminal retry close evidence. Audit only committed
P4 contract, catalog, Claude/Codex projections, neutral routing/Next gates, generated
operator reference and protected-path evidence. Confirm the single recorded post-repair
terminal validation evidence without rerunning package-wide validation. Write only the
independent Audit P4 attempt 2 evidence/verdict. RED returns to the owning P4 seam; GREEN
satisfies G04. Do not execute P5+, change frozen contracts, root adapters, live/user-global
config, external plans, fleet targets or unrelated owner files.
```

**Done:** P4.1–P4.5 and the post-repair terminal phase gate are closed. Repair `cd654a4`
replaced raw canonical Codex runtime copies with deterministic provider-safe projections;
full task/skiller validation and the worktree-local registry check are GREEN from the one
post-repair close cycle on `a45770b`.

**Remaining:** fresh independent G04 Audit P4 attempt 2 only. P5 stays unopened.

**Sources of truth:** `plan.md` D84/Contracts; `phases/P4.md` historical Audit P4 attempt 1,
current Completion Notes and Phase Handoff; frozen D84 contract; `packages/task/lib/task/
command_render.py`; generated `packages/task/adapters/codex/**`; `artifacts/
P4-command-parity-conformance.md`; `packages/task/docs/reference/provider-commands.md`.

**Open risks:** G04 remains unsatisfied until fresh Audit P4 attempt 2 is literal GREEN;
RED routes only to the owning P4 seam under D80/D81.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: P5 and later phases are not part of this execution.
- open_questions: none.

## Addendum — Audit P4 attempt 2 remediation

The Audit P4 attempt 2 RED supersedes the launch block at the top. Repair `0edf17a`
is implementation-complete in the task-owned Codex projector: adapter `1.0.3` preserves
ordinary `model/effort` notation, projects standalone `/clear` and uses one shared token-aware
boundary for projection/fail-closed scanning. Focused suite `22/22`, generated identity
`24/24`, lock `24/24 noop`, runtime scan (`29/29` route notation, `/clear` `5→0`, corruption
`0`) and plan-lint are GREEN. Canonical/Claude bytes, D84 and P5+ are untouched.

**Next:** close: task:plan-close 2026.07.19-DUAL-PROVIDER P4

Run the one terminal P4 close retry on `0edf17a`, then a fresh independent P4 audit.
Do not execute P5.
