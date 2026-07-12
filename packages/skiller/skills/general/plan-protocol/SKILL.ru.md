---
name: plan-protocol
bucket: general
version: 2.2.0
description: "Исполняемые мастер-планы в plans/<ID>: схемы plan/phase/task, 6 статусов, refine-цикл и DoR-гейт, канонический корень плана, репо-дом по умолчанию + поля visibility/supersedes, два дома и архив, handoff с launch-block, роутинг моделей, команды /task:plan-*."
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.md", "plans/<PLAN-ID>/phases/*.md", "plans/<PLAN-ID>/handoff.md"]
snippets: ["plan-template.md", "phase-template.md", "handoff-template.md", "active-template.md", "launch-block-template.md", "code-guidance-patterns.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Plan Protocol

SSOT plan-протокола экосистемы: как устроен исполняемый мастер-план, который «сильная»
модель пишет, а «дешёвая» исполняет без доступа к чату планирования. Протокол фиксирует
ТОЛЬКО Axioma-специфику — схемы, гейты, маркеры, конвейеры; общие практики планирования,
которые plan mode / модель умеют сами, здесь не пересказываются.

## 1. Когда активировать

- Многофазная работа длиннее одной сессии (план переживает контекст).
- Паттерн «сильная модель планирует, дешёвая исполняет»: opus строит план,
  sonnet/haiku закрывают items по нему.
- Вызов любой команды `/task:plan-*` (design/exec/close/audit).

**Порог «нужен ли план» (эвристика):**

| Признаки задачи | Маршрут |
|:--|:--|
| Мелкая правка, багфикс, одиночный файл | `/task:fix` без мастер-плана |
| Фича в одном модуле, PoC, эксперимент | `/task:dev` без мастер-плана |
| Кросс-модульное; compliance (54-ФЗ/платежи/PII); >1 репо; >1 сессии | ОБЯЗАТЕЛЕН `/task:plan-design` с гейтами этого протокола |

## 2. Раскладка

```text
plans/<PLAN-ID>/
├── plan.md            # мастер-план (Meta, Context, Rules, Routing, Status Board, логи)
├── phases/Pn.md       # по файлу на фазу: контекст фазы, items, phase handoff
├── handoff.md         # rolling-указатель «где мы» (перезаписывается)
├── findings/          # RAG-выжимки и recon-отчёты (раздел 16)
├── 20_research/       # research-артефакты плана
├── artifacts/         # рабочие артефакты фаз, судьба — архив
├── workflows/         # полевые копии workflow-скриптов плана (шаблоны-исходники — packages/task/workflows/)
├── root/              # долгоживущий материал, судьба — docs проекта (раздел 3)
└── open-questions.md  # спорное/нерешённое (протокол — раздел 3)
```

Обязательны только `plan.md`/`phases/`/`handoff.md` — остальное опционально,
по потребности плана. `PLAN-ID` — один из двух каноничных паттернов:

- **датовый** (предпочтительный, D16) — `<ГГГГ>.<ММ>.<ДД>-<КОДОВОЕ-ИМЯ>`, например
  `2026.07.10-SETTINGS-DOCTOR`: датовый префикс даёт хронологическую сортировку `plans/`
  и ориентацию «когда» без чтения Meta;
- **старый** (back-compat, D24) — `[A-Z][A-Z0-9-]+`, например `AUDIT-W2`, `MIGRATE-V3`.

Старый паттерн `[A-Z][A-Z0-9-]+` остаётся валидным, существующие планы НЕ
переименовываются; миграция — только вперёд (терминальные уходят в архив по мере закрытия).

Корень `plans/` рядом с каталогами планов:

- **`plans/ACTIVE.md`** — плоский указатель активного плана. Канон — РОВНО 4 строки
  (парсится `plan-lint`): `# ACTIVE`, пустая строка, `**Active:** <PLAN-ID>`
  (нет активного — `—`), `**Updated:** <YYYY-MM-DD>`. Скелет —
  `snippets/active-template.md`. Ведут команды: `plan-design` (режимы new/from-draft —
  ставит ID нового плана) и `plan-close` (закрыт ВЕСЬ план — сбрасывает в `—`).
- **Конвенция черновиков:** любой плоский `.md` прямо в `plans/` (кроме `ACTIVE.md` и
  `README.md`) — черновик plan mode; разворачивается командой
  `/task:plan-design from-draft <файл>` (`plan-lint` предупреждает о залежавшихся).

**ПРАВИЛО MD-only:** Хранимый формат плана — только Markdown с жёсткими маркерами.
Любой JSON — производный артефакт парсера (`plan-lint --json`), не источник истины.

**Дом workflow-скриптов.** Мультиагентный workflow-скрипт — артефакт плана-владельца
(как `findings/`/`artifacts/`): единственное место — `plans/<ID>/workflows/`, вне плана
скриптам не место. Имя — `wf-<кодовое-имя-lower>-<назначение>.js`, где кодовое имя (D28) =
часть ID после даты для датового формата (`2026.07.10-FLEX` → `flex`) либо весь ID для
старого (`SKM-ROADMAP-005` → `skm-roadmap-005`), всегда lowercase; пример —
`wf-ecosystem-design-fleet.js`. Пайплайн-доки прогонов — `<Pn>-pipeline.md` рядом.
Дисциплина авторинга скрипта (обязательные стадии, слоты, structured-summary) — скилл
`workflow-craft`; здесь только ГДЕ лежит и КАК называется. Библиотека портируемых
шаблонов-исходников — `packages/task/workflows/README.md`.

## 3. Канонический корень плана

Смысловое различие двух каталогов артефактов (RAG:✅ P5.1 §2 arc42 — timeless-материал
в корень, итерации — в дочерние):

- **`root/`** — долгоживущий материал, судьба — документация проекта:
  `architecture.md`, `data-model.md`, `contracts/`, `philosophy.md`, `glossary.md`.
  Набор — по потребности плана, не все файлы обязательны.
- **`artifacts/`** — рабочий материал фаз, судьба — архив вместе с планом.

**Протокол Open Questions** (RAG:✅ P5.1 §7 IETF rough consensus): спорный пункт НЕ
блокирует план, если вынесен в `open-questions.md` с одним из статусов:

```text
Exploration
Decision pending (нужен владелец)
Resolved → D#
```

Правила: вопрос, «висящий» в теле фазы без выноса, = находка аудита; закрытие плана
с pending-вопросами = только `🟠 Done with deviations`; возражение фиксируется
содержательно («не нравится» — не возражение).

**Re-design поверх закрытых фаз** (RAG:✅ P5.1 §7 superseded-цепочки): новое решение =
новый D# со ссылкой «supersedes D#-старый»; старый D# НЕ редактируется. Реопен фазы:
Status `🟢`→`🟡` + Version bump плана + D-запись о причине.

## 4. Схема plan.md

Скелет — `snippets/plan-template.md`. Секции строго в этом порядке:

- **`## 0. Meta`** — таблица полей: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner. Необязательные поля:
  - **Home** — `brain` | `repo:<путь>`: где живёт исполняемая копия плана; по умолчанию
    репо проекта (раздел 12, D31);
  - **visibility** — `private` | `public`, дефолт `private` при отсутствии (D25): `public`
    → в git-репо допустима только публичная roadmap-выжимка, приватный бизнес-контекст
    остаётся в vault;
  - **supersedes** — `<старый-ID>`: план сменяет предшественника той же волны трека;
    предшественник уходит в архив `plans/archive/` (раздел 12);
  - **Paused By** — какой план перехватил ACTIVE и когда; заполняет режим `new`
    plan-design, дописывая поле предыдущему активному плану.
- **`## 1. Context`** — 5–15 строк: что делаем и почему. Самодостаточно: исполнитель
  НЕ видит обсуждение, в котором план родился.
- **`## 2. Execution Rules`** — выжимка правил исполнения ≤20 строк + план-специфичные
  отклонения. Полный протокол — этот скилл, его не копировать целиком.
- **`## 3. Routing`** — ТОЛЬКО отклонения от SSOT-матрицы роутинга (раздел 9).
  Пустая секция = действуют дефолты. Формат строки:
  `Items | Model/effort И/ИЛИ Tool Capability | Почему` — tool-capability
  (типовое: `perplexity-web/WebFetch (RAG)`) ДОПОЛНЯЕТ model/effort, не заменяет.
- **`## 4. Phase Index & Status Board`** — таблица `Phase | Title | Items 🟢/всего | Status`.
- **`## 5. Decision Log`** — таблица `D# | Дата | Решение | Почему`.
- **`## 6. Update Log`** — append-only таблица `Дата | Кто (role/model) | Что`.
  Жёсткий лимит «Что» ≤ 2 строк, канонический формат:
  `<item> закрыт: <1 строка сути> — детали см. phases/Pn.md <item> Completion Notes`.
  Пересказывать Completion Notes в Update Log ЗАПРЕЩЕНО (инцидент EDUFY: 54KB plan.md).

## 5. Схема phases/Pn.md

Скелет — `snippets/phase-template.md`. Структура файла фазы:

- `# Pn — Title`
- **`## Phase Context`** — 5–10 строк, самодостаточно (фазу можно исполнять,
  не читая другие фазы).
- **`## Phase Status`** — таблица `ID | Title | Status | Updated`.
- **Items.** Заголовок item — СТРОГО `### Pn.m — Title`. Поля — СТРОГО строками
  `**Поле:** значение`, в этом порядке:
  `Status, Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads,
  Implementation Rules, Code Guidance, Validation, Deliverables, Completion Notes,
  Pending Work, Known Deviations, Escalation Needed`.
  Пустое значение — канонический символ «—» (не пустая строка, не «N/A»).
  Исключение: у поля `Escalation Needed` — и ТОЛЬКО у него — маркер `no` равноправен «—».
  **Code Guidance ОБЯЗАТЕЛЕН**: стиль решения, запреты, допустимые абстракции,
  обязательные тесты, запрещённые shortcuts — то, что дешёвая модель не выведет сама.
- **`## Phase Handoff`** — заполняется при закрытии фазы (что сдали, что дальше).

**Маркер фазы-скелета.** Фаза, намеренно не детализированная при авторинге, несёт
в Phase Context фиксированную строку:

```text
> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design <ID> Pn
```

При маркере пустые поля item'ов легальны, включая Code Guidance = «—». Без маркера
пустой Code Guidance — дефект плана.

**RAG-маркеры** на несущих фактах в Intent/Why/Implementation Rules и в D-логе
обязательны — схема и определение load-bearing в разделе 7.

## 6. Статусы

РОВНО 6 канонических строк — копировать байт-в-байт (greppable, парсер жёсткий):

```text
⬜ Not started
🟡 In progress
🟢 Done
🟠 Done with deviations
🔴 Blocked
⛔ Skipped by decision
```

Статус живёт в плане: завершение работы без обновления плана = незавершённое
исполнение. Закрыл item — обнови `Phase Status` и Status Board в `plan.md`.

**Коммит-гейт закрытия.** Статус `🟢`/`🟠` не ставится без закоммиченного диффа item'а:
Conventional Commits (рус.), атомарно по смыслу (несколько коммитов — нормально),
`validate.sh` затронутого пакета зелёный ДО коммита; фиксы по замечаниям ревью —
ОТДЕЛЬНЫМ коммитом (не `amend` — трассируемость: видно, что нашло ревью);
незакоммиченного диффа по Scope item'а в дереве не остаётся (`git status`); дифф ВНЕ
Scope item'а — не коммитить, зафиксировать в Pending Work. Инцидент-основание — D12
плана SKM-AUDIT-004: 4 «закрытых» item'а числились готовыми, а их код лежал
незакоммиченным в рабочем дереве.

**DoR-гейт фазы.** Фаза не переводится из дизайна в исполнение, пока не пройден
Definition of Ready — чеклист и refine-цикл в разделе 7. Фаза, ушедшая в exec с
незакрытыми `[NEEDS CLARIFICATION]`, = находка plan-audit.

## 7. Refine-цикл и готовность

**Маркер `[NEEDS CLARIFICATION: <вопрос>]`** — канонический способ пометить
неоднозначность прямо в тексте плана/ТЗ item'а (RAG:✅ P5.1 §1 spec-kit). Спорное место
при авторинге — либо маркер, либо вопрос владельцу; самовольное допущение запрещено.
Гейт бинарный: 0 маркеров.

**DoR-гейт фазы** (Definition of Ready, RAG:✅ P5.1 §7 Atlassian) — фиксированный
чеклист; plan-design обязан прогнать его перед выдачей «фаза готова», plan-audit
проверяет пост-фактум:

- [ ] Все `[NEEDS CLARIFICATION]` сняты (0 маркеров в фазе).
- [ ] Scope Included / Scope Excluded фазы заполнены (эквивалент Goals/Non-Goals).
- [ ] Alternatives для несущих решений зафиксированы в D-логе.
- [ ] Open Questions разнесены по статусам `open-questions.md` (раздел 3).
- [ ] Несущие факты несут RAG-маркеры.
- [ ] **Для фаз с ЗАЯВЛЕННОЙ оркестрацией** (multi-agent/fan-out): готовый workflow-скрипт
      в `plans/<ID>/workflows/`, launch-block handoff ссылается на него по `scriptPath`
      (D29). Условие — ТОЛЬКО при заявленной оркестрации: ручное item-by-item исполнение
      фазы workflow НЕ требует (дом/имя скрипта — раздел 2, авторинг — скилл `workflow-craft`).

**Критерий «фаза обязана заявить оркестрацию»** (D16 — раньше решение оставалось на
усмотрение исполнителя каждый раз заново, отсюда наблюдаемая непоследовательность).
Фаза ОБЯЗАНА завести workflow-скрипт (item-by-item НЕ легален), если сработал ЛЮБОЙ
из двух сигналов:

- **N≥3 items с независимым/parallelizable scope** — items фазы не блокируют друг
  друга по данным (Inputs одного item'а не ссылается на Deliverables другого item'а
  ЭТОЙ ЖЕ фазы) И у каждого есть детерминированные Validation-команды (конкретные
  команды с проверяемым результатом, не «проверь вручную»);
- **длинная автономная цепочка с внешним состоянием** — фаза рассчитана на прогон
  без ручного вмешательства между item'ами дольше одной сессии-исполнителя (состояние
  передаётся через git+plan, а не через контекст чата).

Ни один сигнал не сработал (items <3, либо scope items связан последовательно, либо
Validation неформализуема) — фаза остаётся ручной, workflow НЕ заводится «на всякий
случай» (лишний файл + лишняя дисциплина слотов без нужды). Критерий бинарный: агент
сверяет факт по items фазы (число, зависимость Inputs↔Deliverables, наличие команд
Validation) — не оценивает «на усмотрение».

**RAG-маркеры в схеме.** Каждый load-bearing факт/вердикт в Intent/Why/Implementation
Rules item'а и в D-логе несёт `RAG:✅ <дата/суть запроса>` либо `[UNVERIFIED]`.
Load-bearing = «на этом стоит проектное решение». Несущий пункт без маркера =
дефект схемы, находка аудита.

**Refine-цикл** — канонический контур авторинга:
design → self-audit (DoR-чеклист) → правка → повтор до 0 маркеров.

**Pre-mortem для high-stakes** (фискалка/платежи/tenant-isolation/ядро экосистемы):
перед закрытием фазы дизайна — раунд по протоколу Klein (RAG:✅ P5.1 §7, prospective
hindsight +30%): «план провалился через 6–12 мес — почему»; независимая запись причин →
кластеризация → mitigations с owner в Risks/D-лог.

## 8. Handoff-стандарт

`plans/<ID>/handoff.md` — rolling-указатель, ПЕРЕЗАПИСЫВАЕТСЯ при каждом закрытии
item/фазы (история версий — в git, не в файле). Скелет — `snippets/handoff-template.md`.
Поля:

- Заголовок: `# HANDOFF — <ISO-дата> — after Pn.m`
- **Next:** следующая команда в форме launch-block (ниже).
- **Done:** что закрыто.
- **Remaining:** что осталось.
- **Sources of truth:** где правда (plan.md, phases/Pn.md, ключевые файлы).
- **Open risks:** открытые риски.
- **Workarounds/Deferred/Open questions:** ключи совпадают с run-report
  `devloop{workarounds,deferred,open_questions}` — сверяемость с телеметрией.

**Launch-block.** Каждая выдача «что запускать дальше» — handoff.Next и финалы отчётов
plan-exec/plan-close/plan-audit — обязана иметь фиксированную форму
(`snippets/launch-block-template.md`):

```markdown
| Параметр | Значение |
|:--|:--|
| Model | <модель> |
| Thinking | <effort> |
| Context | <fresh session / continue> |
| Суть | <1 строка> |

````
<голая команда одним code-block, копипаст без правок>
````
```

**Самодостаточность (cold-start).** Команда в launch-block обязана работать из холодной
сессии: plan-ID + пути входных доков (cold-start reads) + встроенное утверждение гейта,
если исполнение гейтится. Ссылки вида «эта сессия» — только как дополнение.
`plan-lint` проверяет: handoff.Next содержит launch-block-таблицу и code-block (грепаемо).

При мастер-плане общий session-handoff (скилл `session-handoff`) сворачивается
сюда — второй handoff-файл не заводить.

**Цикл «item/фаза → handoff → /clear»:** после перезаписи handoff.md рекомендован
`/clear` — следующий item стартует с чтения плана (plan.md → phases/Pn.md →
handoff.md), а не хвоста чата. plan-exec и plan-close печатают фиксированную
строку-напоминание:
`Context: handoff свежий — рекомендован /clear перед следующим item`.

**Session-restart discipline (различение поля Context launch-block'а, D16).** Поле
Context launch-block'а несёт РОВНО одно из двух значений — не статичное общее
«рекомендован /clear» независимо от типа следующего шага:

- **`continue (/clear) — ручной item`** — следующий шаг обычный item-by-item exec:
  текущая сессия достаточна, `/clear` перед следующим item'ом.
- **`NEW SESSION — Workflow-оркестрован`** — следующий шаг это Workflow-оркестрованный
  кусок (item/фаза/цепочка), КОТОРЫЙ ЛИБО завершился ЧИСТО (`git status` пусто по его
  Scope, `plan-lint` зелёный), ЛИБО ещё только запускается (критерий раздела 7
  сработал, `scriptPath` готов): launch-block ОБЯЗАН явно предложить НОВУЮ сессию с
  готовой командой `Workflow({scriptPath:...})`, не общий `/clear`. Причина —
  notification-payload фоновых `Workflow()`-тасков растит контекст сессии-исполнителя
  быстрее самой работы, если сессию не рестартовать; `/clear` внутри той же сессии
  этого не решает (сбрасывает контекст чата, не сбрасывает фоновый payload/лимиты
  процесса-исполнителя).

## 9. Routing & Thinking Policy (SSOT-матрица)

Дефолтный роутинг ролей на модели/effort. Секция `## 3. Routing` плана хранит
ТОЛЬКО отклонения от этой таблицы:

| Роль | Модель/effort | Где работает |
|:--|:--|:--|
| issue-planner | opus/high | plan-design |
| invariant-auditor | opus/xhigh | plan-audit |
| package-implementer | sonnet/medium | plan-exec |
| small-implementer | haiku/low ¹ | LOW-срезы dev-loop |
| repo-explorer | haiku/low ¹ | разведка репо (grep/read/map) |
| docs-curator | sonnet/low | plan-close |

¹ Проба 2026-07-02: haiku-агент с effort=low, запущенный через workflow-agent API,
успешно завершился (ответ получен) — раннер принял пару haiku+effort=low без ошибки.
Проба подтверждает приёмку параметра на уровне workflow-agent API; поведение
frontmatter-пина effort внутри интерактивного Claude Code ею НЕ проверено (другой
механизм выбора модели/effort) — при расхождении считать дефолтным effort модели.

**Thinking policy:**

- effort **high+ ОБЯЗАТЕЛЕН** для: декомпозиции, конфликтных требований, инвариантов,
  SemVer-public-API, финальной верификации.
- effort **low ОБЯЗАТЕЛЕН** (thinking вреден — жжёт токены без пользы) для:
  grep/read/map, механических правок, статус-апдейтов, docs sync,
  handoff-форматирования.

## 10. Эскалация (протокол дешёвой модели)

Триггеры — закрытый enum:

- многопакетный рефакторинг
- неясная архитектура
- public contract/SemVer
- protected generated assets
- конфликт правил
- неясные acceptance

При срабатывании исполнитель оставляет ТРИ greppable-артефакта:

1. Blockquote в item:
   `> 🔴 ESCALATION Pn.m: <причина> | trigger: <из enum> | нужен: plan-design`
2. `**Status:** 🔴 Blocked` у item.
3. Финальная строка отчёта: `ESCALATION-REQUIRED: Pn.m — <причина>`.

План разошёлся с кодом → НЕ импровизировать, эскалировать: правит план plan-design,
а не исполнитель на ходу.

## 11. Межплановые паттерны

**Cross-plan gate** (прецедент AIRESTO ERP-GATE-01): зависимость плана от чужого
плана оформляется decision-доком с таблицей предусловий; каждая строка ссылается на
ТОЧНЫЙ ID строки Status Board донорского плана. Чтение однонаправленное: потребитель
читает донора, донор о потребителе не знает и не правится.

**Программный план** (прецеденты FLEX-IMPL, ECOSYSTEM P4): координационный план над
делегатами — `Document Type: Program Master Plan (coordination)`; items =
milestone-делегаты (по плану-делегату на item); Validation item'а = GREEN-аудит
делегата; код в программном плане НЕ пишется. Execution Rules такого плана обязаны
запрещать `/task:plan-exec` и указывать предписанную команду запуска делегатов.

## 12. Жизненный цикл: два дома, архив, документация

**Модель двух домов** (RAG:✅ P5.1 §2 docs-as-code: git=SSOT, hub=display/index;
внешнего канона именно для Obsidian↔repo two-way не найдено — механизм наш
`brain sync`). SSOT плана определяется стадией:

- **Home по умолчанию — репо проекта** (D31): план живёт там, где его deliverables
  (`plans/<ID>` репо, Meta `Home: repo:<путь>`); в Brain остаётся программный/
  межпроектный план, чьи deliverables размазаны по нескольким репо;
- **на старте exec** — repo-копия становится SSOT; Brain-зеркало синкается
  `brain sync`-каналом (frontmatter `repo:` — тот же механизм, что docs/);
- **во время exec** — SSOT = репо; правки базового плана в Brain молча ЗАПРЕЩЕНЫ —
  только через протокол конфликтов; направление синка по умолчанию repo→Brain
  (зеркалирование), не наоборот;
- **после завершения** — синк обратно → архив → миграция root/ в docs.

**Протокол конфликтов.** Базовый план изменился во время исполнения → исполнитель
НЕ мержит молча: фиксирует `temporary divergence` в Known Deviations текущего item →
эскалация по разделу 10; владелец решает — принять в working-копию новым D# или
отложить до конца фазы.

**Скиллы — тот же принцип:** SSOT скиллов — всегда swissknifeman; vendor-копии в
проектах обновляются только `skiller vendor/connect`; локальная правка vendor-копии =
дефект, путь — contribution в SSOT (см. `package-contribution-protocol`).

**Конвейер план→архив→docs** (RAG:✅ P5.1 §2 Diátaxis + Oxide «committed =
реализовано»). По терминальности плана — команда `/task:plan-close archive <ID>`:

1. План перемещается в `plans/archive/<ID>` ОТДЕЛЬНЫМ коммитом
   `chore(plan): archive <ID>`.
2. Из `root/` собирается документация проекта по Diátaxis-типам:
   architecture/philosophy → explanation; data-model/contracts → reference;
   гайды фаз → how-to.
3. Чек-лист миграции (что перенесено в docs, что осталось в архиве) — в финальном
   handoff.

**Планы НЕ удаляются — никогда.** Терминальный план переезжает в `plans/archive/<ID>`
и хранится вечно (провенанс решений: D-лог, Completion Notes, Known Deviations —
единственный источник «почему так сделано» спустя месяцы). `rm`/`git rm` каталога
плана — дефект, а не операция протокола; superseded-предшественник тоже уходит в
архив, не в корзину. Единственное исключение — явное распоряжение владельца с
флагом `--force` в команде (агент по своей инициативе удаление не предлагает).

## 13. Командный протокол

| Команда | Модель/effort | Что делает |
|:--|:--|:--|
| `/task:plan-design` | opus/high | новый план / новая фаза / ТЗ item'ов; refine-цикл + DoR-гейт |
| `/task:plan-exec` | sonnet/medium | исполнить item; самозакрывающийся (обновляет статусы + handoff) |
| `/task:plan-close` | sonnet/low | реконсиляция статусов / закрытие фазы / режим `archive` |
| `/task:plan-audit` | opus/xhigh | adversarial-аудит фазы; вердикт GREEN/ATTENTION/RED |

## 14. Чеклист качества плана

- [ ] Каждый item исполним sonnet'ом без дополнительного контекста (вне плана).
- [ ] Required Reads конечны и упорядочены (не «посмотри по репо»).
- [ ] Code Guidance заполнен у каждого item (не «—»).
- [ ] Недетализированная фаза несёт скелет-маркер — не «просто пустые поля».
- [ ] Несущие факты/вердикты несут `RAG:✅`/`[UNVERIFIED]`-маркеры.
- [ ] Open Questions не «висят» в теле фаз — вынесены в `open-questions.md` со статусом.
- [ ] handoff.Next содержит launch-block (таблица + code-block).
- [ ] Phase-first: фазы закрываются последовательно, item'ы не прыгают между фазами.
- [ ] `plan-lint` зелёный.

## 15. Per-project deployment

Планы живут В ПРОЕКТЕ, не в `~/.claude/plans/`: top-level ключ
`plansDirectory: "plans"` в `.claude/settings.json` проекта (шаримый, коммитится).
Раскатка — три слоя:

- `harness hooks --target <проект> --plans-dir plans` — точечная ручка (ключ, занятый
  другим значением, уважается — не перезаписывается);
- `maind sync --only plans-dir,plans-doc` — флот онбордженных проектов
  (opt-out: `project.plans_dir="off"`);
- `skiller integrate` — новые онбординги (блок plans-dir, дефолт «да»).

Конвенцию в проект приносит managed-блок `maind:plan-conventions` в CLAUDE.md
(провижионер `plans-doc`). Мост из встроенного plan mode: одобренный план сохраняется
плоским черновиком в `plans/` → `/task:plan-design from-draft <файл>` разворачивает
его в `plans/<ID>/` по шаблонам этого скилла (черновик удаляется, история — в git).

## 16. Артефакты плана: findings/

`plans/<PLAN-ID>/findings/<Pn>-<slug>.md` — штатное место артефактов плана: RAG-выжимки
и recon-отчёты, чтобы дальнейшая доработка плана не переплачивала за восстановление
«откуда что взялось» (RAG/субагентские выжимки — дешёвые артефакты для будущих итераций).

- **Путь и имя:** `plans/<PLAN-ID>/findings/<Pn>-<slug>.md` (`Pn` — фаза, `slug` — кебаб
  тема); образец — `plans/SKM-AUDIT-004/findings/`.
- **Что кладут:** RAG-выжимка (источник-URL + дата верификации + вердикт), recon-отчёт
  субагента, диагноз/репро — **компактный синтез, не сырьё**.
- **Как ссылаются:** item, чья работа опирается на артефакт, указывает файл в своих
  `Inputs`/`Required Reads` — downstream-исполнитель читает файл, а не восстанавливает
  контекст по чату.
- **Опционально:** `findings/` не обязателен для каждого плана/item'а — обязателен
  только когда item декларирует файл в своих `Deliverables`. Схема 16 полей item'а не
  меняется, `plan_lint.py` каталог не проверяет (не его слой).

## 17. Связанные скиллы

- `task-brief-template` (general) — одиночная задача без мастер-плана.
- `session-handoff` (general) — handoff произвольной сессии; при мастер-плане
  handoff живёт в `plans/<ID>/handoff.md`.
- `complex-task-orchestrator` (general) — декомпозиция и маршрутизация контекста.
- `context-economy` (general) — Plan→Clear→Execute, дисциплина токенов.
- `anti-drift` (general) — дисциплина итераций исполнителя, circuit breaker.
- `package-contribution-protocol` (architect) — contribution в SSOT вместо правки
  vendor-копий (раздел 12).
