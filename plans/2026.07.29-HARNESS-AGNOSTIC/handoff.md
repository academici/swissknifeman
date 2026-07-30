# HANDOFF — 2026-07-30 — after P3.1

**Next:** `/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P3.2`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — §3 Routing строка P3.1–P3.2 (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | P3.2 — реестр решений каркаса: packaging-модель, решения аудита, проверенные факты платформы |

````
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P3.2
````

**Что сделано этим заходом (`task:plan-exec`, Sonnet/medium — пин команды, совпадает с §3
Routing строкой P3.1).** Фаза P3 открыта: P3.1 закрыт `🟠 Done with deviations` (item-коммит
`f61ac378`). Пять доков `packages/skiller/docs/agent-framework/` приведены к дереву по
постатейной таблице `research/07-framework-canon-drift-2026-07-29.md` §1 — 10 из 11
расхождений сняты по доказательству из дерева (agent-packs, lock, фикс видимости, универсальные
роли, review-gate, dev-loop, ponytail-дисциплина `🔜`→`✅`); одно (`path-scoped rules — индекс
правил в hub`) остаётся `🔜` с точным сужением остатка (правила есть у пяти паков, индекса в
hub нет — код `generate-hub.sh`, вне скоупа item'а). Глобальная «Версия каркаса `v0.1.0-wip`»
удалена как противоречащая D24 (per-pack версионность) и заменена штампом `Проверено против
дерева: 2026-07-30` + машинно-проверяемой таблицей «пак → версия» (10 паков) — машинный якорь
будущего гейта свежести P3.3. `roles.md`/`agent-teams.md` несут записанную оговорку о
неприменимости `skills:`-preload к teammate-режиму (first-party
`code.claude.com/docs/en/agent-teams`, проверено 2026-07-29); `agent-teams.md` обновлён по
актуальным версиям/режимам/событиям/наследованию effort (дефолт `teammateMode` — `in-process` с
v2.1.179, три события команды, effort лида наследуется с v2.1.186). `skills-index-and-hub.md`
снят с `🔜` на `✅` (все три добавки Фазы 1 реализованы), уточнена формулировка «молча no-op» до
first-party формы (пропуск + debug-лог). `index.md` — рабочая ссылка на скилл
`system/agent-packs` вместо битой `#`.

**Session:** Claude Sonnet 5/medium (implementation/medium, `Exec = plan-exec` — совпадает с §3
Routing строкой P3.1, перебора/недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 целиком (9/9 — 5 🟢 + 4 🟠, формально не
закрыта `plan-close`'ом) · **P3.1 (1/6 фазы).**

**Карта «item → коммит» (P3, начало):**
P3.1 `f61ac378` (item-коммит, единственный — Files включал только пять доков
`agent-framework/`).

**Remaining:** Фаза P2 не закрыта формально (`plan-close P2`) — открытый долг с предыдущего
захода, не тронут этим item'ом. P3.2–P3.6 (5 items фазы P3) → P4 (5) → P5 (3). Итого **13 из
35** items плана ещё не исполнено (плюс формальные закрытия фаз P2 и, впоследствии, P3).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P3
`0/6` `🟡 In progress`) · `phases/P3.md` (Phase Context, P3.1 Completion Notes — таблица
«утверждение → было → стало → доказательство») · `research/07-framework-canon-drift-2026-07-29.md`
(вход P3.1–P3.2) · `findings/04-rag-agent-surface-and-skill-listing-2026-07-29.md` (Ф13–Ф18,
first-party платформенные факты) · пять доков `packages/skiller/docs/agent-framework/*` (новое
состояние канона) · `journal.jsonl`.

**Open risks:**
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2`) —
  не сделано ни этим, ни предыдущим заходом.
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** («Все `[NEEDS
  CLARIFICATION]` сняты…» матчится как сам маркер) для КАЖДОЙ фазы, чей статус переходит в
  `🟡`/`🟠`/`🟢` — предсуществующий класс на P0/P1/P2, теперь и на P3 (4 WARN, 0 ERROR при
  закрытии P3.1). Не контентный дефект, чинить в самом линтере (вне скоупа документационных
  items).
- **`packages/skiller/scripts/validate.sh` красный на дереве** — предсуществующий
  `ERROR: реестр устарел относительно источников` (DRIFT `package-architecture`/`skills.json`/
  `publication-lock.json`/`docs/guide/budget.md`), долг P0.5, не пересекается с `Files` P3.1.
  Требует отдельного фикс-item'а (`skiller registry` + коммит регенерированных артефактов) —
  дом либо P0.5 follow-up, либо `roadmap/`.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work): rules-каталоги
  есть у пяти паков, `generate-hub.sh` их не индексирует. Код, вне скоупа документационного
  item'а — кандидат `roadmap/` или отдельный item, если владелец сочтёт нужным.
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
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена девятый
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
  (P3.1 Pending Work).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта D27 (P3.1 подтвердил вывод: 37 скиллов > 8 KB не
  сломаны). Новых открытых вопросов P3.1 не добавил.
