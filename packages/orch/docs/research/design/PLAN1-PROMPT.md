# Задание для новой сессии: спроектировать Plan 1 «Подготовка к оркестрации»

Исполнитель: **Claude Code, Opus, effort high**. Этот файл — полное поручение. Владелец хочет, чтобы
**самое сложное — архитектуру, контракты и надёжный каркас плана — сделал Opus**. Тогда Sonnet и
GPT-Sol 6.1 смогут исполнять пункты из context pack без проектных решений.

---

## 0. Команда запуска

В новой сессии Claude Code (`/model opus`):

```text
/task:plan-design new "Подготовка к оркестрации: контракты, разделение пакетов, привязки к движкам" — выполни orch/PLAN1-PROMPT.md целиком; сообщение владельца для --message-file: orch/plan1-owner-message.md
```

Создание плана внутри сессии: `plan.py new --codename ORCH-PREP --title "<title>" --actor claude-code/opus/high --message-file orch/plan1-owner-message.md`.

---

## 1. Что прочитать до любых действий

Читать по порядку и полностью:

1. `orch/REQUIREMENTS.md` — реестр R1–R26 и I1–I15. **Главный критерий: каждый ID покрыт.**
2. `orch/plan1-owner-message.md` — поручение владельца дословно.
3. `orch/DECISIONS.md` — принятые решения: свой native-движок, CAO — опциональный adapter, нейтральные
   контракты + Engine Port, `packages/orch`, Artifex заморожен. §9 — только стартовая гипотеза.
4. `orch/task-role-decomposition.md` — разделение Task по ролям (файл Sol). Принято: путь A + путь B **в Plan 1** без breaking (R19).
5. `orch/architecture-contract.md`, `orch/repository-audit.md` — инварианты и факты о коде.
6. Skills `task-development-philosophy` и `package-architecture`. Первый — конституция плана; второй — карта репозитория.

Остальное из `orch/` (аудиты A/B, alternatives, model-economics, pilot, research/) читать по необходимости.
`orch/perplexity-thread.md` (109 KB) целиком не читать: сообщения владельца там на строках 3, 659, 1275, 1470;
их сводка уже в REQUIREMENTS.

---

## 2. Что должно получиться

**Plan 1 — подготовка к оркестрации. Не реализация движка.** Итог плана:

- нейтральные контракты исполнения (JSON Schema + stdlib-валидатор + fixtures) в новом пакете `packages/orch`;
- Engine Port: спецификация операций и binding-матрица для native / CAO / Claude-only;
- Task как поставщик данных: `brief`-проекция, проверка полноты, раздельные actor, evidence, идемпотентная регистрация, resolver ссылок на другие планы;
- **рефакторинг-разделение пакетов** (Task, Skiller, Harness) по ролям: worker-вход без lifecycle, перенос методологии к владельцам, launch catalog для роли × provider, `skiller resolve --role`, отвязка от monorepo-путей;
- доказательство переносимости: один `execution-input` исполним без переписывания goal/checks на разных binding
  (рендер prompt для Claude-only, dry-render профиля CAO, fixture native);
- документация: как устроено, как дописать другой движок (R12, R16).

**Вне Plan 1:** запуск native-движка, live stream, recovery, CAO-сервер, платные прогоны моделей —
это Plan 2, его составляют отдельно (R20). В Plan 1 не проектировать Plan 2; в roadmap — только ссылки.

**Жёсткое правило — без breaking changes (R21).** Все существующие команды Task (`plan-run`, `plan-design`,
`review`, …), схемы `plan/v1` (только optional поля → minor), `plan.py`-глаголы, Skiller connect/vendor и
Harness installer работают как раньше. Перенос текста = новый канонический владелец + старое место
ссылается на него или генерируется. Удаление только того, на что после переноса нет ссылок (проверка `grep -rn`).

---

## 3. Как проектировать

