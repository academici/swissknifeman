---
name: spatie-settings
bucket: laravel-extras
version: 0.2.0
description: "spatie/laravel-settings: typed settings classes (extends Settings, group()), migrations add/migrate/rename, cache, runtime vs config/ choice, Filament SettingsPage binding, infra-config (websocket/Reverb) admin→frontend via DTO. Activate creating/editing a settings class/property/migration, an edit screen, or moving infra setting to runtime override."
risk: write
persona: oss-dev
tags: ["php", "laravel", "spatie", "settings", "filament", "configuration"]
requires: []
produces_for: []
outputs: []
snippets: ["ExampleSettings.php", "create_example_settings.php", "filament-settings-page.php"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: spatie/laravel-settings

Settings = typed PHP class; properties map to DB rows (repo `database`) or Redis; runtime-editable in admin (no release), vs `config/*.php` (static from env, fixed at deploy).

## When to activate
- New settings class (`extends Settings`) or add/delete/rename a property.
- Settings migration (`SettingsMigration` with `migrator->add/rename/delete`).
- Deciding storage: `config/` vs settings class.
- Settings edit screen (Filament `SettingsPage` or custom form).
- Cache, class registration, or `MissingSettings` error.

Portable: neutral domains (`Order`, `Article`, `Notification`), namespace `App\Settings\...`.

**Laravel Boost**: with Boost, `spatie/laravel-settings` guidelines come from the package; this skill is self-sufficient without Boost. Version rules for Filament/Livewire `SettingsPage` (step 7) → defer to Boost; here only form↔settings-class binding. Package: https://github.com/laravel/boost (skills: `vendor/laravel/boost/.ai/`).

## Algorithm

### 1. Setting or config?
| Sign | Where |
|:---|:---|
| Admin changes via UI, no deploy | **settings class** |
| Fixed by env/deploy (`APP_*`, creds, drivers) | `config/*.php` + `env()` |
| Need typing, defaults in DB, history via migrations | **settings class** |
| Secret that must not land in DB dump | `config/` + env / vault |

Rule: read `config()` **only in config files and providers**; in app code resolve the settings class for runtime values, not `config()`.

### 2. Create settings class
- Dir `app/Settings/` (domain subdirs allowed: `app/Settings/Order/`), namespace `App\Settings\...`.
- `final class XxxSettings extends Spatie\LaravelSettings\Settings`.
- **Public typed properties** — each property = one DB row. Names in `snake_case` (match migration keys). Nullable (`?string`) for optional.
- Required `public static function group(): string` — group prefix (e.g. `order`); full row key = `group.property`.
- No constructor, no property default values — defaults live in the migration (step 4).
- Register class in `config/settings.php → 'settings' => [...]` (unless `auto_discover_settings` on).

See `snippets/ExampleSettings.php`.

### 3. Custom casts
- Scalar types (`int`, `bool`, `string`, `array`, `float`, `?T`) work out of the box.
- For `DateTime`, enum, DTO — global casts in `config/settings.php → global_casts`, or `public static function casts(): array` in class. Package already knows `DateTimeInterface`, `DateTimeZone`, `Spatie\LaravelData\Data`.

### 4. Settings migration (defaults + schema evolution)
- File in `database/settings/` (path from `migrations_paths`), command `php artisan make:settings-migration`.
- Anonymous class `extends Spatie\LaravelSettings\Migrations\SettingsMigration`, method `up()`.
- **Every class property must have a matching `add()`** — else read throws `Spatie\LaravelSettings\Exceptions\MissingSettings`.
- Key = `group.property` (exactly `group()` + property name). Value = default.
- Schema evolution in a separate migration:
  - `add('group.prop', $default)` — new property;
  - `rename('group.old', 'group.new')` — rename (in sync with class property edit);
  - `delete('group.prop')` — delete;
  - `addEncrypted` / `encrypt` / `decrypt` — for sensitive values.
- `migrate()` idempotent at the "migration ran once" level (tracked like normal migrations). Run via `php artisan migrate` (settings migrations run together) or the package's own command.

See `snippets/create_example_settings.php`.

### 5. Runtime read/write
```php
// Resolve via container (singleton within request)
$settings = app(\App\Settings\Order\OrderSettings::class); // or resolve(...), or ctor DI
$limit = $settings->max_items_per_order;

// Write
$settings->max_items_per_order = 50;
$settings->save();
```
- Prefer **constructor injection** (typed dependency) — testable and explicit.
- Safe to mutate properties of a resolved object **without `save()`** for a one-off override within a request (e.g. override default with a current-entity value) — DB untouched.

### 6. Cache
- Enable via `SETTINGS_CACHE_ENABLED=true` (+ optional store/prefix/ttl; on Laravel 12.9+ `SETTINGS_CACHE_MEMO`).
- With cache on, after editing DB rows directly (bypassing `save()`) — clear settings cache. After `make:settings-migration`/`migrate` the package invalidates cache.
- In tests keep cache off.

### 7. Form binding (Filament SettingsPage)
- Page class `extends Filament\Pages\SettingsPage`, `protected static string $settings = XxxSettings::class;`.
- `form(Schema $schema)` describes fields; **each field's `name` = class property name** (rows save to group automatically).
- Validation and conditional `required(fn (Get $get) => ...)` — on form fields; package reads/writes settings on save.
- Requires plugin `filament/spatie-laravel-settings-plugin`.

See `snippets/filament-settings-page.php`. For non-Filament forms: on save manually assign properties and call `->save()`.

### 7a. Runtime infra-config from admin → frontend
Infra parameter normally fixed at deploy (`config/*.php` + env) must be overridable **at runtime from admin** without release. E.g. websocket-client params (Reverb/Pusher: `host`, `port`, `scheme`, `app_key`, `path`) the frontend needs to connect Echo.

Pattern (on top of steps 2–7):
1. **Settings class for infra group** — `final class WebsocketClientSettings extends Settings`, `group(): 'broadcast'`, public typed properties (`bool $enabled`, `string $host`, `int $port`, …). Flag `enabled` = toggle "use these settings vs env/Vite".
2. **Filament page** (`SettingsPage`, step 7) lets admin edit values; fields with validation (`regex` on host/path, port range) and `required(fn (Get $get) => $get('enabled'))` so a disabled flag doesn't require filling.
3. **Expose to frontend via DTO, not raw settings.** At runtime resolve the settings class, build a **public** DTO (e.g. `WebsocketClientData`), pass to frontend (Inertia `share`/middleware, or `<script>` config). Frontend: when `enabled` use DTO values, else build-time env/Vite. Echo client side — `frontend-backend/laravel-echo-client`.
4. **Secret boundary.** Frontend gets **only public** values (host/port/scheme/app_key for client). Private creds (app_secret etc.) — NOT in this settings class/DTO: stay in env/`config/`, in DB if needed via `addEncrypted` (step 4), never sent to frontend.
5. **DTO → TS typing** (if frontend TypeScript) — DTO under `#[TypeScript]`, see `frontend-backend/backend-type-sync`.

Justified when: admin must change value without deploy and frontend needs it at runtime. Not when: pure build-time param or secret — keep in `config/`/env (step 1).

### 8. Verify
1. Class registered (in `config/settings.php` or auto-discover) — else won't resolve.
2. Every public property has `add()` in migration; groups match.
3. `php artisan migrate` runs settings migration without errors; reading settings doesn't throw `MissingSettings`.
4. App-code runtime values come from settings class, not `config()`.

## Anti-patterns
- Property in class without `add()` in migration → `MissingSettings` on first read.
- Defaults set by property initialization in class instead of migration (default won't reach DB).
- Storing secrets (tokens, passwords) in plain properties instead of `addEncrypted`/env.
- Reading settings via `config()` wrapper or facade where a typed class exists — loses typing and DI.
- Desync `group()` ↔ migration key prefix ↔ form field `name`.
- Editing values directly in DB with cache on without clearing it.

## Quality checklist
- [ ] Class `final`, `extends Settings`, only public typed properties, has `group()`
- [ ] Every property has `add()` in settings migration; keys = `group.property`
- [ ] Defaults in migration, not property initialization
- [ ] Class registered in `config/settings.php` (or auto-discover on)
- [ ] Setting-vs-config choice deliberate (runtime/UI → setting; env/deploy → config)
- [ ] Non-typed types covered by `global_casts`/`casts()`
- [ ] Secrets via `addEncrypted`/env, not plain property
- [ ] Schema evolution in a separate migration (`add`/`rename`/`delete`), in sync with class
- [ ] Form: field `name` == property names; validation on fields
- [ ] Cache: `SETTINGS_CACHE_ENABLED` behavior handled, off in tests
- [ ] Runtime infra-config: public DTO to frontend not raw settings; secrets don't leak; `enabled` flag present (setting vs env)

## Links
- https://github.com/spatie/laravel-settings
- https://filamentphp.com/plugins/filament-spatie-settings
- snippets/ExampleSettings.php — settings class
- snippets/create_example_settings.php — settings migration (defaults + evolution)
- snippets/filament-settings-page.php — Filament form binding
- Related skills: `laravel-filament/filament` (SettingsPage and plugin), `laravel-data-layer/laravel-data` (Data as settings property type and public frontend DTO), `laravel-architecture/enum-attributes` (enum casts for settings), `php/database` (settings migrations alongside normal ones), `frontend-backend/laravel-echo-client` (consuming websocket settings on client), `frontend-backend/backend-type-sync` (settings DTO → TS type)

<!-- ru-source-sha256: db1051023d0475f3bb6340a46675a1908da216a2ae31efc3365b1eafcb9aa0d5 -->
