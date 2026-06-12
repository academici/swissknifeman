---
name: docker-postgres
bucket: devops
version: 0.3.0
description: "PostgreSQL в Docker: healthcheck pg_isready, named volume данных, init-скрипт создания тестовой БД <app>_test для изоляции тестов"
risk: write
persona: operator
tags: ["docker", "devops", "postgres", "testing"]
requires: []
produces_for: ["docker-dev-prod", "docker-services"]
outputs: ["docker-compose.yml (сервис pgsql)", "docker/postgres/init/01-test-db.sh"]
snippets: ["postgres.conf", "init.sql", "pgsql-service.yml", "init-test-db.sh"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Сервис `pgsql` (`postgres:16-alpine`) для Laravel-стека:

- **healthcheck `pg_isready`** — остальные сервисы стартуют только после готовности БД (`depends_on: pgsql: { condition: service_healthy }`); в compose-тесте экранировать `$$POSTGRES_USER`.
- **named volume** `pgsql_data:/var/lib/postgresql/data` — данные переживают пересоздание контейнера.
- **КЛЮЧЕВОЕ — вторая БД `<app>_test`** через init-скрипт в `/docker-entrypoint-initdb.d/`: фундамент изоляции тестов. Pest/PHPUnit (через `phpunit.xml: DB_DATABASE=<app>_test`) гоняют `migrate:fresh` в отдельной базе и не трогают dev-данные.

**Подводный камень**: скрипты из `/docker-entrypoint-initdb.d/` выполняются **только при первом создании volume**. Если volume `pgsql_data` уже существует — init молча не запустится. Для этого случая нужна отдельная make-цель `db-create-test`, идемпотентно создающая базу в работающем контейнере (см. `init-test-db.sh`, режим backfill, и скилл `makefile`).

## Алгоритм

1. Добавить сервис `pgsql` по `pgsql-service.yml`: образ, healthcheck, named volume, порт на `127.0.0.1` (не наружу).
2. Смонтировать каталог init-скриптов: `./docker/postgres/init:/docker-entrypoint-initdb.d:ro`.
3. Положить `docker/postgres/init/01-test-db.sh` (из `init-test-db.sh`) — создаёт `<app>_test` владельцем `${POSTGRES_USER}`.
4. Добавить make-цель `db-create-test` для существующих volume (идемпотентный psql внутрь контейнера).
5. В `phpunit.xml` прописать `DB_DATABASE=<app>_test`; убедиться, что тесты ходят в `DB_HOST=pgsql`.
6. При необходимости тюнинга — `postgres.conf`; расширения — `init.sql`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Сервис pgsql в compose (healthcheck, volume, init-mount) | `snippets/pgsql-service.yml` |
| Создание тестовой БД `<app>_test` (init + backfill для старого volume) | `snippets/init-test-db.sh` |
| Расширения/SQL при инициализации | `snippets/init.sql` |
| Тюнинг параметров PostgreSQL | `snippets/postgres.conf` |

## Чеклист качества

- [ ] healthcheck через `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`
- [ ] данные в named volume, не в контейнере и не в bind-mount
- [ ] порт опубликован только на `127.0.0.1` (доступ снаружи — туннель/exec)
- [ ] init-каталог смонтирован `:ro`, скрипты `set -eu` + `ON_ERROR_STOP=1`
- [ ] тестовая БД `<app>_test` создаётся init-скриптом; для существующего volume есть `make db-create-test`
- [ ] потребители БД используют `depends_on … condition: service_healthy`

## Ссылки

- https://hub.docker.com/_/postgres — раздел Initialization scripts (`/docker-entrypoint-initdb.d`)
- https://www.postgresql.org/docs/current/app-pg-isready.html — pg_isready
- Смежные скиллы: `docker-services` (depends_on-паттерны), `makefile` (цель db-create-test)