1. **Сначала design dossier, потом items.** Через `plan.py add-document` создать knowledge-документы плана:
   - `architecture` — границы пакетов, правило зависимостей (DECISIONS §2.1), куда кладётся код;
   - `contracts` — **полный набор полей каждой схемы** (execution-input, run-policy, role-manifest,
     capability-record, run-event, stage-result, effect-receipt, check-evidence), обязательность, версионирование,
     примеры: plan-bound, ad-hoc, review-only;
   - `engine-port` — операции, состояния, ошибки и отказы, binding-матрица native/CAO/Claude-only с пометками
     supported / adapted / unsupported;
   - `task-changes` — точные сигнатуры новых глаголов и флагов, изменения схем, тест-кейсы совместимости;
   - `instruction-split` — инвентаризация каждого фрагмента `plan-protocol`, `plan-run`, `review`,
     `reviewer-selection`, `design-mode`, `execution-mode`, `common-principles`, `units.brief`: текущий владелец → новый
     владелец → способ переноса;
   - `coverage` — матрица R#/I# → item(s). Ни один ID не пропущен; для «Plan 2» указано, какой контракт Plan 1 его готовит.
   Это и есть «надёжная структура»: Sonnet и Sol получают решения из этих документов через `reads`, а не придумывают.
2. **Сверять с кодом, а не с аудитами.** Аудиты могли устареть; см. факты в §6.
3. **Perplexity обязателен (R22)** для любого внешнего утверждения, которое влияет на дизайн: форматы событий CLI,
   ACP, профили CAO, механизмы доставки skills у провайдеров и т. п. Маршрут: MCP `perplexity-web`. Если он не подключён к
   сессии — `python3 orch/research/tools/pplx_stdio.py search <query.txt> <out.json>` (тот же daemon и pool).
   Сырые ответы сохранять в `research/` плана, а важные для решения — ещё и в `orch/research/perplexity/Q14+…` с записью в
   `orch/research/perplexity-log.md`. Ответ Perplexity — discovery: решение принимается после сверки с первичным источником.
4. Решения с реальной альтернативой записывать как `D#` (`add-decision` → `decide`), не прозой.
5. **Детализировать все фазы сейчас** (`design-done` для каждой), а не по одной: исполнять будут Sonnet и Sol,
   поэтому структуру нужно задать сразу.

---

## 4. Размер кусков (R23)

Цель — каждый item проходит **за один запуск `plan-run` одной сессией**, не дольше ~1–2 часов работы агента.

- Один item = один вертикальный проверяемый результат, обычно в одном пакете. До ~6–8 изменённых файлов кода;
  тесты и fixtures не считаются.
- Item не смешивает проектное решение и механический перенос: решение — в dossier или в отдельном Opus-item, перенос — отдельно.
- Если item требует прочитать больше ~4 крупных файлов или менять 2+ пакета с разной семантикой — делить.
- Есть прецедент: в архивном PLAN1 пункт P3.1 оказался слишком большим и закрыт с отклонением «Opus/Sonnet split»
  (`plans/archive/<PLAN-ID>/phases/P3/P3.1.json`). Такого быть не должно.
- Фаза = интеграционная веха (обычно 3–5 items). Широкий `validate.sh` — в последнем item фазы.
- У каждого item — точные acceptance-команды (`bash packages/<pkg>/scripts/validate.sh`, конкретный тест, `grep` на отсутствие).

---

## 5. Кто исполняет (R24)

Модели — пул (philosophy): `route` задаёт **минимальный** класс. Рекомендованного исполнителя указать
**первой строкой `guidance`** каждого item (`Исполнитель: Opus|Sonnet|Sol`) и сводной таблицей в `plan.rules`.
`provider/model` в route не фиксировать: иначе dispatch откажет более сильной модели.

| Исполнитель | Маршрут в пуле | route item | Что даём |
| --- | --- | --- | --- |
| **Opus** (claude-code) | frontier | `frontier/high` | Контракты и схемы, семантика Task lifecycle (actors, evidence, идемпотентность), перенос инструкций с изменением смысла, Engine Port и binding-матрица, финальный review плана |
| **Sonnet** (claude-code) | implementation | `implementation/high` | Реализация по готовому контракту из dossier: глаголы `plan.py`, validator, resolver, launch catalog, `skiller resolve`, конформанс-тесты |
| **GPT-Sol 6.1** (codex, `gpt-6.1-sol`) | implementation (умеет frontier) | `implementation/medium` | Мелочи и механика: fixtures, перегенерация проекций, docs/CHANGELOG, перенос по готовой таблице, role-manifest по образцу, независимый review фаз (другой провайдер) |

