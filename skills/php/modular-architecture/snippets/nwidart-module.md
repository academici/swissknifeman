# Source: anonymized production project
# Модульный монолит на nwidart/laravel-modules: дерево модуля, module.json,
# composer.json (namespace без префикса Modules\), регистрация Filament discovery.

## Дерево модуля `Modules/Billing`

```text
Modules/
  Billing/
    app/
      Filament/
        Resources/        # Filament-ресурсы модуля (namespace Billing\Filament\Resources)
      Http/
        Controllers/
        Middleware/
      Models/
        Invoice/          # группировка по сущности: Invoice.php, InvoiceItem.php
      Observers/
      Providers/
        BillingServiceProvider.php   # главный провайдер модуля
        RouteServiceProvider.php
        EventServiceProvider.php
      Repositories/
      Enums/
    config/
      config.php          # сливается в config('billing.*')
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
    composer.json         # PSR-4 модуля, сливается merge-plugin'ом в корень
    module.json           # манифест: имя, провайдеры, приоритет
    vite.config.js         # отдельная сборка фронта модуля (build-billing)
    package.json
```

## `module.json`

Манифест модуля для nwidart: имя, alias, приоритет загрузки и список провайдеров.
Провайдер регистрируется БЕЗ префикса `Modules\` — в соответствии с конвенцией ниже.

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

## `composer.json` модуля — конвенция namespace без `Modules\`

По умолчанию nwidart раскладывает классы под `Modules\Billing\...`.
Конвенция проекта: неймспейс начинается с ИМЕНИ модуля (`Billing\Models\Invoice`),
а не с `Modules\Billing\Models\Invoice`. Это задаётся PSR-4 автозагрузкой модуля плюс
`'namespace' => ''` в `config/modules.php` (см. ниже).

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

Корневой `composer.json` сливает все модульные `composer.json` через merge-plugin,
поэтому отдельный `composer dump-autoload` для модуля не нужен:

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

В `config/modules.php` пустой `namespace` включает конвенцию `Billing\...` вместо `Modules\Billing\...`:

```php
// config/modules.php
return [
    'namespace' => '',   // классы модулей резолвятся как Billing\..., а не Modules\Billing\...
    // ...
];
```

## Генерация файлов модуля — `php artisan module:make*`

```bash
# Создать сам модуль (скелет: app/, database/, routes/, tests/, module.json, composer.json, vite.config.js)
php artisan module:make Billing

# Список всех доступных module:* команд
php artisan list module

# Файлы ВНУТРИ модуля — последний аргумент это имя модуля
php artisan module:make-model Invoice Billing
php artisan module:make-controller InvoiceController Billing
php artisan module:make-migration create_invoices_table Billing
php artisan module:make-provider InvoiceServiceProvider Billing
php artisan module:make-seeder InvoiceSeeder Billing
php artisan module:make-test InvoiceTest Billing

# Группировка сущностей в подпапки — путь прямо в имени:
php artisan module:make-model Invoice/Invoice Billing      # Billing\Models\Invoice\Invoice
php artisan module:make-model Invoice/InvoiceItem Billing
```

## Filament-ресурсы внутри модуля

nwidart не генерирует Filament-ресурсы напрямую в модуль. Рабочий цикл:

```bash
# 1. Сгенерировать ресурс штатной командой Filament (попадёт в app/Filament/Resources)
php artisan make:filament-resource Invoice --generate

# 2. Перенести файлы из app/Filament/Resources в Modules/Billing/app/Filament/Resources
# 3. Поправить namespace во ВСЕХ перенесённых файлах (Resource, Pages, RelationManagers):
#    App\Filament\Resources\...  ->  Billing\Filament\Resources\...
```

Регистрация (discovery) ресурсов модуля в панели — в `app/Providers/Filament/AdminPanelProvider.php`.
Каждый модуль добавляет свой `discoverResources` с базовым путём и неймспейсом модуля:

```php
// app/Providers/Filament/AdminPanelProvider.php
public function panel(Panel $panel): Panel
{
    return $panel
        ->id('admin')
        ->path('admin')
        // ресурсы ядра
        ->discoverResources(
            in: app_path('Filament/Resources'),
            for: 'App\\Filament\\Resources',
        )
        // ресурсы модуля Billing — обрати внимание: namespace БЕЗ префикса Modules\
        ->discoverResources(
            in: base_path('Modules/Billing/app/Filament/Resources'),
            for: 'Billing\\Filament\\Resources',
        )
        ->discoverPages(in: app_path('Filament/Pages'), for: 'App\\Filament\\Pages')
        ->discoverWidgets(in: app_path('Filament/Widgets'), for: 'App\\Filament\\Widgets');
}
```

## `vite.config.js` модуля — изолированная сборка фронта

У каждого модуля свой `buildDirectory` (например `build-billing`), чтобы ассеты модулей
не перетирали друг друга. Входы — `resources/css/app.css` и `resources/js/app.js` модуля.

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

// Экспорт путей для общего vite-module-loader.js (агрегатора входов модулей)
export const paths = [
    'Modules/Billing/resources/css/app.css',
    'Modules/Billing/resources/js/app.js',
];
```
