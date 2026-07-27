# HANDOFF — 2026-07-27 — after P8.4

**P8.4 закрыт `🟢 Done`** (item-коммит `5b7cc15e`, bookkeeping — этим же заходом):
`scripts/docs-impact.py` (карты `SURFACE`/`NON_SURFACE`/`INTERFACE`/`CREDIT` данными,
измеренный триггер C — D119/D120, escape hatch трейлером `Docs-Not-Needed:` — D121, диапазон
всегда три точки) + `scripts/test-docs-impact.py` (10 кейсов, все зелёные) +
`.github/workflows/hygiene.yml` (job `hygiene`, `fetch-depth: 0` — D122, шаги PR/push + шаг
теста) + раздел в `docs/develop.md` §11 (измеренная частота 8/12 PR · 11/41 коммит на
`cd93dbc8`, названная граница покрытия) + строка в `CHANGELOG.md`. Дельта против замера
(`artifacts/P8.4/probe-docs-impact-rules.py`) сошлась байт-в-байт: **8/12** PR правилом C на
дереве `cd93dbc8`. Job `hygiene` не проверен реальным CI-run'ом (PR не открыт в этом заходе) —
доказан построчным локальным прогоном обоих шагов; Pending Work — первый живой PR/push даст
подтверждение. Детали — `phases/P8.md` P8.4 Completion Notes.

**P8.5/P8.6 эскалированы `🔴 Blocked`** (этот заход, до старта работы — блокер сработал на
обязательном pre-mutation Task Contract, п. 2 `plan-exec`, работа НЕ начиналась): см.
Open risks (9) и блокквоты `phases/P8.md` P8.5/P8.6.

**Next:** P8.5 и P8.6 **эскалированы на pre-mutation gate** (см. Open risks (9)) —
`task_contract.build()` не парсит батч-строку §3 Routing `"P8.5, P8.6"` (ни точное
совпадение, ни диапазон `Pn.a-Pn.b`). Требуется `plan-design`, реопен-кандидат — владелец
`packages/task/lib/task/task_contract.py` (фаза P2 плана `2026.07.24-AGENT-RELIABILITY`),
либо решение владельца разбить строку §3 на два отдельных ряда `P8.5`/`P8.6`. Свободные
одиночные items остаются: P8.7–P8.9, P9.3, P1.1, P3.1.

| Параметр | Значение |
|:--|:--|
| Model | opus (`frontier`) |
| Thinking | high — дефект компилятора task_contract, затрагивающий все батч-строки §3 Routing |
| Context | NEW SESSION — шаг-не-item |
| Суть | Ре-дизайн P8.5/P8.6 (или правка §3 Routing) после диагноза `task_contract.build()` на батч-ячейках |

```
/task:plan-design 2026.07.25-ECO-OPT P8.5
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(`0b33116c`+`243254aa`) · **P10.2** (`47d6972d`) · **P10.3** (`ae54d790`) · **P10.4**
(`77bf9d8c`) — **фаза P10 закрыта** (1🟢+3🟠) · **P8.1** · **P8.2** · **P8.3** · **P8.4**
(`5b7cc15e`) · **P9.1** · **P2.1** · **P3.2** · **P1.2** · **фаза P5 закрыта** (P5.1🟢
`629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` · P5.4🟢 `253ae4a6` · P5.5🟢 `88f0c7eb` ·
P5.6🟢 `9cafcac1`; аудит заход 2 — ATTENTION, F1/F2 закрыты, F9–F16 бухгалтерия) —
**20/43 items закрыто**, 2 фазы терминальны (P5 закрыта, P10 закрыта), 5 фаз в работе (P8 —
4/9, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2).

**Remaining:** 23/43 items. P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93). P6.1 — ПОСЛЕ P9.1
(условие снято). P4.2 — ПОСЛЕ P3.2 (условие снято). Свободные одиночные items: P1.1
(frontier/high, manual), P3.1 (нужен оператор), P8.7–P8.9, P9.3. Внутри P8: **P8.5 → P8.6**
(общий `.github/workflows/hygiene.yml`, уже создан P8.4); P8.7 (`core/io.py`) — отдельно, не в
цепочке, кандидат №1 для dogfood-прогона P7.1 (волна 1, roadmap).

**Sources of truth:** `plan.md` (§2 Execution Rules; §4 Phase Index — P8 `2/9 🟡 In progress`;
§5 D87–D123; §6 Update Log) · `phases/P8.md` (`## Phase Status` — P8.4 терминален `🟢`; секция
P8.4 Completion Notes — карты/триггер/CI-механика/дельта против замера) · `roadmap.md` § B4b
(батч сужен до `P8.5, P8.6`) · `open-questions.md` (OQ-1 закрыт D113; OQ-9 открыт) · машинные
гейты `plans/cross-plan-files.py`, `plans/verify-citations.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — оба
пред-существующие, долг вне `Files` любого закрытого item'а, кандидат на отдельный фикс-item
за владельцем `maind`; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` планом не вычитана
(`[UNVERIFIED]`, D110 Consequences); (3) P10.4 Pending Work — починка системного расхождения
рендерера `.mcp.json` (роадмап-кандидат, D106); (4) P10.3 Pending Work — `README.md:122`
ссылается на несуществующий `roadmap/self-learning-memory.md` (кандидат `/task:fix`);
(5) F13/F14 из аудита P5 (заход 2) — вне carve-out закрытия, Pending Work за владельцем
P5/`packages/maind`; (6) P10.2 Pending Work (b) — владелец не решил про
`plans/verify-citations-known-exceptions.json`; (7) carve-out (б) канона `plan-protocol`
(SKILL.ru.md §6) текстом ещё не переписан (D118 разрешает P10.1 ссылаться на решение владельца
ДО правки скилла); **(8) P8.4 Job `hygiene` не подтверждён реальным CI-run'ом** — PR не открыт
в этом заходе, доказательство локальное построчное; первый живой PR/push — первое реальное
подтверждение, расхождение (если найдётся) — `/task:fix`; **(9) P8.5/P8.6 эскалированы**:
`task_contract.build()` (`packages/task/lib/task/task_contract.py:223-269`,
`_find_routing_row`) распознаёт §3 Routing только по точному равенству `Items == item_id`
или по диапазону `Pn.a-Pn.b` (`_ROUTING_RANGE_RE`) — запятую-список `"P8.5, P8.6"` (реальная
форма строки батча B4, `plan.md:178`) не парсит ни при `item_id="P8.5"` (`no §3 Routing row
found`), ни при `item_id="P8.5, P8.6"` (`no item block found` — ищет заголовок
`### P8.5, P8.6`). Обязательный шаг п. 2 `plan-exec` без исключений ⇒ item'ы блокированы до
plan-design; тот же класс строки в §3 Routing есть у батча **P8.8, P8.9** (B5) — тот же
дефект сработает и там.

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в строках §6 Update Log — плановая дисциплина, не фазовая). Долг
«перепиннуться на тег, когда апстрим выпустит релиз со схемой `language_servers`» держит
`roadmap.md` § «Отложенное» (срок непроверяем, в item не превращается — D110).
