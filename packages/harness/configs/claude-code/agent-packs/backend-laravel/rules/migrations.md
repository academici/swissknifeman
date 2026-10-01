---
paths:
  - "**/database/migrations/**"
---

When working with migrations (depth - skill `php:database`). Risk-layer: **transactions**
(diagram/reversibility) — `down()` must be correct and reversible.

- Do not change already applied migrations - the structure is edited with a NEW migration.
- Table names via `#[Table]`-model attribute; `down()` is correct and reversible.
- Indexes for new selections; foreign keys with explicit `onDelete`.
- New fields reflected in `$fillable`/`casts` corresponding to the model.
