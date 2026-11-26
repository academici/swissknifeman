# Source: anonymized production project
# Modular monolith on nwidart/laravel-modules: module tree, module.json,
# composer.json (namespace without prefix Modules\), registration Filament discovery.

## Module tree `Modules/Billing`

```text
Modules/
  Billing/
    app/
      Filament/
        Resources/        # Filament-module resources (namespace Billing\Filament\Resources)
      Http/
        Controllers/
        Middleware/
      Models/
        Invoice/          # grouping by entity: Invoice.php, InvoiceItem.php
      Observers/
      Providers/
        BillingServiceProvider.php   # main module provider
        RouteServiceProvider.php
        EventServiceProvider.php
      Repositories/
      Enums/
    config/
      config.php          # merges into config('billing.*')
    database/
      factories/
      migrations/
      seeders/
    resources/
      css/app.css
      js/app.js
      views/
    routes/
      web.php
      api.php
    tests/
      Feature/
      Unit/
    composer.json         # PSR-4 module, merged merge-plugin'ohm to the root
    module.json           # manifest: name, providers, priority
    vite.config.js         # separate module front assembly (build-billing)
    package.json
```

## `module.json`

Module manifest for nwidart: name, alias, download priority and list of providers.
Provider is registered WITHOUT prefix `Modules\` — in accordance with the convention below.

```json
{
    "name": "Billing",
    "alias": "billing",
    "description": "",
    "keywords": [],
    "priority": 0,
    "providers": [
        "Billing\\Providers\\BillingServiceProvider"
    ],
    "files": []
}
```

## `composer.json` module - convention namespace without `Modules\`

Default nwidart lays out classes under `Modules\Billing\...`.
Project convention: namespace begins with the module NAME (`Billing\Models\Invoice`),
and not with `Modules\Billing\Models\Invoice`. This is set PSR-4 autoload module plus
`'namespace' => ''` in `config/modules.php` (see below).

```json
{
    "name": "vendor/billing",
    "description": "",
    "autoload": {
        "psr-4": {
            "Billing\\": "app/",
            "Billing\\Database\\Factories\\": "database/factories/",
            "Billing\\Database\\Seeders\\": "database/seeders/",
            "Billing\\Database\\Migrations\\": "database/migrations/"
        }
    },
    "autoload-dev": {
        "psr-4": {
            "Billing\\Tests\\": "tests/"
        }
    }
}
```

Root `composer.json` merges all modular `composer.json` via merge-plugin,
therefore separate `composer dump-autoload` is not needed for the module:

```json
{
    "require": {
        "nwidart/laravel-modules": "*"
    },
    "extra": {
        "laravel": { "dont-discover": [] },
        "merge-plugin": {
            "include": ["Modules/*/composer.json"]
        }
    },
    "config": {
        "allow-plugins": {
            "wikimedia/composer-merge-plugin": true
        }
    }
}
```

B `config/modules.php` empty `namespace` includes convention `Billing\...` instead `Modules\Billing\...`:

```php
// config/modules.php
return [
    'namespace' => '',   // module classes resolve as Billing\..., and not Modules\Billing\...
    // ...
];
```

## Generating module files - `php artisan module:make*`

```bash
# Create the module itself (skeleton: app/, database/, routes/, tests/, module.json, composer.json, vite.config.js)
php artisan module:make Billing

# List of all available module:* commands
php artisan list module

# Files INSIDE a module - the last argument is the name of the module
php artisan module:make-model Invoice Billing
php artisan module:make-controller InvoiceController Billing
php artisan module:make-migration create_invoices_table Billing
php artisan module:make-provider InvoiceServiceProvider Billing
php artisan module:make-seeder InvoiceSeeder Billing
php artisan module:make-test InvoiceTest Billing

# Grouping entities into subfolders - the path is right in the name:
php artisan module:make-model Invoice/Invoice Billing      # Billing\Models\Invoice\Invoice
php artisan module:make-model Invoice/InvoiceItem Billing
```

## Filament-resources inside the module

nwidart does not generate Filament-resources directly into the module. Duty Cycle:

```bash
# 1. Generate resource using standard command Filament (will hit app/Filament/Resources)
php artisan make:filament-resource Invoice --generate

# 2. Transfer files from app/Filament/Resources in Modules/Billing/app/Filament/Resources
# 3. Correct namespace in ALL transferred files (Resource, Pages, RelationManagers):
#    App\Filament\Resources\...  ->  Billing\Filament\Resources\...
```

Registration (discovery) module resources in the panel - in `app/Providers/Filament/AdminPanelProvider.php`.
Each module adds its own `discoverResources` with the base path and namespace of the module:

```php
// app/Providers/Filament/AdminPanelProvider.php
public function panel(Panel $panel): Panel
{
    return $panel
        ->id('admin')
        ->path('admin')
        // kernel resources
        ->discoverResources(
            in: app_path('Filament/Resources'),
            for: 'App\\Filament\\Resources',
        )
        // module resources Billing — please note: namespace WITHOUT prefix Modules\
        ->discoverResources(
            in: base_path('Modules/Billing/app/Filament/Resources'),
            for: 'Billing\\Filament\\Resources',
        )
        ->discoverPages(in: app_path('Filament/Pages'), for: 'App\\Filament\\Pages')
        ->discoverWidgets(in: app_path('Filament/Widgets'), for: 'App\\Filament\\Widgets');
}
```

## `vite.config.js` module - isolated front assembly

Each module has its own `buildDirectory` (for example `build-billing`), so that module assets
did not grind each other. Inputs - `resources/css/app.css` and `resources/js/app.js` module.

```js
// Modules/Billing/vite.config.js
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, '../../');

export default defineConfig({
    root: projectRoot,
    build: { manifest: true, emptyOutDir: true },
    plugins: [
        laravel({
            publicDirectory: 'public',
            buildDirectory: 'build-billing',
            input: [
                'Modules/Billing/resources/css/app.css',
                'Modules/Billing/resources/js/app.js',
            ],
            refresh: true,
        }),
    ],
});

// Export paths for general vite-module-loader.js (module input aggregator)
export const paths = [
    'Modules/Billing/resources/css/app.css',
    'Modules/Billing/resources/js/app.js',
];
```
