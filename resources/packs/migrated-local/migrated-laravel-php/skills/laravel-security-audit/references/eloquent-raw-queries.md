# Sharp Edge: raw-requests Eloquent / Query Builder

## Search patterns

```bash
grep -rnE "DB::raw|whereRaw|selectRaw|orderByRaw|havingRaw|groupByRaw|DB::(statement|select|insert|update|delete)\(" app/
```

## What is considered a vulnerability

User input (request, route-parameter, title, model field,
filled in by user) hits raw-string via concatenation or
interpolation:

```php
// VULNERABLE: Input in query string
->whereRaw("name like '%{$request->q}%'")
->orderByRaw($request->input('sort'))   // sorting from a request - injection

// SAFE: bindings
->whereRaw('name like ?', ["%{$request->q}%"])
```

## Special cases

- `orderByRaw`/`groupByRaw` **do not support bindings for column names** —
  column name from input validate allow-list'ohm:
  `in_array($sort, ['name', 'created_at'], true)`.
- `DB::statement` in migrations with a constant string is not a godsend.
- Indirect input: a value from the database that once came from the user
  (second-order injection) — also counts.

## Severity

- Enter directly into raw without binding - **critical**.
- Input via allow-list/cast to int — ok, mark as verified.
- Raw with a constant string is not a godsend (but note for variant analysis:
  similar places may be with input).
