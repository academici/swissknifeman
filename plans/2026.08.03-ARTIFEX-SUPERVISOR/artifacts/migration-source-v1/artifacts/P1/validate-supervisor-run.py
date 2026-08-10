#!/usr/bin/env python3
"""Independent stdlib conformance check for supervisor-run-v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import sys
from pathlib import Path


EVENT_SCHEMA = "supervisor-run-event-v1"
ZERO_HASH = "0" * 64
RECORD_KEYS = {
    "schema_version", "seq", "prev_hash", "record_hash", "ts", "run_id",
    "slice_id", "attempt", "event", "state_before", "state_after",
    "idempotency_key", "input_hashes", "evidence", "redaction",
}
REQUIRED_CONTRACT_MARKERS = (
    "intent", "fsync", "reopen", "verify", "observation", "atomic",
    "snapshot.json", "writer.lock", "POSTIMAGE_THIRD_STATE", "SOURCE_DRIFT",
    "ORPHAN_IDENTITY_AMBIGUOUS", "REDACTION_VIOLATION",
    "12d602038c54f5b9b07616e5a9f718be28c5192d29770a5862a21f79351577aa",
)
REQUIRED_GAPS = (
    "exclusive_lock", "hash_chain", "intent_observation", "atomic_snapshot",
    "exact_reconcile", "source_drift", "orphan_identity",
    "no_duplicate_projection",
)
REQUIRED_MUTATIONS = {
    "none": "allow",
    "bad_record_hash": "HASH_MISMATCH",
    "bad_prev_hash": "CHAIN_MISMATCH",
    "sequence_gap": "SEQUENCE_GAP",
    "reorder": "REORDERED_RECORD",
    "truncate": "TRUNCATED_RECORD",
    "duplicate": "DUPLICATE_EVENT",
    "unknown_key": "UNKNOWN_RECORD_KEY",
    "unknown_version": "UNKNOWN_SCHEMA_VERSION",
    "unknown_event": "UNKNOWN_EVENT",
    "unknown_state": "UNKNOWN_STATE",
    "illegal_transition": "ILLEGAL_TRANSITION",
    "observation_without_intent": "OBSERVATION_WITHOUT_INTENT",
    "idempotency_collision": "IDEMPOTENCY_COLLISION",
}
REQUIRED_RECONCILE = {
    ("before_intent", "exact_preimage", "not_needed"):
        ("READY", "no_boundary_authorized", False, False),
    ("after_intent_before_boundary", "exact_preimage", "not_needed"):
        ("ROLLED_BACK", "exact_no_effect", True, False),
    ("during_boundary_before_observation", "exact_postimage", "not_needed"):
        ("VALIDATING", "validate_without_rerun", False, False),
    ("during_boundary_before_observation", "recognized_partial", "valid"):
        ("ROLLED_BACK", "whole_slice_rollback", True, False),
    ("during_boundary_before_observation", "recognized_partial", "missing"):
        ("INCIDENT", "BACKUP_MISSING", False, False),
    ("during_boundary_before_observation", "recognized_partial", "hash_mismatch"):
        ("INCIDENT", "BACKUP_HASH_MISMATCH", False, False),
    ("during_boundary_before_observation", "unknown_partial", "valid"):
        ("INCIDENT", "PARTIAL_UNRECOGNIZED", False, False),
    ("during_boundary_before_observation", "third_state", "not_applicable"):
        ("INCIDENT", "POSTIMAGE_THIRD_STATE", False, False),
    ("after_observation_before_validation", "exact_postimage", "not_needed"):
        ("VALIDATING", "validate_recorded_postimage", False, False),
    ("after_validation_before_projection", "accepted_postimage", "not_needed"):
        ("ACCEPTED", "idempotent_bookkeeping_only", False, False),
    ("orphan_reconcile", "ambiguous_process_identity", "not_applicable"):
        ("OWNER_ATTENTION", "ORPHAN_IDENTITY_AMBIGUOUS", False, False),
    ("before_intent", "source_drift", "not_applicable"):
        ("OWNER_ATTENTION", "SOURCE_DRIFT", False, False),
    ("after_intent_before_boundary", "source_drift", "not_applicable"):
        ("INCIDENT", "SOURCE_DRIFT", False, False),
}
REQUIRED_BOUNDARIES = {
    "lock_held": "LOCK_HELD",
    "lock_identity_ambiguous": "LOCK_IDENTITY_AMBIGUOUS",
    "run_identity_mismatch": "RUN_IDENTITY_MISMATCH",
    "input_hash_missing": "INPUT_HASH_MISSING",
    "redaction_violation": "REDACTION_VIOLATION",
    "budget_limit": "BUDGET_LIMIT",
    "owner_decision_missing": "OWNER_DECISION_REQUIRED",
}


class Refusal(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def record_hash(record):
    unsigned = {key: value for key, value in record.items() if key != "record_hash"}
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def chain_payloads(payloads):
    records = []
    previous = ZERO_HASH
    for seq, payload in enumerate(payloads, 1):
        record = {
            "schema_version": EVENT_SCHEMA,
            "seq": seq,
            "prev_hash": previous,
            **copy.deepcopy(payload),
        }
        record["record_hash"] = record_hash(record)
        records.append(record)
        previous = record["record_hash"]
    return records


def rechain(records):
    previous = ZERO_HASH
    for record in records:
        record["prev_hash"] = previous
        record["record_hash"] = record_hash(record)
        previous = record["record_hash"]
    return records


def as_jsonl(records):
    return "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                   for record in records)


def parse_declared_set(text, name):
    pattern = rf"<!-- declared-set: {re.escape(name)} -->\s*```text\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"contract: missing declared set {name}")
    values = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    if len(values) != len(set(values)):
        raise ValueError(f"contract: duplicate value in {name}")
    return values


def validate_state_machine(data, contract_text):
    declared = data["declared"]
    states = declared["states"]
    events = declared["events"]
    reasons = declared["refusal_reasons"]
    for name, values in (("states", states), ("events", events),
                         ("refusal_reasons", reasons)):
        if values != parse_declared_set(contract_text, name):
            raise ValueError(f"contract/cases declared set mismatch: {name}")
        if len(values) != len(set(values)):
            raise ValueError(f"cases: duplicate {name}")

    rules = data["state_rules"]
    if set(rules) != set(states):
        raise ValueError("state_rules must cover every and only declared state")
    cells = set()
    legal = 0
    refused = 0
    for state in states:
        rule = rules[state]
        if set(rule) != {"on", "otherwise"}:
            raise ValueError(f"{state}: state rule keys are not closed")
        if rule["otherwise"] not in reasons:
            raise ValueError(f"{state}: unknown otherwise refusal")
        for event, next_state in rule["on"].items():
            if event not in events or next_state not in states:
                raise ValueError(f"{state}: unknown transition member")
        for event in events:
            cell = (state, event)
            if cell in cells:
                raise ValueError(f"duplicate state/event cell: {cell}")
            cells.add(cell)
            if event in rule["on"]:
                legal += 1
            else:
                refused += 1
    expected_cells = {(state, event) for state in states for event in events}
    if cells != expected_cells:
        raise ValueError("state/event cartesian product is incomplete")
    if rules["CREATED"]["on"].get("freeze_run") != "READY":
        raise ValueError("missing run freeze transition")
    if rules["OBSERVED"]["on"].get("validation_green") != "ACCEPTED":
        raise ValueError("worker observation cannot reach independent acceptance")
    if rules["COMPLETED"]["on"] or rules["ABORTED"]["on"]:
        raise ValueError("terminal supervisor states must not advance")
    return len(cells), legal, refused


def verify_stream(raw, *, states, events, rules):
    if not raw.endswith("\n"):
        raise Refusal("TRUNCATED_RECORD")
    expected_seq = 1
    previous = ZERO_HASH
    seen_hashes = set()
    idempotency_owners = {}
    durable_intents = set()
    last_state = None
    for raw_line in io.StringIO(raw):
        if not raw_line.strip():
            raise Refusal("TRUNCATED_RECORD")
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise Refusal("TRUNCATED_RECORD") from exc
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise Refusal("UNKNOWN_RECORD_KEY")
        if record["schema_version"] != EVENT_SCHEMA:
            raise Refusal("UNKNOWN_SCHEMA_VERSION")
        if record["record_hash"] in seen_hashes:
            raise Refusal("DUPLICATE_EVENT")
        seq = record["seq"]
        if seq != expected_seq:
            if isinstance(seq, int) and seq == expected_seq + 1:
                raise Refusal("REORDERED_RECORD")
            raise Refusal("SEQUENCE_GAP")
        if record["prev_hash"] != previous:
            raise Refusal("CHAIN_MISMATCH")
        if record_hash(record) != record["record_hash"]:
            raise Refusal("HASH_MISMATCH")
        event = record["event"]
        before = record["state_before"]
        after = record["state_after"]
        if event not in events:
            raise Refusal("UNKNOWN_EVENT")
        if before not in states or after not in states:
            raise Refusal("UNKNOWN_STATE")
        key = record["idempotency_key"]
        if key is not None:
            owner = (record["run_id"], record["slice_id"], record["attempt"])
            prior = idempotency_owners.setdefault(key, owner)
            if prior != owner:
                raise Refusal("IDEMPOTENCY_COLLISION")
        if event == "append_observation" and key not in durable_intents:
            raise Refusal("OBSERVATION_WITHOUT_INTENT")
        if event == "append_intent":
            durable_intents.add(key)
        expected_after = rules[before]["on"].get(event)
        if expected_after is None or expected_after != after:
            raise Refusal(rules[before]["otherwise"])
        if last_state is not None and before != last_state:
            raise Refusal("ILLEGAL_TRANSITION")
        last_state = after
        seen_hashes.add(record["record_hash"])
        previous = record["record_hash"]
        expected_seq += 1
    return "allow"


def mutated_jsonl(payloads, mutation):
    records = chain_payloads(payloads)
    if mutation == "none":
        return as_jsonl(records)
    if mutation == "bad_record_hash":
        records[1]["record_hash"] = "f" * 64
    elif mutation == "bad_prev_hash":
        records[1]["prev_hash"] = "e" * 64
    elif mutation == "sequence_gap":
        records[1]["seq"] += 2
        records[1]["record_hash"] = record_hash(records[1])
    elif mutation == "reorder":
        records[1], records[2] = records[2], records[1]
    elif mutation == "truncate":
        return as_jsonl(records)[:-2]
    elif mutation == "duplicate":
        records.insert(2, copy.deepcopy(records[1]))
    elif mutation == "unknown_key":
        records[1]["unexpected"] = True
        rechain(records)
    elif mutation == "unknown_version":
        records[1]["schema_version"] = "supervisor-run-event-v2"
        rechain(records)
    elif mutation == "unknown_event":
        records[1]["event"] = "guess_and_continue"
        rechain(records)
    elif mutation == "unknown_state":
        records[1]["state_after"] = "MAYBE"
        rechain(records)
    elif mutation == "illegal_transition":
        records[1]["event"] = "validation_green"
        records[1]["state_after"] = "ACCEPTED"
        rechain(records)
    elif mutation == "observation_without_intent":
        altered = [copy.deepcopy(payloads[0]), copy.deepcopy(payloads[3])]
        altered[1]["state_before"] = "READY"
        return as_jsonl(chain_payloads(altered))
    elif mutation == "idempotency_collision":
        records[2]["slice_id"] = "P9.9"
        rechain(records)
    else:
        raise ValueError(f"unknown mutation fixture: {mutation}")
    return as_jsonl(records)


def validate_journal_cases(data):
    states = set(data["declared"]["states"])
    events = set(data["declared"]["events"])
    rules = data["state_rules"]
    payloads = data["journal_fixture"]["payloads"]
    observed = {}
    for case in data["journal_mutations"]:
        mutation = case["mutation"]
        if mutation in observed:
            raise ValueError(f"duplicate journal mutation: {mutation}")
        raw = mutated_jsonl(payloads, mutation)
        try:
            result = verify_stream(raw, states=states, events=events, rules=rules)
        except Refusal as exc:
            result = exc.reason
        observed[mutation] = result
        if result != case["expected"]:
            raise ValueError(
                f"{case['id']}: expected {case['expected']}, observed {result}")
    if observed != REQUIRED_MUTATIONS:
        raise ValueError(f"journal mutation coverage mismatch: {observed}")
    return len(observed)


def validate_reconcile_cases(data):
    observed = {}
    for case in data["reconcile_cases"]:
        key = (case["cut"], case["observed"], case["backup"])
        value = (
            case["expected_state"], case["expected_reason"],
            case["retry"], case["public_call"],
        )
        if key in observed:
            raise ValueError(f"duplicate reconcile case: {key}")
        observed[key] = value
    if observed != REQUIRED_RECONCILE:
        raise ValueError("reconcile matrix differs from frozen expected outcomes")
    if any(value[3] for value in observed.values()):
        raise ValueError("reconcile must never repeat the public call")
    return len(observed)


def validate_boundary_cases(data):
    observed = {}
    for case in data["boundary_cases"]:
        if case["condition"] in observed:
            raise ValueError(f"duplicate boundary condition: {case['condition']}")
        if case["allows_effect"]:
            raise ValueError(f"{case['id']}: refusal boundary allows an effect")
        observed[case["condition"]] = case["expected"]
    if observed != REQUIRED_BOUNDARIES:
        raise ValueError("boundary refusal coverage mismatch")
    return len(observed)


def validate_gap(text):
    missing = [marker for marker in REQUIRED_GAPS if marker not in text]
    if missing:
        raise ValueError(f"gap crosswalk missing machine markers: {missing}")
    if "harness.run.journal" not in text or "task.journal" not in text:
        raise ValueError("gap crosswalk loses live/per-plan journal ownership")
    if "Claude Code only" not in text:
        raise ValueError("gap crosswalk must preserve the current provider limitation")
    if "not relabelled as a\ndurable supervisor" not in text:
        raise ValueError("gap crosswalk overclaims the live driver")
    rows = [line for line in text.splitlines() if line.startswith("|")]
    if len(rows) < 17:
        raise ValueError("gap crosswalk is missing required ownership rows")
    return len(rows) - 2


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--gap", required=True)
    args = parser.parse_args(argv)
    try:
        contract_text = Path(args.contract).read_text(encoding="utf-8")
        gap_text = Path(args.gap).read_text(encoding="utf-8")
        data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
        if data.get("schema_version") != "supervisor-run-cases-v1":
            raise ValueError("cases: unknown schema_version")
        if data.get("contract_version") != "1.0.0":
            raise ValueError("cases: contract_version is not frozen v1")
        missing = [marker for marker in REQUIRED_CONTRACT_MARKERS
                   if marker not in contract_text]
        if missing:
            raise ValueError(f"contract missing normative markers: {missing}")
        cells, legal, refused = validate_state_machine(data, contract_text)
        journal_cases = validate_journal_cases(data)
        reconcile_cases = validate_reconcile_cases(data)
        boundary_cases = validate_boundary_cases(data)
        gap_rows = validate_gap(gap_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError,
            TypeError, ValueError) as exc:
        print(f"supervisor-run: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "supervisor-run: OK "
        f"({cells} transition cells; {legal} legal/{refused} refused; "
        f"{journal_cases} journal mutations; {reconcile_cases} reconcile cases; "
        f"{boundary_cases} boundary refusals; {gap_rows} gap rows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
