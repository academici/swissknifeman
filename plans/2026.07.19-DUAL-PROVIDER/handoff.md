# HANDOFF — 2026-07-21 — after P4

**Next:** audit-phase: task:plan-audit 2026.07.19-DUAL-PROVIDER P4

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | skills.repository · command.filesystem-read · command.git-read |
| Context | cold-start — plan-step |
| Суть | Fresh independent G04 audit of the closed P4 command/routing phase; no P5 execution. |

```text
$ task:plan-audit 2026.07.19-DUAL-PROVIDER P4

Read AGENTS.md, CLAUDE.md, plan.md, handoff.md, phases/P4.md, the frozen
root/contracts/provider-command-routing-contract.md, P4 contribution/conformance artifacts
and P4.1–P4.5 commits. Audit only committed P4 contract, catalog, Claude/Codex projections,
neutral routing/Next gates, generated operator reference and protected-path evidence.
Confirm the recorded terminal validation evidence without rerunning package-wide validation.
Write only the independent Audit P4 evidence/verdict. RED returns to the owning P4 seam;
GREEN satisfies G04. Do not execute P5+, change frozen contracts, root adapters,
live/user-global config, external plans, fleet targets or unrelated owner files.
```

**Done:** P4.1–P4.5 and the terminal phase gate are closed. Full task/skiller validation,
worktree-local registry check, current plan lint, docs/release assessment and protected-path
delta are green in the isolated close worktree.

**Remaining:** fresh independent G04 audit P4 only. P5+ remains outside this execution scope.

**Sources of truth:** `plan.md` D84/Contracts; `phases/P4.md` Completion Notes and Phase
Handoff; frozen `root/contracts/provider-command-routing-contract.md`;
`artifacts/P4-command-parity-conformance.md`; `packages/task/docs/reference/provider-commands.md`.

**Open risks:** G04 remains the independent release-quality gate for P4; RED routes only to
the owning P4 seam under D80/D81.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: P5 and later phases are not part of this execution.
- open_questions: none.
