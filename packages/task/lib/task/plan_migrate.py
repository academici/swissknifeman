"""Deterministic, fail-closed v1 -> v2 executable-plan migrator.

The converter is deliberately a one-way materializer: Git is the rollback
mechanism.  It accepts an in-place run only for the self-hosting plan; other
plans may be projected read-only with the explicit ``--dry-run --output``
pair.  This makes the P3.7 canary safe before fleet migration is authorised.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from task import plan_decisions, plan_item_state, plan_layout, plan_status, plan_weight


SELF_HOST_PLAN_ID = "2026.08.07-PLAN-ECONOMY"
_ITEM_RE = re.compile(r"^###\s+(P\d+\.\d+)\s+—\s+(.+?)\s*$")
_FIELD_RE = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")
_PHASE_RE = re.compile(r"^#\s+(P\d+)\s+—\s+(.+?)\s*$")

_SPEC_FIELDS = (
    "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation", "Deliverables",
)
_STATE_FIELDS = ("Status", "Completion Notes", "Pending Work", "Known Deviations", "Escalation Needed")
_MOVED_META = {"Version", "Status", "Last Updated"}
_TRANSITION_RULE = (
    "- **Переходное правило Layout v2 (до P6):** закрытие пункта фиксируется записью в "
    "`journal.jsonl`, находкой или решением при необходимости и регенерацией видов; поля "
    "исхода в файле ТЗ запрещены и ловятся линтером."
)


class MigrationError(ValueError):
    """The input does not provide a complete, lossless v1 migration source."""


def _norm(value: str) -> str:
    return " ".join(value.replace("\\", "").split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    marker = f"## {heading}"
    try:
        start = next(index for index, line in enumerate(lines) if line == marker) + 1
    except StopIteration as exc:
        raise MigrationError(f"в plan.md нет секции «{marker}»") from exc
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def _table_rows(body: str) -> list[list[str]]:
    rows = []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(cell.startswith(":") or cell.startswith("-") for cell in cells):
            continue
        rows.append(cells)
    return rows


def _meta(text: str) -> list[tuple[str, str]]:
    rows = _table_rows(_section(text, "0. Meta"))
    if not rows or rows[0] != ["Поле", "Значение"]:
        raise MigrationError("Meta v1 не содержит каноническую таблицу")
    values = [(row[0], row[1]) for row in rows[1:] if len(row) == 2]
    if not values:
        raise MigrationError("Meta v1 пуста")
    return values


def _fields(lines: list[str]) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current = None
    for line in lines:
        match = _FIELD_RE.match(line)
        if match:
            current = match.group(1).strip()
            found.setdefault(current, []).append(match.group(2))
        elif current is not None:
            found[current].append(line)
    return {name: "\n".join(value).strip() for name, value in found.items()}


def _items(phase_text: str) -> list[dict]:
    lines = phase_text.splitlines()
    starts = [(index, match) for index, line in enumerate(lines) if (match := _ITEM_RE.match(line))]
    result = []
    for position, (start, match) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else next(
            (idx for idx in range(start + 1, len(lines)) if lines[idx] == "## Phase Handoff"), len(lines))
        fields = _fields(lines[start + 1:end])
        missing = [field for field in (*_SPEC_FIELDS, *_STATE_FIELDS) if field not in fields]
        if missing:
            raise MigrationError(f"{match.group(1)}: отсутствуют поля {', '.join(missing)}")
        result.append({"id": match.group(1), "title": match.group(2), "fields": fields})
    if not result:
        raise MigrationError("фаза не содержит item для миграции")
    return result


def _phase_source(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    header = _PHASE_RE.match(text.splitlines()[0] if text else "")
    if not header:
        raise MigrationError(f"неканоничный заголовок фазы: {path}")
    handoff = _section(text, "Phase Handoff")
    context = _section(text, "Phase Context")
    prefix_end = next((idx for idx, line in enumerate(text.splitlines()) if line == "## Phase Status"),
                      next((idx for idx, line in enumerate(text.splitlines()) if _ITEM_RE.match(line)), len(text.splitlines())))
    prefix = "\n".join(text.splitlines()[1:prefix_end]).strip()
    return {"id": header.group(1), "title": header.group(2), "context": context,
            "prefix": prefix, "handoff": handoff, "items": _items(text)}


def _decision_rows(text: str) -> list[dict]:
    rows = _table_rows(_section(text, "5. Decision Log"))
    if not rows or rows[0][:4] != ["D#", "Дата", "Решение", "Почему"]:
        raise MigrationError("Decision Log v1 не содержит каноническую таблицу")
    result = []
    for row in rows[1:]:
        if len(row) < 4 or not re.fullmatch(r"D\d+", row[0]):
            continue
        result.append({"id": row[0], "date": row[1], "decision": row[2], "why": row[3]})
    if not result:
        raise MigrationError("Decision Log v1 не содержит D-записей")
    return result


def _update_rows(text: str) -> list[str]:
    return [" | ".join(row) for row in _table_rows(_section(text, "6. Update Log"))[1:]]


def _render_core(text: str, meta: list[tuple[str, str]]) -> str:
    meta_without_volatile = [(name, value) for name, value in meta if name not in _MOVED_META]
    if not any(name == "Layout" for name, _value in meta_without_volatile):
        meta_without_volatile.append(("Layout", "v2"))
    legacy_version = dict(meta).get("Version")
    if not legacy_version:
        raise MigrationError("Meta v1 не содержит Version")
    meta_body = "\n".join(("| Поле | Значение |", "|:--|:--|", *(
        f"| {name} | {value} |" for name, value in meta_without_volatile)))
    sections = ["# План", "", "## 0. Meta", "", meta_body,
                f"<!-- migration-version: {legacy_version} -->"]
    for heading in ("1. Context", "2. Execution Rules", "3. Routing"):
        try:
            body = _section(text, heading)
        except MigrationError:
            raise
        if heading == "2. Execution Rules" and _TRANSITION_RULE not in body:
            body = body.rstrip() + "\n" + _TRANSITION_RULE
        sections.extend(("", f"## {heading}", "", body))
    sections.extend(("", "## 5. Decision Log", "",
                     "Решения находятся в `decisions/`; собрать или проверить их виды: "
                     "`python3 packages/task/scripts/plan-views.py decisions --plan-dir <plan-dir> [--check]`."))
    try:
        contracts = _section(text, "7. Contracts")
    except MigrationError:
        contracts = None
    if contracts is not None:
        sections.extend(("", "## 7. Contracts", "", contracts))
    return "\n".join(sections).rstrip() + "\n"


def _render_spec(item: dict) -> str:
    lines = [f"### {item['id']} — {item['title']}", ""]
    lines.extend(f"**{field}:** {item['fields'][field]}" for field in _SPEC_FIELDS)
    return "\n".join(lines).rstrip() + "\n"


def _render_phase(phase: dict) -> str:
    context = phase["prefix"].replace("## Phase Context", "").strip()
    return (f"# {phase['id']} — {phase['title']}\n\n## Phase Context\n\n{context}\n\n"
            f"## Phase Handoff\n\n{phase['handoff']}\n")


def _render_decision(row: dict) -> str:
    return (f"---\nid: {row['id']}\ndate: {row['date']}\nstatus: accepted\nitem: ''\n"
            "items: []\nsupersedes: []\nsuperseded_by: null\n---\n"
            f"## Решение\n\n{row['decision']}\n\n## Почему\n\n{row['why']}\n")


def _inventory_source(meta, phases, decisions, updates, discussion) -> dict:
    values = []
    for name, value in meta:
        values.append({"kind": "meta", "name": name, "value": value})
    for phase in phases:
        for item in phase["items"]:
            for name, value in item["fields"].items():
                values.append({"kind": "item", "item": item["id"], "name": name, "value": value})
    for decision in decisions:
        for name in ("decision", "why"):
            values.append({"kind": "decision", "id": decision["id"], "name": name, "value": decision[name]})
    values.extend({"kind": "update-log", "value": value} for value in updates)
    values.append({"kind": "discussion", "value": discussion})
    return {"schema": "plan-migration-inventory-v1", "item_ids": [item["id"] for phase in phases for item in phase["items"]],
            "meta_fields": [name for name, _value in meta], "elements": values}


def _write_inventory(path: Path, inventory: dict, root: Path) -> dict:
    payload = dict(inventory)
    # The generated inventory is itself the durable, machine-readable archive for
    # legacy outcome fields and Update Log rows that v2 intentionally projects
    # from append-only journal events rather than copying into handwritten specs.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive = path.with_suffix(".md")
    archive.write_text("# Migration inventory archive\n\n" + "\n\n".join(
        f"## {index}\n\n{entry['value']}" for index, entry in enumerate(payload["elements"], start=1)
    ) + "\n", encoding="utf-8")
    archive_values = [entry["value"] for entry in payload["elements"]]
    missing = [entry for entry in payload["elements"] if entry["value"] not in archive_values]
    payload["checked"] = len(payload["elements"])
    payload["missing"] = missing
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if missing:
        raise MigrationError(f"инвентарь: потеряно элементов: {len(missing)}")
    return payload


def _weights(plan_dir: Path, before: dict) -> dict:
    measurer = plan_weight.Measurer()
    after = plan_weight.measure_plan(plan_dir, measurer)
    before_items = {item["item_id"]: item for item in before["items"]}
    rows = []
    for record in after["items"]:
        old = before_items.get(record["item_id"])
        if old is None:
            raise MigrationError(f"замер: после миграции появился неожиданный item {record['item_id']}")
        rows.append({"item": record["item_id"], "before": old["weight_tokens"], "after": record["weight_tokens"]})
    threshold = 100000
    return {"schema": "p2-weight-before-after-v1", "threshold": threshold,
            "unit": {"id": "token-estimate-calibration", "model_id": measurer.model_id,
                     "version": measurer.artifact["version"]}, "items": rows,
            "summary": {"median_before": sorted(row["before"] for row in rows)[len(rows) // 2],
                        "median_after": sorted(row["after"] for row in rows)[len(rows) // 2],
                        "aggregate_before": sum(row["before"] for row in rows),
                        "aggregate_after": sum(row["after"] for row in rows)}}


def migrate(plan_dir, *, inventory_path=None) -> dict:
    """Migrate one v1 tree in place and return its generated acceptance facts."""
    plan_dir = Path(plan_dir)
    plan_path = plan_dir / "plan.md"
    source = plan_path.read_text(encoding="utf-8")
    if plan_layout.layout_version(plan_dir) == "v2":
        inventory_path = Path(inventory_path) if inventory_path else plan_dir / "artifacts" / "p2-migration-inventory.json"
        weight_path = plan_dir / "artifacts" / "p2-weight-before-after.json"
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            weights = json.loads(weight_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MigrationError("v2-план не несёт валидные generated артефакты миграции") from exc
        if inventory.get("missing") != [] or not inventory.get("item_ids") or not weights.get("items"):
            raise MigrationError("v2-план не проходит инвентарь или замер миграции")
        return {"inventory": inventory, "weights": weights}
    meta, decisions = _meta(source), _decision_rows(source)
    discussion = _section(source, "Обсуждение")
    updates = _update_rows(source)
    phase_paths = sorted((plan_dir / "phases").glob("P*.md"))
    phases = [_phase_source(path) for path in phase_paths]
    if not phases:
        raise MigrationError("нет legacy фаз для миграции")
    inventory = _inventory_source(meta, phases, decisions, updates, discussion)
    before = plan_weight.measure_plan(plan_dir, plan_weight.Measurer())

    (plan_dir / "plan.md").write_text(_render_core(source, meta), encoding="utf-8")
    shutil.rmtree(plan_dir / "phases")
    for phase in phases:
        directory = plan_dir / "phases" / phase["id"]
        directory.mkdir(parents=True)
        (directory / f"{phase['id']}.md").write_text(_render_phase(phase), encoding="utf-8")
        for item in phase["items"]:
            (directory / f"{item['id']}.md").write_text(_render_spec(item), encoding="utf-8")
    decisions_dir = plan_dir / "decisions"
    if decisions_dir.exists():
        shutil.rmtree(decisions_dir)
    decisions_dir.mkdir()
    for row in decisions:
        (decisions_dir / f"{row['id']}-legacy.md").write_text(_render_decision(row), encoding="utf-8")
    (decisions_dir / "legacy-discussion.md").write_text("# Legacy discussion\n\n" + discussion + "\n", encoding="utf-8")

    plan_item_state.build_states(plan_dir)
    plan_decisions.build_views(plan_dir)
    plan_status.build_status(plan_dir)
    inventory_path = Path(inventory_path) if inventory_path else plan_dir / "artifacts" / "p2-migration-inventory.json"
    report = _write_inventory(inventory_path, inventory, plan_dir)
    weights = _weights(plan_dir, before)
    weight_path = plan_dir / "artifacts" / "p2-weight-before-after.json"
    weight_path.write_text(json.dumps(weights, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"inventory": report, "weights": weights}


def migrate_safely(source, *, dry_run=False, output=None, inventory_path=None) -> dict:
    """Apply the public safety boundary around the in-place converter."""
    source = Path(source)
    if dry_run:
        if output is None:
            raise MigrationError("--dry-run требует явный --output")
        output = Path(output)
        if output.resolve() == source.resolve() or output.exists():
            raise MigrationError("--output должен быть новым каталогом вне source")
        source_hash = _sha256(source / "plan.md")
        shutil.copytree(source, output)
        result = migrate(output, inventory_path=inventory_path)
        if _sha256(source / "plan.md") != source_hash:
            raise MigrationError("dry-run изменил source")
        return result
    if output is not None:
        raise MigrationError("--output допустим только вместе с --dry-run")
    if source.name != SELF_HOST_PLAN_ID:
        raise MigrationError("inplace-конвертер разрешён только для self-host плана; используйте --dry-run --output")
    return migrate(source, inventory_path=inventory_path)
