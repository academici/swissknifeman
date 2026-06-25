# Острая грань: mass assignment

## Паттерны поиска

```bash
grep -rnE '\$guarded\s*=\s*\[\s*\]' app/Models/
grep -rnE 'request\(\)->all\(\)|\$request->all\(\)' app/ | grep -E 'create\(|update\(|fill\('
grep -rnE 'forceFill\(' app/
```

## Что считается уязвимостью

```php
// УЯЗВИМО: пустой $guarded + ->all() — пользователь задаёт любое поле,
// включая is_admin, role_id, user_id
class User extends Model { protected $guarded = []; }
User::create($request->all());

// БЕЗОПАСНО: только провалидированные поля
User::create($request->validated());
User::create($request->only(['name', 'email']));
```

## На что смотреть при верификации

- `$guarded = []` сам по себе — **high**, если хоть одна точка входа
  использует `->all()`/`->input()` без `->validated()`.
- `forceFill` обходит и `$fillable`, и `$guarded` — ввод туда попадать
  не должен никогда.
- FormRequest с `->validated()` безопасен только если в `rules()`
  перечислены все ключи: правило `'meta' => 'array'` пропускает
  произвольные вложенные ключи.
- Nested-данные в `sync()`/`createMany()` — те же правила.

## Severity

- Привилегированные поля (role, is_admin, *_id владения) достижимы — **critical**.
- `->all()` в create/update без validated — **high**.
- `$guarded = []` без текущих опасных точек входа — **medium** (грань
  сработает при следующей правке).
