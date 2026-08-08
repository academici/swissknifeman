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
_LOOP_SPEC = Path(__file__).resolve().parents[2] / "configs" / "return-loop-v1.spec.json"
_JUDGEMENT_SCHEMA = Path(__file__).resolve().parents[2] / "configs" / "return-judgement-v1.schema.json"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_DECISION = re.compile(r"\bD[1-9][0-9]*\b")
RETURN_LOOP_GATE = "return-loop-v1"
_JUDGEMENT_FIELD = "return_judgement"
_STRICTER_VERDICTS = frozenset(("AVOIDABLE", "OUT_OF_SCOPE", "MALFORMED"))


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema() -> dict:
    try:
        return json.loads(_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReturnError(f"схема return-fingerprint v1 не читается: {_SCHEMA}") from exc


def _loop_spec() -> dict:
    """Load the lifted policy instead of repeating its cap or ladder in code."""
    try:
        value = json.loads(_LOOP_SPEC.read_text(encoding="utf-8"))
        cap = value["cap"]["default"]
        if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
            raise ValueError("cap.default должен быть положительным int")
        return value
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ReturnError(f"спецификация return-loop v1 не читается: {_LOOP_SPEC}") from exc


def _judgement_schema() -> dict:
    try:
        return json.loads(_JUDGEMENT_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReturnError(f"схема return-judgement v1 не читается: {_JUDGEMENT_SCHEMA}") from exc


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


def validate_judgement(record: dict) -> None:
    """Validate a stored judgement with the lifted frozen schema."""
    schema = _judgement_schema()
    _validate(record, schema, schema)


def decide(*, verdict=None, occurrences=1, cap=None, namespace="provisional",
           fingerprint_digest=None) -> dict:
    """Apply the closed monotone judgement policy without invoking a model.

    The judgement is evidence only.  A strict verdict may stop work sooner, but
    it cannot mutate identity, reset the durable counter, or remove an owner
    gate that the return-loop ladder already required.
    """
    spec = _loop_spec()
    cap = spec["cap"]["default"] if cap is None else cap
    if not isinstance(occurrences, int) or isinstance(occurrences, bool) or occurrences < 0:
        raise ReturnError("occurrences должен быть неотрицательным int")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise ReturnError("cap должен быть положительным int")
    if namespace not in ("classified", "provisional", "ungroupable"):
        raise ReturnError("namespace judgement policy неизвестен")
    enum = _judgement_schema()["properties"]["verdict"]["enum"]
    if verdict is not None and verdict not in enum:
        raise ReturnError("verdict вне закрытого enum return-judgement v1")
    over_cap = occurrences > cap
    strict_stop = verdict in _STRICTER_VERDICTS
    return {
        "occurrences": occurrences,
        "cap": cap,
        "namespace": namespace,
        "fingerprint_digest": fingerprint_digest,
        "continue_allowed": not (over_cap or strict_stop),
        "stop_required": over_cap or strict_stop,
        "owner_gate_required": over_cap,
    }


def at_least_as_strict(candidate: dict, baseline: dict) -> bool:
    """Return whether a verdict outcome preserves every frozen monotonic axis."""
    required = ("occurrences", "cap", "namespace", "fingerprint_digest",
                "continue_allowed", "stop_required", "owner_gate_required")
    if not all(key in candidate and key in baseline for key in required):
        return False
    if candidate["occurrences"] < baseline["occurrences"]:
        return False
    if candidate["cap"] != baseline["cap"]:
        return False
    if (candidate["namespace"], candidate["fingerprint_digest"]) != (
            baseline["namespace"], baseline["fingerprint_digest"]):
        return False
    if not baseline["continue_allowed"] and candidate["continue_allowed"]:
        return False
    if baseline["stop_required"] and not candidate["stop_required"]:
        return False
    if baseline["owner_gate_required"] and not candidate["owner_gate_required"]:
        return False
    return True


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


def _history_row(trigger_row: dict, event_row: dict, seams: list[dict], subject: str) -> dict:
    """Keep the owner packet tied to durable journal and seam carriers.

    ``return_event_id`` is deliberately plan-local: it is the immutable physical
    address of the return row, not another fingerprint component.  Judgement
    carriers use it to address one concrete event without changing the frozen
    grouping tuple, digest, or namespace.
    """
    trigger, event = trigger_row["entry"], event_row["entry"]
    notes = " ".join(value for value in (trigger.get("note"), event.get("note"))
                     if isinstance(value, str))
    trigger_day, event_day = trigger.get("ts", "")[:10], event.get("ts", "")[:10]
    findings = sorted(row["identity"] for row in seams
                      if row["item"] == subject and trigger_day <= row["date"] <= event_day)
    return {
        "return_event_id": f"journal.jsonl:{event_row['ordinal']}",
        "ts": event.get("ts"),
        "attempt": trigger.get("attempt"),
        "actor": trigger.get("actor"),
        "command": trigger.get("command"),
        "decision_refs": sorted(set(_DECISION.findall(notes))),
        "finding_refs": findings,
    }


def _evidence_fields(plan_dir: Path) -> list[dict]:
    """Read D139's additive finding-frontmatter carrier without a new registry."""
    findings = plan_dir / "findings"
    if not findings.is_dir():
        return []
    result = []
    for path in sorted(findings.rglob("*.md")):
        fields = _frontmatter(path)
        if fields.get("gate") == RETURN_LOOP_GATE:
            result.append({"path": path, "fields": fields})
    return result


def _first_judgement(plan_dir: Path, subject_id: str, fingerprint_digest: str) -> dict | None:
    """Read the first schema-valid matching record from item-scoped findings.

    Findings are existing immutable history carriers.  Their additive compact
    JSON field is data, never executable text.  A self-judgement is the first
    matching record but is rejected rather than skipped for a later retry.
    """
    findings = plan_dir / "findings"
    if not findings.is_dir():
        return None
    for path in sorted(findings.rglob("*.md")):
        fields = _frontmatter(path)
        raw = fields.get(_JUDGEMENT_FIELD)
        if not isinstance(raw, str):
            continue
        try:
            record = json.loads(raw)
            validate_judgement(record)
        except (json.JSONDecodeError, ReturnError):
            continue
        if record["subject_id"] != subject_id or record["fingerprint_digest"] != fingerprint_digest:
            continue
        if record["reviewer_actor"] == record["executor_actor"]:
            return None
        return record
    return None


def return_loop_evidence(plan_dir) -> list[dict]:
    """Expose D139 evidence records for the opt-in lint checks and tests."""
    return _evidence_fields(Path(plan_dir))


def evidence_errors(fields: dict) -> list[str]:
    if not isinstance(fields.get("item"), str) or not _ITEM.fullmatch(fields["item"]):
        return ["evidence требует item формы Pn.m"]
    qualification = fields.get("qualification")
    if qualification not in ("new", "repeat", "unqualifiable"):
        return ["qualification обязан быть new/repeat/unqualifiable"]
    if qualification == "unqualifiable":
        if not isinstance(fields.get("missing_carrier_reason"), str) or not fields["missing_carrier_reason"].strip():
            return ["unqualifiable требует missing_carrier_reason"]
        if "fingerprint_digest" in fields or "occurrences" in fields:
            return ["unqualifiable не принимает fingerprint_digest/occurrences"]
        return []
    digest = fields.get("fingerprint_digest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        return ["new/repeat требует lowercase fingerprint_digest"]
    try:
        occurrences = int(fields.get("occurrences"))
    except (TypeError, ValueError):
        return ["new/repeat требует положительное occurrences"]
    return [] if occurrences >= 1 else ["new/repeat требует положительное occurrences"]


def _owner_packet(record: dict, occurrences: int, cap: int, history: list[dict],
                  judgement: dict | None = None) -> dict:
    return {
        "fingerprint_tuple": record["tuple"],
        "fingerprint_digest": record["digest"],
        "occurrences": occurrences,
        "cap": cap,
        "history": history,
        "judgements": [judgement] if judgement is not None else [],
        "resolutions_tried": [],
    }


def return_loop_gates(plan_dir) -> list[dict]:
    """Apply the frozen v1 ladder to durable return fingerprints.

    The reducer never treats the words ``blocked`` or ``escalated`` as a risk
    trigger. Only a classified seam's observed defect class named by the lifted
    policy can change a first occurrence from local-fix to isolated review.
    """
    projected = returns(plan_dir)
    spec = _loop_spec()
    cap = spec["cap"]["default"]
    risk_triggers = frozenset(spec["eligibility"]["risk_triggers"])
    gates = []
    by_digest = {record["digest"]: record for record in projected["fingerprints"]
                 if record["namespace"] != "ungroupable"}
    for digest, occurrences in projected["counts"].items():
        record = by_digest[digest]
        history = projected["history"].get(digest, [])
        seam = record["tuple"].get("seam") or {}
        observed = {seam.get("defect_class")} if isinstance(seam.get("defect_class"), str) else set()
        if occurrences > cap:
            action, blocks_gate, reason = "owner-gate", True, "RETURN_LOOP_OWNER_GATE_REQUIRED"
        elif occurrences == 2 or observed & risk_triggers:
            action, blocks_gate, reason = "isolated-review", True, "RETURN_LOOP_ISOLATED_REVIEW_REQUIRED"
        else:
            action, blocks_gate, reason = "local-fix", False, None
        gate = {"fingerprint_digest": digest, "occurrences": occurrences, "cap": cap,
                "qualification": "new" if occurrences == 1 else "repeat",
                "action": action, "blocks": blocks_gate,
                "review_required": action in ("isolated-review", "owner-gate"),
                "reason_code": reason}
        judgement = _first_judgement(plan_dir, record["tuple"]["subject"], digest)
        policy = decide(verdict=judgement["verdict"] if judgement else None,
                        occurrences=occurrences, cap=cap, namespace=record["namespace"],
                        fingerprint_digest=digest)
        gate.update(policy)
        if judgement is not None:
            gate["judgement"] = judgement
            if policy["stop_required"] and not gate["blocks"]:
                gate.update({"action": "judgement-stop", "blocks": True,
                             "review_required": True,
                             "reason_code": "RETURN_JUDGEMENT_STOP_REQUIRED"})
        if action == "owner-gate":
            gate["owner_packet"] = _owner_packet(record, occurrences, cap, history, judgement)
        gates.append(gate)
    for record in projected["fingerprints"]:
        if record["namespace"] == "ungroupable":
            gates.append({"fingerprint_digest": record["digest"], "occurrences": 0, "cap": cap,
                          "qualification": "unqualifiable",
                          "missing_carrier_reason": "return fingerprint is ungroupable",
                          "action": "record-only", "blocks": False, "review_required": False,
                          "reason_code": "RETURN_LOOP_QUALIFICATION_REQUIRED"})
    return gates


def returns(plan_dir) -> dict:
    plan_dir = Path(plan_dir)
    try:
        journal_path = plan_layout.carrier_path(plan_dir, "journal")
    except plan_layout.PlanLayoutError as exc:
        raise ReturnError(str(exc)) from exc
    entries = _journal_entries(journal_path)
    seams = _seams(plan_dir)
    fingerprints, executions, history = [], [], {}
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
            fingerprint = _fingerprint(subject, candidates[-1], row, seams)
            fingerprints.append(fingerprint)
            if fingerprint["namespace"] != "ungroupable":
                history.setdefault(fingerprint["digest"], []).append(
                    _history_row(candidates[-1], row, seams, subject))
    total = len(fingerprints)
    metrics = {"provisional_share": (sum(r["namespace"] == "provisional" for r in fingerprints) / total) if total else 0,
               "ungroupable_share": (sum(r["namespace"] == "ungroupable" for r in fingerprints) / total) if total else 0,
               "schema_invalid_rows": schema_invalid_rows, "non_item_subjects": non_item_subjects}
    for record in fingerprints:
        record["metrics"] = metrics
        validate(record)
    counts = Counter(record["digest"] for record in fingerprints if record["namespace"] != "ungroupable")
    cap = _loop_spec()["cap"]["default"]
    return {"journals": 1, "entries": len(entries), "return_events": total, "metrics": metrics,
            "fingerprints": fingerprints, "counts": dict(sorted(counts.items())),
            "history": {digest: history[digest] for digest in sorted(history)},
            "over_cap_subjects": sorted(digest for digest, count in counts.items() if count > cap)}


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
    record_metrics = {"provisional_share": sum(record["namespace"] == "provisional" for record in fingerprints) / total if total else 0,
                      "ungroupable_share": sum(record["namespace"] == "ungroupable" for record in fingerprints) / total if total else 0,
                      "schema_invalid_rows": sum(sum(bool(row["errors"]) for row in rows) for rows, _ in all_rows),
                      "non_item_subjects": sum(sum(not _ITEM.fullmatch(row["entry"].get("item_id", "")) for row in rows) for rows, _ in all_rows)}
    metrics = {"classified_share": sum(record["namespace"] == "classified" for record in fingerprints) / total if total else 0,
               **record_metrics}
    for record in fingerprints:
        record["metrics"] = record_metrics
        validate(record)
    counts = Counter(record["digest"] for record in fingerprints if record["namespace"] != "ungroupable")
    return {"journals": len(journals), "entries": sum(len(rows) for rows, _ in all_rows),
            "return_events": total, "metrics": metrics, "fingerprints": fingerprints,
            "counts": dict(sorted(counts.items())),
            "over_cap_subjects": sorted(digest for digest, count in counts.items()
                                        if count > _loop_spec()["cap"]["default"])}
