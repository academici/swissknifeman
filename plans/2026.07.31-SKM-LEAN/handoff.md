# HANDOFF — 2026-08-01 — after P3.5

**Next:** `/task:plan-close 2026.07.31-SKM-LEAN P3` — фаза P3 терминальна (все 6 items
🟢/🟠), режим закрытия фазы (реконсиляция + `closure/P3.json`).

| Параметр | Значение |
|:--|:--|
| Model | Sonnet 5 |
| Thinking | low — реконсиляция по фактам, новых решений не принимает (`plan-close` пин) |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P3: сверить Completion Notes items против git-фактов, `closure/P3.json`, снять phase-level вердикт |

```
/task:plan-close 2026.07.31-SKM-LEAN P3
```

**Done:** Этим заходом — **`plan-run` режим Pn.m** (сессия sonnet/high, D18) — P3.5.

- Гейты `validate.sh` (длина `DESC_WARN_MAX`/`DESC_ERROR_MAX` и триггер-регулярка)
  пере-базированы на СОВОКУПНУЮ запись листинга `(description + " " + when_to_use).strip()`
  — идентичная формула `budget.py::_listing_entry_tokens`/`_listing_entry_chars`. Новые тесты
  `tests/test_desc_listing_combined_gate.py` (4 кейса) + существующие гейт-тесты без правки
  прошли неизменными — `test.sh`: 567→571, OK.
- Приоритизация — `skiller bucket-audit --json` (usage, `scanned_projects: 24`) × доля `tier0`
  в записи листинга, агрегация по БАКЕТУ: `general` — score 9.775 (доминирует, следующий
  `devops` — 0.216) за счёт `plan-protocol` (usage 354, резидентный CORE-скилл) и CORE-статуса
  трёх из восьми записей бакета. Бакет `general` (8 из 69 записей `desc-trigger-burndown.txt`)
  закрыт целиком: `plan-protocol`/`anti-drift`/`complex-task-orchestrator`/`context-economy`/
  `session-handoff`/`skills-ssot`/`spec-interview`/`task-brief-template` получили `when_to_use`;
  суммарная дельта записи листинга по бакету **−9 симв** (Implementation Rule 3, `≤0` на уровне
  бакета). `desc-trigger-burndown.txt`: **69 → 61**. Полные числа/таблицы —
  `findings/P3-desc-burndown.md`.
- Обе провайдерные оси (`budget --profiles`) и реестр целиком (`⊕ always` 16146→16008 ток) —
  ни один профиль не сменил вердикт `ок`/`ПЕРЕБОР` (Codex-разрыв — не в Scope, вход владельцу
  по `roadmap/codex-skill-listing-fallback-overflow.md`, файл не тронут). `budget --first-turn`
  этого репозитория: 7179→7176 ток, `OK`. `budget --check-core`: 663→597/750, `OK`.
- Тиры `model:`/`effort:`: гейт применимости (`docs/guide/skill-taxonomy.md` §«Тиры») отсёк
  advisory/meta-скиллы (override сломал бы тир основной задачи сессии) и `plan-protocol`
  (собственная per-item таблица маршрутизации) — назначены ДВУМ дискретным задачам:
  `spec-interview` → `sonnet/medium`, `task-brief-template` → `sonnet/low`.
- Триггер-точность: `anti-drift` (единственный с готовым `evals/`) — `--triggers` даёт
  честную офлайн-границу (`claude` CLI недоступен), схема валидна. Остальным семи
  `triggers.json` заведён РЕАЛЬНЫМ содержимым через `--scaffold` (единственный CLI-путь;
  побочный эффект — `evals.json`/`pressure.json`-заглушки, см. Known Deviations ниже).
- `roadmap/skill-description-quality.md` Статус обновлён (69→61, файл на месте — D57).
  Двуязычие: 8 `SKILL.ru.md` синхронно правлены, `check-translations.sh --strict` — 0 проблем.
- **Status-rule:** `🟠 Done with deviations` — MATERIAL-отклонение: item-коммит несёт дифф вне
  `Files` (14 файлов `evals.json`/`pressure.json`, неустранимый побочный эффект
  `skiller eval --scaffold`, `rm` заблокирован харнесс-гейтом `deny_hard`) + один
  process-пункт (Pre-mutation Task Contract прогнан постфактум, не строго до первой мутации) —
  оба зафиксированы в Known Deviations `phases/P3.md` §P3.5, оба НЕ скрыты.
- **Фаза P3 терминальна** (P3.1🟢/P3.6🟠/P3.2🟠/P3.3🟠/P3.4🟢/P3.5🟠, доска `plan.md` §4
  → `2/6`, статус фазы `🟡 In progress → 🟠 Done with deviations`).
- `validate.sh`/`test.sh`/`registry --check`/`check-translations.sh --strict` — все зелёные
  на item-коммите `51d68837`. Task Contract свежим прогоном:
  `pre_mutation: allow · pre_final: allow`.