**Особые требования к Sol-items.** Codex плохо справляется с перегруженным Task (R1), поэтому item для Sol:

- самодостаточен: точный список файлов, готовый образец или таблица, точные команды;
- в нём нет проектных выборов: если выбор возник — `log --type blocker`, а не импровизация;
- в нём нет units и делегирования.

Независимый review: по одному read-only item `Review Pn` в конце фаз с публичными контрактами (контракты, Task lifecycle).
Его исполняет **Sol** как другой провайдер, лимит — 2 раунда и 1 исправление (I10). Другие review не добавлять.

---

## 6. Факты о коде (проверены 2026-10-05; перепроверить, если код изменился)

- `packages/task/lib/task/plan/` — stdlib, без `core`. Схемы: `packages/task/schemas/plan/v1/*.schema.json`
  (`additionalProperties: false`). Валидатор подмножества JSON Schema — `plan/schema.py` (`validate`, `Registry`):
  кандидат на переиспользование или копию в `packages/orch`. Решить через D#.
- `context.collect()` (`plan/context.py:149`) отдаёт полный pack. Внешние решения возвращаются как `{"ref", "loaded": false}` (`:141`).
- `units.brief()` (`plan/units.py:106`) кладёт полный context и `report_api: {"verb": "unit return"}` (`:117`) —
  это lifecycle-инструкция в worker-входе.
- `lifecycle.start(..., scout=)` (`:381`) запускает модель через `scout.run()` (`:471`). Argv scout лежит в
  `configs/command-routing.json → orchestration.scout` (только claude-code и codex).
- `lifecycle.finish()` (`:509`) принимает `checks: {V#: exit}` без доказательства запуска. `_actor_doc()` (`:303`)
  по умолчанию берёт `result.executor` — смешение executor и registrar.
- Модели: `command-routing.json → mappings.<provider>.class_selectors` и `model_inventory`. `gpt-6.1-sol` есть в
  codex inventory с ролями frontier/implementation/review/design/audit.
- Harness: `run/worker.py:25-26` хардкодит `claude-code` и `task:plan-run`; `:184` — `subprocess.run(capture_output=True)`.
  `run/plan_reader.py:24` хардкодит `packages/task/scripts/plan.py`.
- Роли: `packages/harness/configs/common/agent-packs/roles.json` + `harness/lib/harness/agentpacks.py`.
- Skiller: closure зависимостей — `skiller/lib/skiller/vendor.py:39,54` (`build_requires_index`, `resolve_requires`)
  и `common.py:281` (`resolve_requires_bfs`); выбор skills — `config.resolve_selection`.
- Review-методология в Task: `skills/plan-protocol/references/review-mode.md`, `commands/review.md`,
  `references/reviewer-selection.md`. Существующие review-skills Skiller: `quality:code-review`, `quality:artifact-review`.
- Workflow-шаблоны: `packages/task/workflows/wf-*.js`. Это слоты для Workflow runtime, а не движок.
- `plans/` в этом репозитории gitignored: bookkeeping плана локальный, в коммиты идут код и docs.
- Релизы: `configs/release-units.json`. Публиковать ли `packages/orch` как plugin в Plan 1 — решение D# (предпочтение: нет, внутренний пакет).

---

## 7. Когда спрашивать владельца

Только для реальных решений; остальное принимать самостоятельно и записывать как D#:

- имя пакета (`orch` — рабочее);
- публиковать ли `packages/orch` наружу в Plan 1;
- если перенос текста без breaking невозможен в каком-то месте — показать конкретный случай и варианты.

---

## 8. Готово, когда

- `plan.py check <plan>` — 0 ошибок; все фазы `detailed`.
- Knowledge `coverage` перечисляет **каждый** ID из `orch/REQUIREMENTS.md` с item, где он покрыт, или с пометкой
  «Plan 2: готовится контрактом X». Пропусков нет.
- Ни один item не нарушает §4; у каждого есть исполнитель (§5) и точные acceptance-команды.
- Нет items, которые запускают модели, CAO или платные прогоны.
- В отчёте: список фаз и items с исполнителями, оценка числа запусков, открытые вопросы, точная строка `plan.py next <plan>`.
- Ничего не реализовано и не закоммичено, кроме изменений `orch/` (если были новые Perplexity-запросы).
