"""Carrier-address resolver for the v2-only executable-plan contract."""
from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path


class PlanLayoutError(ValueError):
    """The declared layout cannot deterministically resolve a carrier."""


_META_ROW = re.compile(r"^\|\s*Layout\s*\|\s*([^|]+)\|")
_ITEM = re.compile(r"^(P\d+)\.(\d+)$")
_PHASE_FILE = re.compile(r"^(P\d+)\.md$")
_ITEM_SPEC_FILE = re.compile(r"^(P\d+)\.(\d+)\.md$")
_CONFIG = Path(__file__).resolve().parents[2] / "configs"
_TERMINAL_STATUSES = frozenset(("🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision"))


@dataclass(frozen=True)
class ResolvedSlot:
    """One concrete carrier returned by the declared reader path."""

    role: str
    slot_id: str
    carrier_id: str
    path: Path


def _meta_layout(plan_dir: Path) -> str:
    try:
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanLayoutError(f"plan.md is not readable: {exc}") from exc
    for line in text.splitlines():
        match = _META_ROW.match(line)
        if match:
            return match.group(1).strip()
    raise PlanLayoutError(
        "PLAN_LAYOUT_V1_RETIRED: Layout | v2 required; historical v1 "
        "is executed only by the legacy compatible tag")


def layout_version(plan_dir) -> str:
    """Return the sole executable layout and reject retired declarations."""
    plan_dir = Path(plan_dir)
    version = _meta_layout(plan_dir)
    if version == "v1":
        raise PlanLayoutError(
            "PLAN_LAYOUT_V1_RETIRED: Layout | v1 is no longer executed; "
            "open historical source archive or previous compatible tag")
    if version != "v2":
        raise PlanLayoutError(f"Layout: unknown layout {version!r}; is only valid v2")
    phase_dir = plan_dir / "phases"
    has_v1 = any(_PHASE_FILE.match(p.name) for p in phase_dir.glob("*.md")) if phase_dir.is_dir() else False
    v2_directories = [
        path for path in phase_dir.iterdir()
        if path.is_dir() and _PHASE_FILE.match(path.name + ".md")
    ] if phase_dir.is_dir() else []
    has_v2 = bool(v2_directories)
    if has_v1 or not has_v2:
        raise PlanLayoutError("Layout v2 is declared, but the tree does not consist of phases/Pn/Pn.md")
    invalid_indexes = []
    for directory in sorted(v2_directories):
        index = directory / f"{directory.name}.md"
        try:
            if not stat.S_ISREG(index.lstat().st_mode):
                raise OSError("not regular file")
            with index.open("rb"):
                pass
        except OSError:
            invalid_indexes.append(index.relative_to(plan_dir).as_posix())
    if invalid_indexes:
        raise PlanLayoutError(
            "Layout v2: phase index is not readable or not regular file: "
            + ", ".join(invalid_indexes)
        )
    return version


def registry() -> dict:
    path = _CONFIG / "reader-contract-v1.registry.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanLayoutError(f"media contract is not readable: {exc}") from exc
    return {row["id"]: row for row in data.get("carriers", [])}


def read_path_spec() -> dict:
    """Load the frozen reader-path declaration once for resolver consumers."""
    path = _CONFIG / "read-path-v1.spec.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanLayoutError(f"read path specification is not readable: {exc}") from exc


def carrier_path(plan_dir, carrier_id, *, item_id=None, phase_id=None) -> Path:
    """Resolve one declared carrier.  Wildcard/index carriers are not files."""
    plan_dir = Path(plan_dir)
    version = layout_version(plan_dir)
    carriers = registry()
    row = carriers.get(carrier_id)
    if row is None or version not in row.get("layout_versions", []):
        raise PlanLayoutError(f"media {carrier_id!r} not declared for Layout {version}")
    template = row["path"]
    if "<Pn.m>" in template:
        if not item_id or not _ITEM.match(item_id):
            raise PlanLayoutError(f"{carrier_id}: need exact item Pn.m")
        template = template.replace("<Pn.m>", item_id)
        phase_id = item_id.split(".")[0]
    if "<Pn>" in template:
        if not phase_id:
            raise PlanLayoutError(f"{carrier_id}: needed phase Pn")
        template = template.replace("<Pn>", phase_id)
    if any(token in template for token in ("*", "{", "<")):
        raise PlanLayoutError(f"{carrier_id}: is not a single file media")
    return plan_dir / template


def carrier_glob(plan_dir, carrier_id) -> Path:
    """Resolve a declared multi-file carrier to a deterministic glob pattern."""
    plan_dir = Path(plan_dir)
    version = layout_version(plan_dir)
    row = registry().get(carrier_id)
    if row is None or version not in row.get("layout_versions", []):
        raise PlanLayoutError(f"media {carrier_id!r} not declared for Layout {version}")
    template = re.sub(r"<[^>]+>|\{[^}]+\}", "*", row["path"])
    if "*" not in template:
        raise PlanLayoutError(f"{carrier_id}: is not multiple media")
    return plan_dir / template


