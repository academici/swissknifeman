---
name: eloquent-accessors
description: "Activate when writing/refactoring Eloquent accessors and mutators: when you see legacy getXxxAttribute()/setXxxAttribute() and should move to modern Attribute::make() (get/set), or when deciding where to place and how to type a computed model property. Triggers: getFooAttribute, Attribute::make, accessor, mutator, computed attribute, Illuminate\\Database\\Eloquent\\Casts\\Attribute"
---

## Context

Modern Laravel defines accessors/mutators with a single method returning
`Illuminate\Database\Eloquent\Casts\Attribute` via `Attribute::make(get:, set:)`,
instead of the legacy pair `getXxxAttribute()` / `setXxxAttribute()`. One method
holds both getter and setter, is better for static analysis and IDEs, and is the
Laravel-recommended path. This skill fixes the canon: syntax, naming, visibility,
typing, placement in the class, and legacy migration order.

### When to activate

- Writing a new computed model property (`full_name`, `full_address`, normalized email, etc.).
- Seeing legacy `getXxxAttribute()` / `setXxxAttribute()` and refactoring the model to `Attribute::make()`.
- Reviewing an Eloquent model: checking accessors use modern syntax, are typed, and are correctly placed.
- Needing a normalizing setter (canonicalize email/phone on write).

Do not activate: simple type casts (`casts()` array — not an accessor); enum case
metadata (use `laravel-architecture/enum-attributes`).

## Algorithm

1. **Import**: `use Illuminate\Database\Eloquent\Casts\Attribute;` at the top of the model.
2. **Method**: `protected function fooBar(): Attribute` — `protected`, camelCase **without** the `get` prefix, mandatory `Attribute` return type. Laravel maps `fooBar` → access via `$model->foo_bar` (snake_case).
3. **Body**: `return Attribute::make(get: ..., set: ...)`. Getter only — pass one `get:`; need a setter — add `set:`.
4. **Closure**: receives `($value, $attributes)` — the raw DB value (usually `null` for computed) and the array of all model attributes. Arrow function for simple cases; a regular closure with a return type for multi-line logic.
5. **Placement**: the accessor block goes **after relations, before scopes**. Keep one order: `$fillable`/`casts()` → relations → attributes → scopes.
6. **Legacy migration**: delete `getXxxAttribute()`/`setXxxAttribute()`, add `protected function xxx(): Attribute` with the same behavior, add the import, run tests for equivalence.

## Which snippet to open

| Situation | File |
|---|---|
| Need references: getter, getter+setter, multi-line accessor, legacy migration, class placement | `snippets/accessor.php` |

## Common pitfalls

- **`get`/`set` prefix in the method name** — `Attribute::make` must NOT have it (`fullName()`, not `getFullName()`); legacy methods, conversely, required `getFullNameAttribute`.
- **`public` instead of `protected`** — accessor methods are always `protected`.
- **Missing `Attribute` return type** — without it Laravel won't recognize the method as an accessor.
- **Raw `$value` on computed properties** — for a property without its own column `$value` is usually `null`; build the value from `$attributes` or `$this->...`.
- **Caching**: by default Laravel caches the `get` result for the model's lifetime; for accessors over objects (not primitives) use `->shouldCache()` / `->withoutObjectCaching()` as needed.
- **Mixing with `casts()`** — a simple column type cast belongs in `casts()`, not an accessor; accessors are for computation and normalization.

## Quality checklist

- [ ] `Illuminate\Database\Eloquent\Casts\Attribute` import present
- [ ] Method is `protected`, camelCase without `get`/`set` prefix, `Attribute` return type
- [ ] Getter and (if needed) setter in a single `Attribute::make()`
- [ ] Computed value built from `$attributes`/`$this`, not the "empty" `$value`
- [ ] Accessor block placed after relations and before scopes
- [ ] Legacy `getXxxAttribute()`/`setXxxAttribute()` removed on refactor, behavior covered by a test
- [ ] Simple type casts stay in `casts()`, not duplicated by an accessor

## References

- https://laravel.com/docs/eloquent-mutators#accessors-and-mutators
- https://laravel.com/docs/eloquent-mutators#attribute-casting
- `snippets/accessor.php` — references: getter, getter+setter, multi-line, legacy migration, placement
- Related skills: `laravel-architecture/enum-attributes` (enum case metadata via PHP attributes), `php/laravel` (model structure: casts/relations/scopes/accessors), `laravel-data-layer/laravel-data` (computed fields in DTOs), `php/code-style-spatie` (style: strict_types/typing/naming)
