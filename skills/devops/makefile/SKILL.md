---
name: makefile
bucket: devops
version: 0.1.0
description: "Makefile как единая точка входа для управления проектом в локальной среде разработки"
risk: write
persona: operator
tags: [make, devops]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Makefile Best Practices

Makefile используется как единая точка входа для управления проектом в локальной среде разработки. Он скрывает за собой длинные и сложные команды Docker, Composer, NPM и других утилит.

## Основные Правила

1.  **Документированность:** Всегда добавляйте команду `make help` (обычно первую по умолчанию), которая выводит список доступных команд с их описанием.
2.  **Декларативность:** Старайтесь, чтобы команды Makefile были простыми алиасами. Сложную логику лучше выносить в bash-скрипты.
3.  **`.PHONY`:** Всегда объявляйте цели в `.PHONY`, чтобы Make не путал их с одноименными файлами в корневой директории.

## Структура Makefile

```makefile
# Переменные для удобства (например, имя контейнера)
APP_CONTAINER=app
DB_CONTAINER=db

.PHONY: help up down shell log test

# Команда по умолчанию
help: ## Показать этот список команд
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Запустить контейнеры в фоновом режиме
	docker compose up -d

down: ## Остановить и удалить контейнеры
	docker compose down

shell: ## Зайти в консоль основного контейнера
	docker compose exec -it $(APP_CONTAINER) bash

log: ## Смотреть логи основного контейнера (make log app)
	docker compose logs -f $(APP_CONTAINER)

test: ## Запустить тесты
	docker compose exec -it $(APP_CONTAINER) vendor/bin/phpunit
```

## Типичные Цели (Targets)

-   `make up` — поднять проект.
-   `make down` — опустить проект.
-   `make build` — пересобрать образы.
-   `make install` — установить зависимости (обычно внутри контейнера).
-   `make shell` / `make bash` — провалиться в контейнер приложения.
-   `make test` — прогнать весь набор тестов.
-   `make lint` / `make format` — запустить статический анализатор и форматтер.
-   `make db-migrate` — запустить миграции БД.
-   `make db-seed` — заполнить БД сидами.

## Использование `.env`

Иногда полезно читать переменные окружения прямо в Makefile:

```makefile
ifneq (,$(wildcard ./.env))
    include .env
    export
endif
```
Это позволит использовать переменные из `.env` прямо в командах Make.
