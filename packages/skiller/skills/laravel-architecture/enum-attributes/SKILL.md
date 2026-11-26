---
name: enum-attributes
bucket: laravel-architecture
version: 0.2.0
description: "Use for enum metadata: replace label()/color()/description() match-ladders with PHP attributes #[Label]/#[Color]/#[Description] on cases + reflection resolver; or export enum as TS type via #[TypeScript]. Triggers: PHP enum, attributes on cases, getLabel()/getColor(), Filament HasLabel, laravel-typescript-transformer."
risk: write
persona: oss-dev
tags: ["php", "enum", "attributes", "reflection", "laravel", "patterns", "typescript"]
requires: []
produces_for: []
outputs: []
snippets: [attribute.php, concern-trait.php, enum-example.php, composer-path-repo.json, enum-typescript.php]
adapters: [claude, cursor, fable]
sha256: ""
---

Declarative enum-case metadata: PHP attributes `#[Label('...')]`, `#[Color('...')]`, `#[Description('...')]` on each case + Concern traits exposing `getLabel()`/`getColor()`/`getDescription()`; read via a single reflection resolver. Collection ops (all/values/labels) come from `emreyarligan/enum-concern` wired as a local path-repository.

## Activate when
- Enum has/needs `match($this) { ... }` for labels, colors, descriptions, priorities — move into per-case attributes.
- Need `getLabel()`/`getColor()`/`getDescription()` on enum, incl. Filament `HasLabel` compat.
- Writing a PHP attribute class (`#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]`) or a case-metadata reflection resolver.
- Domain metadata axes (`#[Stage(...)]`, `#[Dashboard(priority: N)]`) + static case selections via `ReflectionEnum::getCases()`.
- Export enum as a TS type (`#[TypeScript]`, `spatie/laravel-typescript-transformer`, `App.Enums.*` union in `.d.ts`).
- Wiring local pkg (`enum-concern`) as `repositories: [{type: path, ...}]` with `symlink`.

Do NOT activate: plain enums with no metadata (backing value is enough); pure frontend type consumption → `frontend-backend/backend-type-sync`.

## Algorithm
1. **Attribute**: `final readonly class Label` with `#[Attribute(Attribute::TARGET_CLASS_CONSTANT)]` + public constructor value. One attribute = one metadata axis (Label, Color, Description, Priority...).
2. **Resolver**: static `EnumCaseAttributeResolver::forCase(UnitEnum $case, string $attributeClass): ?object` — `ReflectionEnum` → `getCase($case->name)` → `getAttributes($attributeClass)` → `newInstance()`. Generic `@template TAttribute` annotation gives IDE/PHPStan typing.
3. **Concern trait**: `HasLabelAttribute::getLabel()` calls resolver, checks instanceof, returns value or default (empty string; gray color `#6c757d`).
4. **Enum**: `use HasLabelAttribute, HasColorAttribute, ...` + attributes on each case. May combine with `EnumConcern` (collections) and Filament `HasLabel`.
5. **Domain attributes**: same pattern adds own axes (`#[Stage(...)]`, `#[Dashboard(priority: N)]`) + static selections `allForStage()` via `ReflectionEnum::getCases()`.
6. **Local pkg**: wire enum-concern via `repositories: [{type: path, url: packages/enum-concern, options: {symlink: true}}]` + `composer require vendor/enum-concern`.

## Which snippet
| Situation | File |
|---|---|
| New attribute class (Label/Color/own axis) | `snippets/attribute.php` |
| Concern trait and/or reflection resolver | `snippets/concern-trait.php` |
| Enrich enum with attributes + static selections | `snippets/enum-example.php` |
| Wire local pkg via path-repository | `snippets/composer-path-repo.json` |
| Stack #[TypeScript] over #[Label]/#[Priority] + export type to front | `snippets/enum-typescript.php` |

