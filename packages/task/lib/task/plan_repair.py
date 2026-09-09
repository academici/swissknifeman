"""Closed continue-first repair evidence and its deterministic reducer."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class RepairDecisionError(ValueError):
    """A value is not a closed ``repair-decision/v1`` record."""


_SCHEMA = Path(__file__).resolve().parents[2] / "configs" / "repair-decision-v1.schema.json"
_ITEM = re.compile(r"^P[0-9]+\.[0-9]+$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ROOT = frozenset(("schema_version", "plan_id", "item_id", "origin", "original_carrier",
                   "baseline", "candidate", "affected_paths", "bounded_diff",
                   "material_surface", "pre_validation", "post_validation", "evidence_ids",
                   "design"))
_SURFACES = frozenset(("public", "frozen", "security", "schema", "dependency",
                       "authority", "irreversible", "product", "test_topology"))
_ACTIONS = frozenset(("repair-in-current-attempt", "gather-evidence",
                      "block-candidate", "design-required"))


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(record: dict) -> str:
    """Return the content address used by journal and block evidence."""
    validate(record)
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def _closed(value, expected, field):
    if not isinstance(value, dict):
        raise RepairDecisionError(f"{field}: ожидается object")
    missing, unknown = sorted(expected - set(value)), sorted(set(value) - expected)
    if missing or unknown:
        raise RepairDecisionError(f"{field}: closed schema missing={missing} unknown={unknown}")


def _strings(value, field, *, nonempty=True):
    if (not isinstance(value, list) or (nonempty and not value) or len(value) != len(set(value))
            or any(not isinstance(row, str) or not row for row in value)):
        raise RepairDecisionError(f"{field}: ожидается unique непустой string array")


def _carrier(value, field):
    _closed(value, {"command", "digest", "result"}, field)
    if (not isinstance(value["command"], str) or not value["command"]
            or not isinstance(value["digest"], str) or not _DIGEST.fullmatch(value["digest"])
            or value["result"] not in {"green", "red"}):
        raise RepairDecisionError(f"{field}: невалидный carrier")


def validate(record: dict) -> None:
    """Validate without a JSON-schema runtime dependency (Task stays stdlib-only)."""
    _closed(record, _ROOT, "repair decision")
    if record["schema_version"] != "repair-decision/v1":
        raise RepairDecisionError("schema_version: ожидается repair-decision/v1")
    if not isinstance(record["plan_id"], str) or not record["plan_id"]:
        raise RepairDecisionError("plan_id: ожидается непустая строка")
    if not isinstance(record["item_id"], str) or not _ITEM.fullmatch(record["item_id"]):
        raise RepairDecisionError("item_id: ожидается Pn.m")
    if record["origin"] not in {"validation", "checkpoint", "producer-readiness"}:
        raise RepairDecisionError("origin: значение вне закрытого enum")
    _carrier(record["original_carrier"], "original_carrier")
    if record["original_carrier"]["result"] != "red":
        raise RepairDecisionError("original_carrier: repair начинается только с red carrier")
    baseline = record["baseline"]
    _closed(baseline, {"reproduced", "carrier"}, "baseline")
    if not isinstance(baseline["reproduced"], bool) or baseline["carrier"] is not None and not isinstance(baseline["carrier"], dict):
        raise RepairDecisionError("baseline: невалидный record")
    if baseline["reproduced"] != (baseline["carrier"] is not None):
        raise RepairDecisionError("baseline: reproduced и carrier должны совпадать")
    if baseline["carrier"] is not None:
        _carrier(baseline["carrier"], "baseline.carrier")
    candidate = record["candidate"]
    _closed(candidate, {"delta_proved", "evidence_ids"}, "candidate")
    if not isinstance(candidate["delta_proved"], bool):
        raise RepairDecisionError("candidate.delta_proved: ожидается boolean")
    _strings(candidate["evidence_ids"], "candidate.evidence_ids", nonempty=candidate["delta_proved"])
    paths = record["affected_paths"]
    if not isinstance(paths, list) or not paths:
        raise RepairDecisionError("affected_paths: нужен непустой список")
    seen = set()
    for index, path in enumerate(paths):
        _closed(path, {"path", "owner_item", "declared_file"}, f"affected_paths[{index}]")
        if (not isinstance(path["path"], str) or not path["path"] or path["path"] in seen
                or not isinstance(path["owner_item"], str) or not _ITEM.fullmatch(path["owner_item"])
                or not isinstance(path["declared_file"], bool)):
            raise RepairDecisionError(f"affected_paths[{index}]: невалидный path/owner")
        seen.add(path["path"])
    diff = record["bounded_diff"]
    _closed(diff, {"files_changed", "max_files", "reversible"}, "bounded_diff")
    if (isinstance(diff["files_changed"], bool) or not isinstance(diff["files_changed"], int)
            or isinstance(diff["max_files"], bool) or not isinstance(diff["max_files"], int)
            or diff["files_changed"] < 0 or diff["max_files"] < 1
            or not isinstance(diff["reversible"], bool)):
        raise RepairDecisionError("bounded_diff: невалиден")
    surface = record["material_surface"]
    _closed(surface, _SURFACES, "material_surface")
    if any(not isinstance(value, bool) for value in surface.values()):
        raise RepairDecisionError("material_surface: все оси должны быть boolean")
    for field in ("pre_validation", "post_validation"):
        if not isinstance(record[field], list) or (field == "pre_validation" and not record[field]):
            raise RepairDecisionError(f"{field}: нужен список carrier")
        for index, carrier in enumerate(record[field]):
            _carrier(carrier, f"{field}[{index}]")
    if not any(row == record["original_carrier"] for row in record["pre_validation"]):
        raise RepairDecisionError("pre_validation: обязан включать exact original carrier")
    _strings(record["evidence_ids"], "evidence_ids")
    design = record["design"]
    if design is not None:
        _closed(design, {"decision_question", "evidence_gap", "alternatives", "expected_artifact"}, "design")
        if (any(not isinstance(design[name], str) or not design[name]
                for name in ("decision_question", "evidence_gap", "expected_artifact"))):
            raise RepairDecisionError("design: R&D поля должны быть непустыми")
        _strings(design["alternatives"], "design.alternatives")


def _decision(action: str, *, record: dict, reason_code: str) -> dict:
    assert action in _ACTIONS
    return {"action": action, "terminal_allowed": False, "reason_code": reason_code,
            "repair_digest": digest(record),
            "post_validation_required": action == "repair-in-current-attempt"}


def evaluate(record: dict) -> dict:
    """Classify one repair record; this is the sole repair/design policy owner."""
    try:
        validate(record)
    except RepairDecisionError:
        # Invalid evidence is never a terminal or design permission.
        return {"action": "gather-evidence", "terminal_allowed": False,
                "reason_code": "REPAIR_EVIDENCE_INVALID", "repair_digest": None,
                "post_validation_required": False}
    baseline = record["baseline"]["carrier"]
    if baseline is not None and baseline["result"] == "red" and not record["candidate"]["delta_proved"]:
        return _decision("repair-in-current-attempt", record=record,
                         reason_code="CLEAN_BASELINE_WITHOUT_CANDIDATE_DELTA")
    surface = record["material_surface"]
    material = any(surface.values())
    bounded = (record["bounded_diff"]["reversible"]
               and record["bounded_diff"]["files_changed"] <= record["bounded_diff"]["max_files"])
    owners = all(row["owner_item"] for row in record["affected_paths"])
    if not material and bounded and owners:
        return _decision("repair-in-current-attempt", record=record,
                         reason_code="BOUNDED_NONMATERIAL_REPAIR")
    if not material:
        return _decision("gather-evidence", record=record,
                         reason_code="REPAIR_BOUNDS_OR_ATTRIBUTION_MISSING")
    if record["design"] is not None:
        return _decision("design-required", record=record,
                         reason_code="NEW_MATERIAL_DECISION_SURFACE")
    return _decision("gather-evidence", record=record,
                     reason_code="DESIGN_EVIDENCE_REQUIRED")
