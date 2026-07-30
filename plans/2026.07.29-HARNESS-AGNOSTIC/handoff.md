# HANDOFF — 2026-07-30 — after P3.2

**Next:** `/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P3.3`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — §3 Routing строка P3.3 (`implementation/high`, `Exec = manual`) |
| Context | continue (/clear) — ручной item |
| Суть | P3.3 — ЗАПУСК ВРУЧНУЮ: замыкание петли аудита, архив прогона, машинный гейт свежести таблицы «пак → версия» |

**P3.3 — `Exec = manual` (D39/D47: effort `high` выше пина `task:plan-exec`).** Голая команда
`/task:plan-exec` этот item отклонит гейтом п. 2 протокола. Запуск — ЛИБО голым промтом ниже
под сессией `implementation/high`, ЛИБО `/model opus` + `/effort high` + `/task:plan-run
2026.07.29-HARNESS-AGNOSTIC P3.3` (D18).

````
Это ИСПОЛНЕНИЕ item'а мастер-плана (plan-протокол), запущенное под implementation/high
(Exec = manual, §3 Routing плана `2026.07.29-HARNESS-AGNOSTIC`). Ввод: «2026.07.29-HARNESS-AGNOSTIC P3.3».
Прочитай ПОЛНЫЙ протокол исполнения командой `task:plan-run` (packages/task/commands/plan-run.md)
и исполни его РОВНО по этому протоколу для item'а P3.3.
````

**Session:** Claude Sonnet 5/medium (implementation/medium, `Exec = plan-exec` — совпадает с §3
Routing строкой P3.1–P3.2, перебора/недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 целиком (9/9 — 5 🟢 + 4 🟠, формально не
закрыта `plan-close`'ом) · **P3.1 (🟠) + P3.2 (🟢) — 2/6 фазы P3.**

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` (item-коммит, единственный) · P3.2 `dd6a1404` (item-коммит, единственный —
`Files` включал только `decisions-ledger.md`).

**Remaining:** Фаза P2 не закрыта формально (`plan-close P2`) — открытый долг с предыдущего
захода, не тронут этим item'ом. P3.3–P3.6 (4 items фазы P3) → P4 (5) → P5 (3). Итого **12 из
35** items плана ещё не исполнено (плюс формальные закрытия фаз P2 и, впоследствии, P3).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P3
`1/6` `🟡 In progress`) · `phases/P3.md` (Phase Context, P3.1/P3.2 Completion Notes) ·
`research/01-audit-adjudication.md` §12 · `research/07-framework-canon-drift-2026-07-29.md`
(вход P3.1–P3.2) · `findings/04-rag-agent-surface-and-skill-listing-2026-07-29.md` (Ф13–Ф18,
first-party платформенные факты) · `packages/skiller/docs/agent-framework/decisions-ledger.md`
(новая секция «Из аудита #4») · `journal.jsonl`.

**Open risks:**
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2`) —
  не сделано ни этим, ни предыдущими заходами.
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** («Все `[NEEDS
  CLARIFICATION]` сняты…» матчится как сам маркер) для КАЖДОЙ фазы, чей статус переходит в
  `🟡`/`🟠`/`🟢` — предсуществующий класс на P0/P1/P2, теперь и на P3. Не контентный дефект,
  чинить в самом линтере (вне скоупа документационных items).
- **`packages/skiller/scripts/validate.sh` красный на дереве** — предсуществующий
  `ERROR: реестр устарел относительно источников` (DRIFT `package-architecture`/`skills.json`/
  `publication-lock.json`/`docs/guide/budget.md`), долг P0.5, не пересекается с `Files` P3.1/
  P3.2. Требует отдельного фикс-item'а (`skiller registry` + коммит регенерированных
  артефактов) — дом либо P0.5 follow-up, либо `roadmap/`.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work): rules-каталоги
  есть у пяти паков, `generate-hub.sh` их не индексирует. Код, вне скоупа документационного
  item'а — кандидат `roadmap/` или отдельный item, если владелец сочтёт нужным.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10
  (ни того ни другого)** — записано в ledger'е P3.2 как измеренный факт, не закрыт кодом; дом —
  `roadmap/`, если владелец решит унифицировать.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work
  (1)): движок настоящий, покрыт тестами напрямую, роутинг вне `Files` P2.4. Дом — follow-up
  item или `roadmap/`.
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`**: оператор обязан перечислять ВСЕ желаемые
  поверхности/паки при каждом вызове; merge-режим — кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`
  (`findings/03`); носитель — `roadmap/`.
- **`plan-lint` WARN — три предсуществующих**: `NEEDS CLARIFICATION`-маркеры в DoR-прозе фаз
  P0/P1/P2 (не предмет закрытых items).
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена десятый
  заход подряд — не наш предмет.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом правки
  `roadmap/`, спека не заведена.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8 (`roadmap/instruction-authorize-order.md`),
  реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (OQ-7) · общий differ канона
  ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · `skiller registry` не прогнан (P0.5, теперь
  ещё и красный DRIFT на дереве) · раскатка на потребителей (D45) · push/PR/тег и публикация
  доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore`
  (Р5) · раскатка adoption-режима · удаление pre-image'ов P1.5 · починка архивных упоминаний A7
  в `phases/P1.md` · декларативный merge-режим `harness hooks --provider codex` (заведён P2.3) ·
  декларативный merge-режим `harness agent-packs --provider codex render` (заведён P2.4) ·
  точная схема Codex `apply_patch` (заведён P2.3) · отдельный machine-owned `check_command` для
  Codex `review-gate` (заведён P2.3) · CLI-флаг `harness doctor --settings --provider codex`
  (заведён P2.4) · формальное закрытие фазы P2 (`plan-close`) · индекс `path-scoped rules` в hub
  (P3.1 Pending Work) · унификация verification-контрактов паков 4/10→10/10 (P3.2 Open risks).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта D27 (P3.1 подтвердил вывод: 37 скиллов > 8 KB не
  сломаны). Новых открытых вопросов P3.2 не добавил.