## Gotchas
- `Attribute::TARGET_CLASS_CONSTANT` is exactly the target covering enum cases; wrong target → PHP throws on `newInstance()`.
- Resolver does reflection per call — for hot paths (table lists) cache in a static array `[$enumClass][$caseName][$attrClass]`.
- Defaults in traits are mandatory: not every case carries every attribute (see case with no Color).
- path-repository `symlink: true` — pkg edits show instantly, but in Docker the symlink must fall inside the build context.
- Pin the local pkg version in its composer.json (`"version": "1.0.0"`), else `^1.0` won't resolve.

## #[TypeScript] + type export to front
Two independent metadata layers coexist on one enum: domain custom attributes on cases, and the type-export attribute on the class. No conflict — different levels (constant vs class), different mechanisms.
1. **Attribute stack**: enum class gets `#[TypeScript]` (`Spatie\TypeScriptTransformer\Attributes\TypeScript`); each case gets domain `#[Label('...')]`, `#[Priority(...)]`. Enum may also `implements HasLabel` (Filament) and `use HasLabelAttribute, EnumConcern`.
2. **Backend resolve**: concern `HasLabelAttribute::getLabel()` via `EnumCaseAttributeResolver::forCase($this, Label::class)` reads per-case `#[Label]` (reflection: `ReflectionEnum->getCase($name)->getAttributes(Label::class)->newInstance()`). Backend side — `#[TypeScript]` unrelated.
3. **Export to front**: `spatie/laravel-typescript-transformer`. In `config/typescript-transformer.php`: `DefaultCollector` collects classes with `#[TypeScript]`, `EnumTransformer` turns enum into a union type, `auto_discover_types => [app_path()]`, `output_file => resource_path('types/generated.d.ts')`. Generate: `php artisan typescript:transform`.
4. **Output namespace**: PHP class path → TS namespace — `App\Enums\User\UserRole` → `App.Enums.User.UserRole`. With `transform_to_native_enums => false` (default) → union of string literals: `export type UserRole = 'admin' | 'secretary' | ...`.
5. **Export boundary**: `#[TypeScript]` exports ONLY case backing values. `#[Label]` labels do NOT reach `.d.ts` — for human-readable names in UI, expose a separate value→label map via DTO/resource (also under `#[TypeScript]`) or a custom writer.
6. **Frontend consumption** (importing `App.Enums.*`, type sync, splitting into modules vs one `generated.d.ts`) → `frontend-backend/backend-type-sync`. Here: backend type source only.

## Quality checklist
- [ ] `#[TypeScript]` on enum class, domain attributes on cases; non-conflicting
- [ ] config: `DefaultCollector` + `EnumTransformer`, `auto_discover_types` includes `app_path()`, `output_file` set
- [ ] after enum edit ran `php artisan typescript:transform`, `generated.d.ts` rebuilt
- [ ] clear that backing values go to front, not `#[Label]`; labels → separate map/DTO
- [ ] attributes `final readonly`, target `TARGET_CLASS_CONSTANT`
- [ ] one resolver per project, with generic annotations for static analysis
- [ ] each trait returns a meaningful default when attribute is absent
- [ ] enum has no match-duplicated labels — attributes only
- [ ] local pkg: path-repo + symlink + version in pkg composer.json

## Links
- https://www.php.net/manual/en/language.attributes.php
- https://github.com/emreyarligan/enum-concern
- https://getcomposer.org/doc/05-repositories.md#path
- https://github.com/spatie/laravel-typescript-transformer
- `snippets/enum-typescript.php` — enum with #[TypeScript]+#[Label] stack, Label attribute + concern, config fragment
- Related: `frontend-backend/backend-type-sync` (consuming App.Enums.* on front), `laravel-filament/filament`, `laravel-auth/attribute-authorization` (same reflection+attribute trick for enum action perms), `laravel-data-layer/laravel-data` (enum cases as DTO props), `php/laravel-structure` (placing Enums/Concerns/Attributes/Support in the tree)
