"""Plugin manifest (mechanisms/02-plugins §3, the single owner of the plugin contract).

A plugin distribution registers one ``PluginManifest`` per ``skm.plugins`` entry point; built-in components
use the same ``ComponentSpec`` (``bootstrap/builtins.py``). These declarations hold data only: validating a
manifest and constructing its components is the loader's job (``bootstrap/plugins.py``, 02-plugins §4).

``skm.plugin_api`` may import only the kernel and module facades (00-conventions §2), so the context members
whose types live in ``skm.platform`` (``EffectiveConfig``, ``StructLogger``, ``SchemaRegistry``,
``SecretResolver``) are typed ``object`` here; bootstrap supplies exactly those objects."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from skm.kernel.clock import Clock

__all__ = [
    "PLUGIN_ID_PATTERN",
    "ComponentKind",
    "ComponentSpec",
    "PluginContext",
    "PluginManifest",
    "Side",
    "requires_skm_matches",
]

# 02-plugins §3: "<publisher>.<name>"
PLUGIN_ID_PATTERN: Final = r"^[a-z0-9]+(\.[a-z0-9-]+)+$"


class ComponentKind(StrEnum):
    """Closed set of component kinds (00-conventions §4.0.4); a new kind is a core change with an ADR."""

    RUNTIME = "runtime"
    INTEGRATION_TARGET = "integration_target"
    CHECK_RUNNER = "check_runner"
    STAGE_HANDLER = "stage_handler"
    ISOLATION = "isolation"
    SECRET_RESOLVER = "secret_resolver"
    BLOB_BACKEND = "blob_backend"
    TOKEN_ESTIMATOR = "token_estimator"
    EVENT_SINK = "event_sink"
    EXPORTER = "exporter"
    KNOWLEDGE_SOURCE = "knowledge_source"
    RESEARCH_SOURCE = "research_source"


class Side(StrEnum):
    """Where a component is constructed: the host (CLI, worker, hook), the control plane or both."""

    HOST = "host"
    CONTROL_PLANE = "control_plane"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class PluginContext:
    """What a component factory receives; the plugin reads configuration only through ``config``."""

    plugin_id: str
    config: Callable[[], object]  # EffectiveConfig: the plugin section plus public keys, read lazily
    settings_view: type | None  # typed view of the plugin section, generated at load
    log: object  # StructLogger, component "plugin.<id>"
    schemas: object  # SchemaRegistry
    secrets: object  # SecretResolver: SecretRefs of the plugin section only
    clock: Clock


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    kind: ComponentKind
    key: str  # key in the registry of the kind (runtime_id, check kind, stage type, ...)
    side: Side
    factory: Callable[[PluginContext], object]  # returns an object implementing the owner's Protocol
    schemas: tuple[str, ...] = ()  # package-relative JSON Schema files (stage params, check definition)
    capabilities: str | None = None  # runtime: exactly "skm_runtimes/<key>/capabilities.toml"

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ComponentKind(self.kind))
        object.__setattr__(self, "side", Side(self.side))
        if not isinstance(self.key, str) or not self.key:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("a component key is a non-empty string")
        if not callable(self.factory):
            raise TypeError("a component factory must be callable")
        object.__setattr__(self, "schemas", tuple(self.schemas))


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str  # "<publisher>.<name>" (PLUGIN_ID_PATTERN); equals the entry point name
    version: str  # SemVer of the plugin
    plugin_api: int  # must equal skm.plugin_api.API_VERSION
    requires_skm: str  # PEP 440 specifier, e.g. ">=2.0,<3"
    title: str
    publisher: str
    components: tuple[ComponentSpec, ...]
    settings_schema: str | None = None  # package-relative schema of section "plugins.<id>"

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", tuple(self.components))


# -------------------------------------------------------------------- requires_skm (PEP 440, stdlib only)
_VERSION: Final = re.compile(
    r"v?(?P<release>[0-9]+(?:\.[0-9]+)*)(?:[-_.]?(?P<pre_l>a|b|rc)[-_.]?(?P<pre_n>[0-9]+))?"
    r"(?:[-_.]?post[-_.]?(?P<post>[0-9]+))?(?:[-_.]?dev[-_.]?(?P<dev>[0-9]+))?",
    re.IGNORECASE,
)
_CLAUSE: Final = re.compile(r"(?P<op>~=|===|==|!=|<=|>=|<|>)\s*(?P<version>[^\s,;]+)")
_PRE_RANK: Final = {"a": 0, "b": 1, "rc": 2}


@dataclass(frozen=True, slots=True, order=True)
class _Version:
    release: tuple[int, ...]  # trailing zeros removed: 2.0 == 2
    pre: tuple[int, int]
    post: int
    dev: tuple[int, int]
    raw_release: tuple[int, ...] = field(compare=False)
    is_pre: bool = field(compare=False)
    is_post: bool = field(compare=False)


def _parse_version(text: str) -> _Version:
    found = _VERSION.fullmatch(text.strip())
    if found is None:
        raise ValueError(f"not a PEP 440 version: {text!r}")
    raw = tuple(int(part) for part in found["release"].split("."))
    release = raw
    while len(release) > 1 and release[-1] == 0:
        release = release[:-1]
    dev = None if found["dev"] is None else int(found["dev"])
    post = None if found["post"] is None else int(found["post"])
    if found["pre_l"] is not None:
        pre = (_PRE_RANK[found["pre_l"].lower()], int(found["pre_n"]))
    else:
        pre = (-1, 0) if dev is not None and post is None else (9, 0)  # X.devN sorts before X.a0
    return _Version(
        release,
        pre,
        -1 if post is None else post,
        (1, 0) if dev is None else (0, dev),
        raw,
        is_pre=found["pre_l"] is not None or dev is not None,
        is_post=post is not None,
    )


def _prefix(candidate: _Version, prefix: tuple[int, ...]) -> bool:
    padded = candidate.raw_release + (0,) * max(0, len(prefix) - len(candidate.raw_release))
    return padded[: len(prefix)] == prefix


def _clause(candidate: _Version, op: str, text: str) -> bool:
    if op in ("==", "!=") and text.endswith(".*"):
        return _prefix(candidate, tuple(int(part) for part in text[:-2].split("."))) == (op == "==")
    bound = _parse_version(text)
    same = candidate.release == bound.release
    if op == "~=":
        if len(bound.raw_release) < 2:
            raise ValueError("~= needs at least two release segments")
        return candidate >= bound and _prefix(candidate, bound.raw_release[:-1])
    if op == "==":
        return candidate == bound
    if op == "!=":
        return candidate != bound
    if op == "<=":
        return candidate <= bound
    if op == ">=":
        return candidate >= bound
    if op == "<":  # "<3" does not admit 3.0.dev1
        return candidate < bound and not (candidate.is_pre and not bound.is_pre and same)
    return candidate > bound and not (candidate.is_post and not bound.is_post and same)


def requires_skm_matches(version: str, specifier: str) -> bool:
    """``version`` matches the PEP 440 ``specifier`` of ``requires_skm``; a skm pre-release is a candidate.

    Comma-separated clauses with ``~= == != <= >= < > ===`` and ``==X.*``; anything else is ``ValueError``.
    """
    candidate = _parse_version(version)
    result = True
    for part in specifier.split(","):
        clause = _CLAUSE.fullmatch(part.strip())
        if clause is None:
            raise ValueError(f"not a PEP 440 specifier clause: {part.strip()!r}")
        if clause["op"] == "===":
            result = result and version.strip() == clause["version"]
        else:
            result = result and _clause(candidate, clause["op"], clause["version"])
    return result
