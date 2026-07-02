---
name: plan-protocol
bucket: general
version: 0.1.0
description: "Исполняемые мастер-планы в plans/<ID>: схемы plan/phase/task, 6 статусов, handoff-стандарт, роутинг моделей, команды /task:plan-*."
risk: write
persona: oss-dev
tags: [workflow, planning, handoff, routing, multi-model]
requires: []
produces_for: [session-handoff, complex-task-orchestrator]
outputs: ["plans/<PLAN-ID>/plan.md", "plans/<PLAN-ID>/phases/*.md", "plans/<PLAN-ID>/handoff.md"]
snippets: ["plan-template.md", "phase-template.md", "handoff-template.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Plan Protocol

SSOT plan-протокола экосистемы: как устроен исполняемый мастер-план, который «сильная»
модель пишет, а «дешёвая» исполняет без доступа к чату планирования.

## 1. Когда активировать

- Многофазная работа длиннее одной сессии (план переживает контекст).
- Паттерн «сильная модель планирует, дешёвая исполняет»: opus строит план,
  sonnet/haiku закрывают items по нему.
- Вызов любой команды `/task:plan-*` (design/exec/close/audit).

## 2. Раскладка

```text
plans/<PLAN-ID>/
├── plan.md          # мастер-план (Meta, Context, Rules, Routing, Status Board, логи)
├── phases/Pn.md     # по файлу на фазу: контекст фазы, items, phase handoff
└── handoff.md       # rolling-указатель «где мы» (перезаписывается)
```

`PLAN-ID` = `[A-Z][A-Z0-9-]+` (например `AUDIT-W2`, `MIGRATE-V3`).

**ПРАВИЛО MD-only:** Хранимый формат плана — только Markdown с жёсткими маркерами.
Любой JSON — производный артефакт парсера (`plan-lint --json`), не источник истины.

## 3. Схема plan.md

Скелет — `snippets/plan-template.md`. Секции строго в этом порядке:

- **`## 0. Meta`** — таблица полей: Plan ID / Title / Version / Status / Document Type /
  Authoring Model / Last Updated / Repository / Related Packages / Execution Mode /
  Target Operator Models / Approval Owner.
- **`## 1. Context`** — 5–15 строк: что делаем и почему. Самодостаточно: исполнитель
  НЕ видит обсуждение, в котором план родился.
- **`## 2. Execution Rules`** — выжимка правил исполнения ≤20 строк + план-специфичные
  отклонения. Полный протокол — этот скилл, его не копировать целиком.
- **`## 3. Routing`** — ТОЛЬКО отклонения от SSOT-матрицы роутинга (раздел 7).
  Пустая секция = действуют дефолты.
- **`## 4. Phase Index & Status Board`** — таблица `Phase | Title | Items 🟢/всего | Status`.
- **`## 5. Decision Log`** — таблица `D# | Дата | Решение | Почему`.
- **`## 6. Update Log`** — append-only таблица `Дата | Кто (role/model) | Что`.

## 4. Схема phases/Pn.md

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
  **Code Guidance ОБЯЗАТЕЛЕН**: стиль решения, запреты, допустимые абстракции,
  обязательные тесты, запрещённые shortcuts — то, что дешёвая модель не выведет сама.
- **`## Phase Handoff`** — заполняется при закрытии фазы (что сдали, что дальше).

## 5. Статусы

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

## 6. Handoff-стандарт

`plans/<ID>/handoff.md` — rolling-указатель, ПЕРЕЗАПИСЫВАЕТСЯ при каждом закрытии
item/фазы (история версий — в git, не в файле). Скелет — `snippets/handoff-template.md`.
Поля:

- Заголовок: `# HANDOFF — <ISO-дата> — after Pn.m`
- **Next:** `/task:plan-exec <ID> Pn.k` — конкретная следующая команда.
- **Done:** что закрыто.
- **Remaining:** что осталось.
- **Sources of truth:** где правда (plan.md, phases/Pn.md, ключевые файлы).
- **Open risks:** открытые риски.
- **Workarounds/Deferred/Open questions:** ключи совпадают с run-report
  `devloop{workarounds,deferred,open_questions}` — сверяемость с телеметрией.

При мастер-плане общий session-handoff (скилл `session-handoff`) сворачивается
сюда — второй handoff-файл не заводить.

## 7. Routing & Thinking Policy (SSOT-матрица)

Дефолтный роутинг ролей на модели/effort. Секция `## 3. Routing` плана хранит
ТОЛЬКО отклонения от этой таблицы:

| Роль | Модель/effort | Где работает |
|:--|:--|:--|
| issue-planner | opus/high | plan-design |
| invariant-auditor | opus/xhigh | plan-audit |
| package-implementer | sonnet/medium | plan-exec |
| small-implementer | haiku/low | LOW-срезы dev-loop |
| repo-explorer | haiku/low | разведка репо (grep/read/map) |
| docs-curator | sonnet/low | plan-close |

**Thinking policy:**

- effort **high+ ОБЯЗАТЕЛЕН** для: декомпозиции, конфликтных требований, инвариантов,
  SemVer-public-API, финальной верификации.
- effort **low ОБЯЗАТЕЛЕН** (thinking вреден — жжёт токены без пользы) для:
  grep/read/map, механических правок, статус-апдейтов, docs sync,
  handoff-форматирования.

## 8. Эскалация (протокол дешёвой модели)

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

## 9. Командный протокол

| Команда | Модель/effort | Что делает |
|:--|:--|:--|
| `/task:plan-design` | opus/high | новый план / новая фаза / ТЗ item'ов |
| `/task:plan-exec` | sonnet/medium | исполнить item; самозакрывающийся (обновляет статусы + handoff) |
| `/task:plan-close` | sonnet/low | реконсиляция статусов / закрытие фазы |
| `/task:plan-audit` | opus/xhigh | adversarial-аудит фазы; вердикт GREEN/ATTENTION/RED |

## 10. Чеклист качества плана

- [ ] Каждый item исполним sonnet'ом без дополнительного контекста (вне плана).
- [ ] Required Reads конечны и упорядочены (не «посмотри по репо»).
- [ ] Code Guidance заполнен у каждого item (не «—»).
- [ ] Phase-first: фазы закрываются последовательно, item'ы не прыгают между фазами.
- [ ] `plan-lint` зелёный.

## 11. Связанные скиллы

- `task-brief-template` (general) — одиночная задача без мастер-плана.
- `session-handoff` (general) — handoff произвольной сессии; при мастер-плане
  handoff живёт в `plans/<ID>/handoff.md`.
- `complex-task-orchestrator` (general) — декомпозиция и маршрутизация контекста.
- `context-economy` (general) — Plan→Clear→Execute, дисциплина токенов.
- `anti-drift` (general) — дисциплина итераций исполнителя, circuit breaker.
