"""Immutable decision records and their four deterministic navigation views."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from task import plan_layout, plan_projection


class DecisionError(ValueError):
    """A decision carrier violates the frozen v2 contract."""


STATUSES = frozenset(("proposed", "accepted", "rejected", "superseded"))
_DECISION_NAME_RE = re.compile(r"^(D\d+)-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
_ID_RE = re.compile(r"^D\d+$")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Decision:
    identifier: str
    date: str
    status: str
    item: str
    items: tuple[str, ...]
    supersedes: tuple[str, ...]
    superseded_by: str | None
    body: str
    path: Path

    @property
    def decision_text(self) -> str:
        match = re.search(r"^## Solution\s*\n(.*?)(?=^## |\Z)", self.body,
                          flags=re.MULTILINE | re.DOTALL)
        return " ".join(match.group(1).split()) if match else "—"


def _scalar(value: str):
    value = value.strip()
    if value in ("null", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [part.strip().strip("'\"") for part in inner.split(",")]
    return value.strip("'\"")


def parse_frontmatter(text: str, *, path: Path) -> tuple[dict, str]:
    """Parse the deliberately small YAML subset used by decision records."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise DecisionError(f"{path}: no YAML-frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            raise DecisionError(f"{path}: invalid string frontmatter {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[a-z_]+", key) or key in fields:
            raise DecisionError(f"{path}: invalid or duplicate key {key!r}")
        fields[key] = _scalar(value)
    return fields, text[match.end():]


def _string_list(value, *, field: str, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(entry, str) and entry for entry in value):
        raise DecisionError(f"{path}: {field} must be a list of non-empty strings")
    return tuple(value)


