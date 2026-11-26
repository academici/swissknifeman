"""In-memory implementations of the repository ports, used by tests and the embedded memory backend.

``uow.py`` holds the transactional backend; ``core/`` and each ``<module>/`` subpackage expose a
``REPOSITORIES`` table that ``bootstrap.adapters`` merges. Behaviour must match the PostgreSQL adapters:
the shared contract suites under ``tests/contracts`` run against both backends.
"""

__all__: list[str] = []
