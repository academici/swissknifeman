"""Permissions of the workspace module: a subset of the catalog (workspace §3)."""

__all__ = ["PERMISSIONS"]

PERMISSIONS = frozenset(
    [
        "workspace.create",
        "workspace.read",
        "workspace.manage",
        "project.create",
        "project.read",
        "project.manage",
        "repo.manage",
        "host.manage",
        "checkout.bind",
        "checkout.read_locator",
        "worker.register",
    ]
)
