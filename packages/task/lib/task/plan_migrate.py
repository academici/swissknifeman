"""Deterministic, fail-closed v1 -> v2 executable-plan migrator.

The converter is deliberately a one-way materializer: Git is the rollback
mechanism.  It only projects a source read-only with the explicit
``--dry-run --output`` pair. Controlled apply is a separate policy/preimage-
gated staged swap; an archived plan can never become an implicit write target.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from task import journal, plan_decisions, plan_item_state, plan_layout, plan_status, plan_weight


_ITEM_RE = re.compile(r"^###\s+(P\d+\.\d+)\s+—\s+(.+?)\s*$")
_FIELD_RE = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")
_PHASE_RE = re.compile(r"^#\s+(P\d+)\s+—\s+(.+?)\s*$")
_ROUTING_ITEM_RE = re.compile(r"^P\d+\.\d+$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")

_SPEC_FIELDS = (
    "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation", "Deliverables",
)
_STATE_FIELDS = ("Status", "Completion Notes", "Pending Work", "Known Deviations", "Escalation Needed")
_MOVED_META = {"Version", "Status", "Last Updated"}
_SOURCE_ARCHIVE_RELATIVE = Path("artifacts") / "migration-source-v1"
_SOURCE_ARCHIVE_MANIFEST = "manifest.json"
_TRANSITION_RULE = (
    "- **Переходное правило Layout v2 (до P6):** закрытие пункта фиксируется записью в "
    "`journal.jsonl`, находкой или решением при необходимости и регенерацией видов; поля "
    "исхода в файле ТЗ запрещены и ловятся линтером."
)
_POLICY_SCHEMA = "urn:swissknifeman:task:layout-v1-migration-policy:v1"
_TERMINAL_STATUSES = {"🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision"}
_DEFECT_CLASSES = frozenset((
    "routing-normalization", "current-state-import", "decision-id-map",
    "skeleton-preservation", "read-budget-carrier", "semantic-handoff",
    "already-v2-admission",
))
_STATUS_RESULT = {
    "🟢 Done": "closed-green",
    "🟠 Done with deviations": "closed-deviations",
    # The sealed journal enum has no skipped result.  The import preserves the
    # exact source status in its note/inventory and projects the same terminal
    # execution class without inventing a decision event.
    "⛔ Skipped by decision": "closed-deviations",
    "🔴 Blocked": "blocked",
}


class MigrationError(ValueError):
    """The input does not provide a complete, lossless v1 migration source."""


def _norm(value: str) -> str:
    return " ".join(value.replace("\\", "").split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def _items(phase_text: str, *, allow_empty: bool = False) -> list[dict]:
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
    if not result and not allow_empty:
        raise MigrationError("фаза не содержит item для миграции")
    return result


def _phase_source(path: Path, *, compatibility: bool = False) -> dict:
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
            "prefix": prefix, "handoff": handoff,
            "items": _items(text, allow_empty=compatibility)}


def _decision_rows(text: str, *, compatibility: bool = False) -> list[dict]:
    try:
        rows = _table_rows(_section(text, "5. Decision Log"))
    except MigrationError:
        if compatibility:
            return []
        raise
    accepted_headers = (("D#", "Дата", "Решение", "Почему"),
                        ("D#", "Date", "Decision", "Why"))
    if not rows or tuple(rows[0][:4]) not in accepted_headers:
        if compatibility and rows:
            headers = rows[0]
            result = []
            for number, row in enumerate(rows[1:], start=1):
                if len(row) != len(headers):
                    continue
                values = dict(zip(headers, row))
                source_id = next((values.get(name) for name in ("D#", "ID", "Id", "id")
                                  if values.get(name)), f"row-{number}")
                date = next((values.get(name) for name in ("Дата", "Date", "date")
                             if values.get(name)), "1970-01-01")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                    date = "1970-01-01"
                decision = next((values.get(name) for name in ("Решение", "Decision", "decision")
                                 if values.get(name)), " | ".join(row))
                why = next((values.get(name) for name in ("Почему", "Why", "why")
                            if values.get(name)), "Imported noncanonical legacy decision row")
                result.append({"id": f"D{number}", "date": date, "decision": decision,
                               "why": why, "source_id": source_id})
            return result
        if compatibility and not rows:
            return []
        raise MigrationError("Decision Log v1 не содержит поддерживаемую каноническую таблицу")
    result = []
    for row in rows[1:]:
        if len(row) < 4 or not re.fullmatch(r"D\d+", row[0]):
            continue
        result.append({"id": row[0], "date": row[1], "decision": row[2], "why": row[3],
                       "source_id": row[0]})
    if not result:
        if compatibility:
            return []
        raise MigrationError("Decision Log v1 не содержит D-записей")
    return result


def _update_rows(text: str) -> list[str]:
    return [" | ".join(row) for row in _table_rows(_section(text, "6. Update Log"))[1:]]


def _legal_routing_token(value: str) -> bool:
    if _ROUTING_ITEM_RE.fullmatch(value):
        return True
    match = _ROUTING_RANGE_RE.fullmatch(value)
    return bool(match and match.group(1) == match.group(3)
                and int(match.group(2)) <= int(match.group(4)))


def _normalize_routing_rows(body: str, *, compatibility: bool = False,
                            omissions: list[dict] | None = None) -> str:
    """Split legacy comma-list Items cells without changing v2 grammar."""
    result = []
    items_column = None
    column_count = None
    for line in body.splitlines():
        if not line.startswith("|"):
            result.append(line)
            continue
        cells = line.split("|")
        values = [cell.strip() for cell in cells[1:-1]]
        if "Items" in values:
            items_column = values.index("Items") + 1
            column_count = len(cells)
            result.append(line)
            continue
        if items_column is None or len(cells) != column_count:
            result.append(line)
            continue
        if all(value.startswith(":") or value.startswith("-") for value in values):
            result.append(line)
            continue
        raw_items = cells[items_column]
        if "," not in raw_items and _legal_routing_token(raw_items.strip()):
            result.append(line)
            continue
        tokens = [token.strip() for token in raw_items.strip().split(",")]
        if compatibility:
            tokens = re.findall(
                r"P\d+\.\d+\s*[–-]\s*P\d+\.\d+|P\d+\.\d+", raw_items)
        valid = [token for token in tokens if token and _legal_routing_token(token)]
        invalid = [token for token in tokens if not token or not _legal_routing_token(token)]
        if invalid and not compatibility:
            raise MigrationError(
                f"Routing Items «{raw_items.strip()}» нельзя безопасно разбить: "
                "ожидаются только item Pn.m или возрастающие single-phase range Pn.a–Pn.b"
            )
        if invalid and omissions is not None:
            omissions.append({"source_row": line, "items": raw_items.strip(),
                              "omitted_tokens": invalid})
        if not valid:
            continue
        leading = raw_items[:len(raw_items) - len(raw_items.lstrip())]
        trailing = raw_items[len(raw_items.rstrip()):]
        for token in valid:
            projected = list(cells)
            projected[items_column] = f"{leading}{token}{trailing}"
            result.append("|".join(projected))
    return "\n".join(result)


def _render_core(text: str, meta: list[tuple[str, str]], *, compatibility: bool = False,
                 routing_omissions: list[dict] | None = None) -> str:
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
        if heading == "3. Routing":
            body = _normalize_routing_rows(
                body, compatibility=compatibility, omissions=routing_omissions)
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


def _blocked_journal_items(plan_dir: Path) -> set[str]:
    """Return items whose last durable event projects to a blocked state.

    Legacy phase tables can be stale while the journal is the authoritative
    outcome carrier.  The v2 projection therefore materializes the required
    escalation marker from the last journal event without changing the source.
    """
    path = plan_dir / journal.FILENAME
    if not path.is_file():
        return set()
    last = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MigrationError(f"journal.jsonl:{number}: невалидный JSON") from exc
        item_id = event.get("item_id")
        result = event.get("result")
        if isinstance(item_id, str) and result in plan_item_state.RESULT_STATUS:
            last[item_id] = result
    return {item_id for item_id, result in last.items()
            if plan_item_state.RESULT_STATUS[result] == "🔴 Blocked"}


def _render_spec(item: dict, *, blocked_by_journal: bool = False) -> str:
    lines = [f"### {item['id']} — {item['title']}", ""]
    if item["fields"]["Status"] == "🔴 Blocked" or blocked_by_journal:
        lines.extend((
            f"> 🔴 ESCALATION {item['id']}: migrated legacy blocked state; source outcome remains in "
            "the append-only journal and migration inventory | trigger: legacy-state | нужен: plan-design",
            "",
        ))
    lines.extend(f"**{field}:** {item['fields'][field]}" for field in _SPEC_FIELDS)
    return "\n".join(lines).rstrip() + "\n"


def _render_phase(phase: dict) -> str:
    context = phase["prefix"].replace("## Phase Context", "").strip()
    if not phase["items"] and "СКЕЛЕТ" not in context:
        context = (context.rstrip() + "\n\n> СКЕЛЕТ — не детализирован; "
                   "сохранён как нетерминальная legacy-фаза.").strip()
    return (f"# {phase['id']} — {phase['title']}\n\n## Phase Context\n\n{context}\n\n"
            f"## Phase Handoff\n\n{phase['handoff']}\n")


def _render_decision(row: dict) -> str:
    return (f"---\nid: {row['id']}\ndate: {row['date']}\nstatus: accepted\nitem: ''\n"
            "items: []\nsupersedes: []\nsuperseded_by: null\n---\n"
            f"## Решение\n\n{row['decision']}\n\n## Почему\n\n{row['why']}\n")


def _inventory_source(meta, phases, decisions, updates, discussion, *,
                      routing_omissions=None, policy_context=None) -> dict:
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
    # Legacy plans created before the discussion carrier was standardized have
    # no such section. Preserve that absence as data instead of refusing an
    # otherwise complete read-only migration or inventing a discussion file.
    values.append({"kind": "discussion", "present": discussion is not None,
                   "value": discussion or ""})
    return {
        "schema": "plan-migration-inventory-v1",
        "item_ids": [item["id"] for phase in phases for item in phase["items"]],
        "meta_fields": [name for name, _value in meta],
        "elements": values,
        "decision_id_map": [
            {"source_id": row["source_id"], "projected_id": row["id"]}
            for row in decisions
        ],
        "routing_omissions": routing_omissions or [],
        "policy_preimage": policy_context,
        "skeleton_phases": [phase["id"] for phase in phases if not phase["items"]],
    }


def _tree_sha256(path: Path) -> str:
    records = []
    for member in sorted(path.rglob("*")):
        relative = member.relative_to(path).as_posix()
        if ".git" in member.relative_to(path).parts:
            continue
        if member.is_symlink():
            records.append((relative, "symlink", os.readlink(member)))
        elif member.is_file():
            records.append((relative, "file", _sha256(member)))
    return _bytes_sha256(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def load_policy(path, source: Path) -> tuple[dict, dict]:
    try:
        policy = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"migration policy не читается: {path}") from exc
    root_required = {"$schema", "version", "generated_at", "inventory_sha256",
                     "read_budget_contract", "rows"}
    if (set(policy) != root_required
            or policy.get("$schema") != _POLICY_SCHEMA or policy.get("version") != "1.0.0"
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(policy.get("generated_at", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(policy.get("inventory_sha256", "")))
            or not isinstance(policy.get("rows"), list)
            or not isinstance(policy.get("read_budget_contract"), str)):
        raise MigrationError("migration policy не проходит закрытую schema v1")
    required = {"target", "source_digest", "source_plan_sha256", "defect_class",
                "transform", "semantic_invariant", "rollback"}
    identities = []
    for row in policy["rows"]:
        if (not isinstance(row, dict) or set(row) != required
                or not all(isinstance(row[key], str) and row[key] for key in required)
                or not Path(row["target"]).is_absolute()
                or not re.fullmatch(r"[0-9a-f]{64}", row["source_digest"])
                or not re.fullmatch(r"[0-9a-f]{64}", row["source_plan_sha256"])
                or row["defect_class"] not in _DEFECT_CLASSES):
            raise MigrationError("migration policy содержит невалидную row")
        identities.append((str(Path(row["target"]).resolve()), row["defect_class"]))
    if len(identities) != len(set(identities)):
        raise MigrationError("migration policy содержит duplicate target/defect class")
    source_resolved = source.resolve()
    candidates = [row for row in policy["rows"]
                  if isinstance(row, dict) and Path(str(row.get("target", ""))).resolve() == source_resolved]
    if not candidates:
        raise MigrationError(f"migration policy не авторизует target: {source}")
    classes = {row["defect_class"] for row in candidates}
    if plan_layout.layout_version(source) == "v2":
        allowed_v2 = {"already-v2-admission", "current-state-import",
                      "read-budget-carrier", "semantic-handoff"}
        if "already-v2-admission" not in classes or not classes <= allowed_v2:
            raise MigrationError(f"v2 target несёт недопустимые admission classes: {source}")
    elif "already-v2-admission" in classes:
        raise MigrationError(f"v1 target не может иметь already-v2-admission: {source}")
    tree_digest = _tree_sha256(source)
    plan_digest = _sha256(source / "plan.md")
    if any(row["source_digest"] != tree_digest or row["source_plan_sha256"] != plan_digest
           for row in candidates):
        raise MigrationError(f"migration policy preimage digest не совпадает: {source}")
    return policy, {"target": str(source_resolved), "source_digest": tree_digest,
                    "source_plan_sha256": plan_digest,
                    "defect_classes": sorted(classes)}


def _policy_has(policy_context: dict | None, defect_class: str) -> bool:
    return bool(policy_context and defect_class in policy_context["defect_classes"])


def _write_current_state_journal(plan_dir: Path, phases: list[dict], inventory: dict,
                                 *, reset: bool = True) -> None:
    """Replace legacy chronology with explicit current-state import rows.

    The untouched chronology remains in the byte-exact source archive.  The
    active v2 journal receives at most one canonical event per non-pristine
    item, ordered by item id at a synthetic epoch boundary.
    """
    path = plan_dir / journal.FILENAME
    if reset:
        path.write_text("", encoding="utf-8")
    imported = []
    ordinal = 0
    for phase in phases:
        for item in phase["items"]:
            status = item["fields"]["Status"].strip()
            if status in ("⬜ Not started", "🟡 In progress"):
                imported.append({
                    "item": item["id"], "source_status": status,
                    "projected_result": None,
                    "reason": ("no canonical execution event; reset to resumable not-started"
                               if status == "🟡 In progress"
                               else "legacy pending item requires post-migration admission"),
                })
                continue
            result = _STATUS_RESULT.get(status)
            if result is None:
                raise MigrationError(
                    f"{item['id']}: migration policy не умеет импортировать status «{status}»")
            ordinal += 1
            friction = ("deviation",) if result == "closed-deviations" else ()
            note = (f"Layout v2 current-state import from legacy status {status}; "
                    "chronology: artifacts/migration-source-v1/journal.jsonl")
            entry = journal.new_entry(
                plan_id=plan_dir.name, item_id=item["id"], command="plan-run",
                actor="migration/current-state-v1", result=result,
                attempt=1, friction=friction, note=note,
                ts=(datetime(1970, 1, 1, tzinfo=timezone.utc)
                    + timedelta(seconds=ordinal)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            journal.append(plan_dir, entry)
            imported.append({"item": item["id"], "source_status": status,
                             "projected_result": result})
    inventory["current_state_import"] = {
        "kind": "canonical-current-state-not-chronology",
        "source": "artifacts/migration-source-v1/journal.jsonl",
        "rows": imported,
    }


def _install_read_budget(plan_dir: Path, contract: str) -> None:
    target = plan_dir / "root" / "contracts" / "read-budget-v1.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contract.rstrip() + "\n", encoding="utf-8")


def _semantic_handoff(plan_dir: Path, phases: list[dict]) -> None:
    items = [item for phase in phases for item in phase["items"]]
    remaining = [item for item in items if item["fields"]["Status"].strip()
                 not in _TERMINAL_STATUSES]
    skeletons = [phase for phase in phases if not phase["items"]]
    if remaining:
        item_id = remaining[0]["id"]
        next_value = f"/task:plan-exec {plan_dir.name} {item_id}"
        command = next_value
        essence = f"Продолжить первый нетерминальный item {item_id}."
    elif skeletons:
        phase_id = skeletons[0]["id"]
        next_value = f"/task:plan-design {plan_dir.name} {phase_id}"
        command = next_value
        essence = f"Детализировать сохранённую legacy-фазу-скелет {phase_id}."
    else:
        next_value = "план закрыт"
        command = f"/task:plan-close archive {plan_dir.name}"
        essence = "Архивировать терминальный план после проверки миграции."
    text = f"""# HANDOFF — migration preview — after P0.0

