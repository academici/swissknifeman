---
name: db-test-preflight
bucket: devops
version: 0.1.0
description: "Пре-флайт проверка тестовой БД (Postgres в Docker) ПЕРЕД запуском тестов: контейнер поднят (docker compose ps / pg_isready), целевая БД существует и её имя оканчивается на _test (не dev/prod), миграции применены; различает host- и docker-подключение. Активировать при запуске тестов с Postgres, настройке хуков/CI и когда «тесты падают на подключении к БД»."
risk: read
persona: operator
tags: [postgres, docker, testing, preflight, devops]
requires: []
produces_for: []
outputs: []
snippets: [preflight.sh, Makefile.test, composer-scripts.json]
adapters: [claude, cursor, fable]
sha256: ""
---

# DB Test Preflight

## Контекст

Используйте этот skill перед запуском тестового набора (`php artisan test`, Pest, PHPUnit, любой test-suite поверх Postgres) и при настройке хуков/CI, где тесты бьют в реальную БД в Docker. Аналог `devops/node-pnpm-preflight`, но для тестовой базы данных.

Явные триггеры активации:

- запуск тестов, использующих Postgres (`php artisan test`, `pest`, `phpunit`, `make test`);
- настройка git-хуков (`pre-push`), composer-скрипта `test`, Makefile-цели или CI-шага перед тестами;
- симптом «тесты падают на подключении к БД» — `SQLSTATE[08006]` (connection refused), `database "*_test" does not exist`, `no such host`, таймаут на старте suite.

Зачем: тестовый прогон вслепую даёт мусорные ошибки (упавший контейнер выглядит как красный тест), а в худшем случае — пишет в **dev/prod** базу, если изоляция окружения сломалась. Пре-флайт ловит это за секунды до запуска suite.

## Алгоритм

1. **Определи способ подключения — host или docker.** Тесты исполняются либо на хосте (`php artisan test` напрямую), либо в контейнере (`docker compose exec app php artisan test`). От этого зависят и хост БД, и команда проверки:
   - **docker-режим**: приложение и Postgres — оба в compose-сети, БД доступна по имени сервиса (`pgsql`/`db`); проверки гоняем через `docker compose exec -T pgsql ...`.
   - **host-режим**: приложение на хосте, Postgres проброшен на `127.0.0.1:<host-port>` (из `.env.docker` / `DB_PORT`); проверки гоняем хостовым `pg_isready -h 127.0.0.1 -p <port>`.
   Признак docker-режима: команды запуска тестов в Makefile/CI начинаются с `docker compose exec`. Запускай проверки **тем же способом**, каким будут запускаться тесты.
2. **Проверь, что контейнер тестовой БД поднят.** `docker compose ps` (или с нужными `--env-file`); сервис `pgsql`/`db` должен быть в состоянии `running`/`healthy`. Если контейнера нет — `docker compose up -d` сервиса БД, затем повтори. Если поднять не удалось — остановись и сообщи блокер, не запускай тесты.
3. **Проверь готовность Postgres принимать соединения** — `pg_isready`:
   - docker: `docker compose exec -T pgsql sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'`;
   - host: `pg_isready -h 127.0.0.1 -p "${DB_PORT:-5432}" -U "${DB_USERNAME:-postgres}"`.
   Код выхода `0` — БД готова. Контейнер может быть `running`, но Postgres внутри ещё инициализируется — `pg_isready` ловит именно это.
