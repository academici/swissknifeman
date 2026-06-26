---
name: modular-architecture
bucket: laravel-architecture
version: 0.3.0
description: "Scale Laravel code as it grows: organize by business domain, Modular Monolith and DDD patterns; implement with nwidart/laravel-modules (module:make*, module structure, namespace without Modules\\, Filament discovery); starting structure — php/laravel-structure"
risk: write
persona: oss-dev
tags: [php, laravel, architecture, nwidart, laravel-modules, filament]
requires: [laravel]
produces_for: []
outputs: []
snippets: [nwidart-module.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Modular Architecture (Laravel)

## When to activate

- Asks to "split monolith into modules", "organize code by domains", "extract domain/bounded context", "modular monolith", "DDD structure" in a Laravel project.
- Flat `app/Http`, `app/Models` bloated: dozens of controllers/models in one folder, multiple teams editing one dir, cross-domain deps appearing.
- Mentions `nwidart/laravel-modules`, `module:make*` commands, `Modules/` dir, per-module isolation of migrations/configs/frontend.
- Need to register Filament resources from modules (`discoverResources` per module) or configure separate per-module Vite build.
- NOT for a new empty project without growth signs — use `php/laravel-structure` there.

## Core idea

Organize code by **business domain** (everything for Invoices in one place), not by technical type (all controllers in one folder, all models in another).

## Algorithm

1. **Define domain boundaries (bounded contexts).** Group entities/logic by business meaning (Invoices, Users, Wallets, Notifications), not technical type. One domain = one module. Avoid a "common" dumping-ground module.
2. **Choose module organization:**
   - *Lightweight (no package):* `app/Modules/<Domain>/` with subfolders `Controllers/`, `DTOs/`, `Jobs/`, `Models/`, `Providers/`, `Repositories/`, `Services/`. Register via custom `ModuleServiceProvider` scanning folders; if needed PSR-4 `"Modules\\": "app/Modules/"` in root `composer.json`.
   - *Full (`nwidart/laravel-modules`):* when generators, migration/config isolation, separate per-module frontend build are needed. Modules live in root `Modules/`, each a self-sufficient unit.
3. **Create module (nwidart):** `php artisan module:make <Name>` — generates full skeleton (`app/`, `database/`, `routes/`, `tests/`, `config/`, `module.json`, `composer.json`, `vite.config.js`). Files inside a module — only via `module:make-*` generators (module name as last arg), not by hand.
4. **Namespace without `Modules\` prefix:** in module `composer.json` map PSR-4 `<Name>\` to `app/` (and `<Name>\Database\Factories|Seeders|Migrations`, `<Name>\Tests`); set `'namespace' => ''` in `config/modules.php`; in `module.json` set provider as `"<Name>\\Providers\\<Name>ServiceProvider"`. Root `composer.json` merges module ones via `wikimedia/composer-merge-plugin` — then one `composer dump-autoload` at root.
5. **Module isolation:** forbid cross-DB join between modules — communication only via Contracts/public Services or Events. Data between modules and layers — via DTO, not raw arrays. Keep controllers thin: validation → DTO → call Service/Action → Response/Resource.
6. **Register module Filament resources (if any):** generate normally `make:filament-resource <Name> --generate`, move to `Modules/<Name>/app/Filament/Resources`, fix namespace `App\Filament\Resources\...` → `<Name>\Filament\Resources\...` in all files (Resource, Pages, RelationManagers), then register `discoverResources(in: base_path('Modules/<Name>/app/Filament/Resources'), for: '<Name>\\Filament\\Resources')` in `AdminPanelProvider`.
7. **Module frontend (if any):** own `vite.config.js` with unique `buildDirectory` (e.g. `build-<name>`), entries `resources/css/app.css` and `resources/js/app.js` of the module; export `paths` for the shared entry aggregator `vite-module-loader.js`.
8. **Run quality checklist** and run `composer dump-autoload`, module migrations, module tests (`Modules/<Name>/tests/`).

Ready snippets for steps 3–7 (tree, `module.json`, `composer.json`, `config/modules.php`, commands, `vite.config.js`, discovery block) — in `snippets/nwidart-module.md`.

## Directory structure (lightweight)

Create `app/Modules` (or `src/Modules`):

```text
app/
  Modules/
    Invoices/
      Controllers/    # HTTP layer
      DTOs/           # Data Transfer Objects
      Jobs/           # background jobs
      Models/         # domain Eloquent models
      Providers/      # module Service Providers
      Repositories/   # data access (if used)
      Services/       # business logic
    Users/
      ...
```

## Module isolation rules

1. **No cross-DB dependencies:** module `Invoices` must not directly SQL-join `Users` tables; modules communicate via interfaces or public Services (Contracts).
2. **Use DTOs:** passing data between modules (or controller→service) — use DTOs, no raw arrays.
3. **Thin controllers** — only: validate Request; build DTO; call Service/Action method; return Response/Resource. All business logic lives in Services or Actions.

## Events

For loose coupling between modules use Event-Driven approach. On user registration, module `Users` fires `UserRegistered`; modules `Notifications` and `Wallets` listen and run their logic independently.

## Autoloading

Register module providers/routes/migrations via a package (e.g. `nWidart/laravel-modules`) or manually via a custom `ModuleServiceProvider` scanning module folders. PSR-4 in `composer.json` may be needed (inside `app/` Laravel resolves everything under `App\` by default):

```json
"autoload": {
    "psr-4": {
        "App\\": "app/",
        "Modules\\": "app/Modules/" 
    }
}
```

## Implementation with `nwidart/laravel-modules`

When the manual `ModuleServiceProvider` no longer pays off (need generators, separate frontend build, per-module migration/config isolation) — switch to `nwidart/laravel-modules`. Modules live in root `Modules/` (not `app/Modules/`), each self-sufficient with own `composer.json`, providers, routes, tests, Vite config.

### Module structure

`module:make` generates a Laravel-app-like structure inside the module:

```text
Modules/Billing/
  app/
    Filament/Resources/   # module Filament resources
    Http/Controllers/
    Models/Invoice/       # group by entity (Invoice.php, InvoiceItem.php)
    Providers/            # BillingServiceProvider, RouteServiceProvider, EventServiceProvider
    Repositories/
  config/config.php       # merged into config('billing.*')
  database/{factories,migrations,seeders}/
  resources/{css,js,views}/
  routes/{web.php,api.php}
  tests/{Feature,Unit}/
  module.json             # manifest: name, alias, priority, providers
  composer.json           # module PSR-4 (merged into root by merge-plugin)
  vite.config.js          # separate module frontend build (build-billing)
```

### Generation commands

- `php artisan module:make Billing` — create module (full skeleton above: `app/`, `database/`, `routes/`, `tests/`, `config/`, `module.json`, `composer.json`, `vite.config.js`).
- `php artisan list module` — list all `module:*` commands.
- Files **inside** module: module name is last arg:
  - `php artisan module:make-model Invoice Billing`
  - `php artisan module:make-controller InvoiceController Billing`
  - `php artisan module:make-migration create_invoices_table Billing`
  - `php artisan module:make-provider`, `module:make-seeder`, `module:make-test` — same.
- Group entities into subfolders — path in the name: `php artisan module:make-model Invoice/Invoice Billing` → `Billing\Models\Invoice\Invoice`.

### Namespace mapping convention (no `Modules\` prefix)

nwidart defaults to `Modules\Billing\Models\Invoice`. Project convention: **namespace starts with module name** — `Billing\Models\Invoice` instead of `Modules\Billing\Models\Invoice`. Achieved by:

1. **PSR-4 in module `composer.json`** maps `Billing\` to `app/` (also `Billing\Database\Factories\`, `...\Seeders\`, `...\Migrations\`, `Billing\Tests\`).
2. **`'namespace' => ''` in `config/modules.php`** — empty prefix so package resolves module classes as `Billing\...`, not `Modules\Billing\...` (affects generators, Blade components, etc.).
3. Provider in `module.json` without `Modules\`: `"providers": ["Billing\\Providers\\BillingServiceProvider"]`.

Root `composer.json` merges all module `composer.json` via `wikimedia/composer-merge-plugin` (`"merge-plugin": { "include": ["Modules/*/composer.json"] }`), so no per-module `dump-autoload` — after creating a module one `composer dump-autoload` at root suffices.

### Module frontend build (Vite)

Each module has own `vite.config.js` with separate `buildDirectory` (`build-billing`) so module assets don't overwrite each other; entries — module `resources/css/app.css` and `resources/js/app.js`. Config exports `paths` for the shared entry aggregator (`vite-module-loader.js`).

### Registering and discovering module Filament resources

nwidart does not generate Filament resources into a module. Workflow:

1. Generate resource via Filament command: `php artisan make:filament-resource Invoice --generate` (lands in `app/Filament/Resources`).
2. Move files to `Modules/Billing/app/Filament/Resources`.
3. Fix namespace in **all** moved files (Resource, Pages, RelationManagers): `App\Filament\Resources\...` → `Billing\Filament\Resources\...`.

Discovery in `app/Providers/Filament/AdminPanelProvider.php`: each module adds its `discoverResources` with module base path and namespace:

```php
->discoverResources(
    in: base_path('Modules/Billing/app/Filament/Resources'),
    for: 'Billing\\Filament\\Resources',   // namespace WITHOUT Modules\ prefix
)
```

Detailed tree, `module.json`, `composer.json`/`config/modules.php` snippets, `vite.config.js`, discovery block — in `snippets/nwidart-module.md`.

## Quality checklist

- [ ] Code organized by business domain, not technical type
- [ ] No cross-DB joins between modules; communication via Contracts/Services or Events
- [ ] Data between modules/layers passed via DTO, not raw arrays
- [ ] Controllers thin, business logic in Services/Actions
- [ ] (nwidart) Module files created via `php artisan module:make*`, not by hand
- [ ] (nwidart) Module namespace — `Module\...` without `Modules\` prefix (PSR-4 + `config/modules.php` `namespace => ''`)
- [ ] (nwidart) Each module Filament resource registered via `discoverResources` with path `base_path('Modules/{Name}/app/Filament/Resources')` and module namespace
- [ ] (nwidart) Module with frontend has own `vite.config.js` with unique `buildDirectory`

## Links

- snippets/nwidart-module.md — module tree, module.json, composer namespace, module:make* commands, vite.config.js, Filament discovery
- https://github.com/nWidart/laravel-modules
- Starting structure of a new project: skill `php/laravel-structure`
- Module Filament resources and discovery: `php/filament`
- Module frontend build (Vite): `frontend/vite-module-loader`, `frontend/vite-multi-build`
- Layers inside a module: `php/repositories`, `php/dependency-injection`, DTO between modules — `php/laravel-data`

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 4c8bd23555827ad680eed154fe36be0bf90e09b70c0b3d52a45789dd3f63b06b -->
