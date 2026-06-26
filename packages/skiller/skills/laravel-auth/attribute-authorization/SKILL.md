---
name: attribute-authorization
bucket: laravel-auth
version: 0.1.0
description: "Declarative method-level authorization via #[CheckPermission] attribute (enum permission + route args) and reflection-middleware CheckAccess over Gate. Activate for declarative action-level checks, enum permissions instead of strings, reflection middleware."
risk: write
persona: oss-dev
tags: [php, laravel, authorization, attribute, reflection, middleware, gate, enum, permissions, rbac]
requires: [laravel-permissions]
produces_for: []
outputs: []
snippets: [CheckPermission.php, CheckAccess.php, OrderController.php]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Attribute-based authorization

Method-level authorization: permission declared via `#[CheckPermission]` attribute above the action, not repeated in body as `$this->authorize(...)` / `Gate::allows(...)`. Attribute carries: **enum permission** (not string), list of route-parameter names (resolved to models via route-model binding), `abort` params (status + message). Middleware `CheckAccess` reads attributes via reflection and reduces to `Gate::allows()`.

Activate when:
- declarative action-level permission check needed (permission visible in method signature; controller unaware of Gate);
- permissions modeled as **enum**, not strings, with type-safety at declaration site;
- designing/editing **reflection-middleware** reading controller-method attributes;
- one action needs **multiple** checks with different abort statuses (403 deny, 404 to mask others' resource).

## Boundary vs `php/laravel-permissions`

Orthogonal layer **on top of** Gate, not a replacement for policies/gates:

| | `laravel-permissions` (RBAC) | `attribute-authorization` (this skill) |
|:---|:---|:---|
| Defines | **the permissions**: ability via `Gate::define`, policies, RBAC, entity-scoped grants | **how permission is checked on action** — declaratively via attribute |
| Permission id | ability string (`'order.view'`) | **enum case**; `$permission->value` goes to Gate |
| Application point | `Gate::allows`, `$user->can`, policies in service layer | attribute over method + middleware executor |
| Mechanism | container, policy resolver, context | `ReflectionMethod::getAttributes()` |

Linkage: keep ability logic ("can it") in Gate/policy per `laravel-permissions`; each permission's `enum::value` = ability string there. This skill only declaratively attaches the ability call to the action. Enum permissions as metadata/type-safe layer — see `php/enum-attributes`.

## Algorithm

1. **Permission enum.** Backed-enum (string), one case per permission; each case value = ability string registered in Gate (see `laravel-permissions`). Attribute accepts `UnitEnum`; `$permission->value` goes to Gate.
2. **Attribute `CheckPermission`** (`app/Attributes/`, see `snippets/CheckPermission.php`):
   - flags `Attribute::TARGET_METHOD | Attribute::IS_REPEATABLE` — method-only target, multiple per action allowed;
   - `final readonly`, constructor with promoted props: `UnitEnum $permission`, `array $arguments = []` (route param names), `int $status = 403`, `?string $message = null`.
3. **Middleware `CheckAccess`** (`app/Http/Middleware/`, see `snippets/CheckAccess.php`):
   - in `handle()`: get action attributes; for each — resolve args and call `abort_if(! Gate::allows(ability: $attr->permission->value, arguments: $args), code: $attr->status, message: $attr->message ?? '')`;
   - **reading attributes**: `$request->route()->getActionName()` → if string contains `@`, split into `[$controllerClass, $methodName]`; check `class_exists` + `method_exists`; `new ReflectionMethod(...)->getAttributes(CheckPermission::class)`; each → `->newInstance()`. Closure routes and missing `@` → return `[]` (middleware transparent).
   - **resolving args**: `array_values(array_map(fn($name) => $request->route($name), $attr->arguments))` — route param names → values (usually Model from route-model binding), positionally, in declaration order.
4. **Register middleware** (section below) — alias + attach to needed groups/routes.
5. **Apply in controller** (see `snippets/OrderController.php`): put `#[CheckPermission(Permission::Foo, arguments: ['order'])]` above action; names in `arguments` MUST match route param names. Multiple attributes = logical AND (all must pass).
6. **Test** (section below): feature tests for 200/403/404 across permissions + when attribute absent; unit for arg resolution and order.

## Middleware registration

**Laravel 11/12** (`bootstrap/app.php`) — alias, then attach to group/routes:

```php
->withMiddleware(function (Middleware $middleware): void {
    $middleware->alias([
        'check-access' => \App\Http\Middleware\CheckAccess::class,
    ]);
    // variant: whole web group
    $middleware->appendToGroup('web', \App\Http\Middleware\CheckAccess::class);
})
```

**Apply to routes:**

```php
Route::middleware(['auth', 'check-access'])->group(function (): void {
    Route::resource('orders', OrderController::class);
});
```

**Laravel 10 and below** — alias in `App\Http\Kernel::$middlewareAliases` (or `$routeMiddleware`).

Order: `CheckAccess` must run **after** `auth` (Gate relies on current user) and **after** SubstituteBindings if `arguments` need resolved models (route-model binding). When attached to whole group, actions without attributes stay open — middleware transparent on them.

## Testing

- **Feature (happy path)**: user with permission → 200; `Gate::allows` receives resolved model.
- **Feature (deny)**: user without permission → `abort` with attribute `status` (default 403; 404 for second action branch).
- **Multiple attributes**: A passes, B fails → deny; swap → deny again (logical AND).
- **No attribute**: action without `#[CheckPermission]` under group with middleware → 200 (transparency).
- **Closure route / nonstandard action**: middleware does not crash, returns `[]`.
- **Unit on resolution**: `arguments: ['a', 'b']` → `[$routeA, $routeB]` to Gate in that order via `array_values` (no string keys).
- Convenient to mock Gate via `Gate::shouldReceive`/fake or register a test ability to isolate middleware from real RBAC logic.

## Quality checklist

- [ ] Attribute `final readonly`, flags `TARGET_METHOD | IS_REPEATABLE`, permission of type `UnitEnum`
- [ ] `$permission->value` goes to Gate, not the enum itself
- [ ] Middleware reads attributes via `ReflectionMethod::getAttributes()`, not by parsing strings otherwise
- [ ] Closure routes, missing `@`, nonexistent class/method → `[]` (middleware throws no exceptions)
- [ ] Args resolved from route params via `array_values` (positional, no string keys)
- [ ] `abort_if` uses `status` and `message` from attribute; `message ?? ''`
- [ ] Names in `arguments` match route param names; models arrive resolved (middleware after SubstituteBindings)
- [ ] Middleware registered and attached after `auth`; controller has no manual `Gate::allows`/`$this->authorize`
- [ ] Abilities themselves defined separately (Gate/policy, skill `laravel-permissions`); here — declaration only
- [ ] Tests for 200 / 403 / 404, multiple attributes, missing attribute, arg order

## References

- snippets/CheckPermission.php — attribute
- snippets/CheckAccess.php — reflection-middleware
- snippets/OrderController.php — controller with `#[CheckPermission]`
- https://www.php.net/manual/en/language.attributes.php
- https://laravel.com/docs/authorization (Gate::allows)
- Related skills: `php/laravel-permissions` (permission/policy/gate definition — boundary above), `php/azguard` (package code-first RBAC as ability source), `php/enum-attributes` (enum as metadata), `php/named-arguments` (call style in snippets), `architect/security-design` (architecture-level auth strategy)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: ed6375eabe5546f132489d223afc214dc2e0242254658109edbab1c6a2fa40d2 -->
