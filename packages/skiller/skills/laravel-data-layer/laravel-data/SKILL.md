---
name: laravel-data
bucket: laravel-data-layer
version: 0.1.0
description: "DTOs with spatie/laravel-data: typed Data classes, nested DataCollection, casts/transformers, computed properties, mapName/mapInputName, from(request) with validation, API/Inertia output, #[TypeScript] annotation. Activate: need a type-safe DTO instead of array/array-access, parse incoming request into an object, single data shape between back and front, replace ad-hoc JsonResource with Data."
risk: write
persona: oss-dev
tags: [php, laravel, spatie, laravel-data, dto, data-transfer-object, casts, validation, inertia, api]
requires: []
produces_for: [backend-type-sync]
outputs: []
snippets: [OrderData.php, from-request-usage.php]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: spatie/laravel-data DTO

Typed data layer replacing assoc arrays, `$request->input()` and ad-hoc `JsonResource` with one object: parses incoming request (with validation), describes data shape via typed props, serializes to API/Inertia, exports to TypeScript.

**Activate when:**
- need a type-safe autocompleted object instead of passing array `['title' => ..., 'items' => [...]]` between layers;
- turn incoming request into an object with validation (`OrderData::from($request)` instead of manual `$request->validate()` + array build);
- one structure needed on back AND front (Data → `#[TypeScript]` → `App.Data.*`, see `frontend-backend/backend-type-sync`);
- old `JsonResource` grew manual relation/enum/date render helpers → switch to Data (relations & casts declarative);
- nested collection of child DTOs (order → items, document → lines) with per-element typing.

**Laravel Boost** ships versioned `spatie/laravel-data` fundamentals as upstream skill (`vendor/laravel/boost/.ai/`); package API → Boost, these conventions → this skill. Package: https://github.com/laravel/boost.

## Algorithm

1. **Base Data class**: extend `Spatie\LaravelData\Data`, declare props via **promoted constructor properties** — typed, `?` for nullable. Prop type = contract; no bare `array` where structure is known.

   ```php
   class OrderData extends Data
   {
       public function __construct(
           public string $reference,
           public OrderStatus $status,       // enum cast automatically
           public ?CustomerData $customer,   // nested Data
       ) {}
   }
   ```

2. **Nested DTOs & collections**: single child → just a typed prop (`?CustomerData $customer`). List of children → `DataCollection` with element type via `#[DataCollectionOf(ItemData::class)]` (or PHPDoc `@var DataCollection<ItemData>`):

   ```php
   /** @var DataCollection<ItemData> */
   #[DataCollectionOf(ItemData::class)]
   public DataCollection $items,
   ```
   Element type mandatory — else package can't expand array, loses typing/TS-export.

3. **Casts (input)**: for types not cast out-of-the-box, attach `#[WithCast(...)]` on prop. Date → `DateTimeInterfaceCast`, enum → `EnumCast` (usually auto by type), custom rule → own class implementing `Cast`. Cast applies on `from()` (input), transformer on `toArray()` (output).

4. **Transformers (output)**: for non-standard serialization attach `#[WithTransformer(...)]` (date format, money, truncation). Global rules (e.g. format of all `DateTimeInterface`) in `config/data.php`; targeted → attribute on prop.

5. **Computed props**: value derived from other fields and appearing in output → declare `public` prop marked `#[Computed]`, init in constructor body or via getter. `#[Computed]` prop is **not** expected in input, but present in `toArray()` and TS type (`total`, `is_overdue`, `display_name`).

6. **Name mapping**: prop↔key name divergence via attributes, not renaming:
   - `#[MapInputName('snake_case')]` — key name in **input** (`from()`);
   - `#[MapOutputName(...)]` — name in **output** (`toArray()`);
   - `#[MapName(...)]` — both sides.
   Class-level `#[MapName(SnakeCaseMapper::class)]` (or `MapInputName`) sets strategy for all props — typically «camelCase in PHP ↔ snake_case in JSON».

