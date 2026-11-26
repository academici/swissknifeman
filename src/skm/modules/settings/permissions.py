"""Permissions declared by the settings module (settings §A.3, conventions §5)."""

__all__ = ["PERMISSIONS"]

PERMISSIONS = frozenset(["config.read", "config.write", "config.write_shared", "config.lock"])
