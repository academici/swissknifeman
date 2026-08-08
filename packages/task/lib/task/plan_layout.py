"""Versioned carrier-address resolver for executable-plan layouts.

The frozen P1 contracts are installed next to this module as data.  A missing
``Layout`` Meta field intentionally means legacy v1; every other value must be
explicitly supported and must agree with the physical phase tree.
"""
from __future__ import annotations

import json
import re
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
        raise PlanLayoutError(f"plan.md не читается: {exc}") from exc
    for line in text.splitlines():
        match = _META_ROW.match(line)
        if match:
            return match.group(1).strip()
    return "v1"


def layout_version(plan_dir) -> str:
    """Return ``v1`` or ``v2`` and reject a declaration/tree disagreement."""
    plan_dir = Path(plan_dir)
    version = _meta_layout(plan_dir)
    if version not in ("v1", "v2"):
        raise PlanLayoutError(f"Layout: неизвестная раскладка {version!r}; допустимы v1, v2")
    phase_dir = plan_dir / "phases"
    has_v1 = any(_PHASE_FILE.match(p.name) for p in phase_dir.glob("*.md")) if phase_dir.is_dir() else False
    has_v2 = any(p.is_dir() and _PHASE_FILE.match(p.name + ".md") for p in phase_dir.iterdir()) if phase_dir.is_dir() else False
    if version == "v1" and has_v2:
        raise PlanLayoutError("Layout v1 объявлен, но дерево содержит phases/Pn/")
    if version == "v2" and (has_v1 or not has_v2):
        raise PlanLayoutError("Layout v2 объявлен, но дерево не состоит из phases/Pn/Pn.md")
    return version


def registry() -> dict:
    path = _CONFIG / "reader-contract-v1.registry.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanLayoutError(f"контракт носителей не читается: {exc}") from exc
    return {row["id"]: row for row in data.get("carriers", [])}


def read_path_spec() -> dict:
    """Load the frozen reader-path declaration once for resolver consumers."""
    path = _CONFIG / "read-path-v1.spec.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanLayoutError(f"спецификация пути чтения не читается: {exc}") from exc


def carrier_path(plan_dir, carrier_id, *, item_id=None, phase_id=None) -> Path:
    """Resolve one declared carrier.  Wildcard/index carriers are not files."""
    plan_dir = Path(plan_dir)
    version = layout_version(plan_dir)
    carriers = registry()
    row = carriers.get(carrier_id)
    if row is None or version not in row.get("layout_versions", []):
        raise PlanLayoutError(f"носитель {carrier_id!r} не объявлен для Layout {version}")
    template = row["path"]
    if "<Pn.m>" in template:
        if not item_id or not _ITEM.match(item_id):
            raise PlanLayoutError(f"{carrier_id}: нужен точный item Pn.m")
        template = template.replace("<Pn.m>", item_id)
        phase_id = item_id.split(".")[0]
    if "<Pn>" in template:
        if not phase_id:
            raise PlanLayoutError(f"{carrier_id}: нужен phase Pn")
        template = template.replace("<Pn>", phase_id)
    if any(token in template for token in ("*", "{", "<")):
        raise PlanLayoutError(f"{carrier_id}: не является одиночным файловым носителем")
    return plan_dir / template


def carrier_glob(plan_dir, carrier_id) -> Path:
    """Resolve a declared multi-file carrier to a deterministic glob pattern."""
    plan_dir = Path(plan_dir)
    version = layout_version(plan_dir)
    row = registry().get(carrier_id)
    if row is None or version not in row.get("layout_versions", []):
        raise PlanLayoutError(f"носитель {carrier_id!r} не объявлен для Layout {version}")
    template = re.sub(r"<[^>]+>|\{[^}]+\}", "*", row["path"])
    if "*" not in template:
        raise PlanLayoutError(f"{carrier_id}: не является множественным носителем")
    return plan_dir / template


def phase_paths(plan_dir) -> dict:
    plan_dir = Path(plan_dir)
    version = layout_version(plan_dir)
    phases = plan_dir / "phases"
    if version == "v1":
        return {m.group(1): p for p in sorted(phases.glob("*.md")) if (m := _PHASE_FILE.match(p.name))}
    result = {}
    for directory in sorted(phases.iterdir() if phases.is_dir() else ()):
        if not directory.is_dir() or not re.match(r"^P\d+$", directory.name):
            continue
        path = directory / f"{directory.name}.md"
        if path.is_file():
            result[directory.name] = path
    return result


