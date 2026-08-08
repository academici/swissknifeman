"""Deterministic owner status view for layout-v2 executable plans."""
from __future__ import annotations

import json
import re
from pathlib import Path

from task import plan_layout, plan_projection


class StatusError(ValueError):
    """The status projection cannot be assembled or read safely."""


_META_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$")
_ITEM_HEADER = re.compile(r"^###\s+(P\d+\.\d+)\s+—\s+(.+?)\s*$")
_FIELD = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$")
_PHASE_HEADER = re.compile(r"^##\s+Phase\s+(P\d+)\s*$")

STATUS_DONE = "🟢 Done"
STATUS_DEVIATIONS = "🟠 Done with deviations"
STATUS_BLOCKED = "🔴 Blocked"
STATUS_PROGRESS = "🟡 In progress"
STATUS_NOT_STARTED = "⬜ Not started"
_STATUSES = frozenset((STATUS_DONE, STATUS_DEVIATIONS, STATUS_BLOCKED,
                       STATUS_PROGRESS, STATUS_NOT_STARTED))
_STATUS_META = ("Version", "Status", "Last Updated")
_BOARD_COLUMNS = ("Phase", "Title", "Items 🟢/всего", "Status")
_ITEM_COLUMNS = ("ID", "Title", "Status", "Updated")
_UPDATE_COLUMNS = ("Дата", "Кто (role/model)", "Что")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StatusError(f"носитель статуса не читается: {path}") from exc


def _table(headers, rows) -> str:
    return "\n".join((
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(":--" for _ in headers) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ))


def _core_meta(plan_dir: Path) -> dict[str, str]:
    text = _read(plan_dir / "plan.md")
    result = {}
    for line in text.splitlines():
        match = _META_ROW.match(line)
        if match:
            result[match.group(1).strip()] = match.group(2).strip()
    return result


def _item(path: Path) -> tuple[str, str, dict[str, str]]:
    lines = _read(path).splitlines()
    header = next((match for line in lines if (match := _ITEM_HEADER.match(line))), None)
    if header is None:
        raise StatusError(f"файл ТЗ не несёт канонический заголовок item: {path}")
    state_path = path.with_name(path.stem + ".state.md")
    fields = {match.group(1): match.group(2).strip()
              for line in _read(state_path).splitlines()
              if (match := _FIELD.match(line))}
    status = fields.get("Status")
    if status not in _STATUSES:
        raise StatusError(f"{state_path}: недопустимый Status {status!r}")
    return header.group(1), header.group(2), fields


def _phase_status(statuses: list[str]) -> str:
    if any(status == STATUS_BLOCKED for status in statuses):
        return STATUS_BLOCKED
    if statuses and all(status == STATUS_DONE for status in statuses):
        return STATUS_DONE
    if any(status in (STATUS_PROGRESS, STATUS_DEVIATIONS) for status in statuses):
        return STATUS_PROGRESS
    return STATUS_NOT_STARTED


