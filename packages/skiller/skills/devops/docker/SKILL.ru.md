> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: docker
bucket: devops
version: 0.2.0
description: "Router for Dockerizing a Laravel/PHP app: directs to the right sub-skill (PHP image, Postgres, dev/prod compose split, full service stack, Vite HMR, Makefile). Use when the task involves Docker/Compose for this stack."
risk: read
persona: operator
tags: [docker, devops, router]
requires: []
produces_for: []
outputs: []
snippets: ["docker-expert.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Что это

Тонкий router-скилл: НЕ контейнеризирует сам, а направляет в специализированный под-скилл под конкретную
потребность. Грузи под-скилл по нужде (progressive disclosure) — не тащи всю экспертизу в контекст заранее.

## Маршрут (потребность → под-скилл)

| Нужно | Под-скилл |
|---|---|
| Production-образ PHP (alpine-fpm или all-in-one serversideup/php, entrypoint.d, healthcheck /up) | `devops:docker-php` |
| PostgreSQL в Docker (healthcheck, named volume, init тестовой БД) | `devops:docker-postgres` |
| Разнести compose на dev (build+bind-mount) и prod (prebuilt image) | `devops:docker-dev-prod` (требует docker-php) |
| Полный Laravel-стек из одного образа (app/queue/scheduler/reverb/docs) | `devops:docker-services` (требует docker-php + docker-postgres) |
| Vite dev-сервер отдельным compose-сервисом (HMR) | `devops:docker-vite` |
| Makefile как единая точка входа (help, .PHONY, docker-алиасы) | `devops:makefile` |

Порядок сборки полного стека: `docker-php` → `docker-postgres` → `docker-dev-prod` → `docker-services`
(+ `docker-vite`, `makefile` по необходимости). DAG зашит в `requires`/`produces_for` под-скиллов.

## Глубокая экспертиза (по требованию)

Общие принципы (оптимизация образа, security-hardening, multi-stage, оркестрация) — `snippets/docker-expert.md`,
читай только когда под-скилла недостаточно.
