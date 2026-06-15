---
name: health-checks
bucket: php
version: 0.1.0
description: "spatie/laravel-health в Laravel: кастомные Check-классы (диск, очередь, heartbeat шедулера, TCP-порт сервиса, кэш, БД) на Result::ok/failed, регистрация в config/health и Health::checks(), /health endpoint (live/ready, JSON/Filament), расписание прогона и уведомления. Активировать при словах health check, healthcheck, liveness/readiness, /health, spatie health, мониторинг доступности, проверка диска/очереди/кэша/heartbeat, при правке app/Health/** или config/health.php."
risk: write
persona: oss-dev
tags: [laravel, health, monitoring, spatie, liveness, readiness, observability]
requires: []
produces_for: []
outputs: []
snippets: [ExampleCheck.php, config-health.php]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: spatie/laravel-health — проверки доступности

## Контекст

Декларативные проверки здоровья Laravel-приложения на пакете `spatie/laravel-health`: каждая проверка — отдельный Check-класс, возвращающий `Result::ok()`/`Result::failed()`; все проверки регистрируются одним списком; результат отдаётся по HTTP (`/health`), прогоняется по расписанию и при падении шлёт уведомление.

Активировать, когда нужно:
- завести **liveness/readiness endpoint** (`/health/live`, `/health/ready`) для k8s/балансировщика/Oh Dear;
- написать **кастомную проверку** доступности инфраструктуры — диск на запись, соединение очереди, кэш, БД, heartbeat шедулера, TCP-порт внешнего сервиса, согласованность конфигов;
- правишь `app/Health/**`, `config/health.php`, регистрацию `Health::checks(...)`, расписание прогона или уведомления о падениях.

Установка пакета и публикация конфига здесь не дублируются — это `composer require spatie/laravel-health` и `php artisan vendor:publish --tag="health-config"` (см. Ссылки). Скилл — про **паттерн проверок и их обвязку**, переносимый в любой Laravel-проект.

## Алгоритм

1. **Класс на проверку.** Каждая проверка — отдельный класс в `app/Health/Checks/`, `final`, наследует `Spatie\Health\Checks\Check`, реализует `run(): Result`. Имя класса = что проверяет (`DatabaseConnectionCheck`, `QueueConnectionCheck`, `DiskWriteCheck`). Одна проверка — одна ответственность.

2. **Контракт `run()` — всегда `Result`, никогда исключение наружу.** Оборачивай рискованные операции (I/O, сеть, драйверы) в `try { ... } catch (Throwable $e) { return Result::make()->failed($e->getMessage()); }`. Успех — `Result::make()->ok('...')`. Промежуточное состояние — `->warning('...')`. Падение — `->failed('...')`. Сообщение короткое и человекочитаемое; диагностику клади в `->meta([...])`.

3. **Конфигурацию читай через `config()` с дефолтами, не хардкодь.** Хост/порт/таймаут/пороги — из `config('health.<сервис>.*')` или `config('<сервис>.*')` с `default:`. Пороги (макс. задержка heartbeat, таймаут сокета) выноси в env через секции `config/health.php`. Так проверка переносима между окружениями без правки кода.

4. **Активная проверка вместо чтения конфига.** Проверка должна *действительно* трогать ресурс, а не только проверять наличие настройки:
   - **БД** — `DB::connection()->select('select 1')`;
   - **кэш** — `Cache::put` уникального ключа → `Cache::get` → сравнить → `Cache::forget`;
   - **диск** — `Storage::disk($d)->put` временного файла (UUID) → `get` → сравнить → `delete`;
   - **TCP-порт сервиса** — `@fsockopen($host, $port, $errno, $errstr, $timeout)`, проверить `is_resource`, `fclose`;
   - **очередь** — определить драйвер дефолтного соединения; для `database` убедиться, что есть таблица `jobs` (`Schema::hasTable`).

5. **Heartbeat шедулера — косвенная проверка.** Сам факт «крон запускает шедулер» проверяется так: в `routes/console.php` каждую минуту пишем метку времени (`cache()->forever('health:scheduler:last_heartbeat', now()->toIso8601String())`), а `SchedulerHeartbeatCheck` сравнивает её возраст с порогом `health.scheduler.max_delay_minutes`; устарела → `failed`. Тот же приём для очереди/воркеров: воркер пишет heartbeat, проверка читает.

6. **Параметризуемые проверки — статический фабричный конструктор.** Если проверку запускают для нескольких целей (несколько дисков), приватный конструктор + `public static function forDisk(string $disk, string $directory): self`. При регистрации задавай уникальное имя: `DiskWriteCheck::forDisk('media', 'health/media')->name('disk_media_write')`.

7. **Регистрация — один список `Health::checks([...])`** в bootstrap-провайдере (`AppServiceProvider::boot()` или выделенный `HealthServiceProvider`). Инстанцируй через `::new()` (или фабрику). Здесь же навешивай `->name(...)`, `->if(...)`/`->unlessEnvironment(...)` для условного запуска. Конфиг пакета (`config/health.php`) задаёт result store, уведомления, секции твоих проверок и `secret_token`.

