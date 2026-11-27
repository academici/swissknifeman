---
paths: ["app/Models/**/*.php"]
---

# Eloquent Models

- Define relationship return types and keep relationship names consistent with their domain meaning.
- Eager-load relationships at the query boundary when callers traverse them across collections.
- Declare and test casts for dates, enums, and value objects. Use explicit mass-assignment allowlists.
- Keep persistence behavior out of accessors that run during serialization. Test scopes and model invariants against their actual database behavior.
