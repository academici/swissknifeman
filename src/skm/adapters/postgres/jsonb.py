"""JSONB and timestamp helpers (adapters §1.2): JSON enters the database only through ``to_jsonb``."""

import json
from datetime import datetime

from psycopg.types.json import Jsonb

__all__ = ["canonical_dumps", "require_aware", "to_jsonb"]


def canonical_dumps(value: object) -> str:
    """Compact, key-sorted, non-ASCII-preserving JSON; NaN/Infinity are rejected."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def to_jsonb(value: object) -> Jsonb:
    """Wrap ``value`` for a ``jsonb`` parameter with canonical serialization."""
    return Jsonb(value, dumps=canonical_dumps)


def require_aware(value: datetime) -> datetime:
    """Naive datetimes never reach the database: ``timestamptz`` parameters must carry a timezone."""
    if value.tzinfo is None:
        raise ValueError("naive datetime is not allowed in the postgres adapter")
    return value
