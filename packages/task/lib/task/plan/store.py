"""Plan snapshot, canonical JSON, atomic saves, plan lock and event log for layout v3 (stdlib only).

Every write goes through ``save``/``save_many``: the whole changed document is validated against its
schema first, then written in canonical form (keys in schema order, UTF-8, indent 2, trailing newline)
through a temporary file and ``os.replace``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable

from task import plan_numbering

from . import schema as _schema
from .model import SHORT_ID, PlanError, id_sort_key

LOG = "log.jsonl"
LOCK = ".lock"
ARCHIVE = plan_numbering.ARCHIVE
_UNIT_REF = re.compile(r"^(P[0-9]+\.[0-9]+)/(U[0-9]+)$")


def now() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``; tests replace this function."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _natural(name: str) -> tuple:
    try:
        return (0, id_sort_key(name))
    except ValueError:
        return (1, name)


# ---------------------------------------------------------------- paths

def phase_path(root: Path, phase_id: str) -> Path:
    return root / "phases" / phase_id / "phase.json"


def item_path(root: Path, item_id: str) -> Path:
    return root / "phases" / item_id.split(".", 1)[0] / f"{item_id}.json"


def unit_path(root: Path, item_id: str, unit_id: str) -> Path:
    return root / "phases" / item_id.split(".", 1)[0] / item_id / f"{unit_id}.json"


def decision_path(root: Path, decision_id: str) -> Path:
    return root / "decisions" / f"{decision_id}.json"


# ---------------------------------------------------------------- snapshot

@dataclass
class Plan:
    """Loaded snapshot of one plan directory. Documents are plain dicts keyed by their file-name id."""

    root: Path
    plan: dict = field(default_factory=dict)
    brief: dict = field(default_factory=dict)
    phases: dict[str, dict] = field(default_factory=dict)
    items: dict[str, dict] = field(default_factory=dict)
    decisions: dict[str, dict] = field(default_factory=dict)
    units: dict[str, dict] = field(default_factory=dict)  # key "P1.2/U1"
    problems: list[tuple[str, str]] = field(default_factory=list)  # (relative file, message)

    @property
    def repo_root(self) -> Path:
        """Repository root: the parent of ``plans/`` (or of ``plans/archive/``)."""
        parent = self.root.parent
        return parent.parent.parent if parent.name == ARCHIVE else parent.parent

    def path(self, kind: str, key: str | None = None) -> Path:
        if kind == "plan":
            return self.root / "plan.json"
        if kind == "brief":
            return self.root / "brief.json"
        if kind == "phase":
            return phase_path(self.root, key)
        if kind == "item":
            return item_path(self.root, key)
        if kind == "decision":
            return decision_path(self.root, key)
        if kind == "unit":
            match = _UNIT_REF.fullmatch(key)
            return unit_path(self.root, match[1], match[2])
        raise ValueError(f"unknown kind: {kind!r}")

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def adopt(self, other: "Plan") -> None:
        """Replace this snapshot's content with ``other`` (used after a mutation reloaded the plan)."""
        self.__dict__.update(other.__dict__)


def _read_json(root: Path, path: Path, problems: list) -> dict | None:
    rel = path.relative_to(root).as_posix()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append((rel, "file is missing"))
        return None
    except (OSError, ValueError) as exc:
        problems.append((rel, f"cannot read JSON: {exc}"))
        return None
    if not isinstance(doc, dict):
        problems.append((rel, "document must be a JSON object"))
        return None
    return doc


