# Artifact storage internals

Concrete adapters retain their names and import paths in `postgres/artifacts/repositories.py`.
These implementation partitions add no ports, commands or adapter registrations.

| File | Contract | Owner |
|---|---|---|
| `src/skm/adapters/postgres/artifacts/mapping.py` | Row codecs, cursor keysets and savepoint error translation | P06.03.b |
| `src/skm/adapters/postgres/artifacts/blobs.py` | Blob, staged blob and content-reader repositories with local parameterized SQL | P06.03.b |
| `src/skm/adapters/postgres/artifacts/files.py` | File and immutable file-version repositories with local parameterized SQL | P06.03.b |
| `src/skm/adapters/postgres/artifacts/grants.py` | Scope-bound access-grant repository with local parameterized SQL | P06.03.b |
