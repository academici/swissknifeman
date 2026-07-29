#!/usr/bin/env python3
"""Deterministic stdlib-only validator for the AGENT-RELIABILITY evidence bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

AUDIT = ("perplexity-audit.md", "dd686f91b4ad8e3279d92a28fb7061cd026608a4757be115643a23faa4a0d37b", 279780, 2993)
CLAIM_RANGES = ((21, 169), (312, 463), (625, 766), (767, 912), (1049, 1194), (1363, 1529), (1538, 1939), (2903, 2993))
REQUIRED_CASES = {"missed-consumer-cold-start", "missing-launch-block-intra-session", "wrong-scope-return", "five-audit-loop", "honest-http-clean-control"}

def fail(message):
    raise ValueError(message)

def raw_stats(path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data), data.count(b"\n")

def load_json(root, relative):
    try:
        return json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid JSON {relative}: {exc}")

def verify(root):
    schema = load_json(root, "schema.json")
    manifest = load_json(root, "manifests/bundle-manifest.json")
    if manifest.get("schema_version") != schema.get("schema_version"):
        fail("manifest/schema version mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or manifest.get("entry_count") != len(entries):
        fail("manifest entry count mismatch")
    paths = set()
    for entry in entries:
        if set(schema["manifest_entry_required"]) - set(entry):
            fail(f"manifest entry misses required field: {entry}")
        relative = entry["path"]
        if relative.startswith("/") or ".." in Path(relative).parts or relative in paths:
            fail(f"unsafe or duplicate manifest path: {relative}")
        paths.add(relative)
        actual = raw_stats(root / relative)
        expected = (entry["sha256"], entry["bytes"], entry["lines"])
        if actual != expected:
            fail(f"integrity mismatch: {relative}; expected {expected}, got {actual}")
    if "manifests/bundle-manifest.json" in paths:
        fail("self-hashing manifest is not supported")
    disk_paths = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if any("__pycache__" in Path(path).parts for path in disk_paths):
        fail("compiled Python cache is not permitted in the bundle")
    expected_disk_paths = paths | {"manifests/bundle-manifest.json"}
    if disk_paths != expected_disk_paths:
        fail(f"manifest disk-set mismatch: missing={sorted(expected_disk_paths - disk_paths)}, extra={sorted(disk_paths - expected_disk_paths)}")
    for relative in schema["required_bundle_files"]:
        if relative not in paths:
            fail(f"required bundle file is not manifest-covered: {relative}")
    audit_path, audit_hash, audit_bytes, audit_lines = AUDIT
    if raw_stats(root / audit_path) != (audit_hash, audit_bytes, audit_lines):
        fail("perplexity audit snapshot is not byte-for-byte pinned")
    journals = load_json(root, "manifests/journal-snapshots.json")["snapshots"]
    if len(journals) != 7:
        fail("expected exactly seven journal snapshots")
    for journal in journals:
        actual = raw_stats(root / journal["path"])
        expected = (journal["sha256"], journal["bytes"], journal["lines"])
        if actual != expected:
            fail(f"journal snapshot mismatch: {journal['path']}")
    records = []
    for number, line in enumerate((root / "sessions/selected-incident-events.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"invalid selected session record {number}: {exc}")
        missing = set(schema["session_record_required"]) - set(record)
        if missing:
            fail(f"session record {number} misses {sorted(missing)}")
        records.append(record)
    if {record["case_id"] for record in records} != REQUIRED_CASES or len(records) != 5:
        fail("selected session record cases are incomplete")
    selected = load_json(root, "manifests/selected-session-evidence.json")
    if selected.get("record_count") != len(records) or set(selected.get("case_ids", [])) != REQUIRED_CASES:
        fail("selected session manifest mismatch")
    corpus = load_json(root, "precomputed/corpus.json").get("cases", [])
    for case in corpus:
        missing = set(schema["corpus_case_required"]) - set(case)
        if missing:
            fail(f"corpus case {case.get('case_id')} misses {sorted(missing)}")
    if {case.get("case_id") for case in corpus} != REQUIRED_CASES:
        fail("corpus cases are incomplete")
    baseline = load_json(root, "precomputed/baseline.json")
    if baseline.get("projects", {}).get("total", {}).get("completed_turns") != 952:
        fail("baseline does not carry corrected 952-turn total")
    if baseline.get("journals", {}).get("snapshot_count") != 7:
        fail("baseline journal count mismatch")
    print(f"verified {len(entries)} manifest entries; 7 journals; 5 sanitized cases")

def map_state(root):
    corpus = load_json(root, "precomputed/corpus.json")["cases"]
    for case in sorted(corpus, key=lambda item: item["case_id"]):
        print(f"{case['case_id']} | {case['kind']} | confidence={case['confidence']}")

def verify_results(root):
    baseline = load_json(root, "precomputed/baseline.json")
    corpus = load_json(root, "precomputed/corpus.json")["cases"]
    if baseline["journals"]["physical_jsonl_records"] != 591 or baseline["journals"]["classified_lifecycle_events"] != 550:
        fail("baseline journal denominators changed")
    if baseline["dedup_correction"]["corrected"]["input_tokens"] != 135110000:
        fail("baseline corrected input-token total changed")
    if len(corpus) != 5 or not any(case["kind"] == "control" for case in corpus):
        fail("corpus must retain the clean control")
    print("results verified: corrected telemetry denominators and clean control are present")

def verify_claim_inventory(root):
    _, _, _, line_count = AUDIT
    audit_lines = raw_stats(root / AUDIT[0])[2]
    if audit_lines != line_count:
        fail("audit line count changed")
    for start, end in CLAIM_RANGES:
        if not (1 <= start <= end <= line_count):
            fail(f"invalid claim range {start}-{end}")
    print(f"claim inventory verified: {len(CLAIM_RANGES)} ranges within {line_count} audit lines")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "map-state", "verify-results", "verify-claim-inventory"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        {"verify": verify, "map-state": map_state, "verify-results": verify_results, "verify-claim-inventory": verify_claim_inventory}[args.command](root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
