---
name: laravel
bucket: php
version: 0.4.0
description: "Используй при применении Laravel architecture patterns: actions, repositories, resources."
risk: write
persona: oss-dev
tags: ["php", "laravel", "architecture", "patterns"]
requires: []
produces_for: ["repositories", "dependency-injection", "database", "modular-architecture", "filament", "botkit"]
outputs: []
snippets: ["service-provider.php", "repository-pattern.php", "action-class.php", "form-request.php", "api-resource.php", "event-listener.php", "custom-middleware.php", "actions.md", "authorization.md", "db-conventions.md", "dto.md", "eloquent-model.md", "layer-boundaries.md", "routes-organization.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Хаб-навигатор по архитектурным паттернам Laravel: actions, repositories, resources, модели,
авторизация, маршруты. Сам скилл тонкий — вся конкретика в 14 сниппетах: `.php`-скелеты
(минимальный каркас класса) и `.md`-разборы (правила, границы, антипаттерны). Тело здесь
служит одной цели — быстро привести тебя к нужному сниппету. Размещение классов и нейминг —
в соседних скиллах (см. `## Ссылки`), тут не дублируются.

## Когда активировать

- Создаёшь новый класс слоя (Action / Repository / Resource / FormRequest / Middleware / Listener /
  Policy / Service Provider) и нужен канонический каркас.
- Сомневаешься, **в каком слое** должна жить логика (мутация, бизнес-решение, выборка, side-effect).
- Настраиваешь Eloquent-модель, миграцию, авторизацию или организацию маршрутов.

## Алгоритм

1. **Сначала определи слой.** Прежде чем писать класс — открой `snippets/layer-boundaries.md` и
   реши, куда логика принадлежит (см. ниже «Границы слоёв»). Неправильный слой — самая дорогая ошибка.
2. **Возьми каркас.** Для типового класса открой соответствующий `.php`-скелет из таблицы ниже.
3. **Добери правила.** Для нетривиальных тем (action, авторизация, DTO, модель, БД, маршруты)
   читай `.md`-разбор — там правила, антипаттерны и forbidden-матрицы.
4. **Сверься с соседями** по нейминг/размещение/стиль (`## Ссылки`) — этот скилл их не повторяет.

## Границы слоёв (altitude)

Корневое правило экосистемы: каждый класс знает свою высоту и не лезет в чужую.
Полная карта, forbidden-матрица и антипаттерны — в `snippets/layer-boundaries.md`.

| Слой | Путь | Живёт здесь | НЕ его дело |
|:---|:---|:---|:---|
| **Action** | `app/Actions/` | use-case, **единственная** граница `DB::transaction()`, мутация entity, dispatch событий | принимать `Request`, выборки-для-UI |
| **Repository** | `app/Repositories/` | data-access: `*ReadRepository` (Builder/фильтры) + `*StoreRepository` (мутации) | открывать транзакцию use-case, бизнес-решения, история/события → подробно `php/repositories` |
| **Model** | `app/Models/` | casts, отношения, scopes (повторяемые предикаты), accessors | бизнес-сценарии, HTTP |
| **Resource** | `app/Http/Resources/` | форма JSON-ответа API (read-only трансформация) | выборки, мутации, авторизация |
| **Service** | `app/Services/` | evaluator (read-only) · read-side facade · side-effect без бизнес-решения | мутация entity, `Request`, `abort()` |
| **Controller** | `app/Http/Controllers/` | HTTP-only: authorize → validate (FormRequest) → Action → respond | бизнес-логика, прямые мутации |
| **Policy** | `app/Policies/` | проверки авторизации | persistence, side-effects |

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Решаю, в каком слое жить логике; нужна forbidden-матрица «кому что нельзя» | `snippets/layer-boundaries.md` |
| Пишу use-case с мутацией: каркас Action-класса | `snippets/action-class.php` |
| Правила Action: `final readonly`, Command-DTO, `DB::transaction()`, ValidationException | `snippets/actions.md` |
| Каркас репозитория (interface + Eloquent-реализация) | `snippets/repository-pattern.php` |
| Настраиваю Eloquent-модель: PHP-атрибуты, fillable, casts, accessors, relations | `snippets/eloquent-model.md` |
| Именование таблиц (domain prefix), миграции через model reference | `snippets/db-conventions.md` |
| Валидация входа HTTP: каркас FormRequest | `snippets/form-request.php` |
| Форма JSON-ответа API: каркас Resource | `snippets/api-resource.php` |
| DTO на Spatie LaravelData: Form/View/Policy/Mapper/Command + генерация TypeScript | `snippets/dto.md` |
| Авторизация: PermissionEnum + Policy с `#[GateAbility]` + Abilities-DTO для фронта | `snippets/authorization.md` |
| Регистрирую/бутстраплю сервис: каркас ServiceProvider | `snippets/service-provider.php` |
| HTTP-фильтр на запрос: каркас Middleware | `snippets/custom-middleware.php` |
| Реакция на доменное событие: каркас Listener | `snippets/event-listener.php` |
| Организация `routes/web.php`/`api.php`: `Route::controller()->prefix()->name()->group()`, доменные подпрефиксы, precognitive, `throttle:30,1` | `snippets/routes-organization.md` |

## Чеклист качества

- [ ] Слой выбран по `layer-boundaries.md`: мутация → Action, выборка → Repository, JSON → Resource.
- [ ] Action — единственная транзакционная граница; репозиторий транзакцию не открывает.
- [ ] Ни один класс ниже Controller/FormRequest не принимает `Illuminate\Http\Request`.
- [ ] Resource не делает выборок и не решает авторизацию — только трансформация уже загруженного.
- [ ] Повторяемые where-цепочки вынесены в model scopes (см. `eloquent-model.md` / `php/repositories`).
- [ ] Размещение и нейминг сверены с `php/laravel-structure` и `general/naming-conventions` (не угаданы).
- [ ] Стиль кода соответствует `php/code-style-spatie` (`final`, типизация, именованные аргументы).

## Ссылки

- Структура проекта и размещение классов (доменная таксономия, правило зеркала) → `php/laravel-structure`
- Репозитории (Read/Store split, scopes, visibility) → `php/repositories`
- Нейминг классов и методов по намерению → `general/naming-conventions`
- Стиль кода (final, типизация, именованные аргументы, Spatie-конвенции) → `php/code-style-spatie`
- DI и взаимодействие компонентов → `php/dependency-injection`
- DTO на пакете → `laravel-data-layer/laravel-data`; «голые» доменные паттерны (VO/pipeline/specification) → `php/php-patterns`
- Миграции и модели → `php/database`; рост до модулей → `laravel-architecture/modular-architecture`
- Тесты архитектурных слоёв → `laravel-testing/laravel-testing`
- Общие лучшие практики Laravel → `php/laravel-best-practices` (external)
