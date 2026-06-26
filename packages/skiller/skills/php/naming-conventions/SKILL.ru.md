---
name: naming-conventions
bucket: php
version: 0.1.0
description: "Именование сущностей Laravel/PHP: методы репозиториев по намерению (а не findByCodeOrFail-взрыв), Action/DTO/VO/Enum/Event/Job, таблицы/колонки/роуты. Борьба с мусорными именами, которые любит генерить ИИ. Активировать при создании или ревью имён классов, методов, миграций."
risk: read
persona: oss-dev
tags: ["php", "laravel", "naming", "conventions", "code-style", "readability"]
requires: []
produces_for: []
outputs: []
snippets: ["naming-antipatterns.php", "repository-method-naming.php"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Именование сущностей в Laravel/PHP

## Контекст

ИИ систематически генерит «мусорные» имена: `findByCodeOrFail`, `findByEmailOrFail`,
`getUserDataById`, `OrderManager`, `handleData`. Этот скилл задаёт дисциплину именования по
типам сущностей Laravel-проекта. Базовый принцип (имя = намерение, не реализация) и
кросс-языковые правила — в `general/naming-conventions`; здесь — PHP/Laravel-конкретика и
разбор частых анти-паттернов.

Не путать с соседями: `code-style-spatie` задаёт стиль кода и именование **роутов/контроллеров**;
`named-arguments` — стиль *вызова*; этот скилл — про имена *самих сущностей* (классы, методы, поля).

## Когда активировать

- Создаёшь/ревьюишь имя класса (Action, Repository, DTO, VO, Service, Enum, Event, Job).
- Называешь метод репозитория/сервиса/модели или scope.
- Пишешь миграцию (таблицы, колонки, ключи).
- Видишь сгенерированное имя, по которому не ясно намерение.

## Главный анти-паттерн: `findByX…OrFail`-взрыв

Метод-на-каждое-поле — экспоненциальный рост и дублирование репозитория:

```php
// ❌ мусор: один метод на колонку, политика ошибок продублирована в имени N раз
public function findByCodeOrFail(string $code): Order { /* … */ }
public function findByEmailOrFail(string $email): Order { /* … */ }
public function findBySlugOrFail(string $slug): Order { /* … */ }
```

Чем заменить (по убыванию предпочтения):

1. **Route model binding** — для контроллеров поиск по ключу делает Laravel
   (`getRouteKeyName()` для не-id), метод репозитория вообще не нужен.
2. **Model scope по намерению** — повторяемый предикат → `scopeActive`, `scopeForUser`;
   репозиторий их компонует. Имя scope про *бизнес-смысл*, не про колонку.
3. **Один метод поиска + критерий**: `findBy(Criteria $c)` / спецификация, а не метод-на-поле.
4. **Eloquent уже умеет** `firstWhere('code', $code)`, `findOrFail($id)`,
   `where(...)->firstOrFail()` — не оборачивай тривиальное.

Допустимо: **один канонический** `findByIdOrFail` поверх `queryForUser()` (см. скилл
`repositories`) и **именованные доменные** запросы (`pendingForReview()`), когда выборка
осмысленна в домене. Грань: «по намерению/бизнес-смыслу» — да; «по каждой колонке» — нет.

## Именование по типам сущностей

| Сущность | Правило | Пример |
|:--|:--|:--|
| **Action** | императив + объект, один публичный `__invoke`/`execute`; без `Manager`/`Service`-хвоста | `CreateOrder`, `PublishDocument`, `CancelSubscription` |
| **Repository** | `<Домен>ReadRepository` / `<Домен>StoreRepository`; методы по *намерению* | `forUser()`, `pendingForReview()`, `withListRelations()` |
| **DTO / Form** | суффикс `Data` (данные) или `Form` (вход команды); не `DTO`/`Object` | `OrderData`, `CreateOrderForm` |
| **Value Object** | доменное существительное, без суффикса | `Money`, `EmailAddress`, `DateRange` |
| **Service** | `<Роль>Service` только при реальной ответственности; иначе — Action/Repository | `VisibilityService`, `PriceCalculator` (не `OrderManager`) |
| **Enum** | имя в единственном числе, кейсы PascalCase | `OrderStatus::Pending`, `Role::Admin` |
| **Event** | прошедшее время (факт случился) | `OrderShipped`, `InvoicePaid` |
| **Listener / Job** | императив (что сделать) | `SendShipmentNotification`, `ProcessPayment` |
| **Model scope** | `scope` + доменное намерение | `scopeActive`, `scopeForUser`, `scopeWithStatus` |
| **Policy** | `<Model>Policy`, методы = ability (`view`, `update`, `delete`) | `OrderPolicy::update()` |
| **Контроллер/роут** | см. `code-style-spatie` (ресурс во мн.ч., kebab URL, camelCase route) | `OrdersController` |

## База данных (миграции)

- Таблицы — snake_case **во множественном** (`orders`, `order_items`); pivot — две модели
  в единственном по алфавиту (`role_user`).
- Колонки — snake_case; FK — `<single>_id` (`user_id`); булевы — `is_`/`has_` (`is_active`);
  даты/время — `_at` (`published_at`), `_date`/`_on` для дат.
- Без `tbl_`/`col_`-префиксов и венгерской нотации.

## Чеклист качества

- [ ] Нет `findByX…OrFail` на каждое поле; поиск — через binding/scope/критерий или один канонический lookup.
- [ ] Action — императив + объект, один публичный метод; нет `Manager`/`Helper`/`Util`/`Processor`-классов без роли.
- [ ] DTO — `Data`/`Form`; VO — доменное существительное без суффикса типа.
- [ ] Enum в единственном числе, кейсы PascalCase; Event — прошедшее время; Job/Listener — императив.
- [ ] Методы репозитория названы по *намерению* (что выбираем), а не по механике SQL.
- [ ] Таблицы во мн.ч. snake_case; FK `_id`, булевы `is_/has_`, время `_at`.
- [ ] Лишний `get`/суффикс типа убран (`user(id)`, не `getUserObjectById`).

## Когда какой сниппет открывать

| Ситуация | Файл |
|:--|:--|
| Нужна сводная таблица «плохо → хорошо» по всем типам Laravel-сущностей | `snippets/naming-antipatterns.php` |
| Рефакторишь репозиторий с россыпью `findByX` в scope/критерий | `snippets/repository-method-naming.php` |

## Ссылки

- `general/naming-conventions` — язык-агностичные принципы (intent, шумовые слова, CQS).
- `php/repositories` — read/store split, `queryForUser`, scopes (где живут именованные запросы).
- `php/code-style-spatie` — стиль кода и именование роутов/контроллеров/конфигов.
- `php/named-arguments` — именованные аргументы на стороне вызова.
- `php/php-patterns` — VO/DTO/specification (куда уходит «критерий» вместо `findByX`).
- `php/laravel-structure` — где какие классы лежат в дереве проекта.