def phase_path(plan_dir, phase_id) -> Path:
    paths = phase_paths(plan_dir)
    try:
        return paths[phase_id]
    except KeyError as exc:
        raise PlanLayoutError(f"фаза {phase_id} не найдена в Layout {layout_version(plan_dir)}") from exc


def _v1_phase_statuses(plan_dir: Path) -> dict[str, str]:
    """Read declared phase statuses from the legacy owner board, not item heuristics."""
    try:
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanLayoutError(f"plan.md не читается: {exc}") from exc
    in_board = False
    headers = None
    statuses = {}
    for line in text.splitlines():
        if line.startswith("## "):
            in_board = line == "## 4. Phase Index & Status Board"
            headers = None
            continue
        if not in_board or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(cell.startswith(":") or cell.startswith("-") for cell in cells):
            continue
        if headers is None:
            headers = cells
            continue
        if headers == ["Phase", "Title", "Items 🟢/всего", "Status"] and len(cells) == 4:
            statuses[cells[0]] = cells[3]
    return statuses


def phase_statuses(plan_dir) -> dict[str, str]:
    """Return the authoritative declared status for every phase in a plan."""
    plan_dir = Path(plan_dir)
    if layout_version(plan_dir) == "v1":
        statuses = _v1_phase_statuses(plan_dir)
    else:
        # Deferred import avoids the plan_layout ↔ plan_status module cycle.
        from task import plan_status
        try:
            _meta, board = plan_status.parse_status_view(plan_dir)
        except plan_status.StatusError as exc:
            raise PlanLayoutError(f"владельческий вид статуса не читается: {exc}") from exc
        statuses = {row["Phase"]: row["Status"] for row, _lineno in board}
    missing = sorted(set(phase_paths(plan_dir)) - set(statuses))
    if missing:
        raise PlanLayoutError(f"нет объявленного статуса фаз: {', '.join(missing)}")
    return statuses


def is_terminal_phase(plan_dir, phase_id) -> bool:
    """Terminality is declared by the phase status, never inferred from its items."""
    statuses = phase_statuses(plan_dir)
    try:
        return statuses[phase_id] in _TERMINAL_STATUSES
    except KeyError as exc:
        raise PlanLayoutError(f"фаза {phase_id} не имеет объявленного статуса") from exc


def phase_context_path(plan_dir, phase_id, *, reader: str) -> Path:
    """Resolve a phase carrier while keeping terminal phases off live reader paths."""
    if reader not in read_path_spec().get("paths", {}):
        raise PlanLayoutError(f"неизвестный читатель пути: {reader!r}")
    if reader != "auditor" and is_terminal_phase(plan_dir, phase_id):
        raise PlanLayoutError(f"{reader}: терминальная фаза {phase_id} не входит в живой путь")
    carrier_id = "phase-index" if layout_version(plan_dir) == "v2" else "legacy-phase-monolith"
    return carrier_path(plan_dir, carrier_id, phase_id=phase_id)


def slots(plan_dir, reader: str) -> tuple[ResolvedSlot, ...]:
    """Resolve declared static and phase-context slots for a reader.

    Dynamic item, bundle, and optional closure slots need an explicit target and
    are intentionally not guessed here.  The function is consequently useful
    for the declaration-level predicate that proves terminal phase carriers do
    not leak into any live path.
    """
    paths = read_path_spec().get("paths", {})
    if reader not in paths:
        raise PlanLayoutError(f"неизвестный читатель пути: {reader!r}")
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
        raise PlanLayoutError("item-spec files существуют только в Layout v2")
    directory = phase_path(plan_dir, phase_id).parent
    result = []
    for path in directory.glob("*.md"):
        match = _ITEM_SPEC_FILE.match(path.name)
        if not match:
            continue
        if match.group(1) != phase_id:
            raise PlanLayoutError(
                f"файл ТЗ {path.name} имеет префикс {match.group(1)}, а каталог фазы — {phase_id}")
        result.append((int(match.group(2)), path))
    return [path for _number, path in sorted(result)]


def plan_core_path(plan_dir) -> Path:
    return carrier_path(plan_dir, "legacy-plan-monolith" if layout_version(plan_dir) == "v1" else "plan-core")
