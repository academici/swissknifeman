"""Permissions the planning module registers (planning §3)."""

from __future__ import annotations

__all__ = ["PERMISSIONS"]

PERMISSIONS = frozenset(
    ["plan.read", "plan.create", "plan.edit", "plan.approve", "plan.publish", "plan.archive"]
)
