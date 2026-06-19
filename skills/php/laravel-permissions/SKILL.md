---
name: laravel-permissions
bucket: php
version: 0.3.1
description: "Ручной/нативный Laravel RBAC: policies, gates, entity-scoped permissions без спец-пакета. Когда нужен пакет azguard → скилл azguard; декларативные атрибуты прав на экшенах → attribute-authorization."
risk: write
persona: oss-dev
tags: ["php", "laravel", "permissions", "azguard", "rbac", "authorization"]
requires: []
produces_for: []
outputs: []
snippets:
  - rbac-setup.php
  - policy-class.php
  - gate-definition.php
  - authorization-context.php
  - context-middleware.php
  - contextual-grant-source.php
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

RBAC для Laravel: стандартные policies/gates + entity-scoped permissions (контекст workspace/project).

Базовый вариант для новых проектов — пакет **azguard** (code-first RBAC, см. скилл `php/azguard`). Сниппеты этого скилла — ручная реализация без пакета: используй их, когда внешняя зависимость нежелательна.

## Алгоритм

1. Для простого RBAC — `rbac-setup.php`, `policy-class.php`, `gate-definition.php`
2. Для entity-scoped roles — `authorization-context.php` + `context-middleware.php` + `contextual-grant-source.php`
3. Middleware устанавливает контекст из route params, GrantSource читает права из context_roles

## Чеклист качества

- [ ] Контекст сбрасывается после request
- [ ] Policy проверяет и глобальные, и контекстные права
- [ ] Таблица context_roles индексирована по (context_type, context_id, model_id)

## Ссылки

- `php/azguard` — готовый code-first RBAC-пакет (предпочтительный путь для новых проектов); этот скилл — ручная реализация без зависимости.
- `php/attribute-authorization` — декларативная проверка прав на экшенах через атрибут `#[CheckPermission]` поверх Gate (ортогональный слой; права определяются здесь).
- `php/enum-attributes` — enum-права как типобезопасный слой вместо строковых abilities.
- `php/laravel-structure` — размещение Policies/Enums/Permissions в дереве проекта.
- `architect/security-design` — auth-стратегия, RBAC/ABAC, threat modeling на уровне архитектуры.
