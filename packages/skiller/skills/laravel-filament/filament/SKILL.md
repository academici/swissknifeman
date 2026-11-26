---
name: filament
bucket: laravel-filament
version: 1.0.1
filament_version: "5.x"
description: "Use for Filament v5 panels, resources, schemas, tables, actions, auth, and Artisan scaffolding."
risk: write
persona: oss-dev
tags: [php, laravel, filament, ui, admin-panel, crud, livewire]
requires: [laravel, laravel-structure]
produces_for: []
outputs: ["app/Filament/**"]
snippets:
  - resource-stub.php
  - relation-manager-stub.php
  - forms-tables-reference.md
  - filament-development.md
adapters: [claude, cursor, fable]
sha256: ""
---

# Filament v5 — Skill

> **Versions:** current - Filament **5.x** (came out 2026-01: this v4 + Livewire 4, new API no; single Schema API entered into **v4**). Code in style v3 (`form(Form $form)`, `Filament\Tables\Actions\*`) — deprecated, do not generate.
> **Requirements:** Laravel ≥ 11.28, PHP ≥ 8.2, Tailwind CSS ≥ 4.1, Livewire 4.
> **Key Rule:** all scaffold — only via `php artisan make:filament-*`. Manual generation of files is prohibited: it is expensive in terms of tokens and differs from standard stubs.
> **SSOT:** in projects with Laravel Boost version guidelines are supplied by himself Filament (`vendor/.../boost/guidelines/`) — they are priority; here is the structure, CLI and design patterns. Tracked via upstream.json.

## Context

CRUD-resources, admin-panels, forms/tables/widgets on Filament v5. UI is described in PHP fluent-components (`make()` + chainable-methods); most configuration methods accept `Closure` for dynamics.

## Algorithm

1. Check version: `composer show filament/filament` (pending `^5` or `^4`; v3 — migrate, do not append).
2. Generate files artisan-with the command from the reference book below (always `--no-interaction`, options - via `--help`).
3. Fill in the generated classes: form diagram - in `Schemas/<Model>Form.php`, table - in `Tables/<Model>sTable.php` (v5-generator removes them from the resource).
4. Create Policy (`make:policy <Model>Policy --model=<Model>`) — Filament applies it automatically.
5. RelationManagers register in `getRelations()`; widgets - in Panel Provider or `getHeaderWidgets()`.
6. Run through the quality checklist.

## File structure (v5-generator)

```
app/Filament/Resources/Customers/
├── CustomerResource.php          # navigation, getPages(), getRelations()
├── Pages/                        # ListCustomers, CreateCustomer, EditCustomer, ViewCustomer
├── Schemas/
│   └── CustomerForm.php          # form schema (+ CustomerInfolist.php for view)
├── Tables/
│   └── CustomersTable.php        # columns, filters, actions
└── RelationManagers/
```

Modular architecture (DDD): `modules/Blog/Filament/...` + `discoverResources()` in PanelServiceProvider with module path.

## Correct namespaces (source of frequent errors)

| What | Namespace |
|---|---|
| Form fields (`TextInput`, `Select`, `Repeater`…) | `Filament\Forms\Components\` |
| Infolist-entries (`TextEntry`, `IconEntry`…) | `Filament\Infolists\Components\` |
| Layout (`Grid`, `Section`, `Fieldset`, `Tabs`, `Wizard`…) | `Filament\Schemas\Components\` |
| Scheme Utilities (`Get`, `Set`) | `Filament\Schemas\Components\Utilities\` |
| Table columns (`TextColumn`, `IconColumn`…) | `Filament\Tables\Columns\` |
| Filters (`SelectFilter`, `Filter`…) | `Filament\Tables\Filters\` |
| **All** actions (`EditAction`, `DeleteAction`, `BulkActionGroup`…) | `Filament\Actions\` — never `Filament\Tables\Actions\` or `Filament\Forms\Actions\` |
| Icons | enum `Filament\Support\Icons\Heroicon` (for example `Heroicon::PencilSquare`) |

Resource signatures:

```php
use Filament\Schemas\Schema;

