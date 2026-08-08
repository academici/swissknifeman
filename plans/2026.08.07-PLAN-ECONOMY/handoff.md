# HANDOFF — 2026-08-08 — after P0.5

**Next:** `/task:plan-design 2026.08.07-PLAN-ECONOMY P0.1` — синхронизировать ТЗ реопена с D114:
добавить пятый класс плотного ASCII, процедуру повторной заморозки артефакта и влияние новой версии
на единицу порога P0.5. После исполнения P0.1 вернуться к `/task:plan-run
2026.08.07-PLAN-ECONOMY P0.5`.

| Параметр | Значение |
|:--|:--|
| Model | frontier |
| Thinking | high — реопен замороженной калибровки |
| Context | NEW SESSION — шаг-не-item |
| Суть | Спроектировать узкий реопен P0.1 по владельческому решению D114 |
| Команда | `/task:plan-design 2026.08.07-PLAN-ECONOMY P0.1` |

```
/task:plan-design 2026.08.07-PLAN-ECONOMY P0.1
```

**Done:** P0.5 запущен на `gpt-5.6-sol/high` (`frontier/high`), pre-mutation contract дал
`allow`. Из `artifacts/fleet-weight.json` рассчитаны три кандидата; владелец утвердил порог
100 000, реопен P0.1 для пятого класса плотного ASCII и область только новых layout-v2 планов без
legacy. Решения записаны D113–D115 и строкой Update Log. Обнаружено арифметическое расхождение
prose `findings/04`: композиционные пробелы — 6196/10540 = 58.8%, не 56%; источником чисел остаётся
машинный дамп.

**Remaining:** P0.1 — спроектировать и исполнить реопен, повторно заморозить
`packages/task/configs/token-estimate-calibration.json`. Затем P0.5 — создать
`root/contracts/read-budget-v1.md` на фактической версии артефакта, заполнить `## 7. Contracts`,
прогнать Validation и закрыть фазу P0. P1–P6 не начинались.

**Sources of truth:** `plan.md` v0.16.0 (D113–D115, Routing, Update Log, Contracts) ·
`phases/P0.md` P0.1/P0.5 · `artifacts/fleet-weight.json` ·
`findings/04-fleet-read-weight-machine.md` · `packages/task/configs/token-estimate-calibration.json`
· `packages/task/configs/read-limit.json` · `journal.jsonl`.

**Open risks:**

- P0.5 нельзя закрывать на старой калибровке: D114 требует новую фактическую версию артефакта;
  плейсхолдер или ссылка на ещё не выпущенную версию запрещены.
- D115 supersedes D18: legacy-ветвь и opt-in удалены из области будущего гейта. ТЗ P0.5/P3 при
  ближайшем plan-design обязаны быть синхронизированы с этим решением, а не сохранять старую прозу.
- `findings/04` содержит ошибочное производное «56%» при правильных исходных counts; контракт и
  последующие проверки должны считать из JSON: 6196/10540 = 58.8%.
- Worktree несёт большой посторонний незакоммиченный дифф; он не трогался и не должен попасть в
  коммиты плана.

**Workarounds/Deferred/Open questions:**

- Workarounds: —.
- Deferred: миграция и поддержка старых планов отсутствуют по D115, а не отложены.
- Open questions: открытых владельческих вопросов P0.5 нет; остаётся технический дизайн реопена
  P0.1.
