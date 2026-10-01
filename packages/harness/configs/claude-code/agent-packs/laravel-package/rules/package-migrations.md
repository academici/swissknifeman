---
paths:
  - "**/database/migrations/**"
---

Package migrations (depth - skill `php-packages:laravel-packages`). Risk-layer:
**consumer schema** — migration is performed in someone else's database, there is no response.

- Distribution - `loadMigrationsFrom` in `boot()` and/or publishable (`publishes` with tag):
  consumer selects whether to run from vendor or publish to yourself.
- Only anonymous-class migrations (`return new class extends Migration`) — named
  class collides with the consumer migration of the same name.
- `down()` is correct and reversible.
- Already applied (released) do not change the migration - the structure is being edited NEW
  migration: consumers have already completed the old version.
