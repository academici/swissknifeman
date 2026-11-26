"""Declarative contract; behavior belongs to the owning implementation leaf."""

__all__ = ["SUBSCRIBERS"]

SUBSCRIBERS: tuple[object, ...] = ()
