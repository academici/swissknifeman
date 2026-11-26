"""Layers and contributions fed to the merge fold (settings §B.3).

Layer order for the resolver is fixed: ``default`` → ``pack`` (priority ascending, ties by pack id) → stored
levels of the chain, farthest first → ``invocation`` (``env`` → ``--config`` files in order → ``--set`` in
order).
These types only describe provenance and values; ordering and folding belong to ``merge.py``/``resolver.py``.
A lock is accepted only from ``instance``/``workspace`` contributions; ``merge.fold`` still ignores a lock
from any other level (data changed outside the commands, §B.5.6) instead of trusting it.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal
from uuid import UUID

from skm.kernel.json_types import JsonValue

from .keys import LOCK_LEVELS, STORED_LEVELS, Level, freeze_json

__all__ = ["Contribution", "Layer", "LayerRef", "Op"]

type Op = Literal["default", "set", "unset", "append"]

_OPS: Final = frozenset({"default", "set", "unset", "append"})
_SOURCE: Final = re.compile(r"env|cli|config-file:.+")


@dataclass(frozen=True, slots=True)
class LayerRef:
    level: Level
    scope_id: UUID | None = None
    # label: "instance", "workspace:personal", "pack:core", "env:SKM__…", "--set", "--config ./x.toml"
    label: str = ""
    pack_id: str | None = None
    pack_priority: int | None = None
    source: str | None = None  # invocation only: "env" | "cli" | "config-file:<path>"
    entry_id: UUID | None = None
    row_version: int | None = None

    def __post_init__(self) -> None:
        level = Level(self.level)
        object.__setattr__(self, "level", level)
        stored = level in STORED_LEVELS
        if (stored and not isinstance(self.scope_id, UUID)) or (not stored and self.scope_id is not None):
            raise ValueError(f"scope_id is required exactly for stored levels, not {level.value!r}")
        if (level is Level.PACK) != (self.pack_id is not None):
            raise ValueError("pack_id is required exactly for the pack level")
        if level is not Level.PACK and self.pack_priority is not None:
            raise ValueError("pack_priority belongs to the pack level only")
        if (level is Level.INVOCATION) != (self.source is not None):
            raise ValueError("source is required exactly for the invocation level")
        if self.source is not None and not _SOURCE.fullmatch(self.source):
            raise ValueError("source must be env, cli or config-file:<path>")
        if not stored and (self.entry_id is not None or self.row_version is not None):
            raise ValueError("entry_id and row_version belong to stored levels only")
        if self.row_version is not None and (isinstance(self.row_version, bool) or self.row_version < 1):
            raise ValueError("row_version must be an integer >= 1")

    @property
    def display(self) -> str:
        """Label for messages: the explicit label, else ``pack:<id>``, the invocation source or the level."""
        if self.label:
            return self.label
        if self.pack_id is not None:
            return f"pack:{self.pack_id}"
        return self.source if self.source is not None else self.level.value

    def to_json(self) -> dict[str, JsonValue]:
        """``layer_ref`` of ``urn:skm:config:explain:v1``: ``level`` plus the fields that are set."""
        document: dict[str, JsonValue] = {"level": self.level.value}
        if self.scope_id is not None:
            document["scope_id"] = str(self.scope_id)
        if self.label:
            document["label"] = self.label
        if self.pack_id is not None:
            document["pack_id"] = self.pack_id
        if self.pack_priority is not None:
            document["pack_priority"] = self.pack_priority
        if self.source is not None:
            document["source"] = self.source
        if self.entry_id is not None:
            document["entry_id"] = str(self.entry_id)
        if self.row_version is not None:
            document["row_version"] = self.row_version
        return document


@dataclass(frozen=True, slots=True)
class Contribution:
    layer: LayerRef
    op: Op
    value: JsonValue  # None for unset; a legal JSON null for set/default/append is a value, not "absent"
    locked: bool = False

    def __post_init__(self) -> None:
        if self.op not in _OPS:
            raise ValueError(f"op must be one of {sorted(_OPS)}, not {self.op!r}")
        if (self.op == "default") != (self.layer.level is Level.DEFAULT):
            raise ValueError("op 'default' belongs to the default level and only to it")
        if self.op == "unset" and self.value is not None:
            raise ValueError("an unset contribution carries no value")
        if self.locked and self.layer.level not in LOCK_LEVELS:
            raise ValueError("only instance and workspace entries can lock a key")
        object.__setattr__(self, "value", freeze_json(self.value, "value"))


@dataclass(frozen=True, slots=True)
class Layer:
    ref: LayerRef
    contributions: Mapping[str, Contribution]  # key → contribution

    def __post_init__(self) -> None:
        for key, contribution in self.contributions.items():
            if contribution.layer.level is not self.ref.level:
                raise ValueError(
                    f"{key}: contribution level {contribution.layer.level.value!r} is not the layer's"
                )
        object.__setattr__(self, "contributions", MappingProxyType(dict(self.contributions)))
