---
name: spatie-settings
bucket: php
version: 0.1.0
description: "spatie/laravel-settings: типизированные классы настроек (extends Settings, public-свойства, group()), миграции настроек add/migrate/rename, кэш, выбор рантайм-настройки vs config/, привязка к Filament SettingsPage. Активировать при создании/правке класса настроек, добавлении свойства, settings-миграции или экрана редактирования настроек."
risk: write
persona: oss-dev
tags: ["php", "laravel", "spatie", "settings", "filament", "configuration"]
requires: []
produces_for: []
outputs: []
snippets: ["ExampleSettings.php", "create_example_settings.php", "filament-settings-page.php"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: spatie/laravel-settings

## Контекст

`spatie/laravel-settings` хранит настройки приложения как **типизированный PHP-класс**: свойства маппятся на строки в БД (репозиторий `database`) или Redis, читаются/пишутся через обычные свойства объекта и редактируются нетехническими пользователями в админке. В отличие от `config/*.php` (статика из env, фиксируется на деплое), значения здесь меняются **в рантайме** без релиза.

**Когда активировать:**

- Создаёте новый класс настроек (`extends Settings`) или добавляете/удаляете/переименовываете свойство существующего.
- Пишете settings-миграцию (`SettingsMigration` с `migrator->add/rename/delete`).
- Решаете, где хранить значение: `config/` vs класс настроек.
- Делаете экран редактирования настроек (Filament `SettingsPage` или произвольная форма).
- Разбираетесь с кэшем настроек, регистрацией класса или ошибкой «missing settings».

Скилл переносимый: домены в примерах нейтральные (`Order`, `Article`, `Notification`), namespace `App\Settings\...`.

**Laravel Boost**: при подключённом Boost гайдлайны `spatie/laravel-settings` приходят из пакета; этот скилл самодостаточен для проектов без Boost. Версионные правила Filament/Livewire для `SettingsPage` (шаг 7) тоже отдаём Boost — здесь только привязка формы к классу настроек. Пакет: https://github.com/laravel/boost (скиллы — `vendor/laravel/boost/.ai/`).

## Алгоритм

### 1. Решить: настройка или config?

| Признак | Куда |
|:---|:---|
| Значение меняет администратор без деплоя, через UI | **класс настроек** |
| Значение фиксируется средой/деплоем (`APP_*`, креды, драйверы) | `config/*.php` + `env()` |
| Нужна типизация, дефолты в БД, история через миграции | **класс настроек** |
| Секрет, который не должен попасть в БД-дамп | `config/` + env / vault |

Правило: `config()` читать **только в config-файлах и провайдерах**; в коде приложения для рантайм-значений резолвить класс настроек, а не `config()`.

### 2. Создать класс настроек

- Каталог `app/Settings/` (можно доменные подпапки: `app/Settings/Order/`), namespace `App\Settings\...`.
- `final class XxxSettings extends Spatie\LaravelSettings\Settings`.
- **Public typed properties** — каждое свойство = одна строка в БД. Имена в `snake_case` (совпадают с ключами в миграции). Nullable (`?string`) для опциональных.
- Обязательный `public static function group(): string` — префикс группы (например `order`); полный ключ строки = `group.property`.
- Не объявлять конструктор, не задавать значения по умолчанию в свойствах — дефолты живут в миграции (см. шаг 4).
- Зарегистрировать класс в `config/settings.php → 'settings' => [...]` (если `auto_discover_settings` не включён).

См. `snippets/ExampleSettings.php`.

### 3. Кастомные типы (casts)

- Скалярные типы (`int`, `bool`, `string`, `array`, `float`, `?T`) работают из коробки.
- Для `DateTime`, enum, DTO — глобальные касты в `config/settings.php → global_casts`, либо метод `public static function casts(): array` в классе. По умолчанию пакет уже знает `DateTimeInterface`, `DateTimeZone`, `Spatie\LaravelData\Data`.

### 4. Settings-миграция (значения по умолчанию + эволюция схемы)

- Файл в `database/settings/` (путь из `migrations_paths`), команда `php artisan make:settings-migration`.
- Анонимный класс `extends Spatie\LaravelSettings\Migrations\SettingsMigration`, метод `up()`.
- **Каждое свойство класса обязано иметь соответствующий `add()`** — иначе при чтении упадёт `Spatie\LaravelSettings\Exceptions\MissingSettings`.
- Ключ = `group.property` (точно как `group()` + имя свойства). Значение = дефолт.
- Эволюция схемы — отдельной миграцией:
  - `add('group.prop', $default)` — новое свойство;
  - `rename('group.old', 'group.new')` — переименование (синхронно с правкой свойства класса);
  - `delete('group.prop')` — удаление;
  - `addEncrypted` / `encrypt` / `decrypt` — для чувствительных значений.
- `migrate()` идемпотентен на уровне «миграция запущена один раз» (трекается, как обычные миграции). Запуск — `php artisan migrate` (settings-миграции прогоняются вместе) либо отдельной командой пакета.

См. `snippets/create_example_settings.php`.

### 5. Чтение и запись в рантайме

```php
// Резолв через контейнер (синглтон в рамках запроса)
$settings = app(\App\Settings\Order\OrderSettings::class); // или resolve(...), или DI в конструктор
$limit = $settings->max_items_per_order;

// Запись
$settings->max_items_per_order = 50;
$settings->save();
```

- Предпочитать **внедрение через конструктор** (typed dependency) — тестируемо и явно.
- Можно безопасно мутировать свойства резолвнутого объекта **без `save()`** для разовой подмены в рамках запроса (например, переопределить дефолт значением из текущей сущности) — БД не трогается.

### 6. Кэш

- Включается `SETTINGS_CACHE_ENABLED=true` (+ опционально store/prefix/ttl, на Laravel 12.9+ `SETTINGS_CACHE_MEMO`).
- При включённом кэше после прямой правки строк в БД (минуя `save()`) — сбросить кэш настроек. После `make:settings-migration`/`migrate` кэш инвалидируется пакетом.
- В тестах кэш обычно держать выключенным.

### 7. Привязка к форме (Filament SettingsPage)

- Класс-страница `extends Filament\Pages\SettingsPage`, `protected static string $settings = XxxSettings::class;`.
- Метод `form(Schema $schema)` описывает поля; **`name` каждого поля = имя свойства класса** (строки сохранятся в группу автоматически).
- Валидация и условные `required(fn (Get $get) => ...)` — на полях формы; пакет сам читает/пишет настройки при сохранении.
- Требует плагин `filament/spatie-laravel-settings-plugin`.

См. `snippets/filament-settings-page.php`. Для не-Filament форм: на сохранении вручную присвоить свойства и вызвать `->save()`.

### 8. Проверка

1. Класс зарегистрирован (в `config/settings.php` или auto-discover) — иначе не резолвится.
2. Каждое public-свойство имеет `add()` в миграции; группы совпадают.
3. `php artisan migrate` прогоняет settings-миграцию без ошибок; чтение настроек не кидает `MissingSettings`.
4. В коде приложения рантайм-значения берутся из класса настроек, а не из `config()`.

## Анти-паттерны

- Свойство в классе без `add()` в миграции → `MissingSettings` при первом чтении.
- Значения по умолчанию заданы инициализацией свойства в классе вместо миграции (дефолт не попадёт в БД).
- Хранение секретов (токены, пароли) в обычных свойствах вместо `addEncrypted`/env.
- Чтение настроек через `config()`-обёртку или фасад там, где есть типизированный класс — теряется типизация и DI.
- Рассинхрон `group()` ↔ префикса ключей в миграции ↔ `name` полей формы.
- Правка значений напрямую в БД при включённом кэше без его сброса.

## Чеклист качества

- [ ] Класс `final`, `extends Settings`, только public typed properties, есть `group()`
- [ ] Каждое свойство имеет `add()` в settings-миграции; ключи = `group.property`
- [ ] Дефолты заданы в миграции, а не инициализацией свойств класса
- [ ] Класс зарегистрирован в `config/settings.php` (или включён auto-discover)
- [ ] Выбор настройка-vs-config осознан (рантайм/UI → настройка; env/деплой → config)
- [ ] Нетипизированные типы покрыты `global_casts`/`casts()`
- [ ] Секреты — через `addEncrypted`/env, не открытым свойством
- [ ] Эволюция схемы — отдельной миграцией (`add`/`rename`/`delete`), синхронно с классом
- [ ] Форма: `name` полей == имена свойств; валидация на полях
- [ ] Кэш: поведение при `SETTINGS_CACHE_ENABLED` учтено, в тестах выключен

## Ссылки

- https://github.com/spatie/laravel-settings
- https://filamentphp.com/plugins/filament-spatie-settings
- snippets/ExampleSettings.php — класс настроек
- snippets/create_example_settings.php — settings-миграция (дефолты + эволюция)
- snippets/filament-settings-page.php — привязка к Filament-форме
