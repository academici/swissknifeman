---
name: shared-memory
bucket: system
version: 0.2.0
description: "Единый «мозг» (общая память) проектов констелляции через хук ~/.claude/hooks/memory/ + демон mAInd. Recall перед работой, remember после. Канон для проектов — MODE=maind (демон :4111, изоляция по scope на стороне maind): приватный project:<id> + общее по тегам ns:<namespace> + global; recall их объединяет. Бэкенд сменный: maind|file|federation|agentmemory|off."
risk: write
persona: architect
tags: [memory, cross-project, topology, recall, context, coordination]
requires: [local-topology]
produces_for: []
outputs: []
snippets: []
adapters: [claude]
sha256: ""
---

# Shared Memory (единый «мозг» констелляции)

## Контекст

Память по проектам разрознена: что выучено в одном проекте, не вспоминается в
связанном. Хук `~/.claude/hooks/memory/` даёт **общий «мозг»** — но не всем
подряд, а **только участникам одной группы** (`brain`). Это решает силос, не
смешивая несвязанные проекты.

Структура хука — как у `auto-approve`: переключатель `memory.sh`, режим в
`env.ini` (`MODE`), группы и участники в `config.json`, бэкенды в `modes/`.
Резолв участников опирается на топологию (см. `local-topology`).

## Когда использовать

- **Recall перед работой.** В начале содержательной задачи спроси общий мозг —
  не решалось ли похожее в связанных проектах:
  ```bash
  ~/.claude/hooks/memory/memory.sh recall "<тема задачи: домен, паттерн, баг>"
  ```
- **Remember после.** Зафиксируй межпроектно-полезный факт (решение, расхождение,
  кандидат в общий пакет) — он станет виден другим участникам группы:
  ```bash
  ~/.claude/hooks/memory/memory.sh remember --type project "<факт одной фразой + почему>"
  ```
- **Осмотреться:** `memory.sh status` (режим, группа, участники, число фактов),
  `memory.sh members` (кто в группе).

Не каждую мелочь: в общий мозг — только то, что полезно **другому** проекту
группы (дубли, расходящиеся реализации, общие решения, кандидаты в общий пакет).
Локальное и одноразовое — мимо.

## Режимы (бэкенды) — `env.ini` MODE

- **maind** ← **канон для прикладных проектов.** Делегирует в `maind memory` (демон
  :4111). Та же память, что у MCP `maind_memory_*`: приватный `project:<id>` + общее по
  тегам `ns:<namespace>` + `global`, recall объединяет. **Изоляция — на стороне maind**
  (демон-пул один и `namespace` он игнорирует; maind встраивает scope-маркер в контент и
  фильтрует на чтении). brain не нужен — scope берётся из проекта. `maind onboard` сам
  ставит `MODE=maind` и namespaces (общий `axioma` + свой, см. [namespaces]).
- **file** — один общий store на группу (markdown). Просто и предсказуемо.
- **federation** — файловый: свои `memory/` участников + общий store. Git-прозрачно, без
  демона. Оставлен для **инфра-узлов** (brain/swissknifeman); НЕ путать с graph-federation maind.
- **agentmemory** — старый прямой proxy к демону (бил мимо API/scope) — **не использовать**,
  заменён режимом `maind`.
- **off** — выключено.

> ⚠️ Пиши/читай память проекта только через `maind memory` (хук в `MODE=maind`) или MCP
> `maind_memory_*` — записи в обход (raw agentmemory) идут без scope-маркера и не находятся
> scoped-recall'ом. Подробности изоляции — `docs/maind/guide/memory.md`.

## Группы и участники (membership)

- **MODE=maind (канон):** членство — через **namespaces проекта** в `config.json`
  (`projects[].namespaces`), не через brains. Общий дом — `axioma` (все свои проекты);
  у проекта плюс свой/продуктовый namespace (memster → `[axioma, memster]`); сторонним
  клиентам — namespace без `axioma`. Видимость = `project:<id>` + его `ns:<…>` + `global`.
- **MODE=file/federation (инфра):** `brains` → `{ имя: { members, store, agentmemory } }`;
  участник видит мозг, только если он в `members`.

## Per-project override (как auto-approve)

Глобально: `~/.claude/hooks/memory/env.ini` (MODE) + `config.json`. В проекте:
`<project>/.claude/memory.env.ini` (MODE) и `<project>/.claude/memory.config.json`
(группа/участники); плюс `memory_brain` в `<project>/.swissknife.json` — какую
группу проект использует по умолчанию.

## Дисциплина

- Recall **до** работы, remember **после** — но только межпроектно-полезное.
- Факт — одной фразой + **почему** (как в нативной памяти: суть + зачем).
- Хук только дописывает; чужие факты не трогает. Секреты в память не кладём.
- Группы держим осмысленными: один мозг = реально связанные проекты, не «всё подряд».

## Чеклист качества

- [ ] Перед содержательной задачей сделан `recall` по теме.
- [ ] Зафиксирован только межпроектно-полезный факт (не локальная мелочь), с «почему».
- [ ] Факт ушёл в правильный scope (приватный по умолчанию; `--share`/общий — только если полезен дому).
- [ ] Для проекта режим `MODE=maind` (демон); `maind health` проходит round-trip.

## Ссылки

- `~/.claude/hooks/memory/` — сам хук (`memory.sh`, `env.ini`, `config.json`, `modes/`, `CREDITS.md`).
- `local-topology` (бакет system) — резолв участников через `~/.swissknifeman/topology.json`.
- `cross-project-coordinator` (бакет system) — поставщик межпроектных находок (дубли/расхождения/кандидаты в общий пакет), которые стоит `remember` для группы.
- `general/session-handoff` — смежная тема: передача контекста между сессиями (разово), тогда как shared-memory — постоянный общий store группы.
- Установка файлов хука: `harness hooks --global` (пакет harness).
