---
paths:
  - "**/api/**"
  - "**/routers/**"
  - "**/views/**"
---

Endpoints ({{WEB_FRAMEWORK}}):

- Thin handler: validation at the boundary (pydantic-model / DRF-serializer), logic in service,
  access to data in repository/ORM.
- Versioning API; explicit response codes and error patterns.
- Without business logic in view; without direct ORM in handler without layer.
- SQL parameterized (no f-string SQL); secrets from the environment.