4. **Узнай целевое имя тестовой БД из тестового окружения, а не из `.env`.** Источник истины — `phpunit.xml` (`<env name="DB_DATABASE" value="..._test" force="true"/>`) и/или `tests/bootstrap.php` (принудительная установка `DB_DATABASE`/`APP_ENV=testing`). Не бери `DB_DATABASE` из `.env` — там dev-база.
5. **GATE по имени БД: оно ДОЛЖНО оканчиваться на `_test`.** Это главная защита от прогона тестов (особенно с `RefreshDatabase`/`migrate:fresh`, которые **дропают таблицы**) по dev/prod базе. Если целевое имя не матчит `*_test` — **жёсткий стоп**, сообщи блокер, не запускай. Регексп проверки: `^[a-z0-9_]+_test$`.
6. **Проверь, что целевая `*_test` БД существует.** `psql ... -Atqc "SELECT 1 FROM pg_database WHERE datname='<db>_test'"` должен вернуть `1`. Если БД нет (свежий volume без init-скрипта) — создай идемпотентно: `CREATE DATABASE <app>_test OWNER "<user>"` (или вызови существующую цель `make db-create-test` / init-скрипт проекта). НЕ создавай и НЕ трогай dev/prod базу.
7. **Проверь, что миграции применены к `*_test` БД.** Прогон с `RefreshDatabase` мигрирует сам, но при стратегии без refresh (или для быстрого «тесты падают на схеме») сверь: `php artisan migrate:status --env=testing` не должен показывать `Pending`. Если есть pending — примени `php artisan migrate --env=testing --force` (в docker-режиме — через `docker compose exec app ...`). Никогда не применяй миграции к базе без суффикса `_test` под видом тестовой.
8. **Только после прохождения всех гейтов — запускай тесты** тем же способом (host/docker), что и проверки. Любой провал шагов 2–7 — это блокер: сообщи причину и команду для починки, тесты не запускай.

## Host vs Docker — шпаргалка

| Что проверяем | docker-режим | host-режим |
|:---|:---|:---|
| Контейнер поднят | `docker compose ps` | `docker compose ps` |
| Postgres готов | `docker compose exec -T pgsql sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` | `pg_isready -h 127.0.0.1 -p $DB_PORT -U $DB_USERNAME` |
| Хост БД для приложения | имя сервиса (`pgsql`) | `127.0.0.1` + проброшенный порт |
| Существование `*_test` | `docker compose exec -T pgsql psql -U "$POSTGRES_USER" -d postgres -Atqc "..."` | `psql -h 127.0.0.1 -p $DB_PORT -U $DB_USERNAME -d postgres -Atqc "..."` |
| Запуск тестов | `docker compose exec app php artisan test` | `php artisan test` |

Правило: проверки и тесты — **одним и тем же способом**. Смешивать (проверил на хосте, а тесты в контейнере) нельзя — это разные БД-эндпоинты.

## Не путать тестовую БД с dev/prod

- Источник имени тестовой БД — `phpunit.xml` + `tests/bootstrap.php` (там `force="true"` и `APP_ENV=testing`), а не `.env`.
- Команды вне тестового окружения (`tinker`, `migrate`, `db:seed` без `--env=testing`) используют `DB_*` из `.env` и пишут в **dev-базу**. Для тестовых мутаций — только явный `--env=testing` или отдельная `*_test` база.
- Гейт `^[a-z0-9_]+_test$` (шаг 5) — последний рубеж: даже при сбое порядка конфигурации он не даст `RefreshDatabase` снести dev/prod схему.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Готовый пре-флайт shell-скрипт: ps → pg_isready → гейт имени `*_test` → существование БД → миграции, с поддержкой host/docker | `snippets/preflight.sh` |
| Встроить пре-флайт в Makefile: цель `test-preflight` как зависимость `test` | `snippets/Makefile.test` |
| Встроить пре-флайт в composer-скрипт `test` и в git-хук `pre-push` | `snippets/composer-scripts.json` |

## Чеклист качества

- [ ] Определён способ подключения (host/docker), проверки и тесты запускаются одинаково
- [ ] `docker compose ps` показывает контейнер БД `running`/`healthy`
- [ ] `pg_isready` вернул код `0` (Postgres принимает соединения)
- [ ] Имя целевой БД взято из `phpunit.xml`/`tests/bootstrap.php`, не из `.env`
- [ ] Имя целевой БД проходит гейт `^[a-z0-9_]+_test$` (жёсткий стоп иначе)
- [ ] `*_test` БД существует (или создана идемпотентно, dev/prod не тронуты)
- [ ] Миграции к `*_test` применены (нет `Pending`) либо стратегия `RefreshDatabase` это покрывает
- [ ] Пре-флайт встроен перед `test` в Makefile/composer/git-хуке, при провале — блокер, не запуск
- [ ] dev/prod база не создавалась и не мигрировалась под видом тестовой

## Ссылки

- snippets/preflight.sh
- snippets/Makefile.test
- snippets/composer-scripts.json
- Связанные скиллы: `devops/docker-postgres`, `devops/makefile`, `devops/node-pnpm-preflight`
