"""Bounded owner-attention and terminal telemetry from strict journal replay only."""
from __future__ import annotations

import hashlib
import json

from . import authority

SCHEMA_VERSION = "artifex-terminal-telemetry-v1"
MAX_PACKET_ITEMS = 32
MAX_PACKET_BYTES = 32_768


class TelemetryRefusal(ValueError):
    """The replay is not a safe source for a bounded terminal packet."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stable_id(decision: dict) -> str:
    identity = {
        "operation": decision["operation"], "reason_code": decision["reason_code"],
        "sources": decision["controlling_sources"], "affected_slices": decision["affected_slices"],
        "source_set_hash": decision["source_set_hash"], "mandate_hash": decision["mandate_hash"],
        "recommendation": decision["selected_alternative"], "alternatives": decision["rejected_alternatives"],
    }
    return hashlib.sha256(_canonical(identity)).hexdigest()


def _row(record: dict) -> dict:
    required = {"seq", "record_hash", "event", "slice_id", "attempt", "state_after", "evidence"}
    if not isinstance(record, dict) or not required.issubset(record):
        raise TelemetryRefusal("REPLAY_RECORD_INVALID")
    if not isinstance(record["seq"], int) or record["seq"] < 1:
        raise TelemetryRefusal("REPLAY_RECORD_INVALID")
    if not isinstance(record["record_hash"], str) or len(record["record_hash"]) != 64:
        raise TelemetryRefusal("REPLAY_RECORD_INVALID")
    if not isinstance(record["evidence"], dict):
        raise TelemetryRefusal("REPLAY_RECORD_INVALID")
    return record


def project(records: list[dict], *, max_items: int = MAX_PACKET_ITEMS,
            max_bytes: int = MAX_PACKET_BYTES) -> dict:
    """Produce a deterministic, redacted projection; snapshots and raw provider output are ignored."""
    if not isinstance(records, list) or not isinstance(max_items, int) or max_items < 1:
        raise TelemetryRefusal("REPLAY_RECORD_INVALID")
    if not isinstance(max_bytes, int) or max_bytes < 256:
        raise TelemetryRefusal("PACKET_LIMIT_INVALID")
    checked = [_row(record) for record in records]
    if [record["seq"] for record in checked] != sorted(record["seq"] for record in checked):
        raise TelemetryRefusal("REPLAY_ORDER_INVALID")
    decisions: dict[str, dict] = {}
    decision_ids: dict[str, str] = {}
    terminal: list[dict] = []
    unknown: dict[str, str] = {}
    for record in checked:
        evidence = record["evidence"]
        decision = evidence.get("authority_decision")
        if decision is not None:
            try:
                authority.validate_record(decision)
            except authority.AuthorityRefusal as exc:
                raise TelemetryRefusal("AUTHORITY_DECISION_INVALID") from exc
            if decision["resolved_class"] == "OWNER":
                stable = _stable_id(decision)
                decisions[stable] = {
                    "finding_id": stable, "decision_id": decision["decision_id"],
                    "attention": decision["attention"], "controlling_sources": decision["controlling_sources"],
                    "recommendation": decision["selected_alternative"], "alternatives": decision["rejected_alternatives"],
                    "blast_radius": decision["blast_radius"], "rollback": decision["rollback"],
                    "affected_slices": decision["affected_slices"],
                    "no_decision_consequence": decision["no_decision_consequence"],
                    "blocking_dependencies": decision["blocking_dependencies"], "reason_code": decision["reason_code"],
                    "status": "open", "seq": record["seq"],
                }
                decision_ids[decision["decision_id"]] = stable
        resolution = evidence.get("attention_resolution")
        if resolution is not None:
            if (not isinstance(resolution, dict) or set(resolution) != {"decision_id", "outcome"}
                    or not isinstance(resolution["decision_id"], str)
                    or resolution["outcome"] not in {"resolved", "withdrawn"}):
                raise TelemetryRefusal("ATTENTION_RESOLUTION_INVALID")
            stable = decision_ids.get(resolution["decision_id"])
            if stable is None or decisions[stable]["status"] != "open":
                raise TelemetryRefusal("ATTENTION_RESOLUTION_UNKNOWN")
            decisions[stable]["status"] = resolution["outcome"]
        observation = evidence.get("observation")
        if isinstance(observation, dict) and observation.get("kind") in {"provider_unavailable", "provider_failure", "orphaned"}:
            reason = observation.get("reason_code")
            if not isinstance(reason, str) or not reason:
                raise TelemetryRefusal("UNKNOWN_REASON_MISSING")
            unknown[f"seq:{record['seq']}:provider"] = reason
        if record["state_after"] in {"ACCEPTED", "ABORTED", "OWNER"} or record["event"] in {"budget_exhausted", "provider_unavailable"}:
            terminal.append({"seq": record["seq"], "event": record["event"], "slice_id": record["slice_id"],
                             "attempt": record["attempt"], "state": record["state_after"], "record_hash": record["record_hash"]})
    rows = list(decisions.values())
    closed = sorted((row for row in rows if row["status"] != "open"), key=lambda row: (row["seq"], row["finding_id"]))
    for row in rows:
        row.pop("seq")
    immediate = sorted((row for row in rows if row["status"] == "open" and row["attention"] == "immediate"), key=lambda row: row["finding_id"])
    routine = [row for row in rows if row["status"] == "open" and row["attention"] == "batched"]
    by_id = {row["finding_id"]: row for row in routine}
    ordered: list[dict] = []
    while by_id:
        ready = sorted((row for row in by_id.values()
                        if not any(dep in by_id for dep in row["blocking_dependencies"])),
                       key=lambda row: row["finding_id"])
        if not ready:
            raise TelemetryRefusal("ATTENTION_DEPENDENCY_CYCLE")
        for row in ready:
            ordered.append(row)
            by_id.pop(row["finding_id"])
    if len(immediate) + len(ordered) > max_items:
        raise TelemetryRefusal("PACKET_ITEM_CAP")
    packet = {"schema_version": SCHEMA_VERSION,
              "queue": {"immediate": immediate, "batched": ordered},
              "closed_attention": closed,
              "terminal": terminal, "unknown_reasons": unknown,
              "replay": {"first_seq": checked[0]["seq"] if checked else 0,
                         "last_seq": checked[-1]["seq"] if checked else 0,
                         "tail_hash": checked[-1]["record_hash"] if checked else "0" * 64}}
    if len(_canonical(packet)) > max_bytes:
        raise TelemetryRefusal("PACKET_BYTE_CAP")
    return packet
