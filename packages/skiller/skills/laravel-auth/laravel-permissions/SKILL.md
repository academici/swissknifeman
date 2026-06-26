---
name: laravel-permissions
bucket: laravel-auth
version: 0.3.1
description: "Manual/native Laravel RBAC: policies, gates, entity-scoped permissions without a dedicated package. Need azguard package → skill azguard; declarative permission attributes on actions → attribute-authorization."
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

RBAC for Laravel: standard policies/gates + entity-scoped permissions (workspace/project context). Snippets here = manual impl without a package; use when external dep is unwanted. New projects: prefer package **azguard** (code-first RBAC, skill `azguard/azguard`).

## Steps

1. Simple RBAC → `rbac-setup.php`, `policy-class.php`, `gate-definition.php`.
2. Entity-scoped roles → `authorization-context.php` + `context-middleware.php` + `contextual-grant-source.php`.
3. Middleware sets context from route params; GrantSource reads permissions from `context_roles`.

## Quality checklist

- [ ] Context resets after request.
- [ ] Policy checks both global and contextual permissions.
- [ ] `context_roles` table indexed on `(context_type, context_id, model_id)`.

## Links

- `azguard/azguard` — ready code-first RBAC package (preferred for new projects); this skill = manual impl without dep.
- `laravel-auth/attribute-authorization` — declarative permission check on actions via `#[CheckPermission]` over Gate (orthogonal layer; permissions defined here).
- `laravel-architecture/enum-attributes` — enum permissions as typesafe layer instead of string abilities.
- `php/laravel-structure` — placement of Policies/Enums/Permissions in the project tree.
- `architect/security-design` — auth strategy, RBAC/ABAC, threat modeling at architecture level.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: d3b8b5b421b1dd5d7d6590f475498bb3da1c829e657552bd23b91e3ee3263aac -->