def parse_decision(path) -> Decision:
    path = Path(path)
    match = _DECISION_NAME_RE.match(path.name)
    if not match:
        raise DecisionError(f"{path}: name must be of the form D<NNN>-<slug>.md")
    try:
        fields, body = parse_frontmatter(path.read_text(encoding="utf-8"), path=path)
    except OSError as exc:
        raise DecisionError(f"{path}: entry not readable") from exc
    required = ("id", "date", "status", "item", "items", "supersedes", "superseded_by")
    missing = [field for field in required if field not in fields]
    if missing:
        raise DecisionError(f"{path}: no required fields {', '.join(missing)}")
    identifier = fields["id"]
    if not isinstance(identifier, str) or identifier != match.group(1) or not _ID_RE.fullmatch(identifier):
        raise DecisionError(f"{path}: id does not match the file name")
    if not isinstance(fields["date"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields["date"]):
        raise DecisionError(f"{path}: date should be ISO-date")
    try:
        date.fromisoformat(fields["date"])
    except ValueError as exc:
        raise DecisionError(f"{path}: date must be a calendar-valid ISO date") from exc
    if fields["status"] not in STATUSES:
        raise DecisionError(f"{path}: unknown status {fields['status']!r}")
    if not isinstance(fields["item"], str):
        raise DecisionError(f"{path}: item must be a string")
    items = _string_list(fields["items"], field="items", path=path)
    if fields["item"] and fields["item"] not in items:
        raise DecisionError(f"{path}: item must be included in items")
    supersedes = _string_list(fields["supersedes"], field="supersedes", path=path)
    successor = fields["superseded_by"]
    if successor is not None and (not isinstance(successor, str) or not _ID_RE.fullmatch(successor)):
        raise DecisionError(f"{path}: superseded_by should be D<NNN> or null")
    headings = {heading for heading in _HEADING_RE.findall(body)}
    if not {"Solution", "Why"}.issubset(headings):
        raise DecisionError(f"{path}: the body must bear ## Solution and ## Why")
    if supersedes and "Consequences" not in headings:
        raise DecisionError(f"{path}: supersedes requires ## Consequences")
    if fields["status"] == "superseded" and not successor:
        raise DecisionError(f"{path}: superseded requires superseded_by")
    if successor and fields["status"] != "superseded":
        raise DecisionError(f"{path}: superseded_by is only valid for status=superseded")
    return Decision(identifier, fields["date"], fields["status"], fields["item"], items,
                    supersedes, successor, body, path)


def load_decisions(plan_dir) -> tuple[Decision, ...]:
    plan_dir = Path(plan_dir)
    try:
        pattern = plan_layout.carrier_glob(plan_dir, "decision-record")
    except plan_layout.PlanLayoutError as exc:
        raise DecisionError(f"failed to resolve solution media: {exc}") from exc
    directory = pattern.parent
    if not directory.is_dir():
        raise DecisionError(f"solution directory missing: {directory}")
    paths = [path for path in directory.glob(pattern.name)
             if path.is_file() and _DECISION_NAME_RE.match(path.name)]
    decisions = tuple(sorted((parse_decision(path) for path in paths),
                             key=lambda item: int(item.identifier[1:])))
    by_id = {decision.identifier: decision for decision in decisions}
    if len(by_id) != len(decisions):
        raise DecisionError("solution identifiers are repeated")
    for decision in decisions:
        for predecessor_id in decision.supersedes:
            predecessor = by_id.get(predecessor_id)
            if predecessor is None:
                raise DecisionError(f"{decision.identifier}: supersedes refers to a missing {predecessor_id}")
            if predecessor.superseded_by != decision.identifier or predecessor.status != "superseded":
                raise DecisionError(f"{decision.identifier} and {predecessor_id}: substitution relationship is not reciprocal")
        if decision.superseded_by:
            successor = by_id.get(decision.superseded_by)
            if successor is None or decision.identifier not in successor.supersedes:
                raise DecisionError(f"{decision.identifier} and {decision.superseded_by}: "
                                    "connection superseded_by is specified non-reciprocally")
    return decisions


def _table(decisions: tuple[Decision, ...]) -> str:
    lines = ["| ID | Date | Status | Items | Solution |", "|:--|:--|:--|:--|:--|"]
    for decision in decisions:
        lines.append("| " + " | ".join((decision.identifier, decision.date, decision.status,
                    ", ".join(decision.items) or "—", decision.decision_text)) + " |")
    if not decisions:
        lines.append("| — | — | — | — | No entries |")
    return "\n".join(lines)


def rendered_views(plan_dir) -> dict[Path, str]:
    plan_dir = Path(plan_dir)
    decisions = load_decisions(plan_dir)
    try:
        decisions_dir = plan_layout.carrier_glob(plan_dir, "decision-record").parent
        open_questions = plan_layout.carrier_path(plan_dir, "open-questions")
    except plan_layout.PlanLayoutError as exc:
        raise DecisionError(f"failed to resolve solution view path: {exc}") from exc
    input_paths = [decision.path for decision in decisions]
    digest = plan_projection.inputs_sha256(input_paths, root=plan_dir)
    through = f"{decisions[-1].date}/{decisions[-1].identifier}" if decisions else "empty"
    groups = {
        decisions_dir / "_current.md": ("Current solutions", tuple(
            d for d in decisions if d.status == "accepted" and not d.superseded_by), "decision-current"),
        decisions_dir / "_archive.md": ("Solutions archive", tuple(
            d for d in decisions if d.status in {"superseded", "rejected"}), "decision-archive"),
        decisions_dir / "_index.md": ("Solution Index", decisions, "decision-index"),
        open_questions: ("Open forks", tuple(
            d for d in decisions if d.status == "proposed"), "decision-open-questions"),
    }
    rendered = {}
    for target, (title, selected, projection) in groups.items():
        metadata = plan_projection.metadata_block(
            projection=projection, projection_version="v1", source_scope="decisions/",
            through=through, inputs_sha256_value=digest, generated_by="task plan-views decisions")
        rendered[target] = plan_projection.rendered_file(
            metadata=metadata, title=title, body=_table(selected))
    return rendered


def build_views(plan_dir, *, check=False) -> tuple[Path, ...]:
    rendered = rendered_views(plan_dir)
    for target, expected in rendered.items():
        plan_projection.write_or_check(target, expected, check=check)
    return tuple(rendered)
