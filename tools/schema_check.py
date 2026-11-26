"""Offline compatibility, generated freshness and schema-lock checks (tooling §8).

The recursive comparer is ported from the donor schemacompat. The local ref graph,
lock snapshots and generation pass belong to this repository. Output contracts
compare in reverse; shared definitions must work in both directions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import tomllib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if not __package__:
    __package__ = "tools"


from .codegen import error_catalog  # noqa: E402
from .codegen.model import CodegenError  # noqa: E402
from .schema_comparison import Comparer as _Comparer  # noqa: E402
from .schema_comparison import escape as _escape  # noqa: E402
from .schema_graph import (  # noqa: E402
    DIRECTIONS,
    LOCK_PATH,
    LOCK_URN,
    Change,
    Graph,
    normalize,
    schema_digest,
)
from .schema_graph import (  # noqa: E402
    RULES as RULES,
)
from .schema_graph import RefError as RefError  # noqa: E402
from .schema_graph import (  # noqa: E402
    canonical as canonical,
)
from .schema_graph import digits as _digits  # noqa: E402
from .schema_graph import (  # noqa: E402
    dumps as _dumps,
)
from .schema_graph import (  # noqa: E402
    loads as _loads,
)

__all__ = [
    "LOCK_PATH",
    "LOCK_URN",
    "RULES",
    "Change",
    "Graph",
    "RefError",
    "_digits",
    "_dumps",
    "_loads",
    "breaking_permission",
    "canonical",
    "check",
    "compare",
    "compatibility",
    "direction",
    "entries",
    "main",
    "normalize",
    "read_lock",
    "schema_digest",
]


def compare(old: Graph, old_id: str, new: Graph, new_id: str, direction: str = "input") -> list[Change]:
    """Changes from the schema ``old_id`` of ``old`` to the schema ``new_id`` of ``new``.

    ``input`` preserves documents accepted by the old schema. ``output`` requires
    documents accepted by the new schema to remain valid under the old one
    schema must be valid by the old one, because consumers check what producers emit with the schema they know
    (a new property or enum value breaks a consumer that holds a closed schema). ``both`` reports either.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    forward = _Comparer(old, new).run(old_id, new_id) if direction != "output" else []
    if direction == "input":
        return forward
    backward = [
        Change(c.path, c.rule, c.breaking, f"[output] {c.message}")
        for c in _Comparer(new, old).run(new_id, old_id)
    ]
    seen = {(c.path, c.rule, c.breaking) for c in forward}
    return forward + [c for c in backward if (c.path, c.rule, c.breaking) not in seen]


def direction(urn: str) -> str:
    """Classify by canonical URN segments, not substrings of an operation name."""
    parts = urn.split(":")
    if len(parts) < 5 or parts[:2] != ["urn", "skm"] or re.fullmatch(r"v[1-9][0-9]*", parts[-1]) is None:
        raise ValueError(f"LOCK_INVALID invalid schema URN {urn!r}")
    kind = parts[3]
    if kind == "defs":
        return "both"
    if kind in {"result", "view", "event", "host-result", "tool-output"}:
        return "output"
    return "input"


def entries(root: Path) -> dict[str, Any]:
    from skm.platform.schema.registry import SchemaRegistry

    schema_root = root / "src/skm/schemas"
    registry = SchemaRegistry.load(schema_root)
    paths = {}
    for path in sorted(schema_root.rglob("*.v*.json")):
        if "data" not in path.relative_to(schema_root).parts:
            document = _loads(path.read_text(encoding="utf-8"))
            paths[document["$id"]] = path.relative_to(schema_root).as_posix()
    result = {}
    for urn in sorted(registry.urns()):
        snapshot = normalize(dict(registry.get(urn)))
        result[urn] = {
            "path": paths[urn],
            "direction": direction(urn),
            "digest": schema_digest(snapshot),
            "snapshot": snapshot,
        }
    return result


def read_lock(root: Path) -> dict[str, Any] | None:
    path = root / LOCK_PATH
    if not path.exists():
        return None
    lock = _loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(lock, dict)
        or lock.get("schema") != LOCK_URN
        or not isinstance(lock.get("entries"), dict)
    ):
        raise ValueError(f"LOCK_INVALID {LOCK_PATH}: invalid envelope")
    for urn, entry in lock["entries"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("snapshot"), dict):
            raise ValueError(f"LOCK_INVALID {urn}: invalid entry")
        if entry.get("direction") != direction(urn) or entry.get("digest") != schema_digest(
            entry["snapshot"]
        ):
            raise ValueError(f"LOCK_INVALID {urn}: direction or snapshot digest mismatch")
        if entry["snapshot"].get("$id") != urn:
            raise ValueError(f"LOCK_INVALID {urn}: snapshot identity mismatch")
    if lock.get("digest") != schema_digest({urn: e["snapshot"] for urn, e in lock["entries"].items()}):
        raise ValueError(f"LOCK_INVALID {LOCK_PATH}: registry digest mismatch")
    if not isinstance(lock.get("updated_at"), str):
        raise ValueError(f"LOCK_INVALID {LOCK_PATH}: missing updated_at")
    return lock


