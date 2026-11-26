"""Permissions the execution module registers."""

from __future__ import annotations

PERMISSIONS = frozenset(
    [
        "run.read",
        "run.start",
        "run.control",
        "inbox.read",
        "inbox.answer",
        "check.verdict",
        "deviation.accept",
        "worker.claim",
        "step.note",
    ]
)
