---
name: laravel-permissions
bucket: php
version: 0.2.0
description: "RBAC, policies, gates и entity-scoped permissions (AzGuard patterns)"
risk: write
persona: oss-dev
tags: ["php", "laravel", "permissions", "azguard"]
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

## Алгоритм

1. Для простого RBAC — `rbac-setup.php`, `policy-class.php`, `gate-definition.php`
2. Для entity-scoped roles — `authorization-context.php` + `context-middleware.php` + `contextual-grant-source.php`
3. Middleware устанавливает контекст из route params, GrantSource читает права из context_roles

## Чеклист качества

- [ ] Контекст сбрасывается после request
- [ ] Policy проверяет и глобальные, и контекстные права
- [ ] Таблица context_roles индексирована по (context_type, context_id, model_id)