7. **Create from request with validation**: `OrderData::from($request)` — package builds validation rules from prop types & attributes (`#[Required]`, `#[Max]`, `#[Rule]`, etc.), validates, throws `ValidationException` on error. Don't duplicate `$request->validate()` — rules live on Data props. `from()` accepts anything: `Request`, array, model, another Data — package normalizes source.

8. **API / Inertia output**:
   - return Data from controller → Laravel serializes via `toArray()`/`toResponse()`;
   - Inertia: `Inertia::render('Order/Show', ['order' => OrderData::from($order)])` — front gets exactly the Data shape;
   - partial/lazy fields → `Lazy::create(...)` for heavy nested collections (loaded only on request).

9. **Type sync with front**: mark Data class `#[TypeScript]` (from `spatie/typescript-transformer`) → lands in `generated.d.ts` as `App.Data.OrderData`. Rest (`artisan typescript:transform`, front import) → skill `frontend-backend/backend-type-sync`; here just declare export-fit Data (explicit types, typed collections, no raw `array`).

10. **Don't make Data a God-object**: Data describes data shape & input/output transforms. Business logic (state change, DB writes, side effects) → services/actions taking & returning Data. Controller: `from(request)` → pass to service → return Data.

## Casts vs transformers (direction)

| What | Attribute | Fires | Example |
|:---|:---|:---|:---|
| Cast | `#[WithCast(...)]` | input, on `from()` | string `"2026-01-31"` → `CarbonImmutable` |
| Transformer | `#[WithTransformer(...)]` | output, on `toArray()` | `CarbonImmutable` → `"2026-01-31T00:00:00Z"` |
| Cast+transformer | `#[WithCastAndTransformer(...)]` | both | single money/enum rule |
| Computed | `#[Computed]` | output only (derived) | `total`, `is_overdue` |

Global (all props of a type) → `config/data.php`; targeted → attribute on prop.

## Which snippet

| Situation | File |
|:---|:---|
| Declare Data class: nested `DataCollection`, cast, transformer, `#[Computed]`, name mapping, `#[TypeScript]` | `snippets/OrderData.php` |
| Create DTO from request with validation, output to API/Inertia; `toArray()` | `snippets/from-request-usage.php` |

## Quality checklist

- [ ] Props typed (promoted constructor properties), nullable marked `?`; no raw `array` where structure known
- [ ] Nested list → `DataCollection` with mandatory element type (`#[DataCollectionOf(...)]` or `@var DataCollection<...>`)
- [ ] Non-standard input cast via `#[WithCast(...)]`, non-standard output via `#[WithTransformer(...)]`; direction not swapped
- [ ] Computed fields → `#[Computed]`, not logic duplicated in controller/resource
- [ ] Name divergence solved via `MapName`/`MapInputName`/`MapOutputName` (or class mapper), not prop renaming
- [ ] Input created via `from()`, validation on Data props, no duplicate `$request->validate()`
- [ ] No business logic leaked into Data: state changed by services/actions, Data describes only shape & transforms
- [ ] If type needed on front → class marked `#[TypeScript]` (then see `frontend-backend/backend-type-sync`)
- [ ] Domains/namespaces neutral (`App\Data\...`), no project-specific business terms

## Links

- https://spatie.be/docs/laravel-data
- https://spatie.be/docs/laravel-data/advanced-usage/typescript
- Related skills: `frontend-backend/backend-type-sync` (Data → TS types), `laravel-architecture/enum-attributes` (enums in Data props), `php/named-arguments` (create Data via explicit named args), `php/php-patterns` (bare DTO/VO without package — when dependency unwanted), `php/laravel-structure` (where Dto/View/Form/Command live in project tree)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 0cdbb2b6d1ec9196b38a52eaaaea002e0b7c08a9ba43da114d707f65be08186f -->
