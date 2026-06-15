---
name: modular-architecture
bucket: php
version: 0.3.0
description: "Масштабирование Laravel-кода при росте: организация по бизнес-доменам, Модульный Монолит (Modular Monolith) и паттерны DDD; реализация на nwidart/laravel-modules (module:make*, структура модуля, namespace без Modules\\, Filament discovery); стартовая структура — php/laravel-structure"
risk: write
persona: oss-dev
tags: [php, laravel, architecture, nwidart, laravel-modules, filament]
requires: [laravel]
produces_for: []
outputs: []
snippets: [nwidart-module.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Модульная Архитектура (Laravel)

## Контекст

Скилл для масштабирования при росте: десятки доменов, несколько команд, кодовая база, где стандартной структуры Laravel (`app/Http`, `app/Models`) уже недостаточно. Для сложных проектов мы применяем концепцию **Модульного Монолита (Modular Monolith)** или паттерны **Domain-Driven Design (DDD)**. Стартовая структура нового проекта — канон `php/laravel-structure`; сюда переходи, когда он перестаёт вмещать рост.

**Когда активировать:**

- Просят «разбить монолит на модули», «организовать код по доменам», «выделить домен/bounded context», «модульный монолит», «DDD-структура» в Laravel-проекте.
- Плоская структура `app/Http`, `app/Models` распухла: десятки контроллеров/моделей в одной папке, несколько команд правят один каталог, появляются cross-домен зависимости.
- Упоминают `nwidart/laravel-modules`, команды `module:make*`, каталог `Modules/`, изоляцию миграций/конфигов/фронта по модулям.
- Нужно подключить Filament-ресурсы из модулей (`discoverResources` по модулям) или настроить раздельную Vite-сборку модуля.

Не активировать для нового пустого проекта без признаков роста — там стартовая структура `php/laravel-structure`.

## Основная Идея

Код должен быть организован не по техническому типу (все контроллеры в одной папке, все модели в другой), а по **Бизнес-Доменам** (например, всё, что связано со Счетами (Invoices), лежит в одном месте).

## Алгоритм

Полная процедура перехода к модульной архитектуре и работы с ней.

1. **Определи границы доменов (bounded contexts).** Сгруппируй сущности и логику по бизнес-смыслу (Invoices, Users, Wallets, Notifications), а не по техническому типу. Один домен = один модуль. Избегай «общего» модуля-свалки.

2. **Выбери способ организации модулей:**
   - *Лёгкий путь (без пакета):* каталог `app/Modules/<Domain>/` с подпапками `Controllers/`, `DTOs/`, `Jobs/`, `Models/`, `Providers/`, `Repositories/`, `Services/` (см. «Структура Директорий»). Регистрация — кастомный `ModuleServiceProvider`, сканирующий папки; при необходимости PSR-4 `"Modules\\": "app/Modules/"` в корневом `composer.json` (см. «Автозагрузка»).
   - *Полноценный путь (`nwidart/laravel-modules`):* когда нужны генераторы, изоляция миграций/конфигов и отдельная сборка фронта на модуль. Модули живут в корневом `Modules/`, каждый — самодостаточная единица (см. «Реализация на `nwidart/laravel-modules`»).

3. **Создай модуль (nwidart):** `php artisan module:make <Name>` — генерирует весь скелет (`app/`, `database/`, `routes/`, `tests/`, `config/`, `module.json`, `composer.json`, `vite.config.js`). Файлы внутри модуля — только генераторами `module:make-*` (имя модуля последним аргументом), не руками.

4. **Настрой namespace без префикса `Modules\`:** в `composer.json` модуля маппни PSR-4 `<Name>\` на `app/` (и `<Name>\Database\Factories|Seeders|Migrations`, `<Name>\Tests`); в `config/modules.php` выставь `'namespace' => ''`; в `module.json` укажи провайдер как `"<Name>\\Providers\\<Name>ServiceProvider"`. Корневой `composer.json` сливает модульные через `wikimedia/composer-merge-plugin` — затем один `composer dump-autoload` в корне.

5. **Обеспечь изоляцию модулей:** запрети cross-DB join между модулями — общение только через Contracts/публичные Services или Events (см. «Правила Изоляции Модулей» и «События»). Данные между модулями и слоями — через DTO, не сырыми массивами. Контроллеры держи тонкими: валидация → DTO → вызов Service/Action → Response/Resource.

6. **Подключи Filament-ресурсы модуля (если есть):** сгенерируй штатно `make:filament-resource <Name> --generate`, перенеси в `Modules/<Name>/app/Filament/Resources`, поправь namespace `App\Filament\Resources\...` → `<Name>\Filament\Resources\...` во всех файлах (Resource, Pages, RelationManagers), затем зарегистрируй `discoverResources(in: base_path('Modules/<Name>/app/Filament/Resources'), for: '<Name>\\Filament\\Resources')` в `AdminPanelProvider`.

7. **Настрой фронт модуля (если есть):** свой `vite.config.js` с уникальным `buildDirectory` (например `build-<name>`), входы `resources/css/app.css` и `resources/js/app.js` модуля; экспортируй `paths` для общего агрегатора входов `vite-module-loader.js`.

8. **Проверь по чеклисту качества** и прогони `composer dump-autoload`, миграции модуля и тесты модуля (`Modules/<Name>/tests/`).

Готовые фрагменты для шагов 3–7 (дерево, `module.json`, `composer.json`, `config/modules.php`, команды, `vite.config.js`, блок discovery) — в `snippets/nwidart-module.md`.

## Структура Директорий

Обычно мы создаем директорию `app/Modules` (или `src/Modules`).

```text
app/
  Modules/
    Invoices/
      Controllers/    # HTTP слой
      DTOs/           # Data Transfer Objects
      Jobs/           # Фоновые задачи
      Models/         # Eloquent модели домена
      Providers/      # Service Providers модуля
      Repositories/   # Доступ к данным (если используется)
      Services/       # Бизнес-логика
    Users/
      ...
```

## Правила Изоляции Модулей

1.  **Отсутствие перекрестных зависимостей БД:** Модуль `Invoices` не должен напрямую делать SQL Join с таблицами модуля `Users`. Вместо этого модули должны общаться через интерфейсы или публичные Сервисы (Contracts).
2.  **Использование DTO:** При передаче данных между модулями (или от контроллера к сервису) используйте Data Transfer Objects. Никаких сырых массивов.
3.  **Тонкие Контроллеры:** Контроллер должен только:
    - Валидировать Request.
    - Сформировать DTO.
    - Вызвать метод Сервиса или Action-класса.
    - Вернуть Response/Resource.
    Вся бизнес-логика должна жить в слое Services или Actions.

## События (Events)

Для максимальной слабой связности (loose coupling) между модулями используйте Event-Driven подход.
Если при регистрации пользователя нужно отправить письмо и создать кошелек, модуль `Users` просто кидает событие `UserRegistered`.
Модуль `Notifications` и модуль `Wallets` слушают это событие и выполняют свою логику независимо.

## Автозагрузка (Autoloading)

Для регистрации провайдеров, роутов и миграций модулей можно использовать пакеты (например, `nWidart/laravel-modules`) или делать это вручную через кастомный `ModuleServiceProvider`, который сканирует папки модулей.

В `composer.json` может потребоваться настройка PSR-4 (хотя внутри `app/` Laravel по умолчанию резолвит всё под неймспейсом `App\`):
```json
"autoload": {
    "psr-4": {
        "App\\": "app/",
        "Modules\\": "app/Modules/" 
    }
}
```

## Реализация на `nwidart/laravel-modules`

Когда ручной `ModuleServiceProvider` перестаёт окупаться (нужны генераторы, отдельная сборка фронта, изоляция миграций/конфигов на модуль) — переходим на пакет `nwidart/laravel-modules`. Модули живут в корневой директории `Modules/` (а не в `app/Modules/`), каждый — самодостаточная единица со своим `composer.json`, провайдерами, роутами, тестами и Vite-конфигом.

### Структура модуля

Скелет, который генерирует `module:make`, повторяет структуру Laravel-приложения внутри модуля:

```text
Modules/Billing/
  app/
    Filament/Resources/   # Filament-ресурсы модуля
    Http/Controllers/
    Models/Invoice/       # группировка по сущности (Invoice.php, InvoiceItem.php)
    Providers/            # BillingServiceProvider, RouteServiceProvider, EventServiceProvider
    Repositories/
  config/config.php       # сливается в config('billing.*')
  database/{factories,migrations,seeders}/
  resources/{css,js,views}/
  routes/{web.php,api.php}
  tests/{Feature,Unit}/
  module.json             # манифест: имя, alias, приоритет, провайдеры
  composer.json           # PSR-4 модуля (сливается merge-plugin'ом в корень)
  vite.config.js          # отдельная сборка фронта модуля (build-billing)
```

### Команды генерации

- `php artisan module:make Billing` — создать модуль (весь скелет выше: `app/`, `database/`, `routes/`, `tests/`, `config/`, `module.json`, `composer.json`, `vite.config.js`).
- `php artisan list module` — посмотреть все доступные `module:*` команды.
- Файлы **внутри** модуля: имя модуля — последний аргумент:
  - `php artisan module:make-model Invoice Billing`
  - `php artisan module:make-controller InvoiceController Billing`
  - `php artisan module:make-migration create_invoices_table Billing`
  - `php artisan module:make-provider`, `module:make-seeder`, `module:make-test` — аналогично.
- Группировка сущностей в подпапки — путь прямо в имени: `php artisan module:make-model Invoice/Invoice Billing` → `Billing\Models\Invoice\Invoice`.

### Конвенция маппинга namespace (без префикса `Modules\`)

По умолчанию nwidart раскладывает классы под `Modules\Billing\Models\Invoice`. Конвенция проекта: **неймспейс начинается с имени модуля** — `Billing\Models\Invoice` вместо `Modules\Billing\Models\Invoice` (короче, читаемее, симметрично `App\`). Достигается двумя настройками:

1. **PSR-4 в `composer.json` модуля** маппит `Billing\` на `app/` (а также `Billing\Database\Factories\`, `...\Seeders\`, `...\Migrations\`, `Billing\Tests\`).
2. **`'namespace' => ''` в `config/modules.php`** — пустой префикс, чтобы пакет резолвил классы модуля как `Billing\...`, а не `Modules\Billing\...` (это влияет на генераторы, Blade-компоненты и т.п.).
3. Провайдер в `module.json` указывается без `Modules\`: `"providers": ["Billing\\Providers\\BillingServiceProvider"]`.

Корневой `composer.json` сливает все модульные `composer.json` через `wikimedia/composer-merge-plugin` (`"merge-plugin": { "include": ["Modules/*/composer.json"] }`), поэтому отдельный `dump-autoload` на модуль не нужен — после создания модуля достаточно одного `composer dump-autoload` в корне.

### Сборка фронта модуля (Vite)

У каждого модуля свой `vite.config.js` с отдельным `buildDirectory` (`build-billing`), чтобы ассеты модулей не перетирали друг друга; входы — `resources/css/app.css` и `resources/js/app.js` модуля. Конфиг экспортирует `paths` для общего агрегатора входов (`vite-module-loader.js`).

### Регистрация и discovery Filament-ресурсов по модулям

nwidart не генерирует Filament-ресурсы прямо в модуль. Рабочий цикл:

1. Сгенерировать ресурс штатной командой Filament: `php artisan make:filament-resource Invoice --generate` (попадает в `app/Filament/Resources`).
2. Перенести файлы в `Modules/Billing/app/Filament/Resources`.
3. Поправить namespace во **всех** перенесённых файлах (Resource, Pages, RelationManagers): `App\Filament\Resources\...` → `Billing\Filament\Resources\...`.

Регистрация (discovery) в панели — в `app/Providers/Filament/AdminPanelProvider.php`: каждый модуль добавляет свой `discoverResources` с базовым путём и неймспейсом модуля:

```php
->discoverResources(
    in: base_path('Modules/Billing/app/Filament/Resources'),
    for: 'Billing\\Filament\\Resources',   // namespace БЕЗ префикса Modules\
)
```

Подробное дерево, `module.json`, фрагменты `composer.json`/`config/modules.php`, `vite.config.js` и блок discovery — в `snippets/nwidart-module.md`.

## Чеклист качества

- [ ] Код организован по бизнес-доменам, а не по техническому типу
- [ ] Между модулями нет cross-DB join'ов; общение через Contracts/Services или Events
- [ ] Данные между модулями/слоями передаются через DTO, не сырыми массивами
- [ ] Контроллеры тонкие, бизнес-логика в Services/Actions
- [ ] (nwidart) Файлы модуля созданы через `php artisan module:make*`, а не руками
- [ ] (nwidart) Namespace модуля — `Module\...` без префикса `Modules\` (PSR-4 + `config/modules.php` `namespace => ''`)
- [ ] (nwidart) Каждый Filament-ресурс модуля зарегистрирован через `discoverResources` с путём `base_path('Modules/{Name}/app/Filament/Resources')` и неймспейсом модуля
- [ ] (nwidart) У модуля с фронтом свой `vite.config.js` с уникальным `buildDirectory`

## Ссылки

- snippets/nwidart-module.md — дерево модуля, module.json, composer namespace, команды module:make*, vite.config.js, Filament discovery
- https://github.com/nWidart/laravel-modules
- Стартовая структура нового проекта: скилл `php/laravel-structure`