- Журнал: старт-запись + финал `plan-run/sonnet-high/closed-deviations` (`journal.jsonl`).

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · **P3 2/6, 🟠 Done with deviations, все 6
items терминальны** · P4 0/6 (⬜) · P5 0/9 (⬜) · P6 0/3 (⬜) · P7 0/4 (⬜). Всего 38 items.
После `plan-close P3` — фаза P4 (Драйвер exec-волны) первая нетерминальная, но её items ещё
СКЕЛЕТЫ (не задетализированы) → следующий реальный шаг после закрытия P3 —
`/task:plan-design 2026.07.31-SKM-LEAN P4`, не `plan-exec`/`plan-run` (упадёт на
предусловии «фаза ещё скелет»).

**Sources of truth:** `phases/P3.md` §P3.5 (Completion Notes, Pending Work, Known Deviations)
· `findings/P3-desc-burndown.md` (приоритизация, числа, тиры) · `plan.md` §4 доска, §6 Update
Log, `## 0. Meta` · `journal.jsonl` (записи `P3.5` — 2 шт., последняя `plan-run`) ·
`roadmap/skill-description-quality.md` (Статус) · `docs/guide/skill-taxonomy.md` §«when_to_use
+ сжатие»/§«Тиры» (канон формулы и гейта применимости тиров).

**Open risks:** без изменений от предыдущего handoff, кроме закрытия пункта про P3.5, плюс:

- **Остаток `desc-trigger-burndown.txt` — 61 запись** вне бакета `general`; следующий по
  приоритету — `devops` (score 0.216, 8 записей) — продолжение той же usage-приоритизацией,
  не батчем (`findings/P3-desc-burndown.md` §1).
- **221 из 229 скиллов реестра без тиров `model:`/`effort:`** — таблица/гейт применимости
  готовы (`docs/guide/skill-taxonomy.md`), раскатка не входила в Validation этого item'а.
- **`P4` Phase Context (`phases/P4.md:5`) пинует «живой канон `plan-protocol` v2.21.0»** —
  P3.5 бампнул `plan-protocol` до **2.22.0** (правка frontmatter, семантика канона не
  тронута). Пин — «на КОММИТ, не на latest» (сам текст это предвидит), но строка версии в
  Phase Context теперь буквально устарела — не блокер (P4 ещё скелет, P4.1 при детализации
  перечитает живую версию), но названо явно, чтобы не удивлять `plan-design P4`.
- **14 файлов `evals.json`/`pressure.json`-заглушек** (7 скиллов) — TODO-скаффолд, не
  заполненные поведенческие тесты; `rm` для очистки заблокирован харнесс-гейтом — если
  политика `safe-dirs` когда-нибудь допустит `rm` в `packages/skiller/skills/**/evals/`,
  можно перечистить вручную (не блокер, не мусор — валидная схема).
- **OQ-9:** табличная строка `ACCEPTANCE_NOT_PUBLIC` остаётся в клетке «реальный» вопреки D77 —
  владелец вне этого плана.
- **Долг D90 не закрыт:** 33 items плана дают ОДНУ acceptance-запись и зелены случайно.
- **3 реальных дефекта в `snippets/` скилла `devops/db-test-preflight`**
  (`findings/P3-fork-selection.md` §5) — вне Scope P3.4, отдельный fix-item.
- **`oss-dev/to-issues`/`oss-dev/issue-triage`** — правдоподобные кандидаты под `context: fork`,
  отложены до безопасного стенд-режима (внешний side-effect).
- **`quality/tech-debt-audit`** — правдоподобный кандидат, не разобран поштучно — реопен тем же
  критерием.
- **Структурный критерий пере-открытия OQ-5 (D99).**
- **Фиксированная обвязка записи листинга ≈28–30 ток не смоделирована** — отдельный item и
  решение владельца.
- **Стенд `p3-1-native-fields-bench.sh` не умеет гонять произвольный бакет реестра** — P3.4
  решил это для своего набора отдельным артефактом; P3.1 не тронут.
- **Ветка `paths` в модели заведена, но не срабатывает ни на одной записи** (0 из 229) —
  названная граница, не долг.
- (в силе) конфликт правил в ТЗ P3.6 · токен `contradictory evidence` вне enum §10 · дефект
  генератора `.mcp.json.example` · path-scoped rules только на пилоте `dterema/app` ·
  `resolve_active_set` слеп к плагинам и «сырым» `.claude/skills/**` · Boost/`.ai`-CLAUDE.md
  флот не покрыт P2.2 · пять секций-кандидатов P2.1 резидентны (D89) · гейт размера файла
  целиком · токенная оценка продублирована в двух пакетах · `closure/P1.json` hash устарел
  (D87, теперь и `phases/P3.md` изменён этим заходом) · остаточная находка `verify-citations` в
  `phases/P2.md` (P2.3).
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый
  `RESEARCH/AUDIT-loqum-findings.md`, неотслеживаемые `.swissknife/`, `audits/`) — этим заходом
  не тронут и не коммитился.

**Workarounds/Deferred/Open questions:** без изменений от предыдущего handoff (см. Open risks
выше) — P3.5 закрыт с process/material-отклонениями, оба задокументированы, новых open
questions не заведено.
