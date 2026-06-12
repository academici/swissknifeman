---
name: docker-php
bucket: devops
version: 0.3.0
description: "Production-ready PHP Docker образ: alpine-fpm или всё-в-одном serversideup/php (FPM+Nginx), entrypoint.d-хуки, healthcheck на /up"
risk: write
persona: operator
tags: ["docker", "php", "devops", "laravel"]
requires: []
produces_for: ["docker-dev-prod", "docker-services"]
outputs: ["infra/docker/php/Dockerfile", "infra/docker/php/php.ini"]
snippets: ["Dockerfile.php-fpm", "Dockerfile.php-cli", "Dockerfile.serversideup", "entrypoint-hook.sh", "php.ini.production", "opcache.ini"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Production-ready PHP Docker образ для Laravel/PHP приложений. Два паттерна:

1. **alpine-fpm** (`php:8.3-fpm-alpine`) — минимальный FPM-образ, веб-сервер отдельным контейнером. Полный контроль и меньший размер, но больше обвязки (nginx-сервис, supervisor для воркеров).
2. **Всё-в-одном** (`serversideup/php:8.3-fpm-nginx`) — FPM + Nginx в одном production-ready образе. Из коробки: S6-overlay, корректная обработка SIGTERM, переменные `PUID`/`PGID` для маппинга прав на bind-mount. Один и тот же образ переиспользуется для app/queue/scheduler/reverb/vite — меняется только `command`.

Ключевая фича serversideup — **хуки `/etc/entrypoint.d/`**: любой исполняемый `NN-*.sh`, скопированный в эту директорию, автоматически выполняется при старте контейнера (в порядке номеров). Типовое применение — выставление прав на каталоги, появляющиеся на bind-mount уже после build (например `public/media`).

## Алгоритм

1. Выбрать паттерн: отдельный fpm (`Dockerfile.php-fpm`) или всё-в-одном (`Dockerfile.serversideup`).
2. Установить системные зависимости и PHP-расширения (`docker-php-ext-install`, `pecl` для imagick/redis).
3. Для serversideup: если фронтенд собирается в этом же образе — поставить Node.js + pnpm (образ переиспользуют vite/docs-сервисы).
4. Добавить entrypoint-хуки: `COPY ... /etc/entrypoint.d/20-*.sh` + `chmod +x` (см. `entrypoint-hook.sh`).
5. Настроить opcache (`opcache.ini`) и production `php.ini.production`; лимиты загрузки (upload_max_filesize и т.п.) — отдельным conf.d-файлом.
6. Завершить Dockerfile non-root пользователем (`USER www-data` для serversideup).
7. В compose повесить healthcheck на Laravel-эндпоинт `/up`:
   `test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8080/up >/dev/null || exit 1"]` с `start_period: 40s` (прогрев фреймворка).

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Минимальный FPM-образ, nginx отдельным контейнером | `snippets/Dockerfile.php-fpm` |
| CLI-образ для artisan/queue (alpine-паттерн) | `snippets/Dockerfile.php-cli` |
| Всё-в-одном FPM+Nginx, один образ на весь стек | `snippets/Dockerfile.serversideup` |
| Автовыполнение скрипта при старте контейнера (права, init) | `snippets/entrypoint-hook.sh` |
| Production-настройки PHP | `snippets/php.ini.production` |
| Настройка OPcache | `snippets/opcache.ini` |

## Чеклист качества

- [ ] non-root user (`www-data` / custom) в финальном слое Dockerfile
- [ ] opcache включён в production
- [ ] healthcheck настроен (для Laravel — эндпоинт `/up`)
- [ ] entrypoint-хуки исполняемые (`chmod +x`) и идемпотентные (`set -eu`, проверка `id -u` перед chown)
- [ ] .dockerignore актуален (node_modules, vendor, .git)
- [ ] один образ переиспользуется для app/queue/scheduler (serversideup-паттерн)

## Ссылки

- https://serversideup.net/open-source/docker-php/docs — serversideup/php (entrypoint.d, PUID/PGID, S6-overlay)
- https://laravel.com/docs/deployment#the-health-route — Laravel health-эндпоинт `/up`
- Смежные скиллы: `docker-dev-prod` (раскладка compose), `docker-services` (стек из одного образа)