def _journal_rows(path: Path) -> tuple[list[tuple[str, str, str]], str]:
    if not path.is_file():
        return [], "—"
    rows = []
    last_updated = "—"
    for number, raw in enumerate(_read(path).splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StatusError(f"{path}:{number}: журнал невалиден") from exc
        ts = str(entry.get("ts") or "")
        if not ts:
            raise StatusError(f"{path}:{number}: у записи нет ts")
        last_updated = max(last_updated, ts[:10]) if last_updated != "—" else ts[:10]
        note = str(entry.get("note") or "—")
        what = " · ".join(part for part in (str(entry.get("command") or "—"),
                                              str(entry.get("result") or "—"), note) if part)
        rows.append((ts[:10], str(entry.get("actor") or "—"), what))
    return rows, last_updated


def status_model(plan_dir) -> dict:
    """Assemble the owner-facing facts from v2 sources, without writing files."""
    plan_dir = Path(plan_dir)
    if plan_layout.layout_version(plan_dir) != "v2":
        raise StatusError("status.md существует только для Layout v2")
    core = _core_meta(plan_dir)
    phases = []
    input_paths = [plan_dir / "plan.md"]
    for phase_id, phase_path in plan_layout.phase_paths(plan_dir).items():
        input_paths.append(phase_path)
        items = []
        for spec_path in plan_layout.item_spec_paths(plan_dir, phase_id):
            item_id, title, state = _item(spec_path)
            state_path = spec_path.with_name(spec_path.stem + ".state.md")
            input_paths.extend((spec_path, state_path))
            items.append({"id": item_id, "title": title, "status": state["Status"],
                          "updated": "—", "state": state})
        phases.append({"id": phase_id, "title": phase_path.read_text(encoding="utf-8").splitlines()[0]
                       .split(" — ", 1)[-1], "items": items,
                       "status": _phase_status([item["status"] for item in items])})
    journal = plan_dir / "journal.jsonl"
    journal_rows, last_updated = _journal_rows(journal)
    if journal.is_file():
        input_paths.append(journal)
    for phase in phases:
        for item in phase["items"]:
            item["updated"] = last_updated
    plan_status = _phase_status([phase["status"] for phase in phases])
    return {"core": core, "phases": phases, "journal_rows": journal_rows,
            "meta": {"Version": "—", "Status": plan_status, "Last Updated": last_updated},
            "input_paths": input_paths}


def render_status(plan_dir) -> str:
    plan_dir = Path(plan_dir)
    model = status_model(plan_dir)
    digest = plan_projection.inputs_sha256(model["input_paths"], root=plan_dir)
    metadata = plan_projection.metadata_block(
        projection="status-view", projection_version="v1", source_scope="plan core + phases + journal",
        through=model["meta"]["Last Updated"], inputs_sha256_value=digest,
        generated_by="task plan-views status")
    board = []
    phase_sections = []
    for phase in model["phases"]:
        done = sum(item["status"] == STATUS_DONE for item in phase["items"])
        board.append((phase["id"], phase["title"], f"{done}/{len(phase['items'])}", phase["status"]))
        phase_sections.extend((f"## Phase {phase['id']}", "", _table(
            _ITEM_COLUMNS, [(item["id"], item["title"], item["status"], item["updated"])
                            for item in phase["items"]]), ""))
    gates = []
    for phase in model["phases"]:
        for item in phase["items"]:
            if item["state"].get("Escalation Needed", "").lower() == "yes":
                gates.append(f"- {item['id']}: escalation")
            if item["state"].get("Known Deviations", "—") not in ("", "—"):
                gates.append(f"- {item['id']}: known deviation")
    body = "\n\n".join((
        "## 0. Meta\n\n" + _table(("Поле", "Значение"),
                                      [(field, model["meta"][field]) for field in _STATUS_META]),
        "## 4. Phase Index & Status Board\n\n" + _table(_BOARD_COLUMNS, board),
        "\n".join(phase_sections).rstrip(),
        "## 6. Update Log\n\n" + _table(_UPDATE_COLUMNS, model["journal_rows"] or [("—", "—", "Нет записей")]),
        "## Owner Gates\n\n" + "\n".join(gates or ["- —"]),
    ))
    return plan_projection.rendered_file(metadata=metadata, title="Статус плана", body=body)


def build_status(plan_dir, *, check=False) -> Path:
    plan_dir = Path(plan_dir)
    try:
        target = plan_layout.carrier_path(plan_dir, "status-view")
    except plan_layout.PlanLayoutError as exc:
        raise StatusError(f"не удалось разрешить status-view: {exc}") from exc
    try:
        plan_projection.write_or_check(target, render_status(plan_dir), check=check)
    except plan_projection.ProjectionError as exc:
        raise StatusError(str(exc)) from exc
    return target


def parse_status_view(plan_dir) -> tuple[dict[str, tuple[str, int]], list[tuple[dict, int]]]:
    """Read only the fields plan_lint needs from an already generated status view."""
    plan_dir = Path(plan_dir)
    try:
        path = plan_layout.carrier_path(plan_dir, "status-view")
    except plan_layout.PlanLayoutError as exc:
        raise StatusError(str(exc)) from exc
    lines = _read(path).splitlines()
    meta, board = {}, []
    section = None
    headers = None
    for lineno, line in enumerate(lines, start=1):
        if line.startswith("## "):
            section = line[3:].strip()
            headers = None
            continue
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(cell.startswith(":") or cell.startswith("-") for cell in cells):
            continue
        if headers is None:
            headers = cells
            continue
        if section == "0. Meta" and headers == ["Поле", "Значение"] and len(cells) == 2:
            meta[cells[0]] = (cells[1], lineno)
        if section == "4. Phase Index & Status Board" and headers == list(_BOARD_COLUMNS) and len(cells) == 4:
            board.append((dict(zip(_BOARD_COLUMNS, cells)), lineno))
    missing = [field for field in _STATUS_META if field not in meta]
    if missing:
        raise StatusError(f"{path}: нет полей владельческого вида: {', '.join(missing)}")
    if not board:
        raise StatusError(f"{path}: нет доски фаз")
    return meta, board
