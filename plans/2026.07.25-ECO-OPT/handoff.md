# HANDOFF — 2026-07-27 — after P8.10

**P8.10 закрыт 🟠 Done with deviations** (`a020f434`) — **все 10 items фазы P8 терминальны**
(7🟢 + 3🟠), фаза ещё НЕ закрыта (`## Phase Handoff` пуст, `closure/P8.json` не собран).
Канон `plan-protocol` §9 объявил значение ячейки `Items` в `## 3. Routing` закрытым набором из
двух форм (один item `Pn.m` либо диапазон одной фазы `Pn.a–Pn.b`); склейка через запятую и
смесь диапазона со списком нелегальны — носитель группы подфаз назван явно (колонка `Batch`).
Оговорка Back-compat получила честную границу: легаси-послабление §3 действует для
ЧЕЛОВЕКА-исполнителя, но не для ячейки `Items` — её читает и машина. Компилятор
`task_contract._find_routing_row` на распознанной склейке отдаёт диагностичный отказ (ячейка,
её номер строки, обе легальные формы) и **остаётся отказом** — маршрут из совпавшего токена не
берётся; ячейка без запятой и без совпадения даёт прежний текст байт-в-байт. Живой прогон на
чужом `2026.07.18-FOREMAN` (его файлы НЕ правились): «§3 Routing row 'P4.1–P4.2, P4.4' (line 87)
is a comma list …». Тесты — 4 новых кейса `RoutingFormTests` с предъявленным красным-до
(3 падения из 72 на версии `task_contract.py` от `HEAD~1`), после правки `Ran 72 tests OK`.
Version-first (D27): скилл `2.19.0 → 2.20.0`, units `core`/`general` `0.12.0 → 0.13.0`,
`packages/skiller/package.json` `0.13.0`. Зелёные: `packages/task/scripts/validate.sh`
(450 тестов), `packages/skiller/scripts/validate.sh` (491 тест, `registry --check` актуален),
`check-translations.sh`, `docs-impact.py --staged`, `tc.build()` по 5 items плана.

**Next:** закрыть фазу **P8** — все её items терминальны, но фаза несёт `🟡`, пустой
`## Phase Handoff` и не имеет `closure/P8.json` (Closure Protocol v1 включён в Meta). Фаза
содержит `🟠`-items (P8.1, P8.3, P8.10) ⇒ после закрытия по правилу «была 🟠 → сперва аудит»
следующим шагом ожидается adversarial-аудит уже ЗАКРЫТОЙ фазы P8 (команду выдаст handoff
закрытия — до терминальности фазы аудит не гоняется). Свободные к запуску items
после этого (без порядковых условий друг относительно друга): **P9.3** (frontier/high, manual) ·
**P1.1** (frontier/high, manual) · **P3.1** (implementation/medium, manual — нужен оператор для
`/doctor`/`/context`) · **P2.3** (frontier/high, manual — её гейт «после P8.1/P8.2/P8.3 и P6.3»
снят в части P8, но P6.3 ещё не исполнена).

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрытие фазы P8: таблицы, Phase Handoff, `closure/P8.json`, lint |

```
/task:plan-close 2026.07.25-ECO-OPT P8
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(`0b33116c`+`243254aa`) · **P10.2** (`47d6972d`) · **P10.3** (`ae54d790`) · **P10.4**
(`77bf9d8c`) — **фаза P10 закрыта** (1🟢+3🟠) · **P8.1** · **P8.2** · **P8.3** · **P8.4**
(`5b7cc15e`) · **P8.5** (`d12ccaf7`) · **P8.6** (`12ff61e1`) · **P8.7** (`fa1ee8bf`) — **батч
B4b закрыт** · **P8.8** (`4ee3ba6d`) · **P8.9** (`980ce398`) — **батч B5 закрыт** · **P8.10**
(`a020f434`) — **все 10 items P8 терминальны** · **P9.1** · **P2.1** · **P3.2** · **P1.2** ·
**фаза P5 закрыта** (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` · P5.4🟢
`253ae4a6` · P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) — **26/44 items закрыто**, 2 фазы
терминальны (P5, P10), 5 фаз в работе (P8 — 10/10 items терминальны, фаза не закрыта; P9 — 1/4,
P2 — 1/3, P3 — 1/6, P1 — 1/2).

**Remaining:** 18/44 items. Свободные к запуску — см. Next. Порядковые условия: P2.3 — ПОСЛЕ
P8.1/P8.2/P8.3 (выполнено) и P6.3 (D93); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2
(условие снято). P8.10 предшественником других items не является.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing; §4 Phase Index — P8 `7/10 🟡`;
§5 D124/D125; §6 Update Log) · `phases/P8.md` (`## Phase Status` — все 10 items терминальны,
`## Phase Handoff` пуст; P8.5–P8.10 Completion Notes) ·
`research/25-P8.5-routing-cell-form-2026-07-27.md` (диагноз §3 Routing, целевой дизайн P8.10) ·
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §9 (канон формы ячейки — SSOT) ·
машинные гейты `plans/cross-plan-files.py`, `plans/verify-citations.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` не вычитана
(`[UNVERIFIED]`, D110); (3) P10.4 Pending Work — рендерер `.mcp.json` (D106); (4) P10.3 Pending
Work — `README.md:122` битая ссылка (кандидат `/task:fix`); (5) F13/F14 аудита P5 (заход 2) —
за владельцем P5/`maind`; (6) P10.2 Pending Work (b) — `verify-citations-known-exceptions.json`
не решён владельцем; (7) carve-out (б) канона `plan-protocol` не переписан (D118); (8) P8.4 job
`hygiene` не подтверждён реальным CI-run'ом; (9) **`plans/2026.07.18-FOREMAN` несёт нелегальную
форму ячейки §3 (`P4.1–P4.2, P4.4`, строка 87) — 3 его items не строят Task Contract; правит
FOREMAN, не этот план (И4–И6). После P8.10 починка самообслуживаема: отказ прямо называет
ячейку, строку и обе легальные формы**; (10) матрица `docs/status.md` не сверена с живыми
контрактами (D2, отложено); (11) `public-hygiene` CI-гейт (P8.6) красный на текущем дереве —
`install.log` в `artifacts/p5-pilot/stage0/` (P8.6 Pending Work, owner); (12) три CORE-скилла
без активационной секции — унаследованный долг в `skill-sections-burndown.txt` (P8.8, правка тел
вне scope); (13) пред-существующая ruff-находка `B904` в
`packages/skiller/lib/skiller/publication.py:1037` — вне `Files` P8.9, не регрессия, не
починена (кандидат `/task:fix`); (14) формулировка Validation 1 в ТЗ P8.10 невыполнима как
записана (тест-модуль импортирует соседний `fixtures` ⇒ каталог тестов обязан быть на
`PYTHONPATH`) — тот же дефект утащит любой будущий item, цитирующий эту команду.

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py` (Scope Excluded
P8.10 — кандидат `roadmap.md`, если форма всплывёт снова); сверка полноты матрицы
`docs/status.md` (D2); удаление/gitignore `install.log` (P8.6 Pending Work, owner); перевод
`maind/provider_deploy.py` на `assert_safe_replace_target` (P8.7, roadmap-кандидат); заполнение
`triggers[]` у четырёх скиллов с `evals/` (P8.8, WARNING). Долг «перепиннуться на тег Serena»
держит `roadmap.md` § «Отложенное» (D110).
