---
name: laravel
bucket: php
version: 0.4.0
description: "Laravel architecture patterns: actions, repositories, resources"
risk: write
persona: oss-dev
tags: ["php", "laravel", "architecture", "patterns"]
requires: []
produces_for: ["repositories", "dependency-injection", "database", "modular-architecture", "filament", "botkit"]
outputs: []
snippets: ["service-provider.php", "repository-pattern.php", "action-class.php", "form-request.php", "api-resource.php", "event-listener.php", "custom-middleware.php", "actions.md", "authorization.md", "db-conventions.md", "dto.md", "eloquent-model.md", "layer-boundaries.md", "routes-organization.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Laravel architecture patterns: actions, repositories, resources

## Алгоритм

Используй сниппеты как шаблоны.

Организация маршрутов (`routes/web.php` / `routes/api.php`): группировка `Route::controller()->prefix()->name()->group()`, доменные подпрефиксы, precognitive, throttle для API — см. `snippets/routes-organization.md`.

## Смежные скиллы

- Структура проекта и размещение классов (доменная таксономия, правило зеркала, нейминг) → `php/laravel-structure`
- Репозитории (Read/Store) → `php/repositories`
- DI и взаимодействие компонентов → `php/dependency-injection`
- DTO на пакете → `php/laravel-data`; «голые» доменные паттерны (VO/pipeline/specification) → `php/php-patterns`
- Миграции и модели → `php/database`; рост до модулей → `php/modular-architecture`
- Тесты архитектурных слоёв → `php/laravel-testing`
- Общие лучшие практики Laravel → `php/laravel-best-practices` (external)
