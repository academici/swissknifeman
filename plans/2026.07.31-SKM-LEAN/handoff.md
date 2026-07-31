# HANDOFF — 2026-07-31 — after P2.3

**Next:** /task:plan-exec 2026.07.31-SKM-LEAN P2.4

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — из §3 Routing (P2.4 `implementation/medium`, `plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | Дефолт `mcp.emit_example` → `true` с opt-out, dry-run по флоту, удаление `roadmap/mcp-config-example-emit.md` |

```
/task:plan-exec 2026.07.31-SKM-LEAN P2.4
```

**Done:** **P2.3 закрыт: 🟢** (item-коммит `c2c0f1f6` — завершающий из двух атомарных: `77be6a4f`
код/тесты/доки/скилл + `c2c0f1f6` регенерация `skiller registry`, доска P2 `2/6` → `3/6`).
Модель стоимости MCP в измерителе (`_measure_mcp`, `budget.py`) пере-издана режим-зависимой
(D19/D22): `ENABLE_TOOL_SEARCH` читается в порядке env-процесса → `settings.local.json` →
`settings.json` → дефолт «включён»; три ветки — `deferred` (дефолт, имена инструментов +
инструкции сервера, нижняя граница; для `maind` инструкции измерены фактически = 0) / `auto`
(верхняя граница, явно названное допущение) / `off` (старая эйджер-модель, честна только при
`ENABLE_TOOL_SEARCH=false`); режим/источник/класс оценки — новые аддитивные ключи
`mcp.mode`/`mcp.mode_source`/`mcp.estimate_class` (`total`/`verdict` не тронуты, D16 — контракт
`maind doctor --context` цел). `KNOWN_MCP_TOOLS` получил алиас `boost` рядом с `laravel-boost`.
Обход подкаталогов `.claude/rules/**` в `_measure_claude_md` починен (`glob("*.md")` →
`glob("**/*.md")`) — на живом флоте сегодня вложенных правил нет, фикс латентный. `.mcp.json`
umbrella прополот критериями `core:mcp-advisor` — состав **подтверждён без изменений** (3
сервера, у каждого назван сигнал в `phases/P2.md` P2.3 Completion Notes). Перезамер «до/после»
живым `skiller budget --first-turn` по 4 проектам: umbrella `10 757 → 7 572` (WARN → OK), agelto
`32 611 → 24 165` (WARN), flexcrm `29 354 → 23 418` (WARN), `vintera/cms` `23 836 → 19 416`
(WARN → ELEVATED) — падение объяснено исправлением прибора (D19), не диетой; ни один проект
флота этим item'ом не изменён. Тесты `packages/skiller/tests/test_budget_first_turn.py`:
11 → 19 (+8), `test.sh` 541 → 549. `docs/guide/cli.md` и `mcp-advisor` `SKILL.ru.md`/`SKILL.md`
обновлены под новую модель. **OQ-4** (закрыт РАНЬШЕ, внутри P1.3 — `Resolved → D84`) — его
структурный критерий пересмотра «пере-считать `session_total` и подтвердить/пере-издать пару
16 000/23 000» ВЫПОЛНЕН этим закрытием: 3 из 4 проектов замера остаются `session_verdict: WARN`
(только umbrella перешёл в OK) — распределение флота не переворачивается, пара **подтверждена**
без новой D-записи; трекер `open-questions.md` не правится, счёт открытых вопросов (пять) не
меняется.

**Прежде (P2.2, 🟢 Done, item-коммит `a91e1fd6`):** пилот path-scoped правил на `dterema/app`,
`CLAUDE.md + rules` 13 658 → 11 284 ток (−2 374, −12,0 % первого хода); вердикт «раскатывать»
с оговоркой про Boost/`.ai`-generated проекты флота.

**Remaining:** **P2.4** готов к исполнению (⬜, маршрут §3 — `implementation/medium`,
`plan-exec`) — дефолт `mcp.emit_example`, dry-run по флоту, закрытие roadmap-остатка. Дальше по
фазе — P2.5 → P2.6, затем P3 → P7 по `roadmap.md`; порядок фазы строгий (`phases/P2.md`
§Phase Context). Доска: P1 `3/4` (закрыта 🟠) · P2 `3/6` 🟡 · P3 `0/5` · P4 `0/6` · P5 `0/9` ·
P6 `0/3` · P7 `0/4`.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P2.md` §P2.3 (спека + Completion Notes —
таблица «до/после», обоснование констант) · `plan.md` (§0 Meta v1.0.5, §3 Routing, §4 доска,
§5 D1–D90, §6 Update Log) · `findings/P2-resident-layer-probe-2026-07-31.md` §5, §5.1, §9
(baseline «до», tool-search RAG) · `packages/skiller/skills/general/mcp-advisor/SKILL.ru.md`
§«Прополка резидентного MCP» (обновлённый caveat) · `open-questions.md` (открытых по-прежнему
пять: OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8; OQ-4 закрыт РАНЬШЕ, внутри P1.3) · `roadmap.md`.

**Open risks:**

- **Гейт приёмки `pre_final` вырожден почти по всему плану вне закрытых items.** Предложение
  (C3/D6) прежнее — отдельный заход `plan-design` на разделитель ` · ` для P3.4/P5.5, приоритет
  без изменений:

  ```
  design-item: task:plan-design 2026.07.31-SKM-LEAN P3.4

  РЕЖИМ: правка ФОРМЫ Validation (разделитель), НЕ пере-дизайн предмета items
  ВХОД: plans/2026.07.31-SKM-LEAN/research/10-validation-acceptance-form-2026-07-31.md → §2 таблица, §4 предложение; затем plan.md §5 D90
  СКОУП: 1) P3.4 и P5.5 — разделить существующие проверки ` · ` вместо «; », текст проверок не менять 2) прогон §2 до/после: ноль красных 3) дальше — остальные items с «; » тем же приёмом
  НЕ ТРОГАТЬ: предмет и число проверок items; Scope/Deliverables; статусы; закрытые items P1.x, P2.1, P2.2, P2.3
  ```

- **Проекты флота с Boost/`.ai`-generated `CLAUDE.md` не покрыты процедурой P2.2 напрямую**
  (`findings/P2-rules-pilot.md` §6) — минимум `vintera/cms`, `sibintek-insiders`, `diabox`;
  до входа в **P2.6** для них нужно отдельное design-решение о пути правки.
- **Пять секций-кандидатов P2.1 остаются резидентными (436 ток)** — по D89 это решение, не долг.
- **Обход подкаталогов `.claude/rules/**` починен, но сегодня не проявлен на живом флоте** —
  ни umbrella, ни agelto/flexcrm/`vintera-cms` не несут вложенных правил; проверить на первом
  проекте, где P2.6 создаст `.claude/rules/<subdir>/`.
- **agelto/flexcrm остаются `WARN` и после исправления модели MCP** — фантомная доля там была
  меньше, чем у umbrella/`vintera-cms`; их диета — предмет **P2.6**, не этого item'а.
- (прежнее, в силе) **гейт размера меряет файл целиком, включая байты вне управляемых блоков** ·
  **токенная оценка продублирована в двух пакетах** (тест-сверка пропускается в standalone) ·
  **`closure/P1.json` `inputs_sha256["phases/P1.md"]` больше не совпадает с живым файлом** (D87).

**Workarounds/Deferred/Open questions:** «—» / сквозная правка формы `Validation` — отложена
до отдельного захода (см. Open risks) / проекты флота с Boost/`.ai`-generated `CLAUDE.md` —
отложены до отдельного design-решения (см. Open risks) / OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8
(пять открытых, без изменений — OQ-4 закрыт РАНЬШЕ, внутри P1.3), см. `open-questions.md`.
