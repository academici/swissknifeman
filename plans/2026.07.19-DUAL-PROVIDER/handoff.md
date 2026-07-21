# HANDOFF — 2026-07-21 — after P4.3

**Next:** «ЗАПУСК ВРУЧНУЮ: gpt-5.6-sol/high»

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high — neutral plan canon and provider invocation semantics |
| Context | continue (/clear) — ручной item |
| Суть | Execute only P4.4 from the terminal P4.3 dual-render compatibility seam. |

```text
Execute only P4.4 of plan 2026.07.19-DUAL-PROVIDER on gpt-5.6-sol/high in a fresh clean worktree based on the committed P4.3 tree.

Read plan.md → handoff.md → phases/P4.md → P4.4 Required Reads in exact order. Preserve frozen D84, exact P4.3 Claude goldens and P4.2 Codex projection. Change only the P4.4 plan-protocol/routing seam and its declared focused tests/artifact. Do not touch P4.5/P5+, root adapters, live/user-global config, FOREMAN, fleet or owner dirt. Run only P4.4 narrow validation; terminal full task/skiller validation remains after P4.5. Close/bookkeep P4.4 with explicit paths and report only commit, seam and test facts.
```

**Done:** P4.3 captured the committed pre-change Claude command/plugin surface independently,
added the named catalog-to-Claude projection and one shared check/write render plan, and proved
exact slash/frontmatter/body/plugin compatibility without changing canonical Claude bytes.
Substantive item/bookkeeping commit: `P4.3_SUBSTANTIVE_COMMIT` (replaced by the immediate
mechanical hash fix).

**Remaining:** P4.4 → P4.5, terminal full validation/phase close and fresh independent P4
audit. P5+ remains closed.

**Sources of truth:** `plan.md` D84/Contracts; `phases/P4.md` P4.3 Completion Notes and P4.4;
frozen `root/contracts/provider-command-routing-contract.md`; independent
`packages/task/tests/fixtures_data/claude-command-golden/`; `packages/task/lib/task/command_render.py`.

**Open risks:** P4.4 must retain exact P4.3 Claude bytes while neutralizing only plan routing,
Next and orchestration semantics. Any D84 change or authority expansion returns to the Owner.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: full task/skiller validation, docs/release assessment, phase close and audit run once at terminal P4 gate under D80/D82.
- open_questions: none.
