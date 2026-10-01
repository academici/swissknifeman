"""Cluster test package `core.provider`.

The file is REQUIRED and cannot be deleted: `unittest discover -s core/tests` doesn't see
subdirectory without `__init__.py` and SILENTLY loses its tests - no errors, no warnings
(measured at Python 3.12.3: `Ran 1` instead `Ran 2`). Without it, the run remains
«green» on the reduced set."""
