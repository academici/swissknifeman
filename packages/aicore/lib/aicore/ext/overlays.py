"""Instruction overlays: text files a person adds to the commands of a module without touching the module.

A module declares a slot ``<module>:<name>`` in ``provides.overlay_slots`` of its ``unit.json``; the files of
the slot are listed under ``[aicore.overlays]`` in the configuration, in layer order. :func:`resolve_overlays`
reads them, :func:`render_overlays` turns them into one marked block that a command appends to its own text.
An overlay adds rules, it never replaces any. The total text is limited because it enters a model's context.

A file named by the *project* layer must lie inside the project: a cloned repository must not be able to pull
other files of the machine into a model's context. Paths are printed with ``~`` for the home directory.
stdlib and ``aicore`` only.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from ..util.digest import sha256_tagged
from ..util.paths import is_within
from . import settings as _settings
from . import units as _units
from .errors import ExtError

MAX_BYTES = 32768
_SLOT = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f\u0085  ]")

PathLike = Union[str, "os.PathLike[str]"]


@dataclass(frozen=True)
class Overlay:
    """One overlay file: where it is, which layer named it, its text and the digest of its bytes."""

    path: Path
    layer: str
    text: str
    digest: str

    @property
    def size(self) -> int:
        return len(self.text.encode("utf-8"))


@dataclass(frozen=True)
class OverlaySet:
    """The overlays of a slot in order. ``warnings`` are ``{"code", "path", "message"}`` (paths with ``~``)."""

    slot: str
    items: Tuple[Overlay, ...]
    warnings: Tuple[Dict[str, str], ...] = ()
    home: str = field(default="", compare=False)

    def shown(self, path: Path) -> str:
        return _line(_settings.collapse_home(str(path), {}, self.home or None))


def _line(text: str) -> str:
    """``text`` on one line that cannot close a comment."""
    return _CONTROL.sub(lambda match: match.group(0).encode("unicode_escape").decode("ascii"),
                        text).replace("-->", "--&gt;")


def _inside(root: Path, path: Path) -> bool:
    return is_within(path, root)  # fails closed, also on a symlink loop


def resolve_overlays(slot: str, *, project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
                     home: Optional[PathLike] = None, config_file: Optional[PathLike] = None,
                     units: Optional[Mapping[str, "_units.UnitDoc"]] = None) -> OverlaySet:
    """The overlays of ``slot`` (``<module>:<name>``) for ``project``.

    ``ExtError``: ``OVERLAY_SLOT_UNKNOWN`` when no module declares the slot (also for a malformed name),
    ``OVERLAY_TOO_LARGE`` when the texts exceed 32768 bytes of UTF-8, ``CONFIG_INVALID`` for a bad
    configuration. A missing file is skipped with an ``OVERLAY_MISSING`` warning; a file that cannot be read,
    is not UTF-8 or (project layer) lies outside the project is skipped with ``OVERLAY_INVALID``.
    """
    environment = os.environ if env is None else env
    known = _units.overlay_slots(units if units is not None else _units.discover_units(env))
    if not _SLOT.match(slot) or slot not in known:
        declared = ", ".join(sorted(known)) or "none"
        raise ExtError("OVERLAY_SLOT_UNKNOWN", f"no module declares the overlay slot {_line(slot)!r} "
                       f"(declared: {declared})")
    loaded = _settings.load(project, env=env, home=home, config_file=config_file)
    base_home = str(home) if home is not None else environment.get("HOME") or str(Path.home())
    items: List[Overlay] = []
    warnings: List[Dict[str, str]] = []
    total = 0
    for raw, layer, _layer_file in loaded.overlays.get(slot, []):
        path = Path(raw)
        shown = _line(_settings.collapse_home(raw, environment, home))

        def warn(code: str, message: str, shown: str = shown) -> None:
            warnings.append({"code": code, "path": shown, "message": f"{shown}: {message}"})

        if layer == "project" and (project is None or not _inside(Path(project), path)):
            warn("OVERLAY_INVALID", "a file named by the project configuration must lie inside the project; skipped")
            continue
        try:
            with open(path, "rb") as handle:
                data = handle.read(MAX_BYTES + 1)
        except FileNotFoundError:
            warn("OVERLAY_MISSING", "the file does not exist; skipped")
            continue
        except OSError as exc:
            warn("OVERLAY_INVALID", f"the file cannot be read ({exc.__class__.__name__}); skipped")
            continue
        total += len(data)
        if total > MAX_BYTES:
            raise ExtError("OVERLAY_TOO_LARGE", f"the overlays of slot {slot} exceed {MAX_BYTES} bytes; "
                           "shorten them or drop one")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            warn("OVERLAY_INVALID", "the file is not UTF-8 text; skipped")
            continue
        items.append(Overlay(path=path, layer=layer, text=text, digest=sha256_tagged(data)))
    return OverlaySet(slot=slot, items=tuple(items), warnings=tuple(warnings), home=base_home)


def render_overlays(overlay_set: OverlaySet) -> str:
    """The marked block of ``overlay_set`` (empty string when there is no overlay).

    ::

        <!-- overlays: SLOT -->
        <!-- overlay: PATH (LAYER) -->
        TEXT
        <!-- end overlays: SLOT -->
    """
    if not overlay_set.items:
        return ""
    lines = [f"<!-- overlays: {overlay_set.slot} -->\n"]
    for overlay in overlay_set.items:
        lines.append(f"<!-- overlay: {overlay_set.shown(overlay.path)} ({_line(overlay.layer)}) -->\n")
        lines.append(overlay.text if overlay.text.endswith("\n") else overlay.text + "\n")
    lines.append(f"<!-- end overlays: {overlay_set.slot} -->\n")
    return "".join(lines)


def describe_overlays(overlay_set: OverlaySet) -> Dict[str, Any]:
    """``{"slot", "overlays": [{"path", "layer", "digest", "bytes"}], "warnings": [...]}`` (paths with ``~``)."""
    return {"slot": overlay_set.slot,
            "overlays": [{"path": overlay_set.shown(item.path), "layer": item.layer, "digest": item.digest,
                          "bytes": item.size} for item in overlay_set.items],
            "warnings": list(overlay_set.warnings)}
