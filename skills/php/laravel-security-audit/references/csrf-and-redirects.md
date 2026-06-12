# Острая грань: CSRF-обходы и open redirect

## Паттерны поиска

```bash
grep -rnE '\$except' app/Http/Middleware/VerifyCsrfToken.php bootstrap/app.php
grep -rnE 'validateCsrfTokens\(' bootstrap/app.php
grep -rnE 'redirect\(\s*\$request|redirect\(\)->to\(\s*\$|redirect\(\)->away\(' app/
grep -rnE "->input\(['\"](redirect|return|next|url|back)" app/
```

## CSRF

```php
// ПОДОЗРИТЕЛЬНО: исключения из CSRF-защиты
protected $except = ['payment/*', 'api-internal/*'];
// Laravel 11+: bootstrap/app.php
$middleware->validateCsrfTokens(except: ['webhooks/*']);
```

Верификация каждого исключения:
- Вебхук с проверкой подписи (Stripe-Signature и т.п.) — ok.
- «Исключили, потому что не работало» — **high**: state-changing endpoint
  без CSRF и без подписи.
- Маска шире необходимого (`payment/*` вместо `payment/webhook`) — **medium**.

## Open redirect

```php
// УЯЗВИМО: цель редиректа из ввода — фишинг через доверенный домен
return redirect($request->input('redirect'));
return redirect()->to($request->query('return_url'));

// БЕЗОПАСНО
return redirect()->intended('/dashboard');          // встроенный механизм
return redirect()->route($allowedRoutes[$key]);      // allow-list
```

Верификация: достижим ли параметр снаружи и валидируется ли против
allow-list/относительного пути. `url()->previous()` с фоллбеком — ok.

## Severity

- CSRF-исключение на state-changing endpoint без подписи — **high**.
- Open redirect на странице логина/OAuth-флоу — **high** (фишинг),
  в остальных местах — **medium**.
