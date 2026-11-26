# Sharp Edge: Insecure Serialization and Authorization Holes

## Serialization

```bash
grep -rnE 'unserialize\(' app/ --include='*.php'
grep -rnE 'decrypt\(|Crypt::decrypt' app/ | grep -vE 'tests/'
grep -rn 'signed' routes/
```

- `unserialize()` on external data - **critical** (PHP object injection,
  gadget chains via dependencies). Replacement: `json_decode`, or
  `unserialize($data, ['allowed_classes' => false])`.
- Leak `APP_KEY` = fake any encrypted/signed values - check if
  what `.env` in deny-sheets and the key is not in the repository.
- Signed routes (`URL::signedRoute`): route changing state must
  check `$request->hasValidSignature()` (middleware `signed`).

## Authorization (privilege escalation / IDOR)

```bash
# controllers reaching the model by id from request without Policy
grep -rnE 'findOrFail\(\$request|find\(\$request|findOrFail\(\$id' app/Http/Controllers/
grep -rln 'authorize' app/Http/Controllers/   # where authorize IS - invert
grep -rn 'Gate::|->can\(|->cannot\(' app/
```

Checklist:

- **IDOR:** model is obtained by id from the request - is there a check
  accessories (`$ticket->user_id === $request->user()->id`, Policy,
  scoped binding `Route::scopeBindings()`)? No - **high/critical**.
- **FormRequest::authorize()** returns `true` without checking - every
  such a request for Check state-changing action separately.
- **Roles from input:** parameter `role`/`is_admin`/`permissions` in the request,
  reaching create/update (see mass-assignment), — **critical**.
- **Route model binding** without Policy: `php artisan route:list` + reconciliation
  with `AuthServiceProvider::$policies` — which models do not have Policy in general.
- Admin routes: middleware-group admin covers EVERYTHING admin-routes
  (search for routes added past the group).

## Severity

- `unserialize` on the input, roles from the input - **critical**.
- IDOR on other people's data - **high** (critical for payment/personal).
- `authorize() { return true; }` on write-action - **high** before verification.
