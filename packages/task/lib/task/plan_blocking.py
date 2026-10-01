"""Deterministic continue-first policy for a suspected Task block.

The model/reviewer supplies evidence only.  This reducer owns the action and is
the only package-owned path that may turn a candidate into a terminal block.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


class BlockCandidateError(ValueError):
    """The candidate is not a valid block-candidate/v1 value."""


class RagEvidenceError(BlockCandidateError):
    """The mandatory Perplexity evidence is absent or not digest-qualified."""


ACTION_REASON_CODES = {
    "repair-candidate": "CANDIDATE_INVALID",
    "continue-local-repair": "LOCAL_REPAIR_REQUIRED",
    "gather-rag": "EXTERNAL_RAG_REQUIRED",
    "request-isolated-review": "ISOLATED_REVIEW_REQUIRED",
    "repair-review": "REVIEW_INVALID",
    "gather-evidence": "EVIDENCE_INSUFFICIENT",
    "terminal-block": "BLOCK_CONFIRMED",
}

ACTION_OBSERVATION_RESULTS = {
    "repair-candidate": "block-candidate",
    "continue-local-repair": "local-repair",
    "gather-rag": "rag-pending",
    "request-isolated-review": "block-candidate",
    "repair-review": "block-candidate",
    "gather-evidence": "block-candidate",
    "terminal-block": None,
}

_ROOT_FIELDS = frozenset((
    "schema_version", "plan_id", "item_id", "signal_class", "scope_class", "external",
    "scope_coverage", "boundary_evidence", "executor_actor", "evidence_ids",
    "resolutions_tried", "rag", "review",
))
_OPTIONAL_ROOT_FIELDS = frozenset(("repair_decision", "repair_digest"))
_RAG_FIELDS = frozenset(("required", "status", "evidence_ids"))
_REVIEW_FIELDS = frozenset(("reviewer_actor", "context", "verdict", "evidence_ids"))
_ITEM_RE = re.compile(r"^P[0-9]+\.[0-9]+$")
_PERPLEXITY_EVIDENCE_RE = re.compile(r"^rag:perplexity:sha256:[0-9a-f]{64}$")
_GENERIC_BOUNDARY_EVIDENCE_RE = re.compile(
    r"^(?:boundary(?:-evidence)?|generic|unknown|n/?a|none|spec:declared-boundary)$",
    re.IGNORECASE,
)
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "configs" / "block-candidate-v1.schema.json"


def _schema() -> dict:
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlockCandidateError(f"diagram block-candidate/v1 is not readable: {exc}") from exc


def _string_list(value, *, field: str, allow_empty: bool) -> bool:
    if not isinstance(value, list) or (not allow_empty and not value):
        return False
    return (len(value) == len(set(value))
            and all(isinstance(item, str) and item for item in value))


def _boundary_evidence(value) -> bool:
    return (_string_list(value, field="boundary_evidence", allow_empty=True)
            and all(not _GENERIC_BOUNDARY_EVIDENCE_RE.fullmatch(item.strip()) for item in value))


def _closed_fields(value, expected, *, field, optional=frozenset()):
    if not isinstance(value, dict):
        raise BlockCandidateError(f"{field}: pending object")
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected - optional)
    if missing:
        raise BlockCandidateError(f"{field}: no fields {missing}")
    if unknown:
        raise BlockCandidateError(f"{field}: unknown fields {unknown}")


def _has_external_class(candidate: dict) -> bool:
    return (candidate["scope_class"] == "external"
            or candidate["signal_class"] == "external-dependency")


def validate(candidate: dict) -> None:
    """Validate the closed schema without adding a runtime JSON-schema dependency."""
    _closed_fields(candidate, _ROOT_FIELDS, field="candidate", optional=_OPTIONAL_ROOT_FIELDS)
    source = _schema()["properties"]
    if candidate["schema_version"] != "block-candidate/v1":
        raise BlockCandidateError("schema_version: pending block-candidate/v1")
    for field in ("plan_id", "executor_actor"):
        if not isinstance(candidate[field], str) or not candidate[field]:
            raise BlockCandidateError(f"{field}: expected non-empty string")
    if not isinstance(candidate["item_id"], str) or not _ITEM_RE.fullmatch(candidate["item_id"]):
        raise BlockCandidateError("item_id: pending Pn.m")
    for field in ("signal_class", "scope_class"):
        if candidate[field] not in source[field]["enum"]:
            raise BlockCandidateError(f"{field}: value outside closed enum")
    if candidate["scope_coverage"] not in source["scope_coverage"]["enum"]:
        raise BlockCandidateError("scope_coverage: value outside closed enum")
    if not _boundary_evidence(candidate["boundary_evidence"]):
        raise BlockCandidateError(
            "boundary_evidence: expected specific unique evidence IDs")
    if not isinstance(candidate["external"], bool):
        raise BlockCandidateError("external: pending boolean")
    if _has_external_class(candidate) and not candidate["external"]:
        raise RagEvidenceError("external enum requires external=true and mandatory RAG")
    if not _string_list(candidate["evidence_ids"], field="evidence_ids", allow_empty=False):
        raise BlockCandidateError("evidence_ids: pending non-empty unique string array")
    if not _string_list(candidate["resolutions_tried"], field="resolutions_tried", allow_empty=True):
        raise BlockCandidateError("resolutions_tried: pending unique string array")

    rag = candidate["rag"]
    _closed_fields(rag, _RAG_FIELDS, field="rag")
    if not isinstance(rag["required"], bool) or rag["status"] not in source["rag"]["properties"]["status"]["enum"]:
        raise BlockCandidateError("rag: invalid required/status")
    if not _string_list(rag["evidence_ids"], field="rag.evidence_ids", allow_empty=True):
        raise BlockCandidateError("rag.evidence_ids: pending unique string array")
    if candidate["external"] != rag["required"]:
        raise BlockCandidateError("rag.required must match external")
    if not rag["required"] and (rag["status"] != "not-required" or rag["evidence_ids"]):
        raise BlockCandidateError("rag without external should be not-required without evidence")
    if rag["required"] and rag["status"] == "not-required":
        raise RagEvidenceError("external RAG cannot be not-required")
    if rag["status"] in ("missing", "pending", "unavailable") and rag["evidence_ids"]:
        raise BlockCandidateError(f"{rag['status']} RAG does not accept evidence_ids")
    if rag["status"] == "fallback-only" and not rag["evidence_ids"]:
        raise BlockCandidateError("fallback-only RAG requires provisional evidence_ids")
    if rag["status"] == "verified" and not rag["evidence_ids"]:
        raise RagEvidenceError("verified RAG requires evidence_ids")
    if rag["status"] == "verified" and not all(
            _PERPLEXITY_EVIDENCE_RE.fullmatch(evidence_id)
            for evidence_id in rag["evidence_ids"]):
        raise RagEvidenceError(
            "verified RAG requires digest-qualified Perplexity evidence_ids")

    review = candidate["review"]
    if review is None:
        return
    _closed_fields(review, _REVIEW_FIELDS, field="review")
    if (not isinstance(review["reviewer_actor"], str) or not review["reviewer_actor"]
            or review["context"] != "isolated-child-return"
            or review["verdict"] not in source["review"]["oneOf"][1]["properties"]["verdict"]["enum"]
            or not _string_list(review["evidence_ids"], field="review.evidence_ids", allow_empty=False)):
        raise BlockCandidateError("review: does not pass closed circuit")
    if ("repair_decision" in candidate) != ("repair_digest" in candidate):
        raise BlockCandidateError("repair evidence requires record and digest together")
    if "repair_decision" in candidate:
        from task import plan_repair
        try:
            plan_repair.validate(candidate["repair_decision"])
        except plan_repair.RepairDecisionError as exc:
            raise BlockCandidateError(f"repair_decision: {exc}") from exc
        if candidate["repair_digest"] != plan_repair.digest(candidate["repair_decision"]):
            raise BlockCandidateError("repair_digest: does not match repair_decision")


def _decision(action: str) -> dict:
    return {
        "action": action,
        "terminal_allowed": action == "terminal-block",
        "reason_code": ACTION_REASON_CODES[action],
        "journal_result": ACTION_OBSERVATION_RESULTS[action],
    }


def evaluate(candidate: dict, *, plan_dir=None) -> dict:
    """Choose the next action; missing proof always remains nonterminal."""
    try:
        validate(candidate)
    except RagEvidenceError:
        return _decision("gather-rag")
    except BlockCandidateError:
        return _decision("repair-candidate")
    if "repair_decision" in candidate:
        from task import plan_repair
        repair = plan_repair.evaluate(candidate["repair_decision"], plan_dir=plan_dir)
        if repair["action"] != "block-candidate":
            # Block confirmation consumes the upstream result; it never gets to
            # relabel a qualified repair as a terminal premise.
            return {**repair, "journal_result": "local-repair" if repair["action"] == "repair-in-current-attempt" else "block-candidate"}
    if candidate["scope_class"] == "local":
        return _decision("continue-local-repair")
    if (candidate["signal_class"] == "acceptance-failure"
            and candidate["scope_coverage"] == "in-scope"):
        # More files, errors or elapsed time are work, not a boundary.  An
        # acceptance failure already covered by the item is decomposed and repaired
        # in the same attempt even when a reviewer calls its size material.
        return _decision("continue-local-repair")
    rag = candidate["rag"]
    if candidate["external"] and (rag["status"] != "verified" or not rag["evidence_ids"]):
        return _decision("gather-rag")
    if candidate["signal_class"] in {
        "procedural",
        "transient",
        "dependency-not-ready",
        "unrelated-pre-existing",
        "routing-rejection",
        "tool-noise",
        "local-reversible",
    }:
        return _decision("continue-local-repair")
    review = candidate["review"]
    if review is None:
        return _decision("request-isolated-review")
    if (review["reviewer_actor"] == candidate["executor_actor"]
            or review["context"] != "isolated-child-return"):
        return _decision("repair-review")
    verdict = review["verdict"]
    if verdict == "JUSTIFIED":
        if not candidate["boundary_evidence"]:
            return _decision("gather-evidence")
        return _decision("terminal-block")
    if verdict == "AVOIDABLE":
        return _decision("continue-local-repair")
    if verdict == "INSUFFICIENT_EVIDENCE":
        return _decision("gather-evidence")
    if verdict in ("OUT_OF_SCOPE", "MALFORMED"):
        return _decision("repair-candidate")
    return _decision("repair-review")
