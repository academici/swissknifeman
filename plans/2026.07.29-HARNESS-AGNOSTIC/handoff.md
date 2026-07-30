# HANDOFF — 2026-07-30 — after P3.5

**Next:** «ЗАПУСК ВРУЧНУЮ: implementation/high»

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — §3 Routing строка P3.6 (`implementation/high`, `Exec = manual`, D39/D47: effort выше пина `plan-exec`) |
| Context | continue (/clear) — ручной item под `task:plan-run` |
| Суть | P3.6 — приземление правил, вынесенных P1.1 из always-on канона, в скиллы реестра (расширение существующих либо новые, анти-bloat) |

Перед запуском выставить сессию: `/model sonnet`, затем `/effort high` (команда `task:plan-run`
модель НЕ пинит — Routing-гейт сверяет ФАКТИЧЕСКУЮ модель сессии, недобор = ROUTING-BLOCKED).

````
/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P3.6
````

Если предпочтителен ручной прогон без команды — тот же item по промпту:

````
Исполни item P3.6 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, implementation/high —
сессия sonnet/high; /task:plan-exec пинит sonnet/medium и по Routing-гейту отклонит item).

Порядок чтения (ровно этот, без повторов):
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — §0 Meta, §1 Context, §2 Execution Rules,
   §3 Routing (строка P3.6), §4 Status Board, §5 D23 (раскладка фазы P3 на шесть items)
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P3.md — Phase Context + P3.5 Completion Notes
   (вход item'а) + P3.6 целиком
4) Required Reads item'а P3.6 (в указанном там порядке; пункт 1 —
   plans/2026.07.29-HARNESS-AGNOSTIC/research/05-instruction-canon-routing.md раздел выносов
   целиком)

Дом плана — repo:/home/vostrikov/projects/packages/swissknifeman-next (см. `## 0. Meta` — этот
worktree/репо и есть Home, отдельного переключения не требуется).

Перед мутацией и перед закрытием собери Task Contract (task.task_contract.build +
route_evidence.capture_actual("implementation", "high", source="self-attested",
model="sonnet") — actual_route ЭТОЙ сессии) и убедись, что pre_mutation/pre_final = "allow";
красный код — см. таблицу в packages/task/commands/plan-exec.md п.2/п.7.

Исполняй СТРОГО Scope Included P3.6, не трогай Scope Excluded (P1.2/P1.3 канон, P3.5
описания вне заведённых/изменённых скиллов, корневые инструкции). Если перечень выносов P1.1
пуст — закрой item `⛔ Skipped by decision` с D-записью, не выдумывай скилл ради формы.

Пометь Status: 🟡 In progress до работы, journal.append --result in-progress перед началом.
````

**Session:** Sonnet 5/medium (implementation/medium — точное соответствие §3 Routing
строке P3.5, `Exec = plan-exec`).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · P2 (9/9 items закрыты — 5 🟢 + 4 🟠, формально
не закрыта `plan-close`'ом) · **P3.1 (🟠) + P3.2 (🟢) + P3.3 (🟠) + P3.4 (🟠) + P3.5 (🟠) —
5/6 items фазы P3.**

**Карта «item → коммит» (P3):**
P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` · P3.5 `1373fccf`
(у всех пяти item-коммит единственный).

**Remaining:** Фаза P2 не закрыта формально (`plan-close P2`) — открытый долг с предыдущих
заходов, не тронут этим item'ом. P3.6 (последний item фазы P3) → P4 (5) → P5 (3). Итого
**9 из 35** items плана ещё не исполнено (плюс формальные закрытия фаз P2 и, впоследствии, P3).

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P3
`1/6` `🟡 In progress`) · `phases/P3.md` (Phase Context, P3.1–P3.5 Completion Notes) ·
`roadmap.md` §«Карта запуска» · `roadmap/skill-description-quality.md` (Статус = остаток,
эта сессия) · `roadmap/README.md` (строка перенесена в «Частично реализовано», эта сессия) ·
`plans/2026.07.29-HARNESS-AGNOSTIC/artifacts/P3-skill-listing-budget.md` (раздел дельты P3.5,
эта сессия) · `packages/skiller/scripts/desc-trigger-burndown.txt` (новый, эта сессия) ·
`journal.jsonl`.

**Open risks:**
- **`packages/skiller/scripts/validate.sh` красный на ОДНОМ предсуществующем гейте** (долг
  P0.5): §14 `ERROR: протухшие переводы SKILL.ru.md→SKILL.md`
  (`skills/repository-bootstrap/package-architecture/SKILL.md`, 225-строчный чужой RU-источник
  — требует содержательного перевода, не механической правки, вне `Files` P3.4/P3.5).
  **Это ЕДИНСТВЕННЫЙ блокирующий долг для Validation P3.6** (его Validation тоже требует
  зелёного `validate.sh`). Чинится одним заходом: содержательный перевод из `SKILL.ru.md` +
  `check-translations.sh --stamp` + коммит. Дом: follow-up fix-item либо `roadmap/`.
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2`).
- **`plan-lint` DoR-гейт (SKILL §7) даёт false positive на строке-легенде** для КАЖДОЙ фазы,
  чей статус перешёл в `🟡`/`🟠`/`🟢` — четыре WARN (P0/P1/P2/P3), не контентный дефект.
