# HANDOFF — 2026-07-22 — after P7

**Next:** waiting: plan.md D108 records exact Owner choice `S1+O1` → design-item: task:plan-design 2026.07.19-DUAL-PROVIDER P7.2

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | cold-start — plan-step |
| Суть | После Owner Approval материализовать bounded P2/P6 remediation design; live work не выполнять. |

```text
# НЕ раньше: plan.md D108 содержит exact Owner literal S1+O1
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.07.19-DUAL-PROVIDER P7.2; first read research/25-p7.2-owner-authority-boundary.md and plan.md D108; design/no-write only; do not execute P7.2, package/live apply/repair/rollback, P7.3+, FOREMAN, fleet, tag or push'
```

**Done:** D107/P6 disposition сохранена. P7.2 post-P6 boundary сведена к двум owner-осям:
`S` — effective provider selection этого проекта; `O` — ownership текущего live `.mcp.json`.
Рекомендованный единственный runnable выбор — `S1+O1`; механика остаётся делегированной D66/D79.

**Remaining:** Approval Owner должен выбрать один exact literal из
`research/25-p7.2-owner-authority-boundary.md`:

- `APPROVE P7.2 AUTHORITY S1+O1: ENABLE PROJECT-LOCAL claude-code+codex FOR swissknifeman ONLY; AUTHORIZE ONE EXACT P2 .mcp.json TRANSFER CANDIDATE FOR SHA256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283; DESIGN/NO-WRITE ONLY; NO LIVE APPLY/REPAIR/ROLLBACK YET`
- `REJECT P7.2 AUTHORITY S0+O0: KEEP LEGACY CLAUDE-ONLY AND .mcp.json UNMANAGED; STOP P7 AND THE PLAN`

**Sources of truth:** `research/25-p7.2-owner-authority-boundary.md` · `open-questions.md`
· `phases/P7.md` P7.2 · `plan.md` D102–D107 · `phases/P6.md` Audit attempt 4.

**Open risks:** No choice has been approved. Mixed `S1+O0`/`S0+O1` leaves P7.2 non-runnable.
D107 F1–F4 remain accepted debt. No current carrier authorizes project config, `.mcp.json`,
P2 lock, D104 targets or any other live mutation.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: exact P2/P6 mechanics, fresh P7.2 preflight and normal live path/action gate until D108.
- open_questions: `OQ-P7.2-1` — Owner choice `S1+O1` or `S0+O0`.
