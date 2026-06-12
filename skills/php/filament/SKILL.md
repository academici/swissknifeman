---
name: filament
bucket: php
version: 0.2.0
description: "Filament v3 resource patterns: CRUD resource, relation managers, panel integration"
risk: write
persona: oss-dev
tags: [php, laravel, filament, ui]
requires: [laravel]
produces_for: []
outputs: []
snippets:
  - resource-stub.php
  - relation-manager-stub.php
  - filament-development.md
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Паттерны Filament v3 Resource для admin-панелей: CRUD, relation managers, navigation groups.

**Laravel Boost**: версионные гайдлайны Filament поставляет Boost (third-party guidelines); здесь — структура ресурсов и проектные паттерны.

## Алгоритм

1. Создай Resource с model binding
2. Определи form() и table() schema
3. Добавь RelationManager для связей
4. Зарегистрируй в PanelProvider

## Чеклист качества

- [ ] navigationGroup задан для группировки
- [ ] authorize через policies
- [ ] labels на русском если проект RU
