---
name: laravel-testing
bucket: php
version: 0.3.0
description: "Feature/unit/pest testing patterns: изоляция тестовой БД, детект Docker/локального окружения, coverage gate"
risk: write
persona: oss-dev
tags: ["php", "laravel", "testing"]
requires: []
produces_for: []
outputs: []
snippets: ["feature-test.php", "unit-test.php", "factory-pattern.php", "pest-test.php", "pest-testing.md", "testing-rules.md", "testing-safety-report.md", "phpunit.xml", "coverage-gate-config.php", "check-coverage-gate.php", "composer-test-scripts.json"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Тестирование Laravel-приложений (Pest/PHPUnit): паттерны Feature/Unit-тестов, безопасная изоляция тестовой БД от рабочей, детект окружения (Docker vs локальный PHP), порог покрытия (coverage gate) для CI. Базовые ожидания: **Feature по умолчанию**, Unit — только для чистой логики без БД; ассерты про поведение (HTTP-код, состояние БД, уведомления), а не про внутреннюю реализацию; данные — через фабрики моделей.

**Laravel Boost**: синтаксис и приёмы Pest — Boost-скилл pest-testing; здесь — изоляция тестовой БД, coverage gate и окружение.

## Алгоритм

### 1. Изоляция тестовой БД (дуальная схема)

В проекте две базы: основная `<app>` (из `.env`, `DB_DATABASE`) и тестовая `<app>_test`. Тесты ходят **только** в `<app>_test`:

- `phpunit.xml` задаёт `DB_DATABASE=<app>_test` и `APP_ENV=testing` **дважды**: через `<server>` (Laravel/Dotenv читает `$_SERVER` первым — ServerConstAdapter) и через `<env force="true">` — `force` перебивает переменные, которые Docker/хост инжектят через `getenv`. Без `force="true"` тесты могут уехать в основную БД.
- Хост/порт/пользователь/пароль БД наследуются из окружения — подменяется только имя базы.
- Лёгкие драйверы: `CACHE_STORE=array`, `SESSION_DRIVER=array`, `QUEUE_CONNECTION=sync`, `MAIL_MAILER=array`, отдельный диск `MEDIA_DISK=media-test` (всё с `force="true"` там, где окружение может перебить).
- Шаблон: сниппет `phpunit.xml`.

### 2. Детект окружения: Docker или локальный PHP

Не выбирай режим по `DB_CONNECTION` (он `pgsql` в обоих случаях). Смотри `DB_HOST`:

| `DB_HOST` | Режим | Команды |
|:---|:---|:---|
| `pgsql` (имя сервиса compose) | Docker | `docker compose exec app php artisan test`, `docker compose exec app composer ...` |
| `127.0.0.1` / `localhost` / IP | Локально | `php artisan test`, `vendor/bin/pest` |

При сомнении — `docker compose ps`: если контейнеры запущены, работай через Docker. Детали и таблица команд — сниппет `testing-rules.md`.

### 3. Запрет разрушающих команд на основной БД

- **Никогда** не выполнять `migrate:fresh` / `db:wipe` без явного тестового окружения (`--env=testing` / `APP_ENV=testing`): `RefreshDatabase` и эти команды стирают базу, на которую смотрит текущее окружение.
- Guard в `TestCase`: перед прогоном ассертить, что подключена именно `<app>_test`:

```php
// tests/TestCase.php
protected function assertIsolatedTestDatabase(): void
{
    $database = DB::connection()->getDatabaseName();

    if (! str_ends_with($database, '_test')) {
        throw new RuntimeException("Тесты подключены к '{$database}', ожидалась '<app>_test'. Прогон остановлен.");
    }
}
```

- **Опасные зоны вне PHPUnit/Pest** (guard их не ловит, т.к. приложение поднимается из обычного `.env`): `php artisan tinker` (фабрики/`create()` мутируют основную БД), `db:seed`, любые ad-hoc скрипты — только с `APP_ENV=testing`. Полный разбор — сниппеты `testing-rules.md` и `testing-safety-report.md`.

### 4. Coverage gate

- Конфиг `coverage.php` в корне: baseline **70%** общий минимум по строкам, **55%** для критических путей (`app/Actions`, `app/Policies`, `app/Services`, `app/Http/Middleware`); пороги переопределяются env-переменными `COVERAGE_GLOBAL_MIN` / `COVERAGE_CRITICAL_MIN` — сниппет `coverage-gate-config.php`.
- Скрипт-гейт читает `coverage/clover.xml` после `php artisan test --coverage --coverage-clover=...`, режимы `COVERAGE_GATE_MODE=report|soft|hard` — сниппет `check-coverage-gate.php`.
- Composer-конвейер: `test` (config:clear → lint:check → artisan test), `test:coverage`, `test:coverage:clover`, `test:coverage:gate`, `test:critical` (поимённый список критичных сьютов) — сниппет `composer-test-scripts.json`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Пишу Feature-тест (HTTP, API, доступ) | `feature-test.php` |
| Пишу Unit-тест чистой логики без БД | `unit-test.php` |
| Нужна фабрика модели / states | `factory-pattern.php` |
| Пишу тест в Pest-синтаксисе | `pest-test.php` |
| Сценарий работы агента с Pest, выбор Feature/Unit, отладка падений | `pest-testing.md` |
| Перед запуском тестов: Docker vs локально, таблица команд, запреты | `testing-rules.md` |
| Разбираюсь, как устроена изоляция БД, создание `<app>_test` | `testing-safety-report.md` |
| Настраиваю phpunit.xml с изолированной тестовой БД | `phpunit.xml` |
| Задаю пороги покрытия проекта | `coverage-gate-config.php` |
| Нужен CI-гейт по clover.xml | `check-coverage-gate.php` |
| Настраиваю composer-скрипты test/coverage | `composer-test-scripts.json` |

## Чеклист качества

- [ ] `phpunit.xml`: `DB_DATABASE=<app>_test` и `APP_ENV=testing` через `<server>` + `<env force="true">`
- [ ] cache/session — array, queue — sync, media — отдельный тестовый диск
- [ ] В `TestCase` есть guard-ассерт на имя тестовой БД
- [ ] Ни одной команды `migrate:fresh`/`db:wipe`/`db:seed`/`tinker` против основной БД
- [ ] Режим (Docker/локально) определён по `DB_HOST`, команды запущены из того же окружения
- [ ] Feature по умолчанию; Unit — чистая логика; данные через фабрики; ассерты поведенческие
- [ ] Coverage gate подключён в CI: общий ≥ 70%, критические пути ≥ 55%

## Ссылки

- Скилл `quality/test-strategy` — стратегия пирамиды и coverage policy
- Скилл `static-analysis` (bucket php) — конвейер rector → pint → phpstan → tests
- Скилл `laravel` (bucket php) — архитектурные паттерны, которые покрываются тестами
- https://pestphp.com/docs — документация Pest
