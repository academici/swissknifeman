# Острая грань: небезопасная сериализация и дыры авторизации

## Сериализация

```bash
grep -rnE 'unserialize\(' app/ --include='*.php'
grep -rnE 'decrypt\(|Crypt::decrypt' app/ | grep -vE 'tests/'
grep -rn 'signed' routes/
```

- `unserialize()` на данных извне — **critical** (PHP object injection,
  гаджет-цепочки через зависимости). Замена: `json_decode`, или
  `unserialize($data, ['allowed_classes' => false])`.
- Утечка `APP_KEY` = подделка любых encrypted/signed значений — проверить,
  что `.env` в deny-листах и ключ не в репозитории.
- Signed routes (`URL::signedRoute`): маршрут, меняющий состояние, должен
  проверять `$request->hasValidSignature()` (middleware `signed`).

## Авторизация (privilege escalation / IDOR)

```bash
# контроллеры, достающие модель по id из запроса без Policy
grep -rnE 'findOrFail\(\$request|find\(\$request|findOrFail\(\$id' app/Http/Controllers/
grep -rln 'authorize' app/Http/Controllers/   # где authorize ЕСТЬ — инвертировать
grep -rn 'Gate::|->can\(|->cannot\(' app/
```

Чек-лист:

- **IDOR:** модель достаётся по id из запроса — есть ли проверка
  принадлежности (`$ticket->user_id === $request->user()->id`, Policy,
  scoped binding `Route::scopeBindings()`)? Нет — **high/critical**.
- **FormRequest::authorize()** возвращает `true` без проверки — каждый
  такой реквест на state-changing экшене проверить отдельно.
- **Роли из ввода:** параметр `role`/`is_admin`/`permissions` в запросе,
  достигающий create/update (см. mass-assignment), — **critical**.
- **Route model binding** без Policy: `php artisan route:list` + сверка
  с `AuthServiceProvider::$policies` — у каких моделей нет Policy вообще.
- Админ-маршруты: middleware-группа admin покрывает ВСЕ admin-маршруты
  (искать маршруты, добавленные мимо группы).

## Severity

- `unserialize` на вводе, роли из ввода — **critical**.
- IDOR на чужих данных — **high** (critical для платёжных/персональных).
- `authorize() { return true; }` на write-экшене — **high** до верификации.
