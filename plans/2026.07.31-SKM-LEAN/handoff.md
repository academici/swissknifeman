# HANDOFF — 2026-07-31 — after P2.6

**Next:** `/task:plan-close 2026.07.31-SKM-LEAN P2`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — закрытие терминальной фазы по фактам items, новых решений нет |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Фаза P2 терминальна (5/6, 6/6 items закрыто: 5×🟢 + 1×🟠) — закрыть таблицы, Phase Handoff, прогнать lint |

```
/task:plan-close 2026.07.31-SKM-LEAN P2
```

**Done:** **P2.6 закрыт: 🟠 Done with deviations.** Хаб-блок (P2.5, краткая
провайдер-зависимая форма) перегенерирован на 9 проектах флота: 7 коммитами в их
репозиториях (`corex 7545ef4`, `memster 1c05c49`, `edufy 232ed3e`, `dterema-app a4d5b45`,
`chatom c83d2aa`, `loqum 19a9f19`, `sibintek-insiders c8b2c49`) + 2 gitignored
(`flexcrm`, `perplexity-web-mcp` — диета применена и измерена, коммитить нечего). Замер
«после» снят тем же скриптом-обходом, что baseline P1.2 (22/22, тот же знаменатель),
опубликован в `findings/P2-fleet-after.md` с тремя обязательными колонками (baseline / после
/ эффект модели MCP через арифметическое разложение `Δmcp`, диета — отдельно в `Δclaude_md`).
Поимённые перечни: D64-исключения (`diabox`, Boost-проекты, `agelto`/`flexcrm` — rules-часть),
D93 non-green (17, свежая проверка `maind sync --all --only mcp --dry-run --json` совпала с
прежним замером P2.4 поимённо). `validate.sh` skiller/harness — зелёные. Спот-чек 2
раскатанных проектов (memster, edufy) совпал построчно.