def load_plan(root: str | Path) -> Plan:
    """Load every JSON document of a v3 plan directory; unreadable files become ``problems``, not exceptions."""
    root = Path(root)
    if not (root / "plan.json").is_file():
        hint = " (layout v2: plan.md without plan.json)" if (root / "plan.md").is_file() else ""
        raise PlanError("PLAN_NOT_V3", f"{root} has no plan.json{hint}")
    plan = Plan(root=root)
    plan.plan = _read_json(root, root / "plan.json", plan.problems) or {}
    plan.brief = _read_json(root, root / "brief.json", plan.problems) or {}
    phases_dir = root / "phases"
    phase_dirs = sorted((p for p in phases_dir.iterdir() if p.is_dir()), key=lambda p: _natural(p.name)) \
        if phases_dir.is_dir() else []
    for phase_dir in phase_dirs:
        doc = _read_json(root, phase_dir / "phase.json", plan.problems)
        plan.phases[phase_dir.name] = doc if doc is not None else {}
        for item_file in sorted((f for f in phase_dir.glob("*.json") if f.name != "phase.json"),
                                key=lambda f: _natural(f.stem)):
            doc = _read_json(root, item_file, plan.problems)
            plan.items[item_file.stem] = doc if doc is not None else {}
        for workspace in sorted((d for d in phase_dir.iterdir() if d.is_dir()), key=lambda d: _natural(d.name)):
            for unit_file in sorted(workspace.glob("*.json"), key=lambda f: _natural(f.stem)):
                doc = _read_json(root, unit_file, plan.problems)
                plan.units[f"{workspace.name}/{unit_file.stem}"] = doc if doc is not None else {}
    decisions_dir = root / "decisions"
    if decisions_dir.is_dir():
        for decision_file in sorted(decisions_dir.glob("*.json"), key=lambda f: _natural(f.stem)):
            doc = _read_json(root, decision_file, plan.problems)
            plan.decisions[decision_file.stem] = doc if doc is not None else {}
    return plan


def plan_dirs(plans_root: Path) -> Iterable[Path]:
    for parent in (plans_root, plans_root / ARCHIVE):
        if parent.is_dir():
            for path in sorted(parent.iterdir()):
                if path.is_dir() and path.name != ARCHIVE and not path.name.startswith("."):
                    yield path


def resolve_plan_dir(ref: str | Path, plans_root: str | Path | None = None) -> Path:
    """Resolve a plan directory from a path, a plan id or a ``PLAN<N>`` short id (live, then archive)."""
    ref = str(ref)
    if not ref:
        raise PlanError("PLAN_NOT_FOUND", "empty plan reference")
    candidate = Path(ref)
    if (candidate / "plan.json").is_file():
        return candidate
    root = Path(plans_root) if plans_root is not None else plan_numbering.find_plans_root()
    for parent in (root, root / ARCHIVE):
        if (parent / ref / "plan.json").is_file():
            return parent / ref
    if SHORT_ID.fullmatch(ref):
        matches = [d for d in plan_dirs(root) if short_id_of(d) == ref]
        if len(matches) > 1:
            raise PlanError("PLAN_AMBIGUOUS", f"{ref} matches {', '.join(d.name for d in matches)}")
        if matches:
            return matches[0]
    for parent in (root, root / ARCHIVE, candidate.parent):
        if (parent / candidate.name / "plan.md").is_file():
            raise PlanError("PLAN_NOT_V3", f"{ref} is a layout v2 plan (plan.md without plan.json)")
    raise PlanError("PLAN_NOT_FOUND", f"no plan {ref!r} under {root}")


def open_plan(ref: str | Path, plans_root: str | Path | None = None) -> Plan:
    return load_plan(resolve_plan_dir(ref, plans_root))


def short_id_of(plan_dir: Path) -> str | None:
    try:
        value = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8")).get("short_id")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------- lock

class PlanLock:
    """Exclusive ``flock`` on ``<plan>/.lock``; waits up to ``timeout`` seconds, then ``PLAN_LOCKED``."""

    def __init__(self, plan_dir: str | Path, timeout: float = 30.0, poll: float = 0.05):
        self.path = Path(plan_dir) / LOCK
        self.timeout = timeout
        self.poll = poll
        self._handle = None

    def __enter__(self) -> "PlanLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise PlanError("PLAN_LOCKED", f"{self.path} is held by another process") from None
                time.sleep(self.poll)
        self._handle = handle
        return self

    def __exit__(self, *exc) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle, fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


# ---------------------------------------------------------------- canonical form and saves

def canonical_dump(doc: object, kind: str, registry: _schema.Registry | None = None) -> str:
    """Canonical text of ``doc``: keys in schema ``properties`` order, UTF-8, indent 2, trailing newline."""
    reg = registry if registry is not None else _schema.load_registry()
    node, base = reg.for_kind(kind)
    return json.dumps(_order(reg, node, base, doc), ensure_ascii=False, indent=2) + "\n"


