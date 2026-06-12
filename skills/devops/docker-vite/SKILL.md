---
name: docker-vite
bucket: devops
version: 0.3.0
description: "Vite dev server отдельным compose-сервисом для Laravel: named volume для node_modules, HMR через localhost, host 0.0.0.0"
risk: write
persona: operator
tags: ["docker", "devops", "vite", "frontend", "laravel"]
requires: []
produces_for: ["docker-dev-prod"]
outputs: ["docker-compose.yml (сервис vite)", "vite.config.js (server-блок)"]
snippets: ["Dockerfile.node", "vite.config.docker.ts", "vite-service.yml", "vite-server-config.js"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Vite dev server как **отдельный сервис compose** рядом с Laravel-app. Может работать из того же PHP-образа (если в него поставлены Node+pnpm, см. `docker-php`) или из отдельного node-образа.

Три критичных момента:

1. **Команда**: `pnpm install && pnpm run dev --host=0.0.0.0 --port=${VITE_PORT:-5173}` — install при каждом старте (node_modules живёт в volume), `--host=0.0.0.0` обязателен, иначе dev-server слушает только loopback внутри контейнера.
2. **node_modules — named volume, НЕ bind-mount**: `vite_node_modules:/var/www/html/node_modules` поверх bind-mount исходников. Иначе — медленный I/O (особенно WSL2/macOS), конфликты бинарных зависимостей хост/контейнер и мусор в рабочей копии.
3. **HMR-конфиг**: внутри контейнера `server.host: "0.0.0.0"`, но браузер ходит с хоста — `hmr.host: "localhost"`. Порт пробрасывается симметрично (`5173:5173`), `strictPort: true` чтобы не уехать на другой порт молча. CORS — на `APP_URL` приложения.

## Алгоритм

1. Добавить сервис `vite` в dev-compose по `vite-service.yml` (тот же Dockerfile, что и app, либо `Dockerfile.node`).
2. Объявить named volume `vite_node_modules` в секции `volumes:` compose-файла.
3. Пробросить порт `${VITE_PORT:-5173}:${VITE_PORT:-5173}`; env-блок переиспользовать через якорь `*app_env`.
4. Настроить server-блок `vite.config.js` по `vite-server-config.js` (host/hmr/cors, порт из `VITE_PORT`).
5. `depends_on: app: { condition: service_healthy }` — vite стартует после готовности приложения.
6. На WSL2/Linux при Permission denied — локальный override `user: "1000:1000"` (см. `docker-dev-prod`).

## Когда какой сниппет открывать

| Ситуация | Файл |
|---|---|
| Сервис vite в docker-compose | `snippets/vite-service.yml` |
| server-блок vite.config.js (host/HMR/CORS/порт) | `snippets/vite-server-config.js` |
| Отдельный node-образ для фронтенда | `snippets/Dockerfile.node` |
| Минимальный vite-конфиг под Docker (TS, базовая версия) | `snippets/vite.config.docker.ts` |

## Чеклист качества

- [ ] `--host=0.0.0.0` в команде dev-server
- [ ] node_modules в named volume, не в bind-mount
- [ ] `hmr.host: "localhost"` — HMR-сокет доступен браузеру с хоста
- [ ] порт параметризован `${VITE_PORT:-5173}` и проброшен симметрично, `strictPort: true`
- [ ] CORS ограничен origin приложения (`APP_URL`), не `*`
- [ ] vite зависит от healthy app (`depends_on … service_healthy`)

## Ссылки

- https://vite.dev/config/server-options — server.host / server.hmr
- https://laravel.com/docs/vite — laravel-vite-plugin
- Смежные скиллы: `docker-php` (Node в PHP-образе), `docker-dev-prod` (override для WSL2)