**Next:** {next_value}

| Параметр | Значение |
|:--|:--|
| Model | implementation |
| Thinking | high — verify migrated current state |
| Context | fresh session |
| Суть | {essence} |

```text
{command}
```

**Done:** Layout v2 preview построен из frozen migration policy.
**Remaining:** Определяется generated current-state carriers.
**Sources of truth:** `plan.md` · `artifacts/p2-migration-inventory.json` · `artifacts/migration-source-v1/manifest.json`
**Open risks:** Source archive и policy preimage обязательны до controlled apply.
**Workarounds/Deferred/Open questions:** workarounds — none; deferred — none; open_questions — none.
"""
    (plan_dir / "handoff.md").write_text(text, encoding="utf-8")


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


def _write_source_archive(plan_dir: Path) -> dict:
    """Preserve the complete v1 plan tree byte-for-byte before projection.

    The migration overwrites stable carriers and adds generated ones.  A full
    snapshot is simpler and safer than trying to maintain a partial list of
    mutable paths: every source file and its exact text remain recoverable.
    """
    archive = plan_dir / _SOURCE_ARCHIVE_RELATIVE
    if archive.exists():
        raise MigrationError(f"архив исходника миграции уже существует: {archive}")
    files = {path.relative_to(plan_dir): path.read_bytes()
             for path in plan_dir.rglob("*") if path.is_file()}
    archive.mkdir(parents=True)
    records = []
    for relative, payload in sorted(files.items()):
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        records.append({"path": relative.as_posix(), "bytes": len(payload),
                        "sha256": _bytes_sha256(payload)})
    manifest = {"schema": "plan-migration-source-v1", "files": records}
    (archive / _SOURCE_ARCHIVE_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _verify_source_archive(plan_dir)
    return manifest


def _append_layout_activation(plan_dir: Path) -> None:
    """Append one deterministic boundary between legacy and v2 execution history."""
    journal_path = plan_dir / journal.FILENAME
    timestamps = []
    for number, raw in enumerate(journal_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(json.loads(raw)["ts"]).replace("Z", "+00:00")))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MigrationError(f"journal.jsonl:{number}: не удаётся вычислить границу Layout v2") from exc
    timestamp = (max(timestamps, default=datetime(1970, 1, 1, tzinfo=timezone.utc)) + timedelta(seconds=1))
    journal.append(plan_dir, journal.new_entry(
        plan_id=plan_dir.name, item_id="layout-v2", command="plan-design", actor="migration/v2",
        result="in-progress", note="Layout v2 migration activation; source tree archived in artifacts/migration-source-v1.",
        ts=timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ))


def _verify_source_archive(plan_dir: Path) -> dict | None:
    """Fail closed if a new-format migration's lossless source archive drifts."""
    archive = plan_dir / _SOURCE_ARCHIVE_RELATIVE
    if not archive.exists():
        # Layout v2 predates this preservation carrier.  Do not invalidate its
        # historical idempotence, but every new migration writes the archive.
        return None
    manifest_path = archive / _SOURCE_ARCHIVE_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"архив исходника миграции не читается: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise MigrationError("архив исходника миграции имеет невалидный manifest")
    records = manifest.get("files")
    if manifest.get("schema") != "plan-migration-source-v1" or not isinstance(records, list) or not records:
        raise MigrationError("архив исходника миграции имеет невалидный manifest")
    expected_paths = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "bytes", "sha256"}:
            raise MigrationError("архив исходника миграции содержит невалидную запись")
        if not isinstance(record["path"], str):
            raise MigrationError("архив исходника миграции содержит небезопасную запись")
        relative = Path(record["path"])
        if (relative.is_absolute() or ".." in relative.parts or record["path"] in expected_paths
                or not isinstance(record["bytes"], int)
                or not isinstance(record["sha256"], str)):
            raise MigrationError("архив исходника миграции содержит небезопасную запись")
        expected_paths.add(record["path"])
        try:
            payload = (archive / relative).read_bytes()
        except OSError as exc:
            raise MigrationError(f"архив исходника миграции потерял {record['path']}") from exc
        if len(payload) != record["bytes"] or _bytes_sha256(payload) != record["sha256"]:
            raise MigrationError(f"архив исходника миграции повреждён: {record['path']}")
    actual_paths = {path.relative_to(archive).as_posix() for path in archive.rglob("*") if path.is_file()}
    if actual_paths != expected_paths | {_SOURCE_ARCHIVE_MANIFEST}:
        raise MigrationError("архив исходника миграции содержит непредусмотренные или отсутствующие файлы")
    return manifest


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