- **69 длинных описаний без триггера** в `desc-trigger-burndown.txt` (унаследованный долг,
  P3.5) — сокращаются по одному при следующей содержательной правке каждого скилла, не
  батчем; `roadmap/skill-description-quality.md` держит критерий.
- **Структурный перебор фолбэк-бюджета обнаружения Codex** (9/10 профилей, WARN-гейт
  `validate.sh` §17 держит число видимым, дельта P3.5 не меняет вердикт ни для одного
  профиля) — три варианта решения записаны `roadmap/codex-skill-listing-fallback-overflow.md`,
  решение владельца не выбрано (OQ-7, D29).
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md`
  прогоном #4 не пополнена — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1 Pending Work) — кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 (review-gate) / 1/10 (`test-verifier`) / 6/10
  (ни того ни другого)** — измеренный факт в ledger'е P3.2, кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work).
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — merge-режим кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **`roadmap/README.md` несёт чужую несвязанную строку** (`agent-scoped-skill-loading-vs-
  connect-default.md`, владельческий черновик 2026-07-30, byte-в-byte не тронут этим item'ом,
  был в дереве до старта P3.5, соседствует с untracked `roadmap/2026.07.29-launch-block-
  command-row.md` — тоже не наш предмет).
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
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
  design-коммит, не `Files` какого-либо item'а. · Доказательство §16/§17 `validate.sh`
  изолированным раннером — вынужденная форма, пока §14 краснеет раньше по порядку.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (заведён P3.4, решение — OQ-7)
  · общий differ канона ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · регенерация
  `package-architecture` SKILL.ru.md→SKILL.md (долг P0.5, сужен P3.4 до одного файла) ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима
  · удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md` ·
  декларативный merge-режим `harness hooks --provider codex` (заведён P2.3) · декларативный
  merge-режим `harness agent-packs --provider codex render` (заведён P2.4) · точная схема
  Codex `apply_patch` (заведён P2.3) · отдельный machine-owned `check_command` для Codex
  `review-gate` (заведён P2.3) · CLI-флаг `harness doctor --settings --provider codex`
  (заведён P2.4) · формальное закрытие фазы P2 (`plan-close`) · индекс `path-scoped rules` в
  hub (P3.1 Pending Work) · унификация verification-контрактов паков 4/10→10/10 (P3.2 Open
  risks) · добор таблицы внешних источников в `references/framework-audits.md` (P3.3
  Pending Work) · сокращение 69 длинных описаний без триггера, one-way (P3.5 Pending Work) ·
  рычаг №4 владельца (сжатие описаний ради слотов, ECO-OPT D74, OQ-7).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — ИЗМЕРЕН P3.4/P3.5,
  решение между тремя вариантами (`roadmap/codex-skill-listing-fallback-overflow.md`) остаётся
  открытым · OQ-8 дрейф канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1); OQ-2 закрыта D71, OQ-1 — D31, OQ-4 закрыта
  P3.4 записью канона авторинга (D27). Новых открытых вопросов P3.5 не добавил.
