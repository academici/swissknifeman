---
name: tech-stack-selection
bucket: architect
version: 0.1.0
description: Выбор технологического стека с trade-off матрицей до архитектурного дизайна. ADR-первый шаг
risk: draft
persona: architect
tags: [stack-choice, architecture]
requires: [brd]
produces_for: [architecture, oss-development, release-engineering]
outputs: ["docs/03_Dev/Tech_Stack_Selection.md", "docs/03_Dev/ADR/ADR-001_tech_stack.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Tech Stack Selection

Применять когда: нужно **выбрать** язык / фреймворк / БД / инфра-платформу до начала архитектурного дизайна. Не путать с `architecture` — там уже проектируют компоненты при выбранном стеке.

Должен быть **выполнен после `brd`** (нужны нефункциональные требования и нагрузка) и **до `architecture`** (без стека нечего проектировать).

---

## Когда НЕ применять

- Стек уже зафиксирован пользователем или ADR — отказать, идти на `architecture`.
- OSS-проект с одной платформой по определению (BrainKit — JS, AzGuard — PHP) — стек выбран ранее, не повторять.
- Проект расширяет существующий код — стек унаследован, делать ADR на конкретный субмодуль если нужно.
- Нет BRD / нефункциональных требований — отказать, отправить на `brd`.

---

## 6 осей выбора (рассматривать все)

| Ось | Что выбираем | Влияет на |
|:---|:---|:---|
| **Язык backend** | TS/Node, Python, Go, Rust, PHP, Java | Производительность, найм, экосистема |
| **Backend-фреймворк** | NestJS, FastAPI, Laravel, Gin, Actix, Spring | Скорость разработки, конвенции |
| **БД (OLTP)** | Postgres, MySQL, SQLite, MongoDB, DynamoDB | Транзакции, scale, cost |
| **Frontend** | Next.js, Nuxt, SvelteKit, Flutter, native | UX, SEO, time-to-market |
| **Infra / deployment** | Vercel, Cloudflare, AWS, GCP, VPS, k8s | Cost, latency, ops complexity |
| **Async / queue** | BullMQ, SQS, RabbitMQ, Temporal, none | Throughput, reliability |

Дополнительные оси при необходимости: cache (Redis/KeyDB/in-memory), search (Meilisearch/Elastic), analytics, ML serving, payments.

---

## Алгоритм выбора (5 шагов)

### Шаг 1. Жёсткие ограничения
Из BRD и проекта извлечь:
- **Регуляторика** — например, fintech требует резидентности данных (Finbrain), AI-tutoring требует COPPA/возрастных ограничений (Edufy)
- **Существующие компетенции команды** — solo founder с PHP не должен брать Rust «потому что модно»
- **Бюджет infra** — pre-seed: serverless / managed; series-A+: можно k8s
- **Конкретные требования к стеку из BRD** — например, «должен работать с iOS Live Activities» = Swift native

Если хоть одна ось зафиксирована жёстко — записать в раздел **Constraints**, исключить альтернативы.

### Шаг 2. Trade-off матрица (обязательна)

Для **минимум 2 вариантов на каждой оси**, прошедших Шаг 1, заполнить:

| Критерий | Вариант A | Вариант B | Вариант C |
|:---|:---|:---|:---|
| Производительность (RPS на 1 vCPU) | | | |
| Time-to-market (1 dev, неделями до MVP) | | | |
| Стоимость найма (медиана senior $/мес) | | | |
| Зрелость экосистемы (рейтинг ключевых либ) | | | |
| Operability (cloud-native? managed?) | | | |
| Lock-in (можно ли уйти за 2 недели) | | | |
| Стоимость infra на baseline-нагрузке | | | |
| Совпадение с другими проектами vault | | | |

Конкретные числа > эпитеты. Если не знаешь — пометь `?` и оставь как открытый вопрос.

### Шаг 3. Совместимость осей
Не выбирать оси независимо. Проверить совместимость:
- **Backend + БД** — есть ли первоклассный ORM/драйвер
- **Frontend + Backend** — поддерживается ли тип-репликация (tRPC, GraphQL, OpenAPI)
- **Infra + язык** — холодный старт, runtime support (Cloudflare Workers ≠ Node-only)
- **Queue + Backend** — нативный SDK или нужен бриджик

Если стек собирается из «зоопарка» — назвать integration cost явно.

### Шаг 4. Рекомендация + миграционный путь
- **Стартовый стек MVP** — одна конкретная комбинация, явно.
- **Что заменяемо без переписывания** — компоненты с чистыми интерфейсами (БД, queue, cache).
- **Что НЕ заменяемо** — обычно язык backend и UI-фреймворк. Это «жёсткое ядро».
- **Триггеры пересмотра** — конкретные метрики (например, «при > 10k RPS пересмотреть кэш-стратегию»).

### Шаг 5. ADR-001 — фиксация решения
Создать `docs/03_Dev/ADR/ADR-001_tech_stack.md` сразу. Не «когда-нибудь потом». Это первая ADR проекта.

---

## Что агент добавляет сам

- **Антипаттерны для стадии.** Pre-seed solo founder + микросервисы + k8s = красный флаг. Назвать явно.
- **Скрытые издержки.** SQLite кажется бесплатным — пока не понадобится горизонтальный scale. Postgres Aurora масштабируется — но cold-start serverless v2 = 12+ секунд.
- **Hire-ability.** Стек должен быть найм-совместимым на ICP проекта (если планируется команда).
- **Compat с vault-проектами.** Если другой проект уже на TS/Postgres — есть инсайт «не плодить зоопарк» и переиспользовать паттерны (см. `02 - Knowledge/`).
- **Open-source readiness.** Если планируется open-source spin-off — учесть лицензии зависимостей (см. `dependency-audit` в OSS-треке).

---

## Структура output-файлов

### `docs/03_Dev/Tech_Stack_Selection.md`

```markdown
---
project: [ProjectName]
stage: tech-stack-selection
based_on_brd: docs/03_Dev/BRD.md
produces_input_for: [Architecture_[Name].md, ADR-001_tech_stack.md]
---

# Tech Stack Selection — [ProjectName]

## Constraints (из BRD и реальности)
- Регуляторика: ...
- Команда: ...
- Бюджет infra: ...
- Жёстко заданные элементы стека: ...

## Trade-off матрица: backend язык
[таблица]

## Trade-off матрица: БД
[таблица]

## Trade-off матрица: frontend
[таблица]

## Trade-off матрица: infra
[таблица]

## Совместимость осей
- Backend + БД: ...
- Frontend + Backend: ...
- Infra + язык: ...

## Стартовый стек MVP
- Backend: ...
- БД: ...
- Frontend: ...
- Infra: ...
- Queue: ...

## Заменяемые компоненты
- [список с указанием стоимости миграции]

## Жёсткое ядро (не меняем без переписывания)
- ...

## Триггеры пересмотра
- При [метрика] → пересмотреть [компонент]

## Антипаттерны для стадии (агент)
- ...

## ADR
→ `docs/03_Dev/ADR/ADR-001_tech_stack.md`
```

### `docs/03_Dev/ADR/ADR-001_tech_stack.md`

```markdown
# ADR-001: Tech stack selection for [ProjectName]

## Status
Accepted — YYYY-MM-DD

## Context
[краткая выжимка из BRD + Tech_Stack_Selection.md]

## Decision
[стек одной таблицей]

## Alternatives considered
[главные альтернативы по каждой оси и почему отклонены]

## Consequences
- Положительные: ...
- Отрицательные / accepted риски: ...
- Триггеры для следующего ADR: ...
```

---

## Жёсткие запреты на этой стадии

НЕЛЬЗЯ:
- Выбирать стек «потому что модно / любимый»
- Пропустить trade-off матрицу хотя бы для backend и БД
- Брать k8s/микросервисы на pre-seed без жёсткого обоснования
- Оставлять «решим потом» — это `architecture` будет страдать
- Не создавать ADR-001 сразу
