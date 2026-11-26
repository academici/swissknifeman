---
name: laravel-permissions
description: "Use for native Laravel policies/gates and entity RBAC."
---

RBAC for Laravel: standard policies/gates + entity-scoped permissions (workspace/project context). Snippets here = manual impl without a package; use when external dep is unwanted. Prefer a code-first RBAC package for new projects.

## Steps

1. Simple RBAC → `rbac-setup.php`, `policy-class.php`, `gate-definition.php`.
2. Entity-scoped roles → `authorization-context.php` + `context-middleware.php` + `contextual-grant-source.php`.
3. Middleware sets context from route params; GrantSource reads permissions from `context_roles`.

## Quality checklist

- [ ] Context resets after request.
- [ ] Policy checks both global and contextual permissions.
- [ ] `context_roles` table indexed on `(context_type, context_id, model_id)`.

## Links

- `laravel-auth/attribute-authorization` — declarative permission check on actions via `#[CheckPermission]` over Gate (orthogonal layer; permissions defined here).
- `laravel-architecture/enum-attributes` — enum permissions as typesafe layer instead of string abilities.
- `php/laravel-structure` — placement of Policies/Enums/Permissions in the project tree.
- `architect/security-design` — auth strategy, RBAC/ABAC, threat modeling at architecture level.
