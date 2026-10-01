# Task: облегчить исполнение планов — review как пункт плана, пул моделей, мягкие гейты

**Статус:** 🟡 утверждено 2026-10-01 (с правкой: `gpt-6.1-sol` — frontier); L1–L5 выполнены локально, ожидает финальной валидации и отдельного code-review.
**Дата:** 2026-10-01. **База:** `cd184462`. **Формат:** одно ограниченное задание, без SKM-плана.
**Источник:** [полевой разбор CoreX P04.2](../../roadmap/2026.09.30-task-execution-review-separation-diagnostic.md)
(6:03 elapsed, 353 exec, 5 compacts) + требования владельца от 2026-10-01.
Все выводы ниже подтверждены чтением кода/канона в этой сессии; внешних утверждений нет.

## Цель владельца

Task проектирует план, режет на фазы и следит за исполнением. Он не должен сам
плодить проверки. Нужно: (1) ревью — отдельные пункты плана, а не «каждый пункт + другой
моделью»; (2) свобода порядка детализации фаз; (3) смена модели в пределах пула без
правки плана и без стопов; (4) Python-гейты не объявляют план «недовыполненным» без
реальной причины.

## Аудит: что именно создаёт трение

| # | Находка | Где | Эффект |
|:--|:--|:--|:--|
| F1 | Execution требует **все** объявленные фазы детализированы + `finish` + GREEN `plan-audit design` по fingerprint **всего** плана. Любая правка любой фазы → `PLAN_DESIGN_AUDIT_STALE`. | `plan_readiness.design_snapshot/design_gate`, вызов из `plan_work.prepare`, `plan_recovery.start`, `plan_delivery`, `plan_repeat`; текст `plan-exec.md`, `design-mode.md` | «Детализировать → исполнить → детализировать» невозможно; CoreX спасал owner-waiver D66 |
| F2 | Модель→класс: Codex/Cursor — точное совпадение `_one(...)`; Cursor игнорирует `model_inventory`; модель с несколькими ролями или неизвестная версия → `ROUTE_LAUNCH_MISMATCH`, класс причин `evidence-forged`. Claude: семейство `fable` не в карте. | `route_evidence_{codex,cursor,claude}.py`, `task_contract.py:168` | Смена модели внутри семейства/более сильная модель = «подделка evidence» |
| F3 | Более сильная модель блокируется: `ECONOMY_ROUTE_OVERSHOOT` для pinned `plan-exec` с `self/light` review; для design — `frontier/xhigh` без акцепта владельца. | `task_contract.py:~1600`, `plan_work._design_route`, `command_render.py:~507` | Стоп при «лучшей» модели; план переписывают |
| F4 | Пул моделей — один плоский inventory без пересечения ролей, без alias/pattern, без статуса актуальности. Классы жёстко 1 pin на класс. | `configs/command-routing.json`, `docs/reference/provider-model-roles.md` | Новая модель = правка кода/плана |
| F5 | Review не имеет места в форме плана: он дописывается в `Validation` каждого пункта (`Independent review: reviewer model != executor`), компилируется как `shell-command`; execution-sheet у дизайнера обрастает колонками Executor/Reviewer/Auto-fix. Канон не говорит, что review — отдельный пункт. | `plan-template.md`, `phase-template.md`, `plan-design.md`, `SKILL.md §5`; `task_contract.build` (Validation → shell-command) | Ревью после каждого пункта, повтор всей матрицы, цикл на шесть часов |
| F6 | Validation пункта разрешает дублирование: «sealed replay + all declared Validation there», один bullet на несколько suite. Канон не говорит, где живёт широкий прогон. | `plan-exec.md`, `SKILL.md §4`, guidance дизайна | Executor повторяет root/Arch/mutations/PG на каждом участнике |
| F7 | `check-open`: `TASK_WORKSET_INCOMPLETE` запрещает final, пока в batch-receipt остались нестартовавшие члены. | `terminal_admission.pre_final_open_runs` | «Не доделано» при честной остановке на границе фазы/ревью |
| F8 | Нет правила про вывод инструментов (большие JSON/логи в контекст). | `plan-exec.md` | 3.2 MB tool outputs, 5 compact (диагн. §11) |

Не затрагивается (оставлено строгим): terminal-evidence, closure/anchors, security/authority,
audit-admission, route UNDERSHOOT (слабая модель по-прежнему стопит), hard-risk review.

## Решения (по умолчанию принимаются при «ок»)

