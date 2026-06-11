---
name: project-map
bucket: general
version: 0.1.0
description: "Быстрая карта структуры проекта и зон ответственности по директориям для безопасного роутинга изменений."
risk: read
persona: oss-dev
tags: [conventions, navigation]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Project Map

## Когда активировать

Используйте этот skill, если нужно быстро понять, где вносить изменения и в каком слое должна жить логика.

## Быстрый роутинг по директориям

- `app/Actions/` — бизнес-операции, точка входа use-case.
- `app/Services/` — доменная оркестрация, интеграции, вычисления.
- `app/Repositories/` — доступ к данным (`*Repository` read-side, `*StoreRepository` write-side).
- `app/Http/Controllers/` — только HTTP-слой: авторизация, валидация, вызов Action.
- `app/Policies/` — правила доступа и permission-контракты.
- `app/Dto/` — DTO и маппинг рядом с DTO-классами.
- `app/Enums/` — статусы, роли, типы, workflow-константы.
- Граф переходов статусов тикета — `TicketStatus::transitionDefinitions()`, runtime — `App\Services\Ticket\TicketStatusTransitions` + `App\Services\Ticket\StateMachine` (не отдельная папка `app/States/`).
- `resources/js/` — Inertia/Vue UI и клиентская логика.
- `routes/` — HTTP-маршрутизация.
- `tests/Feature` и `tests/Unit` — контракт поведения и чистая логика.
- `docs/workflow/` — источник описания доменных процессов.

## Принцип размещения логики

- Если это бизнес-операция с изменением состояния — `Action`.
- Если это повторно используемая оркестрация — `Service`.
- Если это повторяющиеся выборки/мутации — `Repository`.
- Если это только API/страница/редирект — `Controller`.
- Если это проверка прав — `Policy` + permissions enum.

## Антипаттерны

- Бизнес-логика в контроллерах.
- Gate/authorization в репозиториях.
- Переиспользуемые query-предикаты, размазанные по нескольким файлам.
- Хардкод URL во frontend при наличии route/action functions.

## Связанные источники

- Базовая архитектура: `.ai/guidelines/architecture.md`
- Навигация по контексту: `.ai/guidelines/navigation.md`
- Workflow-зависимости: `.ai/guidelines/project-development.md`
