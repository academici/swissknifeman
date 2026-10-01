---
paths:
  - "lib/**/widgets/**"
  - "lib/**/presentation/**"
---

Widgets Flutter:

- `const`-constructors where possible; without business logic in `build()`.
- Controllers/streams/timers close at `dispose()`.
- Lists are lazy (`ListView.builder`), do not build heavy trees entirely.
- Null-safety: without `!` without justification.
