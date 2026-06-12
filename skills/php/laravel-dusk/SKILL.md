---
name: laravel-dusk
bucket: php
version: 0.1.0
description: "Laravel Dusk: браузерные E2E-тесты, изолированная тестовая БД, запуск из Docker через host ChromeDriver, Page Objects"
risk: write
persona: oss-dev
tags: ["php", "laravel", "dusk", "e2e", "browser-testing", "chromedriver", "docker"]
requires: []
produces_for: []
outputs: []
snippets:
  - phpunit.dusk.xml
  - browser-test.php
  - dusk-makefile.mk
  - page-object.php
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Laravel Dusk — браузерные E2E-тесты через ChromeDriver. Скилл закрывает боевую конфигурацию: изолированная тестовая БД, отдельный `phpunit.dusk.xml`, запуск из Docker-контейнера с ChromeDriver на хосте, Page Objects.

## Алгоритм

1. **Базовый класс**: Dusk-тесты наследуют `Tests\DuskTestCase` (extends `Laravel\Dusk\TestCase`), НЕ обычный `TestCase`. Браузер ходит в отдельный процесс приложения — `RefreshDatabase` с его транзакциями там не виден.
2. **Сброс данных**: НИКОГДА `RefreshDatabase` в Dusk. Вместо этого в `setUp()` — `Artisan::call('migrate:fresh', ['--seed' => true, '--force' => true])` на изолированной БД.
3. **Изоляция**: отдельный `phpunit.dusk.xml` с testsuite `tests/Browser` и принудительными `DB_DATABASE=<app>_test` (`force="true"`); guard-проверки в `setUp()`, что подключение действительно смотрит в тестовую БД/тестовый media-диск.
4. **Окружение**: `.env.dusk.local` (тест падает с понятной ошибкой, если файла нет); `SESSION_DRIVER=file`, `QUEUE_CONNECTION=sync` — чтобы сессии и джобы были видны между процессом теста и `artisan serve`.
5. **Режимы**: паттерн `DUSK_ENV_MODE=test|current` — в `test` (default) мутации данных только на `<app>_test` + migrate:fresh; в `current` тесты ходят на текущее окружение без сброса (только чтение/смоук).
6. **Docker**: ChromeDriver в app-образе не нужен — он запускается на хосте (`--port=9515 --allowed-ips= --allowed-origins='*'`), а контейнер подключается по `DUSK_DRIVER_URL=http://host.docker.internal:9515` с `DUSK_START_CHROMEDRIVER=false`.
7. **Page Objects**: повторяющиеся страницы — классы в `tests/Browser/Pages/` с `url()`, `assert()`, `elements()` (шорткаты `@element`).
8. **Запуск**: `php artisan dusk [файл]` или make-цель `test-browser FILE=...`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Настраиваю конфиг тестов и изоляцию БД | `snippets/phpunit.dusk.xml` |
| Пишу браузерный тест (waitFor, press, waitUsing, asserts) | `snippets/browser-test.php` |
| Запускаю Dusk из Docker / поднимаю host ChromeDriver | `snippets/dusk-makefile.mk` |
| Выношу повторяющуюся страницу в Page Object | `snippets/page-object.php` |

## Типичные грабли

- `RefreshDatabase` в Dusk «работает» локально и молча ломает данные: транзакция теста невидима для процесса сервера. Только `migrate:fresh --seed`.
- Без `force="true"` в env-секции phpunit.dusk.xml переменные из `.env.dusk.local` перебьют тестовую БД — и migrate:fresh пройдётся по рабочей базе.
- ChromeDriver на хосте должен быть запущен с `--allowed-ips=` и `--allowed-origins='*'`, иначе соединения из контейнера отбрасываются.
- Перед тестами нужны собранные фронтенд-ассеты (`npm run build`) — проверяйте manifest и собирайте автоматически.
- `assertSee` по динамике — флаки; используйте `waitFor`/`waitUsing` с таймаутом.

## Чеклист качества

- [ ] Тест наследует DuskTestCase, не TestCase; RefreshDatabase отсутствует
- [ ] phpunit.dusk.xml: отдельный testsuite Browser + DB_DATABASE=`<app>_test` с force
- [ ] Guard-проверка изоляции БД перед migrate:fresh
- [ ] SESSION_DRIVER=file, QUEUE_CONNECTION=sync в dusk-окружении
- [ ] Из Docker: DUSK_START_CHROMEDRIVER=false + DUSK_DRIVER_URL на host.docker.internal
- [ ] Повторяющиеся страницы оформлены как Page Objects

## Ссылки

- https://laravel.com/docs/dusk
- https://github.com/php-webdriver/php-webdriver
- Скилл `quality/test-strategy` — стратегия пирамиды и coverage policy
