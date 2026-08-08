"""Deterministic Return Fingerprint v1 reducer and durable counter."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from task import journal, plan_decisions, plan_layout


class ReturnError(ValueError):
    """A return projection input or fingerprint violates the frozen contract."""


_ITEM = re.compile(r"^P\d+(?:\.\d+)?$")
_EXECUTION_COMMANDS = frozenset(("plan-exec", "plan-run", "plan-close", "plan-audit"))
_NEGATIVE_RESULTS = frozenset(("blocked", "escalated", "audit-red"))
_SCHEMA = Path(__file__).resolve().parents[2] / "configs" / "return-fingerprint-v1.schema.json"


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema() -> dict:
    try:
        return json.loads(_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReturnError(f"схема return-fingerprint v1 не читается: {_SCHEMA}") from exc


def _validate(value, schema: dict, root: dict, path: str = "$") -> None:
    """Small, generic Draft-2020 subset needed by the lifted frozen schema.

    The checks are interpreted from the copied schema; no return-specific schema is
    repeated in Python beside its source carrier.
    """
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ReturnError(f"{path}: неподдерживаемая schema ссылка {ref}")
        return _validate(value, root["$defs"][ref.rsplit("/", 1)[-1]], root, path)
    if "allOf" in schema:
        for child in schema["allOf"]:
            _validate(value, child, root, path)
    if "anyOf" in schema:
        errors = []
        for child in schema["anyOf"]:
            try:
                _validate(value, child, root, path)
                break
            except ReturnError as exc:
                errors.append(str(exc))
        else:
            raise ReturnError(f"{path}: не проходит ни один schema-вариант")
    if "not" in schema:
        try:
            _validate(value, schema["not"], root, path)
        except ReturnError:
            pass
        else:
            raise ReturnError(f"{path}: запрещён schema-вариантом")
    if "if" in schema:
        try:
            _validate(value, schema["if"], root, path)
        except ReturnError:
            if "else" in schema:
                _validate(value, schema["else"], root, path)
        else:
            if "then" in schema:
                _validate(value, schema["then"], root, path)
    if "const" in schema and value != schema["const"]:
        raise ReturnError(f"{path}: ожидается {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ReturnError(f"{path}: значение вне enum")
    kinds = schema.get("type")
    if kinds is not None:
        kinds = (kinds,) if isinstance(kinds, str) else tuple(kinds)
        matched = (("object" in kinds and isinstance(value, dict))
                   or ("array" in kinds and isinstance(value, list))
                   or ("string" in kinds and isinstance(value, str))
                   or ("boolean" in kinds and isinstance(value, bool))
                   or ("integer" in kinds and isinstance(value, int) and not isinstance(value, bool))
                   or ("number" in kinds and isinstance(value, (int, float)) and not isinstance(value, bool))
                   or ("null" in kinds and value is None))
        if not matched:
            raise ReturnError(f"{path}: тип не проходит schema")
    if isinstance(value, dict):
        missing = [name for name in schema.get("required", ()) if name not in value]
        if missing:
            raise ReturnError(f"{path}: нет обязательных полей {', '.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ReturnError(f"{path}: лишние поля {', '.join(extra)}")
        for name, child in properties.items():
            if name in value:
                _validate(value[name], child, root, f"{path}.{name}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise ReturnError(f"{path}: число элементов вне schema границ")
        if schema.get("uniqueItems") and len({canonical_json(item) for item in value}) != len(value):
            raise ReturnError(f"{path}: элементы должны быть уникальны")
        for index, item in enumerate(value):
            _validate(item, schema.get("items", {}), root, f"{path}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ReturnError(f"{path}: строка короче minLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ReturnError(f"{path}: строка не проходит pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ReturnError(f"{path}: число вне schema границ")


def validate(record: dict) -> None:
    schema = _schema()
    _validate(record, schema, schema)


def _timestamp(entry: dict, ordinal: int) -> tuple:
    value = entry.get("ts") if isinstance(entry, dict) else None
    try:
        return (0, datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ"), ordinal)
    except (TypeError, ValueError):
        return (1, datetime.max, ordinal)


def _frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return {}
        fields, _body = plan_decisions.parse_frontmatter(text, path=path)
        return fields
    except (OSError, plan_decisions.DecisionError) as exc:
        raise ReturnError(f"seam carrier не читается: {path}") from exc


def _seams(plan_dir: Path) -> list[dict]:
    """Read additive decision/finding seam fields; incomplete carriers stay unusable."""
    carriers = []
    try:
        decisions = plan_decisions.load_decisions(plan_dir)
    except plan_decisions.DecisionError as exc:
        raise ReturnError(str(exc)) from exc
    carriers.extend(decision.path for decision in decisions)
    findings = plan_dir / "findings"
    if findings.is_dir():
        carriers.extend(sorted(findings.rglob("*.md")))
    result = []
    for path in carriers:
        fields = _frontmatter(path)
        seam = {key: fields.get(key) for key in ("file", "rule_or_contract_locus", "defect_class")}
        if (isinstance(fields.get("item"), str) and isinstance(fields.get("date"), str)
                and all(isinstance(value, str) and value for value in seam.values())):
            result.append({"item": fields["item"], "date": fields["date"], "seam": seam,
                           "identity": path.relative_to(plan_dir).as_posix()})
    return result


def _journal_entries(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ReturnError(f"journal не читается: {path}") from exc
    entries = []
    for ordinal, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            entry = {}
        errors = journal.entry_validation_errors(entry)
        entries.append({"entry": entry, "ordinal": ordinal, "errors": errors})
    entries.sort(key=lambda row: _timestamp(row["entry"], row["ordinal"]))
    return entries


def _seam_for(subject: str, trigger: dict, event: dict, seams: list[dict]) -> dict | None:
    trigger_day, event_day = trigger.get("ts", "")[:10], event.get("ts", "")[:10]
    candidates = {canonical_json(row["seam"]): row["seam"] for row in seams
                  if row["item"] == subject and trigger_day <= row["date"] <= event_day}
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _fingerprint(subject: str, trigger_row: dict, event_row: dict, seams: list[dict]) -> dict:
    trigger, event = trigger_row["entry"], event_row["entry"]
    errors = sorted(f"{field}: {message}" for field, message in trigger_row["errors"])
    valid = not errors
    friction = trigger.get("friction") if isinstance(trigger.get("friction"), list) else []
    friction_class = {"friction": sorted(set(friction)) if valid else [],
                      "result": trigger.get("result", "invalid") if valid else "invalid",
                      "schema_valid": valid, "schema_errors": errors}
    seam = _seam_for(subject, trigger, event, seams) if valid else None
    if seam is not None:
        namespace = "classified"
    elif valid and (friction_class["friction"] or friction_class["result"] in _NEGATIVE_RESULTS):
        namespace = "provisional"
    else:
        namespace = "ungroupable"
    tuple_value = {"subject": subject, "friction_class": friction_class, "seam": seam}
    if namespace == "ungroupable":
        tuple_value["event_ordinal"] = event_row["ordinal"]
    digest_input = {"fingerprint_version": "v1", "namespace": namespace, "tuple": tuple_value}
    digest = hashlib.sha256(canonical_json(digest_input).encode("utf-8")).hexdigest()
    return {"fingerprint_version": "v1", "namespace": namespace, "tuple": tuple_value,
            "digest": digest, "metrics": {}}


def returns(plan_dir) -> dict:
    plan_dir = Path(plan_dir)
    try:
        journal_path = plan_layout.carrier_path(plan_dir, "journal")
    except plan_layout.PlanLayoutError as exc:
        raise ReturnError(str(exc)) from exc
    entries = _journal_entries(journal_path)
    seams = _seams(plan_dir)
    fingerprints, executions = [], []
    non_item_subjects = 0
    schema_invalid_rows = sum(bool(row["errors"]) for row in entries)
    for row in entries:
        entry = row["entry"]
        subject = entry.get("item_id") if isinstance(entry, dict) else None
        if not isinstance(subject, str) or not _ITEM.fullmatch(subject):
            non_item_subjects += 1
            continue
        if entry.get("command") in _EXECUTION_COMMANDS:
            executions.append(row)
            continue
        if entry.get("command") != "plan-design":
            continue
        phase = subject.split(".")[0]
        candidates = [candidate for candidate in executions
                      if (candidate["entry"].get("item_id") == subject
                          or candidate["entry"].get("item_id", "").split(".")[0] == phase)]
        if candidates:
            fingerprints.append(_fingerprint(subject, candidates[-1], row, seams))
    total = len(fingerprints)
    metrics = {"provisional_share": (sum(r["namespace"] == "provisional" for r in fingerprints) / total) if total else 0,
               "ungroupable_share": (sum(r["namespace"] == "ungroupable" for r in fingerprints) / total) if total else 0,
               "schema_invalid_rows": schema_invalid_rows, "non_item_subjects": non_item_subjects}
    for record in fingerprints:
        record["metrics"] = metrics
        validate(record)
    counts = Counter(record["digest"] for record in fingerprints if record["namespace"] != "ungroupable")
    return {"journals": 1, "entries": len(entries), "return_events": total, "metrics": metrics,
            "fingerprints": fingerprints, "counts": dict(sorted(counts.items())),
            "over_cap_subjects": []}


def durable_count(plan_dir, digest: str):
    """Reconstruct a count from committed carriers; absent journal stays unknown."""
    plan_dir = Path(plan_dir)
    try:
        path = plan_layout.carrier_path(plan_dir, "journal")
    except plan_layout.PlanLayoutError as exc:
        raise ReturnError(str(exc)) from exc
    if not path.is_file():
        return "unknown"
    return returns(plan_dir)["counts"].get(digest, 0)


def measure_repository(repo_root, *, through: str = "2026-08-07T09:38:14Z") -> dict:
    """Read the frozen pre-reducer historical corpus without modifying it."""
    repo_root = Path(repo_root)
    plans = repo_root / "plans"
    journals = sorted(path for path in plans.rglob("journal.jsonl") if "artifacts" not in path.parts)
    summaries = []
    for path in journals:
        plan_dir = path.parent
        try:
            summaries.append(returns(plan_dir))
        except ReturnError:
            # Archived v1 journals have no v2 layout; they still use the sealed event parser.
            rows = _journal_entries(path)
            summaries.append({"journals": 1, "entries": len(rows), "return_events": 0,
                              "metrics": {"provisional_share": 0, "ungroupable_share": 0,
                                          "schema_invalid_rows": sum(bool(row["errors"]) for row in rows),
                                          "non_item_subjects": sum(not _ITEM.fullmatch(row["entry"].get("item_id", "")) for row in rows)},
                              "fingerprints": [], "counts": {}, "over_cap_subjects": []})
    # v1 journals are intentionally included below by replaying their entries with no seam declarations.
    all_rows = []
    for path in journals:
        rows = [row for row in _journal_entries(path)
                if isinstance(row["entry"].get("ts"), str) and row["entry"]["ts"] <= through]
        executions, fingerprints = [], []
        for row in rows:
            entry, subject = row["entry"], row["entry"].get("item_id")
            if not isinstance(subject, str) or not _ITEM.fullmatch(subject):
                continue
            if entry.get("command") in _EXECUTION_COMMANDS:
                executions.append(row)
            elif entry.get("command") == "plan-design":
                phase = subject.split(".")[0]
                matching = [candidate for candidate in executions
                            if (candidate["entry"].get("item_id") == subject
                                or candidate["entry"].get("item_id", "").split(".")[0] == phase)]
                if matching:
                    fingerprints.append(_fingerprint(subject, matching[-1], row, []))
        all_rows.append((rows, fingerprints))
    fingerprints = [record for _rows, values in all_rows for record in values]
    total = len(fingerprints)
    metrics = {"provisional_share": sum(record["namespace"] == "provisional" for record in fingerprints) / total if total else 0,
               "ungroupable_share": sum(record["namespace"] == "ungroupable" for record in fingerprints) / total if total else 0,
               "schema_invalid_rows": sum(sum(bool(row["errors"]) for row in rows) for rows, _ in all_rows),
               "non_item_subjects": sum(sum(not _ITEM.fullmatch(row["entry"].get("item_id", "")) for row in rows) for rows, _ in all_rows)}
    for record in fingerprints:
        record["metrics"] = metrics
        validate(record)
    counts = Counter(record["digest"] for record in fingerprints if record["namespace"] != "ungroupable")
    return {"journals": len(journals), "entries": sum(len(rows) for rows, _ in all_rows),
            "return_events": total, "metrics": metrics, "fingerprints": fingerprints,
            "counts": dict(sorted(counts.items())), "over_cap_subjects": []}
