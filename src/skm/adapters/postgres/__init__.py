"""PostgreSQL implementations of the repository ports, the unit of work and the schema migrations.

``uow.py`` and ``pool.py`` own transactions and connections; ``core/`` and each ``<module>/`` subpackage
expose a ``REPOSITORIES`` table that ``bootstrap.adapters`` merges; ``migrations/`` owns the DDL chain and
the schema snapshot. Behaviour must match the memory adapters (shared suites under ``tests/contracts``).
"""

__all__: list[str] = []
