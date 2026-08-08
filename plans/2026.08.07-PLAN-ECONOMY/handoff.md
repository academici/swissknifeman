# HANDOFF — 2026-08-08 — after P2.3

**Next:** manual: implementation/high — `2026.08.07-PLAN-ECONOMY P2.4`

**Native Codex launch-block**

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | continue (/clear) — ручной item |
| Суть | Перестроить v2 plan core и собрать status view |
| Команда | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.4'` |

**Provider-neutral plan-protocol launch-block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | P2.4: stable plan core и generated status view |
| Команда | — |

```text
select session model class implementation
select session effort high
$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.4
```

**Done:** `2026.08.07-PLAN-ECONOMY P2.3` ввёл thin v2 phase index, раздельные item-spec/state
carriers и сборку канонической 16-польной модели без изменения v1-диагностик. Item-коммиты:
`f1b2e2f0`, `53f6a481`.

**Remaining:** P2.4–P6; literal full-unittest P2.2/P2.3 требует reconcile по D129.

**Sources of truth:** `phases/P2.md` P2.3/P2.4 · `packages/task/lib/task/plan_lint.py` ·
`packages/task/lib/task/plan_layout.py` · `packages/task/docs/reference/plan-layout-v2.md`.

**Open risks:** Literal `cd packages/task && python3 -m unittest discover -s tests` не получает
корень `core/` в `PYTHONPATH`; `bash packages/task/scripts/validate.sh` зелёный. Активный план несёт
предсуществующие DoR warnings, новых ERROR после P2.3 нет.

**Workarounds/Deferred/Open questions:**

- Workarounds: полный unittest запускать через `bash packages/task/scripts/validate.sh`.
- Deferred: reconcile literal Validation P2.2/P2.3 через `task:plan-design`.
- Open questions: —.
