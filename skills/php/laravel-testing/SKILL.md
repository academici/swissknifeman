---
name: laravel-testing
bucket: php
version: 0.4.1
description: "Feature/unit/pest testing patterns: изоляция тестовой БД, детект Docker/локального окружения, coverage gate, композиция Pest (setUp-трейты, фикстуры, beforeEach fake/freeze, датасеты)"
risk: write
persona: oss-dev
tags: ["php", "laravel", "testing"]
requires: []
produces_for: []
outputs: []
snippets: ["feature-test.php", "unit-test.php", "factory-pattern.php", "pest-test.php", "pest-composition.php", "pest-testing.md", "testing-rules.md", "testing-safety-report.md", "phpunit.xml", "coverage-gate-config.php", "check-coverage-gate.php", "composer-test-scripts.json"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Тестирование Laravel-приложений (Pest/PHPUnit): паттерны Feature/Unit-тестов, безопасная изоляция тестовой БД от рабочей, детект окружения (Docker vs локальный PHP), порог покрытия (coverage gate) для CI. Базовые ожидания: **Feature по умолчанию**, Unit — только для чистой логики без БД; ассерты про поведение (HTTP-код, состояние БД, уведомления), а не про внутреннюю реализацию; данные — через фабрики моделей.

**Когда активировать**: пишу или правлю тесты Laravel (`tests/Feature`, `tests/Unit`, `*Test.php`, Pest `it()/test()`); настраиваю `phpunit.xml`, изоляцию тестовой БД, фабрики моделей; собираю coverage gate в CI; запускаю `php artisan test` / `vendor/bin/pest` и нужно определить окружение (Docker vs локально); переиспользую setUp-логику через трейты/`beforeEach`/датасеты. Не активировать для архитектуры приложения (скилл `laravel`) и общей стратегии пирамиды (скилл `quality/test-strategy`).

**Laravel Boost**: синтаксис и приёмы Pest — Boost-скилл pest-testing; здесь — изоляция тестовой БД, coverage gate и окружение. Пакет: https://github.com/laravel/boost (скиллы — `vendor/laravel/boost/.ai/`).

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

## Композиция Pest: трейты + фикстуры

Boost владеет базовым синтаксисом Pest (тест, `expect`, навигация по `pest()`). Здесь — **дельта**: как переиспользовать setUp-логику и держать сьют детерминированным **композицией, а не наследованием**. Не плоди подклассы `TestCase` (`AdminTestCase`, `ApiTestCase`, `OrderTestCase`) — глубокая иерархия хрупкая и тащит лишнее в каждый тест. Собирай поведение из мелких трейтов и хелперов.

### 1. Переиспользуемые setUp-трейты (concerns) вместо подклассов

Каждый кусок повторяющегося префикса теста — отдельный трейт в `tests/Support/Concerns/` с **узкой ответственностью**:

- `ActsAsUser` — `makeUserWithRole($role)` / `actingAsRole($role)`: создать пользователя фабрикой, назначить роль, авторизовать. Убирает копипасту «создал юзера → assignRole → actingAs» из десятков тестов.
- `SeedsUserRoles` (или `SeedsLookupData`) — `seedUserRoles()`: загрузить узкий справочник (роли/статусы/типы), на который завязаны ассерты доступа; не дублирует общий `DatabaseSeeder`.

`TestCase` остаётся тонким и **подключает трейты**, а не наследует поведение через цепочку классов:

```php
// tests/TestCase.php
abstract class TestCase extends BaseTestCase
{
    use ActsAsUser;       // хелперы доступа
    use SeedsUserRoles;   // справочник ролей
    // + guard изоляции тестовой БД (см. секцию выше)
}
```

Хелперы трейтов доступны во **всех Pest-замыканиях** автоматически — Pest биндит замыкание на класс `TestCase`, так что `$this->actingAsRole(...)` работает внутри `it(...)`. Новая потребность — новый трейт, а не новый подкласс. Где конкретное поведение нужно лишь части сьютов — подключай трейт в `Pest.php` точечно: `pest()->extend(TestCase::class)->use(SeedsLookupData::class)->in('Feature/Admin')`.

### 2. Единая гигиена окружения через `beforeEach` в `tests/Pest.php`

Детерминизм сети и времени задаётся **один раз на директорию**, а не повторяется в каждом файле. Привязка к папкам через `->in('Feature')` / `->in('Unit')`:

```php
pest()->extend(Tests\TestCase::class)
    ->use(Illuminate\Foundation\Testing\RefreshDatabase::class)   // только Feature
    ->beforeEach(function () {
        Str::createRandomStringsNormally();   // сброс возможного фейка из прошлого теста
        Str::createUuidsNormally();
        Http::fake(['127.0.0.1:5173/*' => Http::response('')]);   // гасим dev-ассеты
        Http::preventStrayRequests();         // любой неподделанный HTTP = падение
        Sleep::fake();                        // sleep() в коде не тормозит прогон
        $this->freezeTime();                  // Carbon::now() заморожен
    })
    ->in('Feature');
```

Три кита детерминизма: **`Http::preventStrayRequests()`** превращает молчаливый поход во внешний API в явное падение; **`Sleep::fake()`** убирает реальные паузы; **`freezeTime()`** стабилизирует ассерты времени. Для `Unit` — тот же блок, но **без** `RefreshDatabase` (чистая логика без БД). Кастомные `expect()->extend(...)` и глобальные хелперы тоже живут в `Pest.php` — расширение API вместо наследования.

### 3. Датасеты `->with()` — параметризация вместо копипасты тел

Один сценарий × множество входов задаётся датасетом, а не N почти одинаковыми тестами. Именованный `dataset()` (ключи строками) делает вывод падений читабельным (`with data set "orders.cancel"`):

```php
dataset('order_guest_endpoints', [
    'cancel'  => ['orders.cancel', ['reason' => 'duplicate']],
    'confirm' => ['orders.confirm', []],
]);

it('закрывает endpoint от гостя', function (string $route, array $payload) {
    $order = Order::factory()->pending()->create();   // фабрика Eloquent + states
    $this->post(route($route, $order), $payload)->assertRedirect(route('login'));
})->with('order_guest_endpoints');
```

Локальный набор — инлайн `->with([...])` прямо в тесте; общий, переиспользуемый между файлами — именованный `dataset()`. Данные всегда через **фабрики моделей** (`Model::factory()->state()->create()`) и фабрики-хелперы тестов (`tests/Support/Factories/`), собирающие связный граф (`Order` + участники + позиции), — не через ручные `INSERT` и не через хардкод id.

### Граница с Boost

| Тема | Где |
|:---|:---|
| Базовый Pest: `it/test`, `expect`, `pest()`, навигация по тесту | Boost-скилл `pest-testing` |
| Изоляция тестовой БД, coverage gate, Docker/локальный детект | этот скилл, секции выше |
| Композиция: setUp-трейты, фикстуры, `beforeEach` fake/freeze, датасеты | **этот скилл, эта секция** |

Полный пример (два concern-трейта, `Pest.php` с `beforeEach` для Feature и Unit, кастомный expectation, именованный и инлайн датасеты) — сниппет `pest-composition.php`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Пишу Feature-тест (HTTP, API, доступ) | `feature-test.php` |
| Пишу Unit-тест чистой логики без БД | `unit-test.php` |
| Нужна фабрика модели / states | `factory-pattern.php` |
| Пишу тест в Pest-синтаксисе | `pest-test.php` |
| Переиспользую setUp-трейты/фикстуры, `beforeEach` fake/freeze, датасеты `->with()` | `pest-composition.php` |
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
- [ ] Повторяющийся setUp вынесен в трейт `tests/Support/Concerns/`, а не в новый подкласс `TestCase` (композиция, не наследование)
- [ ] `Pest.php`: `beforeEach` с `Http::preventStrayRequests()` + `Sleep::fake()` + `freezeTime()`; `RefreshDatabase` только в Feature
- [ ] Множественные входы — через `->with()`/`dataset()`, а не копипаста тел; данные через фабрики моделей

## Ссылки

- Скилл `quality/test-strategy` — стратегия пирамиды и coverage policy
- Скилл `static-analysis` (bucket php) — конвейер rector → pint → phpstan → tests
- Скилл `laravel` (bucket php) — архитектурные паттерны, которые покрываются тестами
- https://pestphp.com/docs — документация Pest
