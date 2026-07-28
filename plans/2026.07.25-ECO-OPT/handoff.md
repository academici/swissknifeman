# HANDOFF — 2026-07-28 — after P6.3

**P6.3 закрыт `🟠 Done with deviations`** (`609ab63b` — item-коммит): три дельты в
`general/verify-claims` (coverage-шаг «перечисли факт-классы, включая те, ответ на которые
кажется известным» · `perplexity-web` переформулирован из фолбэка в отдельный класс знания
(полевая практика) · раздел «Делегирование: не ронять ступень» расширен со «проверь факт» на
«дай сводку/перечень») + строка в чеклисте качества, RU→EN→`check-translations.sh --stamp`→
`skiller registry`. Аддитивный абзац в корневом `CLAUDE.md` § «Методология решений». Три новых
pressure-сценария (`evals/pressure.json` id 3–5, по кейсам D20/D53/time-pressure) —
**зелёные**; прогон `skiller eval general/verify-claims` дал **6/7** — красным остался
пре-существующий `pressure#2` (заведён коммитом `34ae85f1`, 2026-07-02, вне Scope этого item'а,
не тронут — анти-подгонка D58). Честная граница результата зафиксирована дословно
(`findings/P6.3-pressure-run.md`): 7 текстовых кейсов — smoke-тест формулировки, НЕ измерение
overconfidence-поведения. Третий усилитель D20 (пункт DoR) вынесен анкерованной спекой
`research/14-P6.3-dor-delta-spec.md` для исполнителя **P2.3** (D81, OQ-8 закрыт заранее);
четвёртый кандидат (гигиена сужения заголовка) закрыт как уже покрытый reconcile-механизмом
(D59). Детали — `phases/P6.md` P6.3 Completion Notes.

**Все items фазы P6 терминальны** (P6.1🟢/P6.2🟠/P6.3🟠) — фазовое закрытие (Status Board
`## 4.`, `closure/P6.json`, Phase Handoff) остаётся **отдельным** `/task:plan-close
2026.07.25-ECO-OPT P6` шагом, этим item'ом не выполнено (та же топология, что у P4.3/P3.6/P1.1).

**Next:** следующий по готовности — **P2.2** (`Exec = manual`, `frontier/high`, solo). У P2.3 ТРИ
гейта (§ Implementation Rules P2.3): (а) AGENT-RELIABILITY P2 терминальна — да; (б) P6.3
терминальна — **да, теперь**; (в) P8.1/P8.2/P8.3 терминальны — да; **(г) P2.2 терминальна —
НЕТ** (`⬜ Not started`, потребляет формат карты P2.2). Значит P2.3 всё ещё ждёт — на P2.2,
не на P6.3. P2.2 гейтов не несёт (ревизия интент-команд/agent-packs, owner-гейт только на
изменение `model`/`effort`-пинов, D16).

| Параметр | Значение |
|:--|:--|
| Model | opus — предписано Routing (`frontier/high`) |
| Thinking | high — предписано Routing |
| Context | continue (/clear) — ручной item |
| Суть | P2.2: правило A/B/C по шести интент-командам + agent-packs, карта `artifacts/P2.2/opus5-revision-map.md` (формат, который потребит P2.3) |

**ЗАПУСК ВРУЧНУЮ: opus/high** (`Exec = manual` — owner-гейт на пины + design-класс правки;
`/task:plan-exec` пинит sonnet/medium и обязан такой item отклонить):

```
/model opus
/effort high
/task:plan-run 2026.07.25-ECO-OPT P2.2
```

**Done:** **47/52 items терминальны** (29 🟢 · 17 🟠 · 1 ⛔). Закрыты фазы **P1** (1/2, 🟢),
**P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠),
**P10** (1/4, 🟠), **P11** (6/8, 🟠); **P6** — все 3 item'а терминальны (1/3 🟢), Phase Status
Board ждёт отдельный `plan-close`.

**Remaining:** 5 items: P2.2/P2.3 · P7.1–P7.3. Порядковые условия: P2.3 — ПОСЛЕ P2.2 (D94 связка
№3, формат карты) и ПОСЛЕ P8.1/P8.2/P8.3 (терминальны) и ПОСЛЕ P6.3 (терминальна, снято этим
заходом); P7.1 + P7.3 → P7.2. Плюс отдельно висит фазовое закрытие `/task:plan-close
2026.07.25-ECO-OPT P6` (все items терминальны, доска не обновлена).

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index — `P6 1/3` ждёт
`plan-close`; §6 Update Log — запись закрытия P6.3) · `phases/P6.md` (Phase Status + P6.3
Completion Notes) · `phases/P2.md` (P2.2/P2.3 гейты и Implementation Rules) ·
`findings/P6.3-pressure-run.md` (полный вывод прогона + честная граница) ·
`research/14-P6.3-dor-delta-spec.md` (спека для P2.3) ·
`packages/skiller/skills/general/verify-claims/**` · машинные гейты
`packages/skiller/scripts/{check-translations.sh,validate.sh}`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей, записи (40)–(46)) плюс:
(47) **`pressure#2` (делегирование, id:2) красный** — пре-существующий кейс не в Scope P6.3, не
чинился (анти-подгонка D58); следующий, кто трогает `verify-claims`/его evals, обязан либо
починить формулировку скилла под этот кейс, либо явно принять его как известный предел
smoke-теста — молчаливо игнорировать нельзя.
(48) **чистый прирост тела RU-источника ~17 строк** против ориентира «~15» в Implementation
Rules P6.3 (Known Deviations, процессное) — CORE-резидент бюджета не пострадал (663/750 ток),
но следующая правка `verify-claims` наследует чуть более длинный текст.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — без изменений этим заходом (F1 roadmap-кандидат, расхождение flexcrm 142 vs
186, апстрим-URL `oss-dev/to-issues` 404, протокол backup-restore, `PreCompact`/`PostCompact`
хук — roadmap-кандидат).
· **open questions** — без изменений; OQ-8 уже закрыт (D81, спека готова); OQ-11 остаётся
`Decision pending` до закрытия P11.
