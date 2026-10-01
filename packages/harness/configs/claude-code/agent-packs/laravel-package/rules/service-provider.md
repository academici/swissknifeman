---
paths:
  - "**/*ServiceProvider.php"
---

ServiceProvider package (depth - skill `php-packages:laravel-package-service-provider`).
Risk-layer: **all consumers at once** — provider is executed for everyone for every request.

- `register()` — only cheap bindings (`bind`/`singleton`/`scoped`) and `mergeConfigFrom`.
  NO I/O (DB/HTTP/file system): container is not ready yet, the price is paid for
  every request of every consumer.
- `boot()` — `publishes`, `loadRoutesFrom`/`loadMigrationsFrom`/`loadViewsFrom`/
  `loadTranslationsFrom`, `Gate::`/`Event::listen`.
- Config - `mergeConfigFrom` (not a complete replacement): partially published config
  consumer should not lose package defaults.
- Publish-tag do not rename existing resources - it will break
  `vendor:publish --tag=...` from consumers.