8. **HTTP endpoint — два уровня.**
   - **liveness** «процесс жив» — `SimpleHealthCheckController` на `/health/live` (без прогона тяжёлых проверок);
   - **readiness** «готов обслуживать» — `HealthCheckJsonResultsController` на `/health/ready`, отдаёт JSON последних результатов; код ответа при падении задаётся `health.json_results_failure_status` (по умолчанию 503), что и читает балансировщик/probe.
   Дашборд — `Route::get('/health', HealthCheckResultsController::class)` (Blade) или **Filament** через `spatie/laravel-health` Filament-страницу.

9. **Расписание прогона.** В `routes/console.php`: `Schedule::command('health:check')->everyMinute();` — прогоняет проверки и сохраняет результат в store. Endpoint readiness отдаёт *сохранённый* результат, а не гоняет проверки на каждый HTTP-запрос (важно для probe под нагрузкой).

10. **Уведомления.** В `config/health.php` → `notifications`: включить `enabled` (env), выбрать каналы (`mail`, `slack`), throttle (`throttle_notifications_for_minutes`), `only_on_failure`. Канал получает `CheckFailedNotification`. Для внешнего мониторинга — `oh_dear_endpoint` или heartbeat-URL (`scheduler.heartbeat_url`, `horizon.heartbeat_url`), который пингуется при успехе.

## Стандартная матрица проверок (generic-сервис)

| Проверка | Что трогает | Класс / приём |
|:---|:---|:---|
| База данных | `select 1` через дефолтное соединение | `DatabaseConnectionCheck` |
| Кэш | put/get/forget уникального ключа | `CacheStoreCheck` |
| Диск | put/get/delete временного файла (per-disk фабрика) | `DiskWriteCheck::forDisk(...)` |
| Очередь | драйвер дефолтного соединения + наличие таблицы `jobs` | `QueueConnectionCheck` |
| Heartbeat шедулера | возраст метки из кэша против порога | `SchedulerHeartbeatCheck` |
| TCP-порт сервиса | `fsockopen($host,$port,...,$timeout)` | `ServiceTcpConnectionCheck` |
| Согласованность конфигов | сравнение пар client/server-параметров | `ServiceClientConfigCheck` |
| Внешний провайдер | хотя бы один API-ключ задан (`config('...providers')`) | `ConfiguredProvidersCheck` |

Встроенные проверки пакета (`UsedDiskSpaceCheck`, `DatabaseCheck`, `DebugModeCheck`, `EnvironmentCheck`, `OptimizedAppCheck`, `ScheduleCheck`, `HorizonCheck`, `RedisCheck`) бери как есть — не дублируй их кастомными. Кастом пиши только для того, чего нет из коробки.

## Антипаттерны

- `run()` бросает исключение наружу вместо `Result::failed()` — прогон всех проверок падает целиком.
- Проверка читает только конфиг (`config(...) !== null`), но не трогает ресурс — «зелёная», когда сервис лёг.
- Хардкод хоста/порта/порога в классе вместо `config(...)` с дефолтом — не переносится между окружениями.
- Endpoint гоняет проверки синхронно на каждый HTTP-запрос probe — DoS под нагрузкой; отдавай сохранённый результат, гоняй по расписанию.
- Временные артефакты (файл/ключ кэша) не удаляются после проверки — мусор и ложные срабатывания.
- Liveness-probe завязан на БД/очередь: внешняя зависимость легла → k8s бесконечно перезапускает живой под. Liveness ≠ readiness.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Написать кастомную проверку (`run(): Result`, try/catch, meta, фабрика) | `snippets/ExampleCheck.php` |
| Зарегистрировать проверки, настроить store/уведомления/секции/endpoint/расписание | `snippets/config-health.php` |

## Чеклист качества

- [ ] Каждая проверка — отдельный `final` класс в `app/Health/Checks/`, наследует `Check`, реализует `run(): Result`
- [ ] `run()` всегда возвращает `Result` (ok/warning/failed); рискованные операции в `try/catch (Throwable)`
- [ ] Проверка реально трогает ресурс (put/get, `select 1`, `fsockopen`), а не только читает конфиг
- [ ] Хост/порт/таймаут/пороги читаются из `config(...)` с дефолтами и env, не захардкожены
- [ ] Временные артефакты (файл, ключ кэша) удаляются после проверки
- [ ] Диагностика — в `->meta([...])`, сообщение `ok/failed` короткое и человекочитаемое
- [ ] Параметризуемые проверки — приватный конструктор + статическая фабрика + уникальный `->name()`
- [ ] Все проверки в одном `Health::checks([...])` в bootstrap-провайдере
- [ ] Есть liveness (`SimpleHealthCheckController`) и readiness (`HealthCheckJsonResultsController`); liveness не завязан на внешние зависимости
- [ ] `health:check` стоит в расписании; endpoint отдаёт сохранённый результат, не гоняет проверки на каждый запрос
- [ ] Уведомления о падении настроены (канал, throttle, `only_on_failure`); endpoint/Oh Dear защищён `secret_token` при необходимости
- [ ] Встроенные проверки пакета не продублированы кастомными

## Ссылки

- https://spatie.be/docs/laravel-health/v1/introduction
- https://spatie.be/docs/laravel-health/v1/basic-usage/configuring-checks
- https://spatie.be/docs/laravel-health/v1/basic-usage/creating-custom-checks
- https://spatie.be/docs/laravel-health/v1/available-checks/overview
- https://spatie.be/docs/laravel-health/v1/basic-usage/getting-results
- snippets/ExampleCheck.php
- snippets/config-health.php