def _order(reg: _schema.Registry, node: dict, base: str, value: Any) -> Any:
    while "$ref" in node:
        try:
            node, base = reg.resolve(node["$ref"], base)
        except LookupError:
            return value
    if "oneOf" in node:
        for branch in node["oneOf"]:
            if not _schema.validate_node(reg, branch, base, value):
                return _order(reg, branch, base, value)
        return value
    if isinstance(value, dict) and "properties" in node:
        properties = node["properties"]
        ordered = {key: _order(reg, properties[key], base, value[key]) for key in properties if key in value}
        ordered.update({key: item for key, item in value.items() if key not in properties})
        return ordered
    if isinstance(value, list) and "items" in node:
        return [_order(reg, node["items"], base, item) for item in value]
    return value


def _issue_text(label: str, issues) -> str:
    shown = "; ".join(issue.message for issue in issues[:3])
    more = f" (+{len(issues) - 3} more)" if len(issues) > 3 else ""
    return f"{label}: {len(issues)} schema issue(s): {shown}{more}"


def check_doc(doc: object, kind: str, label: str, registry: _schema.Registry | None = None) -> None:
    """Raise ``SCHEMA_INVALID`` (with the issues attached) unless ``doc`` is a valid ``kind`` document."""
    issues = _schema.validate(doc, kind, registry)
    if issues:
        raise PlanError("SCHEMA_INVALID", _issue_text(label, issues), issues)


def save_many(entries: Iterable[tuple[Path, dict, str]], registry: _schema.Registry | None = None) -> list[Path]:
    """Validate every ``(path, doc, kind)`` first, then write them all; one invalid doc writes nothing."""
    reg = registry if registry is not None else _schema.load_registry()
    prepared = []
    for path, doc, kind in entries:
        root_schema, _ = reg.for_kind(kind)
        if "updated_at" in root_schema.get("properties", {}) and isinstance(doc, dict):
            doc["updated_at"] = now()
        check_doc(doc, kind, Path(path).name, reg)
        prepared.append((Path(path), canonical_dump(doc, kind, reg)))
    for path, text in prepared:
        _atomic_write(path, text)
    return [path for path, _ in prepared]


def save(path: str | Path, doc: dict, kind: str, registry: _schema.Registry | None = None) -> Path:
    return save_many([(Path(path), doc, kind)], registry)[0]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


# ---------------------------------------------------------------- event log

def new_event(event_type: str, summary: str, actor: dict, *, item: str | None = None, phase: str | None = None,
              impact: str | None = None, next: str | None = None, refs=None, data: dict | None = None) -> dict:
    """Build a ``log-event`` document stamped with the current time."""
    event: dict[str, Any] = {"v": 1, "ts": now(), "type": event_type, "summary": summary, "actor": actor}
    for key, value in (("item", item), ("phase", phase), ("impact", impact), ("next", next),
                       ("refs", list(refs) if refs else None), ("data", data)):
        if value is not None:
            event[key] = value
    return event


def append_log(plan_dir: str | Path, event: dict, *, lock: PlanLock | None = None,
               registry: _schema.Registry | None = None) -> None:
    """Validate ``event`` and append it as one line; takes the plan lock unless the caller already holds it."""
    reg = registry if registry is not None else _schema.load_registry()
    issues = _schema.validate(event, "log-event", reg)
    if issues:
        raise PlanError("SCHEMA_INVALID", _issue_text("log event", issues), issues)
    node, base = reg.for_kind("log-event")
    line = json.dumps(_order(reg, node, base, event), ensure_ascii=False, separators=(",", ":")) + "\n"

    def write() -> None:
        with open(Path(plan_dir) / LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    if lock is not None:
        write()
    else:
        with PlanLock(plan_dir):
            write()


def log_lines(plan_dir: str | Path) -> list[tuple[int, dict | None, str | None]]:
    """``(line number, event, error)`` for every non-blank line of ``log.jsonl``; a bad line has ``event=None``."""
    path = Path(plan_dir) / LOG
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            rows.append((number, None, f"invalid JSON: {exc}"))
            continue
        rows.append((number, event, None) if isinstance(event, dict)
                    else (number, None, "event must be a JSON object"))
    return rows


def read_log(plan_dir: str | Path) -> list[dict]:
    """All events of ``log.jsonl``; a malformed line raises ``LOG_INVALID``."""
    events = []
    for number, event, error in log_lines(plan_dir):
        if error is not None:
            raise PlanError("LOG_INVALID", f"{LOG}:{number}: {error}")
        events.append(event)
    return events
