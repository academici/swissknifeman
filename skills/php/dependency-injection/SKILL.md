---
name: dependency-injection
bucket: php
version: 0.1.0
description: "Взаимодействие слоёв через constructor injection: final readonly + promotion, матрица инъекций, композиция Actions"
risk: write
persona: oss-dev
tags: ["php", "laravel", "di", "architecture"]
requires: []
produces_for: []
outputs: []
snippets: ["action-di.php", "service-orchestrator.php", "composite-action.php", "controller-action.php", "provider-bindings.php", "di-matrix.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Система взаимодействия кода в Laravel-приложении: **constructor injection — единственный канал зависимостей доменного кода**. Конструктор объявляет коллабораторов (сервисы, репозитории, другие Actions), параметры метода несут данные (модели, DTO, примитивы). Контейнер Laravel резолвит конкретные классы zero-config — биндинги в провайдере по умолчанию не нужны.

Канон класса с зависимостями:

```php
final readonly class StoreAction
{
    public function __construct(
        private DocumentPersistenceService $persistence,
    ) {}
}
```

`final readonly` + **promoted properties**. Эталонный проект местами пишет отдельные свойства с `private readonly` в обычном классе — канон упрощает: promotion в конструкторе, `readonly` на уровне класса.

## Алгоритм

### 1. Определи слой и сверь направление инъекции

Открой `di-matrix.md` и проверь, что зависимость разрешена для слоя: Controller → Action; Action → Service / Repository / другие Actions; Service → Repository / Service; Repository → только узкие сервисы-фильтры; Policy → read-only сервисы. **Никто не инжектит Controller или Request.** Нарушение направления — не «добавить биндинг», а пересмотреть границу классов.

### 2. Объяви зависимости в конструкторе

- `final readonly class` + promoted `private`-свойства, без тела конструктора.
- Только конкретные классы. Интерфейс + bind — лишь при реальной вариативности реализаций (драйверы, внешние интеграции, подмена сложной зависимости в тестах) — см. `provider-bindings.php`.
- Данные (Document, DTO, флаги) — параметрами `execute()`/метода, не в конструктор.

### 3. Выбери форму по сценарию

- Один шаг записи → Action с 1-2 зависимостями, Command DTO, `DB::transaction` (`action-di.php`).
- Координация нескольких репозиториев/сервисов → сервис-оркестратор без своей транзакции (`service-orchestrator.php`).
- Многошаговый сценарий → **composite Action**, инжектирующий атомарные Actions, один `execute()`, одна внешняя транзакция (`composite-action.php`). Не заводить «use-case Service».
- Вызов из HTTP → тонкий контроллер: Action через method injection в экшен-метод (нужен одному методу) или constructor (нескольким) (`controller-action.php`).

### 4. Различай коллабораторов и инфраструктуру

Инжектируется то, у чего есть своя логика и что подменяется в тестах. Инфраструктурные статики допустимы как есть: `DB::transaction`, `Event::dispatch` / `SomethingChanged::dispatch`, `Gate`. Запрещены `app()` / `resolve()` / фасадный резолв **зависимостей** в доменном коде — скрытая зависимость, нетестируемо.

### 5. Валидируй бизнес-правила правильно

Нарушение бизнес-правила в Action → `ValidationException::withMessages([...])`, не `abort()`. Проверки — до открытия транзакции, где возможно.

### 6. Реагируй на сигналы плохих границ

- Циклическая зависимость — выделяй третий класс с общей логикой.
- 6+ зависимостей в конструкторе — класс делает слишком много, дели.
- Зависимость нужна одному методу из десяти — пересмотри границы класса.

## Когда какой сниппет открывать

| Задача | Сниппет |
|:---|:---|
| Новый Action: одна зависимость или StateMachine + репозиторий, валидация | `action-di.php` |
| Сервис, координирующий несколько репозиториев/сервисов, события, broadcast | `service-orchestrator.php` |
| Многошаговый сценарий из существующих Actions, одна транзакция | `composite-action.php` |
| Как контроллер получает и вызывает Action, method vs constructor injection | `controller-action.php` |
| Кажется, что нужен интерфейс/bind/контекстуальный биндинг | `provider-bindings.php` |
| Проверка направления инъекции, разбор антипаттерна | `di-matrix.md` |

## Чеклист качества

- [ ] Класс с зависимостями — `final readonly`, promoted properties, пустое тело конструктора
- [ ] В конструкторе только коллабораторы; данные — параметрами метода
- [ ] Зависимости — конкретные классы; интерфейс только при реальной вариативности (и тогда bind в провайдере)
- [ ] Направление инъекции разрешено матрицей слоёв; Request/Controller никуда не инжектятся
- [ ] Нет `app()` / `resolve()` / фасадного резолва зависимостей в Action/Service/Repository
- [ ] Многошаговый сценарий — composite Action с одной внешней транзакцией, не use-case Service
- [ ] Бизнес-валидация в Action — `ValidationException`, не `abort()`
- [ ] Конструктор ≤ 5 зависимостей; нет циклов; нет зависимостей «для одного метода»
- [ ] PHP-сниппеты проходят `php -l`

## Ссылки

- `php/laravel-structure` — где живут Actions/Services/Repositories, правила размещения файлов.
- `php/repositories` — что разрешено инжектить репозиториям и как они устроены внутри.
- `php/laravel` → `layer-boundaries.md` — границы слоёв и направления вызовов; `actions.md` — анатомия Action и Command DTO.
