---
name: docker-dev-prod
bucket: devops
version: 0.3.0
description: "Разнесение docker-compose на dev (build + bind-mount) и prod (готовый образ + named volumes), локальный override, якорь &app_env"
risk: write
persona: operator
tags: ["docker", "devops", "compose", "laravel"]
requires: []
produces_for: ["docker-services"]
outputs: ["docker-compose.yml", "docker-compose.prod.yml", "docker-compose.override.example.yml"]
snippets: ["docker-compose.yml", "docker-compose.dev.yml", "docker-compose.prod.yml", "docker-compose.override.yml", "docker-compose.override.example.yml", ".env.example", "Makefile"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Один Laravel-проект — два compose-файла в корне репозитория:

- **`docker-compose.yml` (dev)** — `build` из контекста (`dockerfile: docker/php/Dockerfile`) + bind-mount исходников `./:/var/www/html`. Код правится на хосте, виден в контейнере сразу.
- **`docker-compose.prod.yml`** — заранее собранный образ `image: <app>/app:latest` (`make image`) + named volumes для артефактов, которые не должны затираться bind-mount'ом: `public/build`, `public/filament` (если есть admin-сборка), `vendor`.

Принципы:

- **.env читается из смонтированного файла, НЕ через build args**: значение, переданное на этапе build/create, «замерзает» в контейнере — после правки .env пришлось бы пересоздавать контейнер. В `environment` прокидываются только переменные из окружения compose (`${VAR}`); специфичные (например `APP_URL`) оставляются на смонтированный `.env`.
- **YAML-якорь `&app_env`**: общий блок окружения объявляется один раз на сервисе `app` (`environment: &app_env`) и переиспользуется в queue/scheduler/reverb/vite через `environment: *app_env` (расширение — `<<: *app_env`).
- **Локальный оверрайд**: `docker-compose.override.yml` не коммитится; в репо лежит шаблон `docker-compose.override.example.yml`. Главный кейс — WSL2/Linux с bind-mount: `user: "1000:1000"` (или PUID/PGID в env) для сервиса vite, иначе Permission denied на node_modules.

## Алгоритм

1. Создать `docker-compose.yml` (dev) по `docker-compose.dev.yml`: app с `build:` + bind-mount, healthcheck `/up`, якорь `&app_env`.
2. Создать `docker-compose.prod.yml`: те же сервисы, но `image: <app>/app:latest`, named volumes `frontend_build`, `vendor_data`; `APP_ENV: production`, `LOG_LEVEL: warning`.
3. Скопировать шаблон `docker-compose.override.example.yml` в репо; в README указать `cp docker-compose.override.example.yml docker-compose.override.yml`.
4. Переменные портов/uid выносить в `.env`/`.env.docker` с дефолтами (`${APP_PORT:-8080}`).
5. Prod-команды запускать с явным `-f docker-compose.prod.yml` (см. скилл `makefile`).

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Минимальный каркас compose (старая версия) | `snippets/docker-compose.yml` |
| Полный dev-compose: build + bind-mount + якорь &app_env | `snippets/docker-compose.dev.yml` |
| Prod-compose: готовый образ + named volumes артефактов | `snippets/docker-compose.prod.yml` |
| Минимальный локальный оверрайд (старая версия) | `snippets/docker-compose.override.yml` |
| Шаблон локального оверрайда (WSL2, user 1000:1000) | `snippets/docker-compose.override.example.yml` |
| Базовые env-переменные | `snippets/.env.example` |
| Базовые make-цели | `snippets/Makefile` |

## Чеклист качества

- [ ] dev: `build` из контекста, prod: `image: <app>/app:latest` — без смешивания
- [ ] .env монтируется файлом, значения не «замораживаются» через build args
- [ ] общий блок окружения через якорь `&app_env`, без копипасты по сервисам
- [ ] prod: named volumes для `public/build`, `vendor` (и `public/filament` при admin-сборке)
- [ ] `docker-compose.override.yml` в .gitignore, в репо — `*.example.yml`
- [ ] порты и PUID/PGID параметризованы с дефолтами `${VAR:-default}`

## Ссылки

- https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/ — механика override-файлов
- https://docs.docker.com/reference/compose-file/fragments/ — YAML-якоря в compose
- Смежные скиллы: `docker-php` (Dockerfile), `docker-services` (полный стек сервисов), `makefile` (делегирующий Makefile)
