---
name: backend-type-sync
bucket: frontend-backend
version: 0.1.1
description: "Use for Laravel enum/DTO to TypeScript generation; route typing belongs to Wayfinder."
risk: write
persona: oss-dev
tags: [typescript, laravel, spatie, types, enum, dto, frontend, type-sync, ci]
requires: [wayfinder]
produces_for: []
outputs: []
snippets: [typescript-transformer.php, annotated-enum.php, generated-type-usage.vue]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Backend → Frontend type sync

Single source of truth for types: PHP classes (enum, DTO, Spatie-Data) auto-generate TypeScript declarations imported as `App.Enums.*` / `App.Data.*`. Package: `spatie/laravel-typescript-transformer`.

## Activate when
- Frontend needs an enum/DTO that already exists in PHP — annotate + generate, don't hand-copy types.
- Frontend missing a new field/case; FE types drift from BE.
- Setting up type-sync from scratch (install, config, npm script, git-hook, CI).

## Boundaries
- **Types (this skill)** — data structure: DTO fields, enum values. Artifact: `resources/js/types/generated.d.ts`, namespace `App.*`.
- **Routes (`frontend-wayfinder/wayfinder`)** — typed URLs/controller-actions. Artifact: `resources/js/wayfinder/`. Separate generation (`php artisan wayfinder:generate`), separate package (`laravel/wayfinder`). Don't get DTO types from wayfinder or vice versa.
- **PHP enum internals (`laravel-architecture/enum-attributes`)** — backed values, `#[Label]`/`#[Priority]`, methods. This skill only adds `#[TypeScript]` on a ready enum.
- Laravel Boost = upstream versioned basics of Spatie-Data/transformer. Package: https://github.com/laravel/boost.

## Algorithm

1. **Verify install.** `composer.json` must have `spatie/laravel-typescript-transformer` (for DTO/Spatie-Data also `spatie/laravel-data`). If missing:
   ```
   composer require spatie/laravel-typescript-transformer
   php artisan vendor:publish --provider="Spatie\LaravelTypeScriptTransformer\TypeScriptTransformerServiceProvider"
   ```
   Creates `config/typescript-transformer.php`.

2. **Configure `config/typescript-transformer.php`** (see `snippets/typescript-transformer.php`):
   - `auto_discover_types` — scan paths (default `app_path()`); **PHP namespace sets TS namespace** (`App\Enums\Order\OrderStatus` → `App.Enums.Order.OrderStatus`).
   - `collectors` — `DefaultCollector` catches `#[TypeScript]` classes.
   - `transformers` — enable as needed: `EnumTransformer` (PHP-enum), `SpatieEnumTransformer`, `DtoTransformer` (Spatie-Data), `SpatieStateTransformer` (if using States).
   - `default_type_replacements` — map `Carbon`/`DateTimeImmutable` → `string` (JSON strings on the wire).
   - `output_file` — single `resource_path('types/generated.d.ts')`.
   - `transform_to_native_enums` — `false` (union type) default; `true` if frontend needs runtime values as `enum`.
   - `transform_null_to_optional` — `false` (`null` in union) or `true` (optional `?`); pick one, keep uniform.

3. **Annotate PHP class** with `#[TypeScript]` (see `snippets/annotated-enum.php`):
   - **enum** (backed) → `App.Enums.*`.
   - **Spatie-Data DTO** (`extends Spatie\LaravelData\Data`) → `App.Data.*` (or `App.Dto.*` — depends on class namespace, not package).
   - Type collection arrays via PHPDoc `@param Foo[] $items` / `@var Foo[]` — else `array` → `any[]`.
   - Nested DTO/enum fields must **also** be annotated, else `any`.

4. **Generate:**
   ```
   php artisan typescript:transform
   ```
   Add to `composer.json` (`"typescript:transform"`) and mirror as npm script in `package.json` (`"types": "php artisan typescript:transform"`). Check `generated.d.ts` diff after.