| ID | Решение | Альтернатива |
|:--|:--|:--|
| D1 | Whole-plan design audit становится **opt-in**: `**Design Audit:** required` в `plan.md`. По умолчанию gate = готовность фаз выбранных пунктов. Снимает порядок «все фазы → audit → execution» (roadmap 2026.09.17). | оставить как есть |
| D2 | Класс actual-модели = **максимум** класс-ролей её записи в пуле; `actual ≥ required` всегда допустим. Overshoot — запись в route (`over`), не блокировка. UNDERSHOOT остаётся блокировкой. | блок overshoot только для `economy` |
| D3 | Неизвестная модель → `ROUTE-UNVERIFIABLE` (nonterminal, `evidence-missing`) с подсказкой «добавь в пул», не `evidence-forged`. Owner-attestation остаётся путём обхода. | оставить forged |
| D4 | Review — **обычный пункт плана** (числовой ID `Pn.m`, заголовок `Ревью Pn`, read-only, Deliverable = verdict-файл). Новый синтаксис `Pn.R` не вводится (ID-regex в ~9 модулях). | ввести `Pn.R` |
| D5 | `TASK_WORKSET_INCOMPLETE` перестаёт блокировать final (остаётся в отчёте; final обязан назвать Next). Открытый run по-прежнему блокирует. | не трогать |
| D6 | Staged `Validation` / per-command receipts / owner-stop continuity (W0–W4 диагностики) — **вне этого задания**: D4 закрывает основной сценарий формой плана. | сразу делать W0–W4 |
| D7 | Классификация моделей в пуле — моя на основе существующего inventory (`gpt-6-sol`: implementation+review; `gpt-6-astra`: frontier). Владелец правит одну строку конфига. | — |

## Шаги

### L1. Phase-scoped design gate (код + канон) — закрывает F1
- `plan_readiness.validate_execution_design(plan_dir, item_ids=None)`: по умолчанию проверяет
  только фазы целевых пунктов (не skeleton, обязательные поля item); остальные объявленные фазы
  могут быть skeleton/backlog/не аудированы; журнал `finish`/audit не требуется.
- Strict-режим (как сейчас, вместе с owner-waiver) — только при `Design Audit: required`.
- `design_gate()` возвращает `mode`; передать `item_ids` во всех 5 вызовах.
- Канон: `plan-exec.md`, `plan-design.md`, `design-mode.md`, `SKILL.md §1/§4`: два допустимых пути —
  detail-all или detail-one→execute→detail-next; audit дизайна — по запросу/`required`.
- Roadmap 2026.09.17: пометить правило «весь план → audit → execution» заменённым.
- **Acceptance:** тесты: skeleton P2 не блокирует exec P1.1; изменённая P2 не делает P1 stale;
  `required` сохраняет прежнее поведение (существующие waiver-тесты зелёные).

### L2. Пул моделей и допуск маршрута — закрывает F2, F3, F4
- `command-routing.json`: `model_inventory.entries` → пул: `id`, `roles` (классы + теги
  `review|design|audit|explore`), опц. `aliases`, `patterns` (regex), `status: active|legacy`.
  Заполнить для claude-code (`fable`, `opus`, `sonnet`, `haiku`), codex, cursor; роли могут пересекаться.
- Один резолвер `route_evidence.resolve_model_class(provider, model, metadata)`: exact → alias →
  pattern → family-token (Claude); класс = max класс-ролей; legacy допустим с предупреждением.
  Три адаптера используют его; Cursor читает inventory.
- Убрать блокировку overshoot (`task_contract`, `_design_route`, `command_render` → всегда `info`).
- Неизвестная модель → `ROUTE_MODEL_UNKNOWN` (категория `evidence-missing`).
- Регенерировать `provider-model-roles.md` и provider-команды штатным генератором.
- **Acceptance:** `claude-sonnet-5-5` / `claude-fable-*` / `grok-4.7` / модель с двумя ролями
  разрешаются; более сильная модель допускается; более слабая — `ROUTE_UNDERSHOOT`;
  неизвестная — UNVERIFIABLE; тесты route_evidence_* и parity обновлены.

### L3. Review как пункт плана — закрывает F5
- `plan-template.md`, `phase-template.md`, `design-mode.md`, `plan-design.md`, `SKILL.md §5`:
  - Review per item по умолчанию `none` (self-check + affected tests); `full` — только named hard risk.
  - В конце фазы — пункт `Ревью Pn` (read-only, verdict-файл, Routing `Review: none`);
    у большой фазы — срезы: `Ревью Pn (P1–P3)` между срезами. Findings → одно owning-исправление,
    повторное ревью проверяет только findings.
  - Reviewer = свежая сессия; «другая модель» только по явному требованию владельца или hard risk;
    кандидат берётся из пула по тегу `review`.
  - Execution-sheet: колонки Executor/Reviewer — рекомендация, не контракт; admission по классу/effort.
  - Запрет в `Validation` пункта строк `Independent review…` (они — отдельный пункт).
- **Acceptance:** шаблоны и guidance согласованы; `plan-lint` примера плана с review-пунктом зелёный.

