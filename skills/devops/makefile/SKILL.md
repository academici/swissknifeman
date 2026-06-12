---
name: makefile
bucket: devops
version: 0.2.0
description: "Makefile как единая точка входа: help, .PHONY, алиасы Docker-команд; паттерн делегирующего корневого Makefile с catch-all в docker/Makefile"
risk: write
persona: operator
tags: ["make", "devops", "docker"]
requires: []
produces_for: ["docker-dev-prod", "docker-services"]
outputs: ["Makefile", "docker/Makefile"]
snippets: ["Makefile.root", "Makefile.docker"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Makefile — единая точка входа для управления проектом в локальной среде: скрывает длинные команды Docker, Composer, pnpm.

Основные правила:

1. **Документированность**: цель `make help` (первая по умолчанию) выводит список команд с описанием.
2. **Декларативность**: цели — простые алиасы; сложную логику выносить в bash-скрипты.
3. **`.PHONY`**: объявлять все цели, чтобы Make не путал их с одноимёнными файлами.
4. **`.env` в Make**: `ifneq (,$(wildcard ./.env)) include .env / export endif` — переменные окружения доступны в командах.

**Паттерн «делегирующий Makefile»**: корневой Makefile содержит только `help` и catch-all:

```makefile
%:
	@$(MAKE) -f docker/Makefile $@
```

Вся docker-логика изолирована в `docker/Makefile`, но любая команда (`make up`, `make migrate`, `make test`) запускается из корня репозитория. Корень остаётся чистым, docker-обвязка живёт рядом с Dockerfile/конфигами в `docker/`.

## Алгоритм

1. Создать корневой Makefile по `Makefile.root`: `MAKEFLAGS += --no-print-directory`, `help`, catch-all `%`.
2. Создать `docker/Makefile` по `Makefile.docker`: переменная `DOCKER_COMPOSE_DEV` с подключением env-файлов (`--env-file .env --env-file .env.docker`, если второй существует; при явном `--env-file` compose перестаёт читать `.env` автоматически).
3. Завести типовые цели: `up/down/build/restart/ps/logs/shell/artisan/migrate/test/db-create-test`; prod-цели — с явным `-f docker-compose.prod.yml` и префиксом `prod:` (в .PHONY и целях двоеточие экранируется: `prod\:migrate`).
4. Все цели перечислить в `.PHONY`; `help` — первой.
5. Параметризованные вызовы — через `ARGS`: `make artisan ARGS="migrate --seed"`.

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Корневой делегирующий Makefile (help + catch-all) | `snippets/Makefile.root` |
| Docker-логика: up/down/build/shell/logs/migrate/test/db-create-test, env-файлы | `snippets/Makefile.docker` |

## Чеклист качества

- [ ] `make help` — первая цель, описывает все команды
- [ ] все цели в `.PHONY` (включая экранированные `prod\:*`)
- [ ] корневой Makefile не содержит docker-логики — только делегирование
- [ ] `--env-file` перечисляет и `.env`: с явным флагом compose не читает его сам
- [ ] prod-цели всегда с явным `-f docker-compose.prod.yml`
- [ ] сложная логика (создание тестовой БД и т.п.) — в bash-скриптах, Make лишь вызывает их

## Ссылки

- https://www.gnu.org/software/make/manual/make.html#Phony-Targets — .PHONY
- https://www.gnu.org/software/make/manual/make.html#Last-Resort — match-anything (catch-all) правила
- Смежные скиллы: `docker-dev-prod` (compose-файлы, которые дергает Makefile), `docker-postgres` (цель db-create-test)