5. **Use on frontend** via global `App.*` namespace (see `snippets/generated-type-usage.vue`):
   - enum values: `App.Enums.Order.OrderStatus` as type; literals are plain strings (`'paid'`), TS checks membership.
   - DTO as props/reactive data: `defineProps<{ item: App.Data.Order.OrderListItem }>()`.
   - `generated.d.ts` is `declare namespace App` — global, **no import**; ensure file is in `tsconfig.json` `include`.

6. **Guard against drift:**
   - **git pre-commit hook** (Husky or native) — regenerate, fail if `generated.d.ts` changed but uncommitted (see Git-hook).
   - **CI** — step `php artisan typescript:transform` + `git diff --exit-code resources/js/types/generated.d.ts`: PR fails if not regenerated.

7. **Commit the generated file.** `generated.d.ts` is **committed** (not in `.gitignore`): needed for `tsc`/IDE/CI without PHP; diff shows BE↔FE contract change. wayfinder vendor artifacts (`resources/js/wayfinder/`) — commit too, but that's `frontend-wayfinder/wayfinder`'s zone.

## Annotation targets

| `#[TypeScript]` on | Base class | TS namespace | Yields |
|:---|:---|:---|:---|
| PHP backed-enum | `enum X: string` | `App.Enums.*` | string/number union or native enum |
| Spatie-Data DTO | `extends Spatie\LaravelData\Data` | `App.Data.*` / `App.Dto.*` | object type with fields |
| Spatie-Enum (if used) | `Spatie\Enum\Enum` | `App.Enums.*` | via `SpatieEnumTransformer` |

TS namespace = PHP class namespace under `auto_discover_types`. Want `App.Data.*` → put DTO in `App\Data\...`; `App.Dto.*` → classes in `App\Dto\...`. Package doesn't affect this.

## Git-hook

Husky `.husky/pre-commit`:
```sh
php artisan typescript:transform
if ! git diff --quiet -- resources/js/types/generated.d.ts; then
  git add resources/js/types/generated.d.ts
  echo "types/generated.d.ts regenerated and added to commit"
fi
```
CI variant (strict, no auto-`add`, check only):
```sh
php artisan typescript:transform
git diff --exit-code -- resources/js/types/generated.d.ts \
  || { echo "generated.d.ts deprecated: run 'npm run types' and commit"; exit 1; }
```

## Quality checklist
- [ ] `spatie/laravel-typescript-transformer` in `composer.json`, `config/typescript-transformer.php` published
- [ ] Needed `transformers` enabled (Enum/SpatieEnum/Dto/State — per actual use)
- [ ] `default_type_replacements` maps `Carbon`/datetime → `string`
- [ ] `output_file` single `resources/js/types/generated.d.ts`, file in `tsconfig.json` `include`
- [ ] PHP class has `#[TypeScript]`; nested DTO/enum fields too
- [ ] Collections typed via PHPDoc (`@var Foo[]`), no accidental `any[]`
- [ ] `typescript:transform` in both `composer.json` and `package.json` (npm script)
- [ ] Frontend uses `App.Enums.*` / `App.Data.*`, DTO types **not** hand-duplicated
- [ ] git pre-commit hook OR CI step catches stale `generated.d.ts` (`git diff --exit-code`)
- [ ] `generated.d.ts` committed (not in `.gitignore`)
- [ ] Zones not confused: routes — `frontend-wayfinder/wayfinder`, enum internals — `laravel-architecture/enum-attributes`

## References
- snippets/typescript-transformer.php — transformer config (collectors, transformers, replacements, output_file)
- snippets/annotated-enum.php — enum and Spatie-Data DTO with `#[TypeScript]`, collection typing
- snippets/generated-type-usage.vue — using `App.Enums.*` / `App.Data.*` in Vue/TS
- https://spatie.be/docs/typescript-transformer
- https://spatie.be/docs/laravel-data
- Related skills: `frontend-wayfinder/wayfinder` (routes), `laravel-architecture/enum-attributes` (enum internals), `laravel-data-layer/laravel-data` (Spatie-Data DTO internals, annotated with `#[TypeScript]`), `frontend-backend/inertia-vue` (types/ layer), `frontend-vue/vitest` (exclude `generated.d.ts` from coverage)
