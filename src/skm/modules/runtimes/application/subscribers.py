"""Registered event subscribers of the ``runtimes`` module (runtimes §10: none)."""

from __future__ import annotations

from skm.application_bus.registry import SubscriberSpec

__all__ = ["SUBSCRIBERS"]

SUBSCRIBERS: tuple[SubscriberSpec, ...] = ()
