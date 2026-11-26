"""Packaged migration files: ``NNNN_<module>_<slug>.sql`` and ``runner_bootstrap.sql`` (adapters §1.10).

This directory is a package so that the wheel carries every file in it and ``importlib.resources`` finds
them the same way from a checkout and from an installed distribution. The runner discovers the numbered files;
an applied file is never edited (its checksum would no longer match): a schema change is a new file at the end
of the chain.
"""

__all__: list[str] = []
