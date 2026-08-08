"""Deterministic, on-demand history projection for Layout-v2 plan items."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from task import journal, plan_decisions, plan_layout, plan_projection


class HistoryError(ValueError):
    """A declared history input is unavailable or violates its frozen contract."""


_ITEM_RE = re.compile(r"^P\d+\.\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SOURCE_RANK = {"journal": 0, "decisions": 1, "findings": 2}


@dataclass(frozen=True)
class HistoryRecord:
    source: str
    identity: str
    event_time: datetime
    payload: dict
    path: Path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HistoryError(f"вход истории не читается: {path}") from exc


def _event_time(value: str, *, path: Path, field: str, date_only: bool = False) -> datetime:
    if not isinstance(value, str):
        raise HistoryError(f"{path}: {field} должен быть строкой времени")
    if date_only:
        if not _DATE_RE.fullmatch(value):
            raise HistoryError(f"{path}: {field} должен быть ISO-датой")
        value = value + "T00:00:00Z"
    elif not _TIMESTAMP_RE.fullmatch(value):
        raise HistoryError(f"{path}: {field} должен быть UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HistoryError(f"{path}: {field} содержит несуществующую дату") from exc


def _journal_records(plan_dir: Path, item_id: str) -> tuple[list[HistoryRecord], Path]:
    path = plan_layout.carrier_path(plan_dir, "journal")
    records = []
    for line_number, raw in enumerate(_read(path).splitlines(), 1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HistoryError(f"{path}:{line_number}: журнал невалиден") from exc
        try:
            journal.validate_entry(entry)
        except journal.JournalValidationError as exc:
            raise HistoryError(f"{path}:{line_number}: журнал не проходит sealed schema: {exc}") from exc
        if entry["plan_id"] != plan_dir.name:
            raise HistoryError(f"{path}:{line_number}: plan_id не совпадает с каталогом плана")
        if entry["item_id"] != item_id:
            continue
        identity = f"{line_number}:{journal.line_sha256(raw)}"
        records.append(HistoryRecord(
            "journal", identity, _event_time(entry["ts"], path=path, field="ts"), entry, path))
    return records, path


def _findings(plan_dir: Path, item_id: str) -> tuple[list[HistoryRecord], list[Path]]:
    directory = plan_dir / "findings"
    if not directory.is_dir():
        raise HistoryError(f"каталог item-scoped findings отсутствует: {directory}")
    records, inputs = [], []
    for path in sorted(directory.rglob("*.md")):
        text = _read(path)
        match = _FRONTMATTER_RE.match(text)
        if not match:
            continue
        fields = {}
        for line in match.group(1).splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if ":" not in line or line.startswith((" ", "\t")):
                raise HistoryError(f"{path}: недопустимая строка frontmatter {line!r}")
            key, value = line.split(":", 1)
            key = key.strip()
            if key in fields:
                raise HistoryError(f"{path}: повторный ключ frontmatter {key!r}")
            fields[key] = value.strip().strip("'\"")
        if fields.get("item") != item_id:
            continue
        if "date" not in fields:
            raise HistoryError(f"{path}: item-scoped finding не несёт date")
        relative = path.relative_to(plan_dir).as_posix()
        records.append(HistoryRecord(
            "findings", relative, _event_time(fields["date"], path=path, field="date", date_only=True),
            {"item": item_id, "date": fields["date"], "path": relative}, path))
        inputs.append(path)
    return records, inputs


def _decision_records(plan_dir: Path, item_id: str) -> tuple[list[HistoryRecord], list[Path]]:
    decisions = plan_decisions.load_decisions(plan_dir)
    selected = [decision for decision in decisions if decision.item == item_id]
    records = [HistoryRecord(
        "decisions", decision.identifier,
        _event_time(decision.date, path=decision.path, field="date", date_only=True),
        {"id": decision.identifier, "date": decision.date, "status": decision.status,
         "item": decision.item, "supersedes": list(decision.supersedes),
         "superseded_by": decision.superseded_by}, decision.path)
        for decision in selected]
    return records, [decision.path for decision in selected]


def history_records(plan_dir, item_id: str) -> tuple[list[HistoryRecord], list[Path]]:
    plan_dir = Path(plan_dir)
    if not _ITEM_RE.fullmatch(item_id):
        raise HistoryError("item должен иметь форму Pn.m")
    if plan_layout.layout_version(plan_dir) != "v2":
        raise HistoryError("исторический вид существует только для Layout v2")
    journal_records, journal_path = _journal_records(plan_dir, item_id)
    decision_records, decision_paths = _decision_records(plan_dir, item_id)
    finding_records, finding_paths = _findings(plan_dir, item_id)
    records = journal_records + decision_records + finding_records
    records.sort(key=lambda record: (record.event_time, _SOURCE_RANK[record.source], record.identity))
    return records, [journal_path, *decision_paths, *finding_paths]


def _record_line(record: HistoryRecord) -> str:
    stamp = record.event_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    if record.source == "journal":
        return (f"| {stamp} | journal | `{record.identity}` | {record.payload['result']} |")
    if record.source == "decisions":
        return (f"| {stamp} | decisions | `{record.payload['id']}` | "
                f"{record.payload['status']} |")
    return f"| {stamp} | findings | `{record.identity}` | finding |"


def render_history(plan_dir, item_id: str) -> str:
    plan_dir = Path(plan_dir)
    records, inputs = history_records(plan_dir, item_id)
    through = (records[-1].event_time.strftime("%Y-%m-%dT%H:%M:%SZ")
               if records else "empty")
    metadata = plan_projection.metadata_block(
        projection="history", projection_version="1.0.0",
        source_scope=json.dumps({"item": item_id, "sources": ["journal", "decisions", "findings"]}, sort_keys=True),
        through=through,
        inputs_sha256_value=plan_projection.inputs_sha256(inputs, root=plan_dir),
        generated_by="task plan-views history")
    lines = ["| Time | Source | Identity | Status |", "|:--|:--|:--|:--|"]
    lines.extend(_record_line(record) for record in records)
    if not records:
        lines.append("| — | — | — | Нет записей |")
    return plan_projection.rendered_file(
        metadata=metadata, title=f"История {item_id}", body="\n".join(lines))


def materialize_history(plan_dir, item_id: str, output=None, *, check=False) -> Path:
    plan_dir = Path(plan_dir)
    target = Path(output) if output else plan_layout.carrier_path(plan_dir, "history-view", item_id=item_id)
    try:
        plan_projection.write_or_check(target, render_history(plan_dir, item_id), check=check)
    except plan_projection.ProjectionError as exc:
        raise HistoryError(str(exc)) from exc
    return target
