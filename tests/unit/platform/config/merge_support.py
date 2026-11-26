"""Key specs, layer refs and contributions shared by the config merge and lock suites."""

from typing import Any, cast
from uuid import uuid4

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    MISSING,
    STORED_LEVELS,
    Chain,
    KeySpec,
    Level,
    MergeStrategy,
    NarrowSpec,
    Reload,
    Sensitivity,
    UiHints,
)
from skm.platform.config.layers import Contribution, LayerRef

__all__ = ["SCOPES", "WORK", "contribution", "key_spec", "layer_ref"]

SCOPES = {level: uuid4() for level in STORED_LEVELS}
WORK = frozenset({Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN})


def key_spec(
    key: str,
    value_schema: dict[str, Any],
    merge: MergeStrategy,
    *,
    owner: str = "test",
    default: object = MISSING,
    levels: frozenset[Level] = WORK,
    chain: Chain = Chain.WORK,
    reload: Reload = Reload.LIVE,
    override: bool = True,
    pack: bool = True,
    narrow: NarrowSpec | None = None,
    widget: str = "number",
) -> KeySpec:
    """A public, portable, lockable test key; it is nullable exactly when it has no default."""
    return KeySpec(
        key=key,
        section=key.split(".")[0],
        owner=owner,
        value_schema=value_schema,
        default=cast("JsonValue", default),
        description="",
        chain=chain,
        levels=levels,
        merge=merge,
        reload=reload,
        override=override,
        sensitivity=Sensitivity.PUBLIC,
        portable=True,
        lockable=True,
        nullable=default is MISSING,
        pack=pack,
        confirm=False,
        path=False,
        write_permission=None,
        narrow=narrow,
        validators=(),
        deprecated=None,
        ui=UiHints("g", 1, widget),
    )


def layer_ref(level: Level, label: str | None = None) -> LayerRef:
    """The layer of ``level``: stored levels sit on their ``SCOPES`` scope, labelled by level name."""
    if level is Level.DEFAULT:
        return LayerRef(level)
    if level is Level.PACK:
        return LayerRef(level, pack_id="p")
    if level is Level.INVOCATION:
        return LayerRef(level, source="cli")
    return LayerRef(level, SCOPES[level], label or level.value)


def contribution(
    level: Level, value: JsonValue = None, op: str = "set", *, locked: bool = False
) -> Contribution:
    """A contribution on ``layer_ref(level)``; the default level always contributes its default."""
    return Contribution(
        layer_ref(level), cast("Any", "default" if level is Level.DEFAULT else op), value, locked=locked
    )
