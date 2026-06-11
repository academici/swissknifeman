# Laravel Domain Structure

## Принцип

**Сначала домен — потом слой.** Код организуется по бизнес-сущности, а не по техническому типу.

```
✅ app/Models/Ticket/Ticket.php
✅ app/Policies/Ticket/CommonPolicy.php
✅ app/Actions/Ticket/Common/StoreAction.php

❌ app/Models/Ticket.php          — плоский список без домена
❌ app/Policies/TicketPolicy.php  — доменная логика без папки
```

## Каноническая структура `app/`

```
app/
├── Actions/<Domain>/<Subprocess>/   ← use-case точки входа
├── Attributes/<Domain>/             ← PHP-атрибуты, metadata
├── Dto/
│   ├── <Domain>/                    ← Form, View, Policy, Mapper
│   └── Actions/<Domain>/            ← Command DTO для Actions
├── Enums/<Domain>/                  ← статусы, роли, коды событий
├── Events/<Domain>/                 ← доменные события
├── Exceptions/<Domain>/
├── Http/
│   ├── Controllers/<Domain>/
│   ├── Requests/<Domain>/           ← Form Requests
│   └── Resources/<Domain>/          ← API Resources
├── Jobs/<Domain>/
├── Models/<Domain>/
├── Notifications/<Domain>/
├── Observers/<Domain>/
├── Policies/<Domain>/
├── Repositories/<Domain>/           ← *Repository (read) + *StoreRepository (write)
└── Services/<Domain>/
```

## Правило зеркала

Если сущность в `app/Models/Ticket/Ticket.php` — все её соседи живут в `.../Ticket/`:

| Слой | Путь |
|:---|:---|
| Модель | `app/Models/Ticket/Ticket.php` |
| Enum | `app/Enums/Ticket/TicketStatus.php` |
| Controller | `app/Http/Controllers/Ticket/TicketsController.php` |
| Policy | `app/Policies/Ticket/CommonPolicy.php` |
| Repository (read) | `app/Repositories/Ticket/TicketReadRepository.php` |
| Repository (write) | `app/Repositories/Ticket/TicketStoreRepository.php` |
| Service | `app/Services/Ticket/WorkflowService.php` |
| Observer | `app/Observers/Ticket/Observer.php` |
| DTO | `app/Dto/Ticket/Form/Form.php` |
| Action | `app/Actions/Ticket/Common/StoreAction.php` |

## Sub-process разделение в Actions и DTO

Для сложных доменов Actions делятся на бизнес-процессы:

```
app/Actions/Ticket/
├── Common/       ← сохранение формы, взять в работу, общие переходы
├── Question/     ← консолидация, утверждение, письменный ответ
└── Application/  ← call-center, tech-capabilities

app/Dto/Actions/Ticket/
├── Common/
├── Question/
└── Application/
```

## Именование классов

| Тип | Шаблон | Пример |
|:---|:---|:---|
| Action | `VerbNounAction` | `StoreAction`, `RegisteredAction` |
| Command DTO | `VerbNounCommand` | `StoreCommand`, `WrittenReplyCommand` |
| Policy метод | `can<Action>` | `canEdit`, `canRegister` |
| View DTO | `...View` или `...View` с суффиксом | `ListItemView`, `DetailExtraView` |
| Form DTO | `Form` | `Form`, `Participants` |
| Repository (read) | `*ReadRepository` | `TicketReadRepository` |
| Repository (write) | `*StoreRepository` | `TicketStoreRepository` |
| Service (evaluator) | `*Service`, `*Evaluator` | `WorkflowService`, `AccessEvaluator` |

## Запреты

- **Нельзя** добавлять ticket-логику вне `*/Ticket/*`, если это не инфраструктурный слой.
- **Нельзя** использовать папку `Common/` для доменной логики, принадлежащей конкретному домену.
- **Нельзя** создавать класс без проверки: нет ли уже аналогичного в домене.

## Правило навигации

> Если сущность в `app/Models/<Domain>/`, её Policy, Service, Repository, Controller, DTO — все в `.../< Domain>/`.

## PR-чеклист

- [ ] Новый файл лежит в доменной папке
- [ ] Соседние слои синхронизированы (Model / Policy / Service / DTO / Frontend)
- [ ] Нет старых импортов из legacy-путей после rename
