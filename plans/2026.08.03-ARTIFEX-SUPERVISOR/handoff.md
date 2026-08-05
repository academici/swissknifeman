# HANDOFF — 2026-08-05 — after P4

**Next:** run-items: task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.7

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | repository-code-edit · committed-tree-validation · provenance-reconciliation |
| Context | same-session — item |
| Суть | Исправить Harness validation F2 и собрать append-forward provenance F3–F7. |
| Команда | `$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.7` |

| Model | Thinking | Approval policy | Sandbox | CWD | Context | Суть | Команда |
|:--|:--|:--|:--|:--|:--|:--|:--|
| gpt-5.6-terra | high | never | danger-full-access | `/home/vostrikov/projects/packages/swissknifeman` | `same-session — item` | P4.7 committed-tree Harness/provenance remediation | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'Run $ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P4.7. Read plan.md, phases/P4.md, brief/21-p4-audit1-final-remediation.md, research/32-p4-audit1-final-remediation.md and the Audit P4 block first. Execute only P4.7; preserve historical commits/journal and unrelated dirty worktree.'` |

**Done:** P4 reopened by D103 through all four protocol steps; plan version is 0.19.0; D104 and
the Layer-0 owner message form a resolver-valid prospective P4.8 grant; historical status and
commit-map corrections are append-forward; P4.7/P4.8 are detailed to DoR. This is the last P4
design pass.

**Remaining:** execute and self-close P4.7; execute and self-close owner-gated P4.8; run
`$ task:plan-close 2026.08.03-ARTIFEX-SUPERVISOR P4`; then run the second and final permitted
`$ task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P4`. P5 remains blocked until that audit is GREEN.

**Sources of truth:** `plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md` ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P4.md` ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/brief/21-p4-audit1-final-remediation.md` ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/research/32-p4-audit1-final-remediation.md` ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-p4.8-authority-preflight.py` ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/roadmap.md`.

**Open risks:** P4.7 includes `packages/harness/tests/test_run_plan_reader.py`, which already has
an unrelated dirty edit in the current worktree. The executor must require all P4.7 Files clean and
must not stash, revert, adopt or commit that foreign diff. Historical P4.1/P4.2 intermediate
handoffs cannot be recreated; the honest repair is the validated append-forward limitation.

**Workarounds/Deferred/Open questions:**

- workarounds: —.
- deferred: P5/P6 execution remains outside P4 remediation.
- open_questions: —.
