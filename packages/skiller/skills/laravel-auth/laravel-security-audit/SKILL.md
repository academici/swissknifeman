---
name: laravel-security-audit
bucket: laravel-auth
version: 0.1.0
description: "Audit Laravel code for sharp edges: raw Eloquent queries, mass assignment, Blade XSS, CSRF bypass, open redirect, unsafe serialization, authz holes."
risk: draft
persona: oss-dev
tags: [php, laravel, security]
requires: [static-analysis]
produces_for: [security-design]
outputs: []
snippets: ["security-audit-scheduled.yml"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Laravel Security Audit

Method: "sharp edges" — find bugs AND innocuous-looking patterns that invite vulnerabilities on the next edit.

## Activate when
- Before release/deploy or preparing security review.
- Reviewing a PR touching auth, user input, DB queries, files.
- Scheduled background audit (see snippet).

## Algorithm
1. **Grep pass.** Run patterns from table below over `app/`, `routes/`, `resources/views/`, `config/`.
2. **Manual verify.** Each hit — check context: does user input actually reach the dangerous sink? Match ≠ vuln; unverified report = noise.
3. **Report with severity.** Each finding: file:line, chain from input to vulnerable call, severity (critical / high / medium / low), recommendation. Output feeds `security-design`.

## Sharp-edges table

| Edge | Grep | Detail |
|---|---|---|
| Raw Eloquent queries | `DB::raw`, `whereRaw`, `selectRaw`, `orderByRaw`, `DB::statement` | [references/eloquent-raw-queries.md](references/eloquent-raw-queries.md) |
| Mass assignment | `$guarded = []`, `request()->all()` near `create(`/`update(`, `forceFill` | [references/mass-assignment.md](references/mass-assignment.md) |
| Blade XSS | `{!!`, `@js(`, `v-html`, `Js::from` | [references/blade-xss.md](references/blade-xss.md) |
| CSRF & redirect | `VerifyCsrfToken` `$except`, `redirect($request`, `redirect()->to($` | [references/csrf-and-redirects.md](references/csrf-and-redirects.md) |
| Serialization & authz | `unserialize(`, missing Policy/`authorize()`, IDOR via id from request | [references/serialization-authz.md](references/serialization-authz.md) |

## Out of scope
- No dependency check — that's `dependency-audit` (composer audit etc.).
- No replacement for static analysis — `static-analysis` (PHPStan/larastan) must already be installed; audit relies on its signals.
- No auto-fix — audit produces a report; fixes are separate tasks prioritized by severity.

## Background mode
`snippets/security-audit-scheduled.yml` — GitHub Actions template: audit on cron + manual run, result = GitHub Issue categorized by severity. See docs/workflows/background-agents.

## Links
- `php/static-analysis` (requires) — PHPStan/Larastan, whose signals the audit relies on.
- `oss-dev/dependency-audit` — dependency audit (composer audit, SBOM) — adjacent, distinct task.
- `architect/security-design` (produces_for) — where report goes: auth strategy, OWASP, STRIDE.
- `php/laravel-permissions`, `php/azguard`, `php/attribute-authorization` — authz holes (IDOR, missing Policy) checked against these layers.
- `php/database` — mass assignment and raw queries in migration/model context.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: f1f94975df40d58c8d69ced5052ae7fddf96cb072f384711608ff1f20f72d971 -->