def phase_paths(plan_dir) -> dict:
    plan_dir = Path(plan_dir)
    version = layout_version(plan_dir)
    phases = plan_dir / "phases"
    result = {}
    for directory in sorted(phases.iterdir() if phases.is_dir() else ()):
        if not directory.is_dir() or not re.match(r"^P\d+$", directory.name):
            continue
        path = directory / f"{directory.name}.md"
        result[directory.name] = path
    return result


def phase_path(plan_dir, phase_id) -> Path:
    paths = phase_paths(plan_dir)
    try:
        return paths[phase_id]
    except KeyError as exc:
        raise PlanLayoutError(f"phase {phase_id} not found in Layout {layout_version(plan_dir)}") from exc


def phase_statuses(plan_dir) -> dict[str, str]:
    """Return the authoritative declared status for every phase in a plan."""
    plan_dir = Path(plan_dir)
    layout_version(plan_dir)
    # Deferred import avoids the plan_layout ↔ plan_status module cycle.
    from task import plan_status
    try:
        _meta, board = plan_status.parse_status_view(plan_dir)
    except plan_status.StatusError as exc:
        raise PlanLayoutError(f"owner type of status is not readable: {exc}") from exc
    statuses = {row["Phase"]: row["Status"] for row, _lineno in board}
    missing = sorted(set(phase_paths(plan_dir)) - set(statuses))
    if missing:
        raise PlanLayoutError(f"no declared phase status: {', '.join(missing)}")
    return statuses


def is_terminal_phase(plan_dir, phase_id) -> bool:
    """Terminality is declared by the phase status, never inferred from its items."""
    statuses = phase_statuses(plan_dir)
    try:
        return statuses[phase_id] in _TERMINAL_STATUSES
    except KeyError as exc:
        raise PlanLayoutError(f"phase {phase_id} has no declared status") from exc


def phase_context_path(plan_dir, phase_id, *, reader: str) -> Path:
    """Resolve a phase carrier while keeping terminal phases off live reader paths."""
    if reader not in read_path_spec().get("paths", {}):
        raise PlanLayoutError(f"unknown path reader: {reader!r}")
    if reader != "auditor" and is_terminal_phase(plan_dir, phase_id):
        raise PlanLayoutError(f"{reader}: terminal phase {phase_id} is not in the live path")
    return carrier_path(plan_dir, "phase-index", phase_id=phase_id)


def slots(plan_dir, reader: str) -> tuple[ResolvedSlot, ...]:
    """Resolve declared static and phase-context slots for a reader.

    Dynamic item, bundle, and optional closure slots need an explicit target and
    are intentionally not guessed here.  The function is consequently useful
    for the declaration-level predicate that proves terminal phase carriers do
    not leak into any live path.
    """
    paths = read_path_spec().get("paths", {})
    if reader not in paths:
        raise PlanLayoutError(f"unknown path reader: {reader!r}")
    result = []
    for slot in paths[reader].get("slots", []):
        carrier_id = slot["carrier_id"]
        if carrier_id == "phase-index":
            for phase_id in phase_paths(plan_dir):
                if reader == "auditor" or not is_terminal_phase(plan_dir, phase_id):
                    result.append(ResolvedSlot(reader, slot["id"], carrier_id,
                                               phase_context_path(plan_dir, phase_id, reader=reader)))
            continue
        if carrier_id in {"item-spec", "item-state", "bundle", "history-view", "phase-closure"}:
            continue
        try:
            path = carrier_path(plan_dir, carrier_id)
        except PlanLayoutError:
            # Multi-file and target-dependent carriers are not concrete slots.
            continue
        result.append(ResolvedSlot(reader, slot["id"], carrier_id, path))
    return tuple(result)


def item_spec_paths(plan_dir, phase_id) -> list[Path]:
    """Return v2 item-spec files for one phase in numeric item order.

    The helper owns directory enumeration so consumers do not recreate the
    ``phases/Pn/Pn.m.md`` convention beside the carrier registry.
    """
    plan_dir = Path(plan_dir)
    if layout_version(plan_dir) != "v2":
        raise PlanLayoutError("item-spec files exist only in Layout v2")
    directory = phase_path(plan_dir, phase_id).parent
    result = []
    for path in directory.glob("*.md"):
        match = _ITEM_SPEC_FILE.match(path.name)
        if not match:
            continue
        if match.group(1) != phase_id:
            raise PlanLayoutError(
                f"technical specification file {path.name} has the prefix {match.group(1)}, and the phase directory is {phase_id}")
        result.append((int(match.group(2)), path))
    return [path for _number, path in sorted(result)]


def plan_core_path(plan_dir) -> Path:
    layout_version(plan_dir)
    return carrier_path(plan_dir, "plan-core")
