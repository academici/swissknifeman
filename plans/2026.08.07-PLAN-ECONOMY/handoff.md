# HANDOFF — 2026-08-09 — after P6.5

**Next:** design-item: task:plan-design 2026.08.07-PLAN-ECONOMY P6.5

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | cold-start-root — capability-missing |
| Суть | Исправить Scope/Files и Required Reads P6.5 после модульного split `plan_lint`. |
| Команда | `$ task:plan-design 2026.08.07-PLAN-ECONOMY P6.5` |

Provider-neutral plan-protocol launch-block:

```text
task:plan-design 2026.08.07-PLAN-ECONOMY P6.5
```

Native Codex launch-block:

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.07-PLAN-ECONOMY P6.5'
```

**Done:** P6.5 прошёл routing и Task Contract pre-mutation, но остановлен до implementation; terminal escalation и return-evidence записаны, v2 state/status/decisions/bundle регенерированы.

**Remaining:** В `P6.5` заменить устаревший implementation site `packages/task/lib/task/plan_lint.py` на фактический owning module `packages/task/lib/task/plan_lint_checks/conflicts.py`, синхронизировать `Files`/Required Reads/anchors и вернуть item в исполнимое состояние.

**Sources of truth:** `plan.md` §3 Routing · `phases/P6/P6.5.md` · `phases/P6/P6.5.state.md` · `findings/P6.5-return-evidence-2026-08-09.md` · `journal.jsonl`.

**Open risks:** Документированный writer `packages/task/scripts/plan-returns.py` отсутствует; return-evidence квалифицирован как `unqualifiable`. Генератор closure не применим, пока P6 нетерминальна.

**Workarounds/Deferred/Open questions:** workarounds — нет · deferred — реализация P6.5 до ремонта item-spec · open_questions — должен ли owning-source repair также обновить plan-run/plan-exec текст, всё ещё называющий отсутствующий writer.
