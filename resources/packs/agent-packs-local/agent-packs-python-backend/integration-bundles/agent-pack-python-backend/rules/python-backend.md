# Python Backend Conventions

- Keep domain logic free of filesystem, network, clock, and environment side effects.
- Enforce explicit type annotations and immutable value objects across module boundaries.
- Perform external I/O outside database transactions and keep repository ports narrow.
- Cover edge cases and failure modes with fast, deterministic pytest suites.
