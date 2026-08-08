# HANDOFF — 2026-08-08 — after P3.3

**Next:** «ЗАПУСК ВРУЧНУЮ: implementation/high»

## Native Codex launch-block

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high — две сцепленные семьи проверок |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | continue (/clear) — ручной batch |
| Суть | Реализовать bundle/freshness и read-path гейты P3.4–P3.5. |
| Команда | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P3.4 P3.5'` |

## Provider-neutral plan-protocol launch-block

| Параметр | Значение |
|:--|:--|
| Model | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной batch |
| Суть | Исполнить B2: P3.4–P3.5. |
| Команда | — |

```text
$ task:plan-run 2026.08.07-PLAN-ECONOMY P3.4 P3.5
```

**Done:** P3.3 закрыт green: `plan_gates` hard-fail проверяет D2(a)/D2(b) только для
ready items layout v2, не дублируя `plan_weight`/`plan_admission`; v1 остаётся молча вне
области. Item commit: `2381ac2d`.

**Remaining:** B2 P3.4–P3.5 и P3.6–P6.

**Sources of truth:** `root/contracts/read-budget-v1.md` · `packages/task/lib/task/plan_gates.py` ·
`packages/task/lib/task/plan_weight.py` · `packages/task/lib/task/plan_admission.py`.

**Open risks:** Codex hook lifecycle preflight дополнительно сообщает `record-provenance-mismatch`;
см. `findings/23-p3.2-hook-integrity-preflight-2026-08-08.md`.

**Workarounds/Deferred/Open questions:**

- Workarounds: none.
- Deferred: repair Codex lifecycle provenance in the owning `harness` package; repeat its dry-run
  integrity check before treating it as green.
- Open questions: —