def _admit_existing_v2(plan_dir: Path, *, inventory_path: Path,
                       policy: dict | None, policy_context: dict | None) -> dict:
    weight_path = plan_dir / "artifacts" / "p2-weight-before-after.json"
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        weights = json.loads(weight_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError("v2-план не несёт валидные generated артефакты миграции") from exc
    if inventory.get("missing") != [] or not inventory.get("item_ids") or not weights.get("items"):
        raise MigrationError("v2-план не проходит инвентарь или замер миграции")
    source_archive = _verify_source_archive(plan_dir)
    if policy_context is not None:
        archive = plan_dir / _SOURCE_ARCHIVE_RELATIVE
        phase_paths = sorted((archive / "phases").glob("P*.md"))
        phases = [_phase_source(path, compatibility=True) for path in phase_paths]
        if not phases:
            raise MigrationError("already-v2 admission не нашёл legacy phase preimage")
        if _policy_has(policy_context, "current-state-import"):
            _write_current_state_journal(plan_dir, phases, inventory, reset=True)
            _append_layout_activation(plan_dir)
        if _policy_has(policy_context, "read-budget-carrier"):
            _install_read_budget(plan_dir, policy["read_budget_contract"])
        if _policy_has(policy_context, "semantic-handoff"):
            _semantic_handoff(plan_dir, phases)
        plan_item_state.build_states(plan_dir)
        plan_status.build_status(plan_dir)
        inventory["policy_preimage"] = policy_context
        inventory_path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return {"inventory": inventory, "weights": weights, "source_archive": source_archive}


def migrate(plan_dir, *, inventory_path=None, policy=None, policy_context=None) -> dict:
    """Migrate one v1 tree in place and return its generated acceptance facts."""
    plan_dir = Path(plan_dir)
    plan_path = plan_dir / "plan.md"
    source_bytes = plan_path.read_bytes()
    source = source_bytes.decode("utf-8")
    if plan_layout.layout_version(plan_dir) == "v2":
        inventory_path = Path(inventory_path) if inventory_path else plan_dir / "artifacts" / "p2-migration-inventory.json"
        return _admit_existing_v2(
            plan_dir, inventory_path=inventory_path,
            policy=policy, policy_context=policy_context)
    compatibility = policy_context is not None
    meta = _meta(source)
    decisions = _decision_rows(
        source, compatibility=_policy_has(policy_context, "decision-id-map"))
    try:
        discussion = _section(source, "Обсуждение")
    except MigrationError:
        discussion = None
    updates = _update_rows(source)
    phase_paths = sorted((plan_dir / "phases").glob("P*.md"))
    phases = [_phase_source(
        path, compatibility=_policy_has(policy_context, "skeleton-preservation"))
        for path in phase_paths]
    if not phases:
        raise MigrationError("нет legacy фаз для миграции")
    routing_omissions = []
    inventory = _inventory_source(
        meta, phases, decisions, updates, discussion,
        routing_omissions=routing_omissions, policy_context=policy_context)
    if _policy_has(policy_context, "current-state-import"):
        blocked_items = {
            item["id"] for phase in phases for item in phase["items"]
            if item["fields"]["Status"].strip() == "🔴 Blocked"
        }
    else:
        blocked_items = _blocked_journal_items(plan_dir)
    before = plan_weight.measure_plan(plan_dir, plan_weight.Measurer())
    source_archive = _write_source_archive(plan_dir)

    (plan_dir / "plan.md").write_text(_render_core(
        source, meta,
        compatibility=_policy_has(policy_context, "routing-normalization"),
        routing_omissions=routing_omissions), encoding="utf-8")
    shutil.rmtree(plan_dir / "phases")
    for phase in phases:
        directory = plan_dir / "phases" / phase["id"]
        directory.mkdir(parents=True)
        (directory / f"{phase['id']}.md").write_text(_render_phase(phase), encoding="utf-8")
        for item in phase["items"]:
            (directory / f"{item['id']}.md").write_text(
                _render_spec(item, blocked_by_journal=item["id"] in blocked_items), encoding="utf-8")
    decisions_dir = plan_dir / "decisions"
    if decisions_dir.exists():
        shutil.rmtree(decisions_dir)
    decisions_dir.mkdir()
    for row in decisions:
        (decisions_dir / f"{row['id']}-legacy.md").write_text(_render_decision(row), encoding="utf-8")
    if discussion is not None:
        (decisions_dir / "legacy-discussion.md").write_text(
            "# Legacy discussion\n\n" + discussion + "\n", encoding="utf-8")

    if _policy_has(policy_context, "current-state-import"):
        _write_current_state_journal(plan_dir, phases, inventory)
    elif not (plan_dir / journal.FILENAME).is_file():
        raise MigrationError("journal.jsonl отсутствует; нужен policy current-state-import")
    _append_layout_activation(plan_dir)
    if _policy_has(policy_context, "read-budget-carrier"):
        _install_read_budget(plan_dir, policy["read_budget_contract"])
    if _policy_has(policy_context, "semantic-handoff"):
        _semantic_handoff(plan_dir, phases)
    plan_item_state.build_states(plan_dir)
    plan_decisions.build_views(plan_dir)
    plan_status.build_status(plan_dir)
    inventory_path = Path(inventory_path) if inventory_path else plan_dir / "artifacts" / "p2-migration-inventory.json"
    report = _write_inventory(inventory_path, inventory, plan_dir)
    weights = _weights(plan_dir, before)
    weight_path = plan_dir / "artifacts" / "p2-weight-before-after.json"
    weight_path.write_text(json.dumps(weights, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"inventory": report, "weights": weights, "source_archive": source_archive}


def _source_records(plan_dir: Path) -> list[dict]:
    return [
        {"path": path.relative_to(plan_dir).as_posix(), "bytes": path.stat().st_size,
         "sha256": _sha256(path)}
        for path in sorted(plan_dir.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(plan_dir).parts
    ]


def _post_apply_check(plan_dir: Path) -> None:
    if plan_layout.layout_version(plan_dir) != "v2":
        raise MigrationError("controlled apply не материализовал Layout v2")
    _verify_source_archive(plan_dir)


def _apply_preview(source: Path, preview: Path, policy_context: dict) -> dict:
    """Atomically install one approved preview or restore the exact preimage."""
    if _tree_sha256(source) != policy_context["source_digest"]:
        raise MigrationError("controlled apply: source digest изменился после policy admission")
    if plan_layout.layout_version(source) == "v2":
        return {"applied": False, "reason": "already-v2", "policy_preimage": policy_context}
    if plan_layout.layout_version(preview) != "v2":
        raise MigrationError("controlled apply: preview не является Layout v2")
    archive_manifest = _verify_source_archive(preview)
    if archive_manifest is None or archive_manifest.get("files") != _source_records(source):
        raise MigrationError("controlled apply: preview archive не совпадает с source preimage")
    try:
        preview_inventory = json.loads(
            (preview / "artifacts" / "p2-migration-inventory.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError("controlled apply: preview inventory не читается") from exc
    if preview_inventory.get("policy_preimage") != policy_context:
        raise MigrationError("controlled apply: preview построен не из текущего policy preimage")

    parent = source.parent
    nonce = policy_context["source_digest"][:12]
    staged = parent / f".{source.name}.migration-stage-{nonce}"
    backup = parent / f".{source.name}.migration-backup-{nonce}"
    failed = parent / f".{source.name}.migration-failed-{nonce}"
    if staged.exists() or backup.exists() or failed.exists():
        raise MigrationError("controlled apply: staging/rollback carrier уже существует")
    shutil.copytree(preview, staged, symlinks=True)
    swapped = False
    try:
        source.rename(backup)
        swapped = True
        staged.rename(source)
        _post_apply_check(source)
    except Exception:
        if swapped:
            if source.exists():
                source.rename(failed)
            backup.rename(source)
            if failed.exists():
                shutil.rmtree(failed)
        elif staged.exists():
            shutil.rmtree(staged)
        raise
    shutil.rmtree(backup)
    return {"applied": True, "reason": "preview-installed",
            "policy_preimage": policy_context}


def migrate_safely(source, *, dry_run=False, output=None, inventory_path=None,
                   policy_path=None, apply=False, preview=None) -> dict:
    """Apply the public safety boundary around the in-place converter."""
    source = Path(source)
    policy = policy_context = None
    if policy_path is not None:
        policy, policy_context = load_policy(policy_path, source)
    if dry_run:
        if apply:
            raise MigrationError("--dry-run и --apply взаимоисключающие")
        if output is None:
            raise MigrationError("--dry-run требует явный --output")
        output = Path(output)
        if output.resolve() == source.resolve() or output.exists():
            raise MigrationError("--output должен быть новым каталогом вне source")
        source_hash = _sha256(source / "plan.md")
        source_tree_hash = _tree_sha256(source)
        shutil.copytree(source, output)
        result = migrate(output, inventory_path=inventory_path,
                         policy=policy, policy_context=policy_context)
        if _sha256(source / "plan.md") != source_hash:
            raise MigrationError("dry-run изменил source")
        if _tree_sha256(source) != source_tree_hash:
            raise MigrationError("dry-run изменил source tree")
        return result
    if output is not None:
        raise MigrationError("--output допустим только вместе с --dry-run")
    if apply:
        if policy is None or preview is None:
            raise MigrationError("--apply требует --policy и явный --preview")
        return _apply_preview(source, Path(preview), policy_context)
    raise MigrationError("inplace-конвертер выведен из эксплуатации; используйте --dry-run --output")
