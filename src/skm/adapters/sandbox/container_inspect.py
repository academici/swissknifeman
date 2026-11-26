"""Reading ``docker inspect`` documents for the ``container`` profile (adapters §7.2).

Typed accessors over the untyped inspect JSON, the baseline fields a recovered container must match, mount
and volume extraction, and the identity checks of the unstarted baseline probe container. Nothing here runs
``docker``; the backend in ``container`` passes the documents in.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.json_types import JsonValue

if TYPE_CHECKING:
    from skm.adapters.sandbox.container import DockerResult


__all__ = [
    "ABSENT",
    "BASELINE_FIELDS",
    "CONTAINER_ID",
    "PROBE_COMMAND",
    "PROBE_LABEL",
    "as_flag",
    "as_mapping",
    "as_number",
    "as_strings",
    "as_text",
    "dig",
    "effective_mounts",
    "has_writable_mount",
    "image_entrypoint",
    "inspected_one",
    "merged_env",
    "probe_volumes",
    "requested_mounts",
    "returned_id",
    "verified_probe_id",
]

CONTAINER_ID: Final = re.compile(r"[0-9a-f]{64}")
_ANONYMOUS_VOLUME: Final = re.compile(r"[0-9a-f]{64}")
ABSENT: Final = object()
PROBE_LABEL: Final = "skm.confinement_baseline"
PROBE_COMMAND: Final = "/skm-baseline-probe-is-never-started"


def dig(document: object, path: str) -> object:
    for key in path.split("."):
        if not isinstance(document, dict) or key not in document:
            return ABSENT
        document = cast("dict[str, object]", document)[key]
    return document


def as_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError
    return value


def as_flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError
    return value


def as_number(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError
    return value


def as_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError
    return tuple(as_text(item) for item in cast("list[object]", value))


def image_entrypoint(value: object) -> tuple[str, ...]:
    entrypoint = as_strings(value)
    return () if entrypoint == ("",) else entrypoint


def merged_env(requested: Mapping[str, str], image_env: Sequence[str]) -> frozenset[str]:
    merged = {name: f"{name}={value}" for name, value in requested.items()}
    for line in image_env:
        merged.setdefault(line.partition("=")[0], line)
    return frozenset(merged.values())


def as_mapping(value: object, allow_none: object = True) -> dict[str, JsonValue]:
    if value is None and allow_none:
        return {}
    if not isinstance(value, dict):
        raise ValueError
    return cast("dict[str, JsonValue]", value)


def _protected_paths(value: object) -> frozenset[str]:
    paths = frozenset(as_strings(value))
    if not paths:
        raise ValueError
    return paths


BASELINE_FIELDS: Final[tuple[tuple[str, Callable[[object], object]], ...]] = (
    ("HostConfig.MaskedPaths", _protected_paths),
    ("HostConfig.ReadonlyPaths", _protected_paths),
    ("HostConfig.IpcMode", as_text),
    ("HostConfig.CgroupnsMode", as_text),
    ("HostConfig.ShmSize", as_number),
    ("HostConfig.LogConfig.Config", as_mapping),
)


def requested_mounts(value: object) -> frozenset[tuple[str, ...]]:
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise ValueError
    found: set[tuple[str, ...]] = set()
    for item in cast("list[object]", value):
        if not isinstance(item, dict):
            raise ValueError
        mount = cast("dict[str, object]", item)
        access = "ro" if as_flag(mount.get("ReadOnly", False)) else "rw"
        found.add(
            (as_text(mount.get("Type")), as_text(mount.get("Source")), as_text(mount.get("Target")), access)
        )
        known = {"Type", "Source", "Target", "ReadOnly"}
        found.update(("option", key) for key, option in mount.items() if key not in known and option)
    return frozenset(found)


def effective_mounts(volumes: Mapping[str, JsonValue]) -> Callable[[object], frozenset[tuple[str, ...]]]:
    volume_targets = frozenset(os.path.normpath(k) for k in volumes)

    def read(value: object) -> frozenset[tuple[str, ...]]:
        if not isinstance(value, list):
            raise ValueError
        found: set[tuple[str, ...]] = set()
        for item in cast("list[object]", value):
            if not isinstance(item, dict):
                raise ValueError
            mount = cast("dict[str, object]", item)
            kind, target = as_text(mount.get("Type")), as_text(mount.get("Destination"))
            if kind == "volume" and os.path.normpath(target) in volume_targets:
                continue
            access = "rw" if as_flag(mount.get("RW")) else "ro"
            found.add((kind, as_text(mount.get("Source")), target, access))
        return frozenset(found)

    return read


def probe_volumes(report: Mapping[str, object]) -> tuple[str, ...]:
    declared = {os.path.normpath(path) for path in as_mapping(dig(report, "Config.Volumes"))}
    mounts = report.get("Mounts")
    if not isinstance(mounts, list):
        raise ValueError
    names: list[str] = []
    found: set[str] = set()
    for item in cast("list[object]", mounts):
        if not isinstance(item, dict):
            raise ValueError
        mount = cast("dict[str, object]", item)
        name, target = as_text(mount.get("Name")), as_text(mount.get("Destination"))
        if mount.get("Type") != "volume" or target not in declared or not _ANONYMOUS_VOLUME.fullmatch(name):
            raise ValueError
        names.append(name)
        found.add(target)
    if declared - found - {"/tmp"}:  # noqa: S108
        raise ValueError
    return tuple(names)


def returned_id(result: DockerResult) -> str | None:
    container_id = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""
    return container_id if result.exit_code == 0 and CONTAINER_ID.fullmatch(container_id) else None


def inspected_one(result: DockerResult) -> dict[str, object] | None:
    try:
        document: object = json.loads(result.stdout) if result.exit_code == 0 else None
    except ValueError:
        return None
    if not isinstance(document, list) or len(cast("list[object]", document)) != 1:
        return None
    only = cast("list[object]", document)[0]
    return cast("dict[str, object]", only) if isinstance(only, dict) else None


def verified_probe_id(report: Mapping[str, object] | None, probe_id: str | None, name: str) -> str | None:
    if report is None:
        return probe_id
    cid = report.get("Id")
    labels = dig(report, "Config.Labels")
    if (
        not isinstance(cid, str) or CONTAINER_ID.fullmatch(cid) is None
        or (probe_id is not None and cid != probe_id) or report.get("Name") != f"/{name}"
        or dig(report, "State.Status") != "created"
        or not isinstance(labels, dict) or cast("dict[str, object]", labels).get(PROBE_LABEL) != "true"
        or dig(report, "Config.Cmd") != [PROBE_COMMAND]
    ):  # fmt: skip
        return None
    return cid


def has_writable_mount(record: Mapping[str, object]) -> bool:
    mounts = record.get("Mounts")
    if not isinstance(mounts, list):
        return True
    return any(
        not isinstance(mount, dict) or (mount.get("Type") != "volume" and mount.get("RW") is not False)
        for mount in cast("list[JsonValue]", mounts)
    )
