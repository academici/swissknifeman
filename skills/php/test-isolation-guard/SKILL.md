---
name: test-isolation-guard
bucket: php
version: 0.1.0
description: "Защита тестов Laravel от запуска по боевой/dev БД и медиа-диску: bootstrap.php выставляет DB_DATABASE=*_test и media-test до autoload, класс-страж TestEnvironmentGuard аварийно прерывает createApplication() при нарушении изоляции, безопасный RefreshDatabase. Активировать при настройке тестового окружения, защите CI и подозрении, что тесты бьют по dev/prod БД."
risk: write
persona: oss-dev
tags: [php, laravel, testing, isolation, safety, database, ci, refreshdatabase]
requires: [laravel-testing]
produces_for: []
outputs: []
snippets: [bootstrap.php, TestEnvironmentGuard.php, TestCase.php]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Test isolation guard

## Контекст

Активировать, когда нужно гарантировать, что тесты Laravel (PHPUnit/Pest) физически не могут выполниться по боевой или dev БД и не пишут файлы в боевой медиа-стор. Прямые триггеры:

- **Настройка тестового окружения** нового проекта/пакета — закладываем изоляцию с первого дня.
- **Защита CI** — раннер должен падать с понятным сообщением, а не молча сносить данные.
- **Подозрение, что тесты бьют по dev/prod БД** — после инцидента, странных пропаж данных или когда `RefreshDatabase` подозрительно «почистил» рабочую базу.

Корень проблемы: `RefreshDatabase` выполняет `migrate:fresh` на активном подключении. Если активная БД — основная (из `.env`), один прогон тестов уничтожит данные. Аналогично загрузки в тестах уходят на боевой медиа-диск, если диск не подменён. Скилл строит **три рубежа защиты**: bootstrap до autoload, страж на `createApplication()`, безопасный `RefreshDatabase`.

Версионные основы тестирования (Feature/Unit/Pest, детект Docker/локального окружения) — в скилле `php/laravel-testing` (`requires`); здесь — именно слой жёсткой изоляции и аварийного прерывания.

## Алгоритм

1. **Определи целевые тестовые ресурсы** проекта:
   - имя тестовой БД — по конвенции `<app>_test` (обязан заканчиваться на `_test`);
   - имя тестового медиа-диска — `media-test` с изолированным локальным `root`;
   - убедись, что тестовая БД и диск реально существуют (или задокументируй, как их создать).

2. **Рубеж 1 — `phpunit.xml`.** Пропиши в `<php>` серверные/окруженческие значения: `APP_ENV=testing`, `DB_CONNECTION`, `DB_DATABASE=<app>_test`, `MEDIA_DISK=media-test`, плюс `CACHE_STORE=array`, `SESSION_DRIVER=array`, `QUEUE_CONNECTION=sync`. Это первичный источник изоляции для штатного раннера.

3. **Рубеж 1.5 — `tests/bootstrap.php`** (см. `snippets/bootstrap.php`). Подключи его в `phpunit.xml` атрибутом `bootstrap="tests/bootstrap.php"`. Файл выставляет те же `DB_DATABASE=*_test` и `MEDIA_DISK=media-test` **до** `require vendor/autoload.php`, записывая в `$_SERVER`, `$_ENV` и через `putenv()`. Это страхует от регресса порядка инструментов (IDE-раннер, CI, кривой `.env`): Laravel при загрузке гарантированно видит тестовые значения. Помни приоритет источников в `env()`: `$_SERVER` > `$_ENV`, `putenv()` закрывает `getenv()` — поэтому пишем во все три.

4. **Рубеж 2 — класс-страж `Tests\Support\TestEnvironmentGuard`** (см. `snippets/TestEnvironmentGuard.php`). Через контейнер `config` (не через прямое чтение `env`, чтобы проверять именно итоговую разрешённую конфигурацию):
   - `assertIsolatedTestDatabase()`: берёт `database.default`, затем `database.connections.{default}.database`, и проверяет `str_ends_with($database, '_test')`. Если нет — бросает `RuntimeException` с понятным русским сообщением и инструкцией: что проверить в `phpunit.xml`/`bootstrap.php` и как создать тестовую БД.
   - `assertIsolatedTestMediaDisk()`: берёт `media-library.disk_name`, проверяет, что это `media-test` и что `filesystems.disks.media-test` описан массивом. Иначе — `RuntimeException` с инструкцией.
   - Сообщения должны быть **самодостаточными**: получив их в CI-логе, инженер чинит окружение без чтения исходников.

