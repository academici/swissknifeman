# HANDOFF — 2026-07-30 — after P3.3

**Next:** **ЗАПУСК ВРУЧНУЮ: implementation/high**

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — §3 Routing строка P3.4 (`implementation/high`, `Exec = manual`) |
| Context | continue (/clear) — ручной item |
| Суть | P3.4 — вторая (Codex) модель бюджета обнаружения в `budget.py`, флаг `--provider`, тесты, WARN-гейт, артефакт замера |

**P3.4 — `Exec = manual` (D39/D47: effort `high` выше пина `task:plan-exec`).** Голая команда
`/task:plan-exec` этот item отклонит гейтом п. 2 протокола. Запуск — ЛИБО голым промтом ниже
под сессией `implementation/high`, ЛИБО `/model sonnet` + `/effort high` + `/task:plan-run
2026.07.29-HARNESS-AGNOSTIC P3.4` (D18).

````
Это ИСПОЛНЕНИЕ item'а мастер-плана (plan-протокол), запущенное под implementation/high
(Exec = manual, §3 Routing плана `2026.07.29-HARNESS-AGNOSTIC`). Ввод: «2026.07.29-HARNESS-AGNOSTIC P3.4».
Прочитай ПОЛНЫЙ протокол исполнения командой `task:plan-run` (packages/task/commands/plan-run.md)
и исполни его РОВНО по этому протоколу для item'а P3.4.
````

**Session:** Claude Opus 5/high (frontier/high при предписанных §3 Routing
`implementation/high` — перебор тира, записан в Known Deviations P3.3; недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 целиком (9/9 — 5 🟢 + 4 🟠, формально не
закрыта `plan-close`'ом) · **P3.1 (🟠) + P3.2 (🟢) + P3.3 (🟠) — 3/6 фазы P3.**

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` (у всех трёх item-коммит единственный).

**Remaining:** Фаза P2 не закрыта формально (`plan-close P2`) — открытый долг с предыдущих
заходов, не тронут этим item'ом. P3.4–P3.6 (3 items фазы P3) → P4 (5) → P5 (3). Итого
**11 из 35** items плана ещё не исполнено (плюс формальные закрытия фаз P2 и, впоследствии, P3).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P3
`1/6` `🟡 In progress`) · `phases/P3.md` (Phase Context, P3.1–P3.3 Completion Notes) ·
`roadmap.md` §«Карта запуска» (P3.4 — solo, `plan-run`, implementation/high) ·
`findings/04-rag-agent-surface-and-skill-listing-2026-07-29.md` (Ф13/Ф14 — вход P3.4) ·
`packages/skiller/docs/audits/2026-07-29-harness-agnostic{,.raw}.md` (архив прогона) ·
`packages/skiller/scripts/validate.sh` §16 (гейт свежести канона) · `journal.jsonl`.

**Open risks:**
- **`packages/skiller/scripts/validate.sh` красный на дереве по ДВУМ предсуществующим
  гейтам** (долг P0.5, не пересекается с `Files` P3.1/P3.2/P3.3): §12b `ERROR: реестр
  устарел относительно источников` (DRIFT `skills.json`, `.claude/skills/package-architecture/
  SKILL.md`, `.agents/skills/package-architecture/SKILL.md`, `adapters/repository-bootstrap/
  publication-lock.json`, `docs/guide/budget.md`) и §14 `ERROR: протухшие переводы
  SKILL.ru.md→SKILL.md` (`skills/repository-bootstrap/package-architecture/SKILL.md`).
  **Оба срабатывают РАНЬШЕ новой секции 16**, поэтому гейт свежести канона в полном прогоне
  не виден и доказан изолированным раннером. Чинится одним заходом: `bash bin/skiller
  registry` + регенерация EN-канона из `SKILL.ru.md` + `check-translations.sh --stamp` +
  коммит регенерированных артефактов. **Это блокирующий долг для Validation P3.4/P3.5/P3.6** —
  каждый из них требует зелёного `validate.sh`. Дом: follow-up fix-item либо `roadmap/`.
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2`).
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** («Все `[NEEDS
  CLARIFICATION]` сняты…» матчится как сам маркер) для КАЖДОЙ фазы, чей статус перешёл в
  `🟡`/`🟠`/`🟢` — четыре WARN (P0/P1/P2/P3). Не контентный дефект, чинить в самом линтере.
- **`plan-lint` phase-first WARN**: «P3 содержит активные 🟡 items, хотя P2 ещё не терминальна»
  — производная того же незакрытого P2; снимается его `plan-close`.
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md`
  прогоном #4 не пополнена (`Scope Included` P3.3 её не называл) — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work): rules-каталоги
  есть у пяти паков, `generate-hub.sh` их не индексирует. Кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10
  (ни того ни другого)** — измеренный факт в ledger'е P3.2, кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work).
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — merge-режим кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена
  одиннадцатый заход подряд — не наш предмет.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют; новые страницы
  архива (`docs/audits/2026-07-29-harness-agnostic{,.raw}.md`) сборкой не проверены.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а. · Доказательство гейта свежести канона
  изолированным раннером (текст секции 16 извлечён `sed`'ом из закоммиченного `validate.sh`)
  — вынужденная форма, пока §12b/§14 краснеют раньше.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (OQ-7) · общий differ канона
  ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · `skiller registry` не прогнан (P0.5 —
  теперь блокирует Validation оставшихся items P3) · раскатка на потребителей (D45) ·
  push/PR/тег и публикация доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский
  канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима · удаление pre-image'ов P1.5 ·
  починка архивных упоминаний A7 в `phases/P1.md` · декларативный merge-режим `harness hooks
  --provider codex` (заведён P2.3) · декларативный merge-режим `harness agent-packs --provider
  codex render` (заведён P2.4) · точная схема Codex `apply_patch` (заведён P2.3) · отдельный
  machine-owned `check_command` для Codex `review-gate` (заведён P2.3) · CLI-флаг `harness
  doctor --settings --provider codex` (заведён P2.4) · формальное закрытие фазы P2
  (`plan-close`) · индекс `path-scoped rules` в hub (P3.1 Pending Work) · унификация
  verification-контрактов паков 4/10→10/10 (P3.2 Open risks) · добор таблицы внешних
  источников в `references/framework-audits.md` (P3.3 Pending Work).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта D27. Новых открытых вопросов P3.3 не добавил.