public static function form(Schema $schema): Schema      // NOT form(Form $form)
public static function infolist(Schema $schema): Schema
public static function table(Table $table): Table
```

Types of overridden properties (union-types are required):

```php
protected static string | BackedEnum | null $navigationIcon;   // not ?string
protected static string | UnitEnum | null $navigationGroup;    // not ?string
protected string $view;   // on Page/Widget — NOT static
```

## CLI-reference make:filament-*

```bash
# Panel installation
composer require filament/filament
php artisan filament:install --panels
php artisan make:filament-user

# Resources
php artisan make:filament-resource Customer                 # basic
php artisan make:filament-resource Customer --generate      # form/table from the database schema
php artisan make:filament-resource Customer --simple        # one screen, modals
php artisan make:filament-resource Customer --soft-deletes
php artisan make:filament-resource Customer --view          # + view-page
php artisan make:filament-resource Customer --model --migration --factory
php artisan make:filament-resource Customer --model-namespace=Modules\\Blog\\Models

# Relation Managers
php artisan make:filament-relation-manager CustomerResource orders number
php artisan make:filament-relation-manager CustomerResource orders number --soft-deletes
php artisan make:filament-relation-manager CustomerResource roles name --attach   # BelongsToMany

# Pages / Widgets
php artisan make:filament-page Settings
php artisan make:filament-widget StatsOverview --stats-overview
php artisan make:filament-widget RevenueChart --chart
php artisan make:filament-widget LatestOrders --table
php artisan make:filament-widget OrdersChart --resource=OrderResource --chart

# Export / Import
php artisan make:filament-exporter Customer
php artisan make:filament-importer Customer

# Production
php artisan filament:cache-components   # and filament:clear-cache to reset
```

Full list and current flags: `php artisan list make | grep filament` — flags change between minors, don't rely on memory.

## Form reactivity

- Reading adjacent field: `->visible(fn (Get $get): bool => $get('type') === 'business')` on `->live()`-field.
- Entry in the adjacent field: `->afterStateUpdated(fn (Set $set, ?string $state) => $set('slug', Str::slug($state ?? '')))`.
- For text inputs - `->live(onBlur: true)`, so as not to jerk the server for every input.
- BelongsTo: `Select::make('author_id')->relationship('author', 'name')` (`BelongsToSelect` does not exist).
- Inline HasMany: `Repeater::make('items')->relationship()->schema([...])` — y Repeater `->schema()`, not `->fields()`.

Field reference/columns/filters with examples: snippets/forms-tables-reference.md.

## Authorization (Laravel Policies)

| Policy-method | Controls |
|---|---|
| `viewAny()` | visibility in navigation + list-page |
| `create()` / `update()` / `view()` / `delete()` | corresponding buttons and pages |
| `deleteAny()` | mass deletion |
| `forceDelete()` / `restore()` | for soft deletes |

## Multi-tenancy

```php
// PanelServiceProvider
->tenant(Team::class, ownershipRelationship: 'team')
```

Resource requests are automatically copied by tenant via `getEloquentQuery()`.

## Common errors (from the official guidelines)

- Files (`FileUpload`) default **private** — for public access explicitly `->visibility('public')`.
- `Grid`/`Section`/`Fieldset`/`Repeater` **not** occupy the entire width by default - set `->columnSpan()`/`->columnSpanFull()`.
- `->dehydrated(false)` erases the value from state before saving - only for UI-fields.
- Tests edit-pages: `->call('save')` (not `'create'`), without `assertRedirect()` — edit does not redirect.
- Panel tests: always `$this->actingAs(...)` before `livewire(...)`.

## Quality checklist

- [ ] All files were created via `php artisan make:filament-*`
- [ ] No imports `Filament\Tables\Actions\*`, `Filament\Forms\Actions\*`; `form()` accepts `Schema`
- [ ] `$navigationGroup` set; `$recordTitleAttribute` is set for global search
- [ ] Policy created, `viewAny()` covers the required roles
- [ ] RelationManagers in `getRelations()`; for BelongsToMany — flag `--attach`
- [ ] Labels/headings in the project language
- [ ] Production: `php artisan filament:cache-components`

## Links

- snippets/resource-stub.php, snippets/relation-manager-stub.php
- snippets/forms-tables-reference.md — fields, columns, filters, actions, widgets
- snippets/filament-development.md — project expectations
- https://filamentphp.com/docs/5.x — official documentation (resources, schemas, tables, actions, tenancy)
- Boost-guidelines Filament: `packages/panels/resources/boost/guidelines/core.blade.php` in filamentphp/filament (see upstream.json)
