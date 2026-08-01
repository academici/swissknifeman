# HANDOFF — 2026-08-01 — after P3

**Next:** «ЗАПУСК ВРУЧНУЮ: `frontier/high`» — P4.1 `Exec = manual` (`roadmap.md` строка P4.1);
Execution Rules плана и `roadmap.md` не называют `plan-exec`/`plan-run` для P4.1, издающего
голый промпт item'а отдельным code-block.

| Параметр | Значение |
|:--|:--|
| Model | Opus 5 |
| Thinking | high — замораживаемая поверхность драйвера, решения необратимы (`roadmap.md` P4.1) |
| Context | continue (/clear) — ручной item |
| Суть | Издать `root/contracts/driver-plan-protocol-v2.md` — переиздание parse-контракта против живого `plan-protocol` v2.21.0+ |

```
Прочитай plans/2026.07.31-SKM-LEAN/phases/P4.md item P4.1 целиком (Intent, Why, Scope
Included/Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance,
Validation, Deliverables) и исполни его строго по ТЗ. Пометь item 🟡 In progress до начала
практической работы, затем закрой по правилам plan-protocol (Task Contract pre-mutation/
pre-final, Completion Notes, Known Deviations, журнал, два коммита).
```

**Done:** Этим заходом — **`plan-close` режим Pn (закрытие фазы)** (сессия sonnet/low,
механическая реконсиляция) — фаза **P3**.

- Все 6 items фазы терминальны: P3.1 🟢 · P3.6 🟠 · P3.2 🟠 · P3.3 🟠 · P3.4 🟢 · P3.5 🟠
  (сверено с `## Phase Status` `phases/P3.md` и `## 4. Phase Index & Status Board` `plan.md` —
  без расхождений, `2/6` до и после).
- Docs-sync: **не требуется** — `docs/guide/skill-taxonomy.md` (критерий отбора под форк +
  таблица тиров) и `docs/guide/cli.md` (строка «исключено записей») уже обновлены внутри
  item-коммитов `8f5206ba`/`51d68837`/`a4adcd3b`.
- `## Phase Handoff` в `phases/P3.md` заполнен: сдача, механически собранные Known Deviations
  всех 6 items (перечислены по item'ам, без пересказа), docs-sync вердикт, «что дальше».
- `closure/P3.json` (Closure Protocol v1) записан: 6 items, `evidence_class: real`, гейты
  `validate.sh`/`test.sh`/`registry --check` PASS, метрики (`items_green_of_total: 2/6`,
  `first_turn_repo_tokens: 7179 → 7176`, `desc_trigger_burndown: 69 → 61`,
  `context_fork_skills: 4`), `limitations` — три пункта (нераскатанный `paths:`,
  `disable-model-invocation` за пределы пилота, остаток burn-down/тиров).
- `plan.md`: строка `## 6. Update Log` добавлена, `Last Updated` в `## 0. Meta` обновлён;
  `Status` плана НЕ трогается — P4–P7 ещё не терминальны, план не закрыт целиком.
- Журнал: `plan-close/sonnet-low/closed-deviations` для item `P3` (`journal.jsonl`).
- Все фазы плана НЕ терминальны целиком (P4–P7 ещё `⬜`) — `plans/ACTIVE.md` не тронут,
  остаётся `2026.07.31-SKM-LEAN`.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · **P3 2/6, 🟠 Done with deviations,
терминальна, `closure/P3.json` записан** · P4 0/6 (⬜) · P5 0/9 (⬜) · P6 0/3 (⬜) · P7 0/4
(⬜). Всего 38 items. P4.1 — первый нетерминальный item (уже задетализирован, не скелет).

**Sources of truth:** `phases/P3.md` §Phase Handoff (сдача фазы, собранные Known Deviations) ·
`closure/P3.json` · `plan.md` §4 доска, §6 Update Log, `## 0. Meta` · `journal.jsonl` (запись
`P3`, `plan-close/closed-deviations`) · `roadmap.md` (маршрут P4.1 — `Exec = manual`).

**Open risks:** без изменений по содержанию от предыдущего handoff, кроме закрытия пункта про
P3, плюс:

- **Остаток `desc-trigger-burndown.txt` — 61 запись** вне бакета `general`; следующий по
  приоритету — `devops` (score 0.216, 8 записей) — продолжение той же usage-приоритизацией,
  не батчем (`findings/P3-desc-burndown.md` §1). Адрес — вне этого плана (roadmap-долг фазы P3).
- **221 из 229 скиллов реестра без тиров `model:`/`effort:`** — таблица/гейт применимости
  готовы (`docs/guide/skill-taxonomy.md`), раскатка не входила в Validation P3.5.
- **`paths:` не раскатан на реестр** (0 из 229) — отрицательный вердикт (доминирование
  `disable-model-invocation`, D98) — названная граница, не долг.
- **`disable-model-invocation` не раскатан за пределы 4 пилотных скиллов** — решение владельца
  OQ-5 → (A), структурный критерий пере-открытия D99.
- **14 файлов `evals.json`/`pressure.json`-заглушек** (7 скиллов) — TODO-скаффолд, `rm`
  заблокирован харнесс-гейтом — не мусор, валидная схема.
- **OQ-9:** табличная строка `ACCEPTANCE_NOT_PUBLIC` остаётся в клетке «реальный» вопреки D77 —
  владелец вне этого плана.
- **Долг D90 не закрыт:** 33 items плана дают ОДНУ acceptance-запись и зелены случайно.
- **3 реальных дефекта в `snippets/` скилла `devops/db-test-preflight`**
  (`findings/P3-fork-selection.md` §5) — вне Scope P3.4, отдельный fix-item.
- **`oss-dev/to-issues`/`oss-dev/issue-triage`** — правдоподобные кандидаты под `context: fork`,
  отложены до безопасного стенд-режима (внешний side-effect).
- **`quality/tech-debt-audit`** — правдоподобный кандидат, не разобран поштучно — реопен тем же
  критерием.
- **Фиксированная обвязка записи листинга ≈28–30 ток не смоделирована** — отдельный item и
  решение владельца.
- **Стенд `p3-1-native-fields-bench.sh` не умеет гонять произвольный бакет реестра** — граница
  осталась как есть.
- (в силе) конфликт правил в ТЗ P3.6 · токен `contradictory evidence` вне enum §10 · дефект
  генератора `.mcp.json.example` · path-scoped rules только на пилоте `dterema/app` ·
  `resolve_active_set` слеп к плагинам и «сырым» `.claude/skills/**` · Boost/`.ai`-CLAUDE.md
  флот не покрыт P2.2 · пять секций-кандидатов P2.1 резидентны (D89) · гейт размера файла
  целиком · токенная оценка продублирована в двух пакетах · `closure/P1.json` hash устарел
  (D87, теперь и `phases/P3.md` снова изменён этим заходом) · остаточная находка
  `verify-citations` в `phases/P2.md` (P2.3).
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый
  `RESEARCH/AUDIT-loqum-findings.md`, неотслеживаемые `.swissknife/`, `audits/`) — этим заходом
  не тронут и не коммитился.

**Workarounds/Deferred/Open questions:** без изменений от предыдущего handoff (см. Open risks
выше) — фаза P3 закрыта, новых open questions этим заходом не заведено.