**Не раскатано этим заходом (Pending Work item'а, `phases/P2.md` P2.6):** (1) path-scoped
rules-миграция (P2.2) — 0 новых проектов, кандидаты `vintera`/`brain` названы, причина —
объём поштучной классификации секций равен повторению самого пилота на каждом проекте;
(2) `.mcp.json.example` A-класс (`vintera`, `dterema`, `dterema-app`) — эмиссия ПОПЫТАНА и
ОТМЕНЕНА `git checkout --` до коммита: обнаружен дефект `write_example` (перезаписывает
`.mcp.json.example` целиком нашим инвентарём вместо мержа, теряя сторонние ручные записи —
`naive-ui`/`figma`/`playwright`/nuxt-docs/`laravel-boost`), правка генератора — новый механизм,
вне Scope Excluded этого item'а.

Item-коммит swissknifeman — `99aa2aac` (findings/P2-fleet-after.md).

**Remaining:** доска P2: **5/6** (6/6 items закрыто: 5×🟢 + 1×🟠 `P2.6`), фаза терминальна — следующий шаг
закрывает фазу (`plan-close`), не item. Общая доска: P1 3/4 (закрыта 🟠) · P2 5/6 (терминальна,
🟠) · P3 0/5 · P4 0/6 · P5 0/9 · P6 0/3 · P7 0/4.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P2.md` §P2.6 Completion Notes/Pending
Work · `findings/P2-fleet-after.md` (числа «после», три колонки, D64/D93 перечни, найденный
дефект `.mcp.json.example`) · `findings/P1-fleet-baseline.md` + `artifacts/p1-2-fleet-sweep.sh`
(база сравнения и инструмент) · `plan.md` §4 доска (P2 5/6, терминальна), §6 Update Log ·
`packages/skiller/scripts/generate-hub.sh` (генератор хаба, не правился) ·
`packages/maind/lib/maind/mcpconfig.py` (или соседний модуль `write_example` — адрес найденного
дефекта, не правился этим item'ом).

**Open risks:**

- **Найденный дефект генератора `.mcp.json.example`:** `write_example` перезаписывает файл
  целиком при наличии стороннего ручного содержимого вместо мержа `mcpServers` — подтверждено
  живьём на трёх проектах (`vintera`/`dterema`/`dterema-app`), откачено до коммита. Адрес —
  отдельный fix-item (правка `packages/maind/lib/maind/mcpconfig.py`), не входит в Scope
  Excluded P2.6. Пока не починено — эмиссия A-класса для этих трёх проектов недоступна.
- **Path-scoped rules-миграция раскатана только на исходном пилоте (`dterema/app`).**
  Реальные кандидаты — `vintera` (7288 ток), `brain` (6695 ток); объём поштучной
  классификации секций делает это отдельным item'ом по образцу P2.2 (implementation/high,
  manual), не механической раскаткой.
- (в силе) **Эффект краткой формы на connect-проектах ниже потенциального:
  `resolve_active_set` слеп к каналу плагинов** — адрес P3 (`findings/P2-hub-pilot.md` §5.1).
- (в силе) **Гейт приёмки `pre_final` вырожден почти по всему плану вне закрытых items** —
  отдельный заход `plan-design` на разделитель ` · ` для P3.4/P5.5 (см. предыдущий заход
  handoff, команда не изменилась):

  ```
  design-item: task:plan-design 2026.07.31-SKM-LEAN P3.4

  РЕЖИМ: правка ФОРМЫ Validation (разделитель), НЕ пере-дизайн предмета items
  ВХОД: plans/2026.07.31-SKM-LEAN/research/10-validation-acceptance-form-2026-07-31.md → §2 таблица, §4 предложение; затем plan.md §5 D90
  СКОУП: 1) P3.4 и P5.5 — разделить существующие проверки ` · ` вместо «; », текст проверок не менять 2) прогон §2 до/после: ноль красных 3) дальше — остальные items с «; » тем же приёмом
  НЕ ТРОГАТЬ: предмет и число проверок items; Scope/Deliverables; статусы; закрытые items P1.x, P2.1–P2.5
  ```

- (в силе) **Проекты флота с Boost/`.ai`-generated `CLAUDE.md` не покрыты процедурой P2.2**
  (`vintera/cms`, `sibintek-insiders`, `diabox`) — решение по ним не принято, отдельное.
- (в силе) **Пять секций-кандидатов P2.1 остаются резидентными (436 ток)** — по D89 это
  решение, не долг.
- (в силе) **гейт размера меряет файл целиком** · **токенная оценка продублирована в двух
  пакетах** · **`closure/P1.json` `inputs_sha256["phases/P1.md"]` больше не совпадает с живым
  файлом** (D87).
- (в силе, вне диффа этого захода) **Остаточная находка `verify-citations`:** `phases/P2.md`
  Completion Notes закрытого P2.3 несут сокращённую ссылку на `context-economy/SKILL.md` —
  адрес прежний.
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый `RESEARCH/AUDIT-loqum-
  findings.md`, неотслеживаемые `.swissknife/`, `audits/`) — этим заходом не тронут, не
  коммитился.
- **В деревьях нескольких проектов флота (`memster`, `edufy`, `chatom`, `corex` и др.) на
  момент раскатки был посторонний незакоммиченный дифф владельца** (их собственная
  параллельная работа) — этим заходом не тронут, не коммитился, не стэшился; коммит хаб-блока
  сделан ТОЛЬКО поимённым `git add <файл>` по каждому проекту.

**Workarounds/Deferred/Open questions:** «—» / rules-миграция сверх пилота — отложена (см.
Pending Work выше) / эмиссия `.mcp.json.example` A-класса — отложена до починки `write_example`
/ сквозная правка формы `Validation` — отложена (см. Open risks) / OQ-2 · OQ-3 · OQ-5 · OQ-6 ·
OQ-8 (без изменений этим заходом), см. `open-questions.md`.