5. **Рубеж 2 — подключение стража в `Tests\TestCase`** (см. `snippets/TestCase.php`). Переопредели `createApplication()`: вызови `parent::createApplication()`, затем оба `assert*` стража, и только потом верни `$app`. Страж срабатывает на КАЖДОМ поднятии приложения — до первого запроса к БД и до записи файлов. Если изоляция нарушена, тест падает мгновенно, `migrate:fresh` не запускается.

6. **Рубеж 3 — безопасный `RefreshDatabase`.** Только после того, как рубежи 1–2 на месте, подключай трейт `Illuminate\Foundation\Testing\RefreshDatabase` в тестах с БД (или через `pest()->extend(...)->use(RefreshDatabase::class)->in('Feature')`). К этому моменту активная БД заведомо `*_test`, поэтому `migrate:fresh` безопасен.

7. **Запрет команд вне тестового окружения.** Зафиксируй (в правилах проекта/агента): без явного `APP_ENV=testing` и `DB_DATABASE=*_test` нельзя выполнять `migrate:fresh`, `db:wipe`, `db:seed`, `migrate`, а также `tinker` с мутациями — иначе удар идёт по dev/prod БД из обычного `.env`.

8. **Проверь срабатывание стража.** Временно укажи в окружении нетестовую БД (или запусти тест с пустым `phpunit.xml`) и убедись, что прогон падает с понятным сообщением, а не доходит до `migrate:fresh`. Верни корректное окружение.

## Доменные правила изоляции

- **`config`, а не `env`.** Страж читает итоговую конфигурацию через контейнер, потому что именно её использует фреймворк; `env()` может отличаться из-за кэша конфигурации и приоритетов источников.
- **`str_ends_with(..., '_test')` вместо точного имени.** Гард переносим между проектами: он не зашит на конкретное имя БД, требует лишь суффикс `_test`.
- **Три источника окружения.** В `bootstrap.php` пишем в `$_SERVER`, `$_ENV` и `putenv()` одновременно — иначе часть кода прочитает не то значение.
- **Страж — последний рубеж, а не единственный.** Он не заменяет `phpunit.xml`/`bootstrap.php`, а ловит их регресс. Не убирай первые рубежи, опираясь только на гард.
- **Медиа-диск — отдельная проверка.** БД и файлы изолируются независимо; тестовый диск должен иметь собственный `root`, не пересекающийся с боевым.
- **Сообщения по-русски и с инструкцией.** Каждое исключение объясняет, что нарушено и как починить (где смотреть, как создать ресурс).

## Чеклист качества

- [ ] `phpunit.xml` задаёт `APP_ENV=testing`, `DB_DATABASE=*_test`, `MEDIA_DISK=media-test` и подключает `tests/bootstrap.php`
- [ ] `tests/bootstrap.php` выставляет тестовые `DB_DATABASE`/`MEDIA_DISK` в `$_SERVER`, `$_ENV` и `putenv()` ДО `require vendor/autoload.php`
- [ ] `TestEnvironmentGuard::assertIsolatedTestDatabase()` проверяет суффикс `_test` через `config`, не через `env`
- [ ] `TestEnvironmentGuard::assertIsolatedTestMediaDisk()` проверяет диск `media-test` и наличие его конфигурации
- [ ] Оба исключения — `RuntimeException` с русским сообщением и инструкцией, как починить
- [ ] `TestCase::createApplication()` вызывает оба стража до возврата `$app`
- [ ] `RefreshDatabase` подключён только после рубежей 1–2; прогон по нетестовой БД невозможен
- [ ] Срабатывание стража проверено вручную: нетестовая БД даёт аварийное падение до `migrate:fresh`
- [ ] Зафиксирован запрет `migrate:fresh`/`db:wipe`/`db:seed`/`tinker`-мутаций вне `APP_ENV=testing`

## Ссылки

- snippets/bootstrap.php — `tests/bootstrap.php` с изоляцией до autoload
- snippets/TestEnvironmentGuard.php — класс-страж БД и медиа-диска
- snippets/TestCase.php — подключение стража в `createApplication()` + безопасный `RefreshDatabase`
- https://laravel.com/docs/database-testing#resetting-the-database-after-each-test
- https://github.com/laravel/framework/blob/master/src/Illuminate/Foundation/Testing/RefreshDatabase.php
- Связанные скиллы: `php/laravel-testing`, `php/medialibrary`
