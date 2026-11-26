"""Declarative contract; behavior belongs to the owning implementation leaf."""

__all__ = ["PERMISSIONS"]

PERMISSIONS = frozenset(["file.read", "file.write", "admin.storage"])
