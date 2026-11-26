"""Declarative state transition rows, as listed by state machines such as the autopilot's."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransitionDeclaration:
    rule_id: str | None
    source: str
    target: str
