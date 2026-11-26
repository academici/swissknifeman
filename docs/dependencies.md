# Dependencies

The [engineering standards](architecture/engineering-standards.md) and
[ADR 0012](adr/0012-dependency-policy.md) define the allowed set.
[pyproject.toml](../pyproject.toml) declares dependencies; [uv.lock](../uv.lock)
pins the resolved environment. Owners below are maintenance responsibilities by
component, not claims that a named person has accepted an assignment.

| Library | Layer | Purpose | Alternative | Update owner |
|---|---|---|---|---|
| `psycopg[binary,pool]` 3.x | PostgreSQL adapters | Explicit SQL and synchronous pool | ORM/Alembic requires a new ADR | PostgreSQL adapter maintainer |
| `jsonschema` | `platform/schema` | Draft 2020-12 validation | Own validator rejected: incomplete vocabulary | Schema maintainer |
| `referencing` | `platform/schema` | Local URN registry and reference resolution | Network retrieval is not the product registry | Schema maintainer |
| `starlette` | API entrypoint | ASGI routing and SSE | Handwritten ASGI adds maintenance | API maintainer |
| `uvicorn` | API entrypoint | ASGI server | Another ASGI server needs justification | API maintainer |
| `httpx` | HTTP client adapter | Embedded/HTTP client parity | urllib needs more transport code | Client adapter maintainer |
| `keyring` (optional `secrets` extra) | Secret adapters | System secret storage | Existing env/file secret resolvers | Secret adapter maintainer |
| `pytest` (dev) | Tests | Test collection and fixtures | unittest lacks project fixture conventions | Test tooling maintainer |
| `hypothesis` (dev) | Tests | Property tests for IDs, graphs and merges | Example cases alone miss generated edges | Test tooling maintainer |
| `ruff` (dev) | Tooling | Formatting and lint | Multiple formatter/linter tools | Tooling maintainer |
| `pyright` (dev) | Tooling | Static type checks | Another checker requires aligned configuration | Tooling maintainer |
| `coverage[toml]` (dev) | Test tooling | Coverage measurement from project config | Manual coverage inspection | Test tooling maintainer |
| `uv` (environment tool) | Development | Frozen environment and lock management | pip plus separate locking | Tooling maintainer |
| `hatchling` (build) | Packaging | PEP 517 wheel/sdist backend | Another backend requires packaging verification | Packaging maintainer |

The standard library is preferred for small development tools, including link
checking. ORM, pydantic/attrs/msgspec, DI frameworks, async frameworks in the core,
brokers and telemetry SDKs require an ADR. Frontend dependencies arrive with the
web implementation; this table does not assert that web tooling already exists.

The runtime observation projection uses local constants from the OpenTelemetry GenAI v0.1.0
conventions and keeps the existing dependency set. See the GenAI addendum in
[ADR 0012](adr/0012-dependency-policy.md).
