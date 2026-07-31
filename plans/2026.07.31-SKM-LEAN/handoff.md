# HANDOFF — 2026-08-01 — after P2

**Next:** `/task:plan-design 2026.07.31-SKM-LEAN P3.1`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | xhigh — эскалация P1 (закрыта 🟠) сначала требует аудита фазы, но P2 закрылась
без открытых эскалаций/design-решений; следующая нетерминальная фаза P3 — скелет с
`Exec = manual` items, первый item P3.1 (implementation/high) — стенд A/B на живой
версии Claude Code против апстрим-бага, требует детализации ТЗ до запуска |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Фаза P2 закрыта (🟠 Done with deviations, 6/6 items терминальны); следующий шаг — детализировать P3.1 (стенд/смоук-гейт нативных полей) |

```
/task:plan-design 2026.07.31-SKM-LEAN P3.1
```

**Done:** Фаза **P2 (Резидент-диета) закрыта — 🟠 Done with deviations.** Все 6 items
терминальны: P2.1 (диета канона инструкций, 🟢), P2.2 (path-scoped rules — пилот на
`dterema/app`, 🟢), P2.3 (модель стоимости MCP под tool search, 🟢), P2.4
(`.mcp.json.example` default-on, fail-safe инварианты, 🟢), P2.5 (снят дубль нативного
листинга скиллов в хаб-индексе, 🟢), P2.6 (раскатка на флот + замер «после», 🟠 —
частично: hub-блок раскатан на 9 проектах, rules-миграция и `.mcp.json.example`
A-класс на `vintera`/`dterema`/`dterema-app` не раскатаны, см. Known Deviations
`phases/P2.md` §Phase Handoff).

**Известные отклонения фазы (собрано механически из Known Deviations items,
`phases/P2.md` §Phase Handoff):**
- P2.1: две DoR-строки фазы P2 переформулированы (process); правка
  `verify-citations-known-exceptions.json` вне `Files`/carve-out (process).
- P2.2 / P2.3: —.
- P2.4: `journal.jsonl` несёт более раннюю запись под ТЗ ДО ре-дизайна D91–D93;
  закрытие журналируется `attempt: 1` под обновлённым ТЗ (process).
- P2.5: (1) источник сверки усилен конъюнкцией против буквы Implementation Rule 3;
  (2) генератор перенесён из bash-heredoc в `lib/skiller/hub.py`; (3) гейт «нет
  установленных скиллов» стал канальным.
- P2.6 (material): rules-миграция (`vintera`, `brain`) и `.mcp.json.example`
  A-класс (`vintera`, `dterema`, `dterema-app`) не раскатаны этим заходом;
  `.mcp.json.example`-эмиссия была ПОПЫТАНА и отменена `git checkout --` до коммита
  по факту найденного дефекта генератора (`write_example` перезаписывает вместо
  мержа).

**Docs-sync:** не требуется — раскатанные механизмы фазы (канон-диета, rules-пилот,
MCP-модель стоимости, `.mcp.json.example` fail-safe, хаб-индекс) уже описаны в
`root/` и находках `findings/P2.*`; новых процессов/фич для `docs/` проекта сверх
уже задокументированного не появилось.

**Remaining:** доска: P1 3/4 (закрыта 🟠) · **P2 5/6 (закрыта 🟠)** · P3 0/5 · P4 0/6 ·
P5 0/9 · P6 0/3 · P7 0/4. План НЕ закрыт целиком — `plans/ACTIVE.md` не трогался.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P2.md` §Phase Handoff (сводка
известных отклонений) · `findings/P2-fleet-after.md` (числа «после») ·
`findings/P1-fleet-baseline.md` + `artifacts/p1-2-fleet-sweep.sh` (база сравнения) ·
`plan.md` §4 доска, §6 Update Log.

**Open risks:**

- **Найденный дефект генератора `.mcp.json.example`:** `write_example` перезаписывает
  файл целиком при наличии стороннего ручного содержимого вместо мержа `mcpServers`
  — подтверждено на `vintera`/`dterema`/`dterema-app`, откачено до коммита. Адрес —
  отдельный fix-item (`packages/maind/lib/maind/mcpconfig.py` или соседний модуль),
  не входит в Scope P2.6.
- **Path-scoped rules-миграция раскатана только на исходном пилоте (`dterema/app`).**
  Кандидаты `vintera` (7288 ток), `brain` (6695 ток) — отдельный item по образцу
  P2.2 (implementation/high, manual).
- (в силе) **Эффект краткой формы на connect-проектах ниже потенциального:
  `resolve_active_set` слеп к каналу плагинов** — адрес P3 (`findings/P2-hub-pilot.md`
  §5.1).
- (в силе) **Гейт приёмки `pre_final` вырожден почти по всему плану вне закрытых
  items** — отдельный заход `plan-design` на разделитель ` · ` для P3.4/P5.5:

  ```
  design-item: task:plan-design 2026.07.31-SKM-LEAN P3.4

  РЕЖИМ: правка ФОРМЫ Validation (разделитель), НЕ пере-дизайн предмета items
  ВХОД: plans/2026.07.31-SKM-LEAN/research/10-validation-acceptance-form-2026-07-31.md → §2 таблица, §4 предложение; затем plan.md §5 D90
  СКОУП: 1) P3.4 и P5.5 — разделить существующие проверки ` · ` вместо «; », текст проверок не менять 2) прогон §2 до/после: ноль красных 3) дальше — остальные items с «; » тем же приёмом
  НЕ ТРОГАТЬ: предмет и число проверок items; Scope/Deliverables; статусы; закрытые items P1.x, P2.1–P2.6
  ```

- (в силе) **Проекты флота с Boost/`.ai`-generated `CLAUDE.md` не покрыты процедурой
  P2.2** (`vintera/cms`, `sibintek-insiders`, `diabox`) — решение по ним не принято.
- (в силе) **Пять секций-кандидатов P2.1 остаются резидентными (436 ток)** — по D89
  это решение, не долг.
- (в силе) **гейт размера меряет файл целиком** · **токенная оценка продублирована в
  двух пакетах** · **`closure/P1.json` `inputs_sha256["phases/P1.md"]` больше не
  совпадает с живым файлом** (D87).
- (в силе, вне диффа этого захода) **Остаточная находка `verify-citations`:**
  `phases/P2.md` Completion Notes закрытого P2.3 несут сокращённую ссылку на
  `context-economy/SKILL.md` — адрес прежний.
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый
  `RESEARCH/AUDIT-loqum-findings.md`, неотслеживаемые `.swissknife/`, `audits/`) —
  этим заходом не тронут, не коммитился (не входит в Files фазы P2).

**Workarounds/Deferred/Open questions:** «—» / rules-миграция сверх пилота —
отложена / эмиссия `.mcp.json.example` A-класса — отложена до починки
`write_example` / сквозная правка формы `Validation` — отложена (см. Open risks) /
OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8 (без изменений этим заходом), см.
`open-questions.md`.
