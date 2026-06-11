---
name: docker-php
bucket: devops
version: 0.2.0
description: "Production-ready PHP-FPM Docker образ с opcache, healthcheck и non-root user"
risk: write
persona: operator
tags: ["docker", "php", "devops"]
requires: []
produces_for: ["docker-dev-prod"]
outputs: ["infra/docker/php/Dockerfile", "infra/docker/php/php.ini"]
snippets: ["Dockerfile.php-fpm", "Dockerfile.php-cli", "php.ini.production", "opcache.ini"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Создание production-ready PHP-FPM Docker образа для Laravel/PHP приложений.

## Входные данные

- Версия PHP (8.2/8.3/8.4)
- Нужен ли xdebug (только dev)
- Расширения PHP

## Алгоритм

1. Выбрать базовый образ `php:{version}-fpm-alpine`
2. Установить системные зависимости и PHP extensions
3. Настроить opcache через snippets/opcache.ini
4. Создать non-root user
5. Добавить HEALTHCHECK
6. Скопировать php.ini.production

## Чеклист качества

- [ ] non-root user в Dockerfile
- [ ] opcache включён в production
- [ ] healthcheck настроен
- [ ] .dockerignore актуален
