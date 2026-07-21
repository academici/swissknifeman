# HANDOFF — 2026-07-21 — after P4.4

**Next:** exec-items: task:plan-exec 2026.07.19-DUAL-PROVIDER P4.5

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium — independent parity and generated operator docs |
| Capabilities | skills.repository · command.filesystem-read/write · command.git-read/write |
| Context | cold-start — plan-step |
| Суть | Execute only P4.5 from the terminal P4.4 neutral plan-routing seam. |

```text
Provider render: Claude `/task:plan-exec 2026.07.19-DUAL-PROVIDER P4.5`; Codex `$ task:plan-exec 2026.07.19-DUAL-PROVIDER P4.5`.

Read plan.md → handoff.md → phases/P4.md → P4.5 Required Reads in exact order. Consume frozen D84 and the committed P4.1–P4.4 catalog/render/plan seams. Change only P4.5 declared parity/docs files. Do not touch P5+, root adapters, live/user-global config, FOREMAN, fleet or owner dirt. Run the terminal P4 validation/close/audit exactly once after P4.5 as required by D80/D82.
```

**Done:** P4.4 added semantic Next carriers, dual provider invocation rendering, two-axis
fixed/inherited route gates, orchestration capability failures and neutral plan-protocol v2.11.0
without changing P4.3 Claude command/plugin bytes. Substantive item/bookkeeping commit is
recorded by the immediate mechanical hash fix.

**Remaining:** P4.5, terminal full validation/phase close and fresh independent P4
audit. P5+ remains closed.

**Sources of truth:** `plan.md` D84/Contracts; `phases/P4.md` P4.4 Completion Notes and P4.5;
frozen `root/contracts/provider-command-routing-contract.md`; independent
`packages/task/tests/fixtures_data/provider-plan-cases.json`; `packages/task/lib/task/command_render.py`;
`packages/skiller/skills/general/plan-protocol/SKILL.md` v2.11.0.

**Open risks:** P4.5 must independently derive exhaustive parity instead of fitting expected data
to renderer output. Any D84 change or authority expansion returns to the Owner.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: full task/skiller validation, docs/release assessment, phase close and audit run once at terminal P4 gate under D80/D82.
- open_questions: none.
