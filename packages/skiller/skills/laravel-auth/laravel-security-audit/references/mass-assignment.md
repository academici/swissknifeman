# Sharp Edge: mass assignment

## Search patterns

```bash
grep -rnE '\$guarded\s*=\s*\[\s*\]' app/Models/
grep -rnE 'request\(\)->all\(\)|\$request->all\(\)' app/ | grep -E 'create\(|update\(|fill\('
grep -rnE 'forceFill\(' app/
```

## What is considered a vulnerability

```php
// VULNERABLE: empty $guarded + ->all() — user sets any field,
// including is_admin, role_id, user_id
class User extends Model { protected $guarded = []; }
User::create($request->all());

// SAFE: validated fields only
User::create($request->validated());
User::create($request->only(['name', 'email']));
```

## What to look for during verification

- `$guarded = []` by itself - **high**, if at least one entry point
  uses `->all()`/`->input()` without `->validated()`.
- `forceFill` bypasses and `$fillable`, and `$guarded` — input get there
  should never.
- FormRequest with `->validated()` is only safe if `rules()`
  lists all keys: rule `'meta' => 'array'` skips
  arbitrary nested keys.
- Nested-data in `sync()`/`createMany()` — same rules.

## Severity

- Privileged fields (role, is_admin, *_id ownership) are reachable - **critical**.
- `->all()` in create/update without validated — **high**.
- `$guarded = []` without current dangerous entry points - **medium** (edge
  will work on the next edit).
