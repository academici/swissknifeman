"""Typed producer readiness and terminal-phase re-entry evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class ReadinessError(ValueError):
    pass


_ITEM = re.compile(r"^P[0-9]+\.[0-9]+$")
_PHASE = re.compile(r"^P[0-9]+$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_DIRECTIVE = re.compile(
    r"`producer-readiness/v1`\s*:\s*consumer=(P\d+\.\d+)\s*;\s*"
    r"modes=(nonempty-candidates\|empty-by-decision|empty-by-decision\|nonempty-candidates)")


def _closed(value, fields, name):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ReadinessError(f"{name}: closed schema mismatch")


def _strings(value, name, *, required=False):
    if not isinstance(value, list) or (required and not value) or len(value) != len(set(value)) \
            or any(not isinstance(row, str) or not row for row in value):
        raise ReadinessError(f"{name}: expected unique strings")


def directive(deliverables: str) -> dict | None:
    matches = _DIRECTIVE.findall(deliverables or "")
    if not matches:
        return None
    if len(matches) != 1:
        raise ReadinessError("Deliverables: требуется ровно одна producer-readiness/v1 directive")
    consumer, modes = matches[0]
    return {"consumer_item": consumer, "modes": tuple(modes.split("|"))}


def validate_readiness(record: dict) -> None:
    fields = {"schema_version", "producer_item", "consumer_item", "mode", "roots", "command",
              "candidate_count", "candidate_paths_sha256", "source_commit", "predicate", "exclusions"}
    if not isinstance(record, dict):
        raise ReadinessError("producer readiness: expected object")
    if record.get("mode") == "empty-by-decision":
        fields.add("owner_decision")
    _closed(record, fields, "producer readiness")
    if record["schema_version"] != "producer-readiness/v1" or not _ITEM.fullmatch(record["producer_item"]) \
            or not _ITEM.fullmatch(record["consumer_item"]):
        raise ReadinessError("producer readiness: invalid identity")
    if record["mode"] not in {"nonempty-candidates", "empty-by-decision"}:
        raise ReadinessError("producer readiness: invalid mode")
    _strings(record["roots"], "roots", required=True)
    _strings(record["exclusions"], "exclusions")
    if not isinstance(record["command"], str) or not record["command"] or not isinstance(record["predicate"], str) or not record["predicate"]:
        raise ReadinessError("producer readiness: command/predicate required")
    if isinstance(record["candidate_count"], bool) or not isinstance(record["candidate_count"], int) or record["candidate_count"] < 0:
        raise ReadinessError("producer readiness: candidate_count invalid")
    if not _SHA.fullmatch(record["candidate_paths_sha256"]) or not _COMMIT.fullmatch(record["source_commit"]):
        raise ReadinessError("producer readiness: digest/commit invalid")
    if record["mode"] == "nonempty-candidates" and record["candidate_count"] == 0:
        raise ReadinessError("nonempty-candidates requires candidate_count > 0")
    if record["mode"] == "empty-by-decision":
        if record["candidate_count"] != 0 or not re.fullmatch(r"D[0-9]+", record["owner_decision"]):
            raise ReadinessError("empty-by-decision requires zero candidates and D#")


def readiness_digest(record: dict) -> str:
    validate_readiness(record)
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_reentry(record: dict) -> None:
    _closed(record, {"schema_version", "phase_id", "trigger", "evidence_ids", "origin_item", "resume_item"}, "phase reentry")
    if record["schema_version"] != "phase-reentry-justification/v1" or not _PHASE.fullmatch(record["phase_id"]) \
            or not _ITEM.fullmatch(record["origin_item"]) or not _ITEM.fullmatch(record["resume_item"]):
        raise ReadinessError("phase reentry: invalid identity")
    if record["trigger"] not in {"owner-decision-change", "terminal-evidence-invalid", "safety-or-authority-boundary"}:
        raise ReadinessError("phase reentry: trigger is not allowed")
    _strings(record["evidence_ids"], "evidence_ids", required=True)


def validate_fix_branch(record: dict, *, declared_items=()) -> None:
    fields = {"schema_version", "origin_item", "owner", "scope", "priority", "rollback", "validation", "target_item", "resume_item"}
    _closed(record, fields, "fix branch")
    if record["schema_version"] != "fix-branch/v1" or record["priority"] != "priority":
        raise ReadinessError("fix branch: invalid version or priority")
    for field in ("origin_item", "target_item", "resume_item"):
        if not _ITEM.fullmatch(record[field]):
            raise ReadinessError(f"fix branch: {field} must be Pn.m")
    for field in ("owner", "scope", "rollback", "validation"):
        if not isinstance(record[field], str) or not record[field]:
            raise ReadinessError(f"fix branch: {field} required")
    if declared_items and record["target_item"] not in set(declared_items):
        raise ReadinessError("fix branch: target item is not declared")


def terminal_projection(record: dict) -> dict:
    """Return the only consumer-visible, digest-bound subset."""
    validate_readiness(record)
    return {"schema_version": "producer-readiness-projection/v1", "digest": readiness_digest(record),
            "producer_item": record["producer_item"], "consumer_item": record["consumer_item"],
            "mode": record["mode"], "candidate_count": record["candidate_count"],
            "source_commit": record["source_commit"]}
