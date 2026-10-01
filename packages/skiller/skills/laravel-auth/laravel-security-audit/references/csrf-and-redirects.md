# Sharp Edge: CSRF-walks and open redirect

## Search patterns

```bash
grep -rnE '\$except' app/Http/Middleware/VerifyCsrfToken.php bootstrap/app.php
grep -rnE 'validateCsrfTokens\(' bootstrap/app.php
grep -rnE 'redirect\(\s*\$request|redirect\(\)->to\(\s*\$|redirect\(\)->away\(' app/
grep -rnE "->input\(['\"](redirect|return|next|url|back)" app/
```

## CSRF

```php
// SUSPICIOUS: exceptions to CSRF-protection
protected $except = ['payment/*', 'api-internal/*'];
// Laravel 11+: bootstrap/app.php
$middleware->validateCsrfTokens(except: ['webhooks/*']);
```

Verification of each exception:
- Webhook with signature verification (Stripe-Signature etc.) — ok.
- «Excluded because it didn't work» — **high**: state-changing endpoint
  without CSRF and without a signature.
- The mask is wider than necessary (`payment/*` instead `payment/webhook`) — **medium**.

## Open redirect

```php
// VULNERABLE: the purpose of the redirect from input is phishing through a trusted domain
return redirect($request->input('redirect'));
return redirect()->to($request->query('return_url'));

// SAFE
return redirect()->intended('/dashboard');          // built-in mechanism
return redirect()->route($allowedRoutes[$key]);      // allow-list
```

Verification: whether the parameter is reachable from the outside and validated against
allow-list/relative path. `url()->previous()` with fallback - ok.

## Severity

- CSRF-exception on state-changing endpoint without signature - **high**.
- Open redirect on the login page/OAuth-flow — **high** (phishing),
  in other places - **medium**.