### L4. Лёгкое исполнение — закрывает F6, F7, F8
- `plan-exec.md`/`plan-run.md`/`execution-mode.md`: Validation пункта = affected-команды этого
  пункта; широкие suite (root/package/PG/mutations/replay) — один раз в review/accepting-пункте
  фазы; replay доказывает воспроизводимость, не повторяет behavioral suite; вывод больших
  логов — в файл, в контекст status/counts/≤N диагностик.
- `terminal_admission`: `TASK_WORKSET_INCOMPLETE` → `final_allowed: true` (D5).
- **Acceptance:** тест check-open: открытый run блокирует, нестартовавший остаток — нет.

### L5. Философия и поставка
- `task-development-philosophy` → v0.3.0: принципы *Review placement*, *Design pacing*,
  *Model pool* (+ decision test). Регенерировать проекции `skiller registry`.
- CHANGELOG `[Unreleased]`; bump `task` (минор) по `release-discipline`.
- Проверка: адресные тесты по ходу; **один** `bash packages/task/scripts/validate.sh` и
  `skiller registry`/`scripts/validate.sh` в конце; ревью — `/code-review` отдельной сессией.

## Порядок и бюджет
L1 → L2 → L3 → L4 → L5. Широкая валидация одна, в конце. Без отдельного аудита этого
задания. Если L2-регенерация выявит дрейф сверх ожидаемого — чиню владельца дрейфа, не
расширяю scope.

## Вне scope / остаток
- W0–W4 диагностики (staged Validation, scope-aware receipts, owner-stop continuity) — отдельное
  решение после пилота на реальном плане с review-пунктами.
- Cursor explicit-model *effort*-evidence ([2026.09.23](../../roadmap/2026.09.23-task-cursor-explicit-model-route-evidence-gap.md)) — резолвер
  закрывает только model→class.
- Установка в consumer-проекты и fleet rollout.

## Выполнено 2026-10-01 (локально, без коммита)

| Шаг | Результат |
|:--|:--|
| L1 | `plan_readiness.validate_execution_design(plan_dir, item_ids)` phase-scoped; strict только при `Design Audit: required`; `design-gate` отдаёт `mode`. Пять вызовов передают пункты. Канон: plan-exec/design/design-mode/SKILL. |
| L2 | `route_evidence.resolve_model_class` — один резолвер для трёх провайдеров; пул в `command-routing.json` (aliases/patterns/`retired`, max class; добавлен `fable`, `gpt-6.1-sol` — frontier). Overshoot не блокирует (`task_contract`, `plan_work`, `command_render`). Неизвестная модель → `ROUTE_LAUNCH_UNAVAILABLE`. |
| L3 | SKILL §5, plan-template, plan-design, review-mode: review как пункт `Ревью Pn`, Review по умолчанию `none`. |
| L4 | `TASK_WORKSET_REMAINING` не запрещает final; правила validation economy и bounded output в plan-exec/plan-run/execution-mode. |
| L5 | `task-development-philosophy` 0.3.0, CHANGELOG, регенерация `skiller registry` и provider-проекций. |

**Дополнительно (второй проход, «отшлифовать пакет»):**
- Исправлен собственный регресс: неизвестная явная Cursor-модель проваливалась в fallback на `cli-config`;
  теперь отдельный код `ROUTE_MODEL_UNKNOWN` (fail-closed), тест добавлен.
- W2 (часть): свежесть validation-receipt не зависит от git `head`; идентичность окружения — family+major.minor+OS
  (раньше patch/kernel/путь интерпретатора протухали receipts между сессиями и провайдерами).
- W4: owner-requested new session / pause сохраняют checkpoint без route/batch/capability-аттестации текущего executor.
- Docs: control-plane-map, design-audit-waiver, provider-model-roles (генерируется) приведены к новому gate и пулу.
- `test_plan_continuity` импортирует `fixtures` (раньше падал при одиночном запуске).
- Оставлено осознанно (см. «Вне scope»): W1 (стадии Validation — требуют схемы контракта), per-command footprint,
  harness Stop-hook (`stop_hook_active` как bounded escape) — затрагивает fleet-хуки.

**Проверки:** `packages/task/scripts/validate.sh` — OK (1263 тестов). `skiller validate` — 730/731:
`test_dry_run_reaches_skiller_without_error` падает с `RELEASE_IMMUTABLE_TUPLE general@0.15.3,
package.skiller@0.17.14` и на чистом HEAD `cd184462` — требует bump версий при релизе, не связано с этим заданием.
Исправлен ранее сломанный хвост `test_design_finish_still_rejects_missing_input_for_unfinished_work`.

**Не сделано:** commit/PR, bump версий, `/code-review` отдельной сессией, W0–W4, effort-evidence Cursor.