def compatibility(old_entries: Mapping[str, Any], new_entries: Mapping[str, Any]) -> list[dict[str, Any]]:
    old = Graph({urn: entry["snapshot"] for urn, entry in old_entries.items()})
    new = Graph({urn: entry["snapshot"] for urn, entry in new_entries.items()})
    result = []
    for urn in sorted(old_entries.keys() | new_entries.keys()):
        if urn not in new_entries:
            changes = [Change("", "kind-removed", True, "schema removed; retain old major contracts")]
        elif urn not in old_entries:
            changes = [Change("", "kind-added", False, "new schema or major")]
        else:
            changes = compare(old, urn, new, urn, direction(urn))
            if direction(urn) == "both":
                changes.extend(_definitions(old, new, urn))
        result.extend({"urn": urn, **change._asdict()} for change in changes)
    return result


def _definitions(old: Graph, new: Graph, urn: str) -> list[Change]:
    """Shared definitions are exported contracts even before another schema uses them."""
    before = old.documents[urn].get("$defs", {})
    after = new.documents[urn].get("$defs", {})
    result = []
    for name in sorted(before.keys() | after.keys()):
        pointer = "/$defs/" + _escape(name)
        if name not in after:
            result.append(Change(pointer, "kind-removed", True, "shared definition removed"))
        elif name not in before:
            result.append(Change(pointer, "kind-added", False, "shared definition added"))
        else:
            result.extend(
                Change(pointer + c.path, c.rule, c.breaking, c.message)
                for c in compare(old, urn + "#" + pointer, new, urn + "#" + pointer, "both")
            )
    return result


def breaking_permission(root: Path) -> None:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(\.dev\d+|a\d+|b\d+|rc\d+))?", version)
    if match is None:
        raise ValueError("ALLOW_BREAKING_REFUSED cannot prove product version precedes 2.0.0")
    release = tuple(int(match[i]) for i in (1, 2, 3))
    if release > (2, 0, 0) or (release == (2, 0, 0) and match[4] is None):
        raise ValueError("ALLOW_BREAKING_REFUSED only before release 2.0.0")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    active_level = None
    for line in changelog.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading:
            level = len(heading[1])
            if active_level is not None and level <= active_level:
                break
            if active_level is None and re.search(r"\bUnreleased\b", heading[2], re.IGNORECASE):
                active_level = level
        elif active_level is not None and re.match(r"^\s*(?:[-*]\s*)?BREAKING:\s*\S.*", line):
            return
    raise ValueError("ALLOW_BREAKING_REFUSED explain BREAKING: in CHANGELOG.md [Unreleased]")


def check(root: Path = ROOT, *, update_lock: bool = False, allow_breaking: bool = False) -> dict[str, Any]:
    if allow_breaking:
        if not update_lock:
            raise ValueError("ALLOW_BREAKING_REFUSED --allow-breaking requires --update-lock")
        breaking_permission(root)
    # The registry imports ErrorCode. Check the independent stdlib emitter first,
    # so even a syntax error in that generated module is reported as GEN_STALE.
    if (root / error_catalog.CATALOG_RELPATH).exists():
        catalog = error_catalog.load_catalog(root)
        expected = {
            error_catalog.OUTPUT_DIR_RELPATH / "error_codes.py": error_catalog.render_error_codes(catalog),
            error_catalog.OUTPUT_DIR_RELPATH / "__init__.py": error_catalog.render_package_marker(),
        }
        errors = [
            f"GEN_STALE {path}"
            for path, text in sorted(expected.items())
            if not (root / path).is_file() or (root / path).read_bytes() != text.encode("utf-8")
        ]
        if errors:
            return {"ok": False, "errors": errors, "changes": [], "lock_stale": None}
    from . import gen

    current = entries(root)
    # Every emitter, including the sole P01.02 ErrorCode emitter, renders in memory.
    rendered = gen.outputs(root)
    stale = [
        str(path)
        for path, text in sorted(rendered.items())
        if not (root / path).is_file() or (root / path).read_bytes() != text.encode("utf-8")
    ]
    lock = read_lock(root)
    changes = compatibility(lock["entries"] if lock else {}, current)
    breaking = any(change["breaking"] for change in changes)
    lock_stale = (
        lock is None
        or lock["entries"] != current
        or (root / LOCK_PATH).read_text(encoding="utf-8") != _dumps(lock, ensure_ascii=False, indent=2) + "\n"
    )
    errors = [f"GEN_STALE {path}" for path in stale]
    if breaking and not allow_breaking:
        errors.append("SCHEMA_BREAKING use a new major + migration")
    if update_lock and not errors:
        if lock_stale:
            document = {
                "schema": LOCK_URN,
                "updated_at": datetime.fromtimestamp(time.time(), UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "digest": schema_digest({urn: e["snapshot"] for urn, e in current.items()}),
                "entries": current,
            }
            path = root / LOCK_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lock_stale = False
    elif lock_stale:
        errors.append(f"LOCK_STALE {LOCK_PATH}; run make schema-lock")
    return {"ok": not errors, "errors": errors, "changes": changes, "lock_stale": lock_stale}


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-lock", action="store_true")
    parser.add_argument("--allow-breaking", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = check(root, update_lock=args.update_lock, allow_breaking=args.allow_breaking)
    except (OSError, ValueError, CodegenError) as error:
        report = {"ok": False, "errors": [str(error)], "changes": []}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for error in report["errors"]:
            print(error, file=sys.stderr)
        for change in report["changes"]:
            if change["breaking"]:
                print(
                    f"{change['urn']} {change['path'] or '/'}: {change['rule']}: {change['message']}",
                    file=sys.stderr,
                )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
