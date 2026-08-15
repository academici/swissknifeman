"""Typed render boundary preserving literal interpolation values."""
from .catalog import Catalog, Overlay, resolve_catalog


def render_message(english: Catalog, overlay: Overlay | None, key: str, *, immutable_tokens=()):
    return resolve_catalog(english, overlay, key, immutable_tokens=tuple(immutable_tokens))
