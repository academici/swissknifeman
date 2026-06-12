---
name: docker-services
bucket: devops
version: 0.1.0
description: "Полный сервисный стек Laravel из одного образа: app (fpm-nginx), queue, scheduler, reverb, опционально docs; healthcheck /up и depends_on service_healthy"
risk: write
persona: operator
tags: ["docker", "devops", "compose", "laravel", "queue", "websocket"]
requires: ["docker-php"]
produces_for: []
outputs: ["docker-compose.yml (сервисы app/queue/scheduler/reverb/docs)"]
snippets: ["services.yml", "healthchecks.yml"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Полный сервисный стек Laravel из **одного образа** (`docker-php`, паттерн serversideup fpm-nginx): каждый процесс — отдельный контейнер, различается только `command`.

| Сервис | Команда | Порт |
|---|---|---|
| app | дефолт образа (FPM + Nginx) | 8080 |
| queue | `php artisan queue:work --sleep=3 --tries=3 --max-time=3600` | — |
| scheduler | `php artisan schedule:work` | — |
| reverb | `php artisan reverb:start --host=0.0.0.0 --port=8000` (websocket) | 8000 |
| docs (опц.) | init-контейнер сборки (`restart: "no"`) + nginx:alpine раздаёт статику | 4173 |

Связность стека:

- **healthcheck app** по Laravel-эндпоинту: `curl -fsS http://127.0.0.1:8080/up` с `start_period: 40s`.
- **Порядок старта** через `depends_on: { pgsql: { condition: service_healthy } }`; воркеры дополнительно ждут healthy app. Docs-nginx ждёт init-контейнер через `condition: service_completed_successfully`.
- **Общее окружение** — YAML-якорь `&app_env` на app, остальные сервисы — `environment: *app_env` (расширение — `<<: *app_env`).

## Алгоритм

1. Собрать app-сервис: образ из `docker-php`, healthcheck `/up`, `stop_signal: SIGTERM`, объявить якорь `&app_env`.
2. Добавить queue/scheduler/reverb по `services.yml`: тот же build/image, свой `command`, `environment: *app_env`, `depends_on` на healthy app+pgsql(+redis).
3. Для reverb пробросить `${REVERB_SERVER_PORT:-8000}` наружу (websocket-клиенты ходят с хоста).
4. Опционально docs: init-контейнер собирает статику (`restart: "no"`), nginx-alpine раздаёт её read-only.
5. Для prod добавить healthcheck'и воркерам (`pgrep -af 'artisan queue:work'`) — см. `healthchecks.yml`.
6. Управление — make-цели `logs:core`, `*-restart`, `workers:restart` (скилл `makefile`).

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Поднять стек целиком (app+queue+scheduler+reverb+docs) | `snippets/services.yml` |
| Паттерны healthcheck и depends_on (app, воркеры, init-контейнер) | `snippets/healthchecks.yml` |

## Чеклист качества

- [ ] один образ для всех PHP-сервисов, различие только в `command`
- [ ] app: healthcheck на `/up`, `start_period` достаточен для прогрева
- [ ] воркеры зависят от healthy app/pgsql/redis, не просто от «запущен»
- [ ] окружение через якорь `&app_env`, без дублирования блоков
- [ ] `stop_signal: SIGTERM` у app/reverb — корректное завершение
- [ ] init-контейнеры: `restart: "no"` + `service_completed_successfully` у потребителей
- [ ] queue:work с `--max-time` — воркер периодически перезапускается и подхватывает новый код

## Ссылки

- https://docs.docker.com/reference/compose-file/services/#depends_on — условия depends_on
- https://laravel.com/docs/queues#running-the-queue-worker, https://laravel.com/docs/reverb — воркеры и Reverb
- Смежные скиллы: `docker-php` (образ), `docker-dev-prod` (dev/prod раскладка), `docker-postgres` (healthy pgsql), `makefile` (управление стеком)
