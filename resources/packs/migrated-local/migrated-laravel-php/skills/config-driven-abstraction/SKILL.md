---
name: config-driven-abstraction
description: "Config-driven cache-safe Registry+Builder for multi-panel/multi-tenant Laravel: immutable registry key→instance, fluent builder w/ feature-flags, config name-maps not closures, per-variant class not runtime $table. Activate designing multi-panel/multi-tenant resolution, pluggable drivers. Triggers: registry, builder pattern, config:cache, driver resolution."
---

# Config-Driven Abstraction (Registry + Builder)

Cache-safe pluggable abstractions for multi-panel / multi-tenant / driver resolution.

## Rules

1. **Immutable Registry: key → instance.** Resolve a panel/driver/strategy by key from an immutable registry built at boot. No mutation after boot (predictable, safe).
2. **`config:cache` safety — no closures in config.** Config arrays must be serializable: map names to class strings (`'driver' => DatabaseDriver::class`), NOT closures. A closure in config breaks `php artisan config:cache` silently.
3. **Fluent builder; feature-flags as methods.** `Panel::make()->withReactions()->withThreads()` — flags are methods, not a giant array, so the surface is typed and discoverable.
4. **Shared default + opt-in per-item.** Default to a shared schema/table; let an item opt in to its own (per-panel table) explicitly — don't force per-tenant infra on everyone.
5. **Per-variant = a concrete class, not a runtime `$table`.** A model that swaps `$table` at runtime is a footgun (caching, relations, IDE). Define/generate a concrete subclass per variant instead.
6. **`final` blocks extend-and-swap.** If consumers must subclass for variants, don't mark the model `final` (a sibling-class test workaround is a design smell).

## Red flags (real incidents)

- Closures in config → `config:cache` fails.
- One shared model calling `setTable()` at runtime per panel.
- `final` on a model the variant design needs to extend.

## Related

- `laravel-architecture:modular-architecture`, `php:production-readiness-checklist`.
