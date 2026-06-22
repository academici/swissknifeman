---
name: php-patterns
bucket: php
version: 0.2.0
description: "PHP domain patterns: VO, DTO, pipeline, specification"
risk: write
persona: oss-dev
tags: ["php", "laravel", "patterns", "dto", "architecture"]
requires: []
produces_for: []
outputs: []
snippets: ["value-object.php", "dto.php", "pipeline.php", "specification.php"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

PHP domain patterns: VO, DTO, pipeline, specification

## Алгоритм

Используй сниппеты как шаблоны.

## Ссылки

- `php/laravel-data` — DTO на `spatie/laravel-data` (типизированный слой данных, валидация из запроса, `#[TypeScript]`); этот скилл — про «голые» PHP-паттерны (VO/DTO/pipeline/specification) без пакета.
- `php/laravel` — где эти паттерны живут в архитектуре приложения (actions, repositories).
- `php/laravel-structure` — куда класть VO/DTO в дереве проекта.
- `php/dependency-injection` — как pipeline/specification собираются через constructor injection.
- `php/named-arguments` — стиль вызовов конструкторов VO/DTO.
