#!/usr/bin/env python3
"""P0.1-owned semantic verifier for the AGENT-RELIABILITY source-evidence bundle.

This script never edits or re-implements `verify_source_bundle.py` (immutable,
D30). It owns exactly the semantic assertions that immutable script's `verify`/
`verify-results`/`verify-claim-inventory`/`map-state` commands do not perform:
per-record journal key closure, fresh histogram recompute, cross-manifest case
linkage, and an explicit `pinned-not-recomputable`/`unknown` ledger for facts
that cannot be derived from the committed (privacy-minimized) bundle alone.

stdlib-only. Reads only files under --bundle-root; never opens tmp/, profiles,
mAInd or foreign repos; never writes below the bundle root.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMMUTABLE_COMMANDS = {
    "immutable-bundle-verify": "verify",
    "immutable-bundle-map-state": "map-state",
    "immutable-bundle-verify-results": "verify-results",
    "immutable-bundle-verify-claim-inventory": "verify-claim-inventory",
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path):
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON on line {number}: {exc}") from exc
    return records


def is_iso8601(value):
    if not isinstance(value, str):
        return False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.datetime.fromisoformat(candidate)
        return True
    except ValueError:
        return False


class Verifier:
    def __init__(self, bundle_root, contract):
        self.root = bundle_root
        self.contract = contract
        self.results = {}

    def run_all(self):
        order = [a["id"] for a in self.contract["assertions"]]
        for assertion_id in order:
            proof_class = next(a["proof_class"] for a in self.contract["assertions"] if a["id"] == assertion_id)
            method = getattr(self, "check_" + assertion_id.replace("-", "_"))
            try:
                detail = method()
                status = "pass"
            except AssertionError as exc:
                detail = {"error": str(exc)}
                status = "fail"
            self.results[assertion_id] = {"proof_class": proof_class, "status": status, "detail": detail}
        return self.results

    # -- cross-checked: delegate to the immutable verifier, never re-implement it --
    def _run_immutable(self, command):
        verifier_path = self.root / "verify_source_bundle.py"
        proc = subprocess.run(
            [sys.executable, str(verifier_path), command, "--root", str(self.root)],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0, f"{command} exit={proc.returncode} stderr={proc.stderr.strip()}"
        return {"command": command, "returncode": proc.returncode, "stdout": proc.stdout.strip()}

    def check_immutable_bundle_verify(self):
        return self._run_immutable(IMMUTABLE_COMMANDS["immutable-bundle-verify"])

    def check_immutable_bundle_map_state(self):
        return self._run_immutable(IMMUTABLE_COMMANDS["immutable-bundle-map-state"])

    def check_immutable_bundle_verify_results(self):
        return self._run_immutable(IMMUTABLE_COMMANDS["immutable-bundle-verify-results"])

    def check_immutable_bundle_verify_claim_inventory(self):
        return self._run_immutable(IMMUTABLE_COMMANDS["immutable-bundle-verify-claim-inventory"])

    # -- recomputed: fresh parse of every committed journal snapshot --
    def _journal_records(self):
        snapshots = load_json(self.root / "manifests" / "journal-snapshots.json")["snapshots"]
        per_file = {}
        for snapshot in snapshots:
            per_file[snapshot["path"]] = load_jsonl(self.root / snapshot["path"])
        return per_file

    def check_journal_physical_record_count(self):
        per_file = self._journal_records()
        counts = {path: len(records) for path, records in per_file.items()}
        total = sum(counts.values())
        baseline = load_json(self.root / "precomputed" / "baseline.json")
        expected = baseline["journals"]["physical_jsonl_records"]
        assert total == expected, f"recomputed total {total} != baseline {expected}"
        return {"per_file": counts, "total": total}

    def check_journal_key_closure(self):
        required = set(self.contract["required_journal_keys"])
        forbidden = set(self.contract["forbidden_journal_keys"])
        violations = []
        for path, records in self._journal_records().items():
            for index, record in enumerate(records):
                keys = set(record)
                if keys != required:
                    violations.append({"path": path, "index": index, "missing": sorted(required - keys), "extra": sorted(keys - required)})
                present_forbidden = keys & forbidden
                if present_forbidden:
                    violations.append({"path": path, "index": index, "forbidden_keys": sorted(present_forbidden)})
        assert not violations, f"{len(violations)} journal key-closure violation(s): {violations[:5]}"
        return {"records_checked": sum(len(r) for r in self._journal_records().values()), "violations": 0}

    def check_journal_result_histogram(self):
        histogram = {}
        for records in self._journal_records().values():
            for record in records:
                key = record.get("result")
                histogram[key] = histogram.get(key, 0) + 1
        return {"histogram": histogram, "total": sum(histogram.values())}

    def check_journal_friction_histogram(self):
        histogram = {}
        total_entries = 0
        for records in self._journal_records().values():
            for record in records:
                friction = record.get("friction")
                if not isinstance(friction, list):
                    continue
                for entry in friction:
                    histogram[entry] = histogram.get(entry, 0) + 1
                    total_entries += 1
        return {"histogram": histogram, "total_entries": total_entries}

    # -- pinned-not-recomputable: explicit non-claims --
    def check_classified_lifecycle_events_550(self):
        baseline = load_json(self.root / "precomputed" / "baseline.json")
        return {
            "pinned_classified_lifecycle_events": baseline["journals"]["classified_lifecycle_events"],
            "pinned_outcomes": baseline["journals"]["outcomes"],
            "reason": "no committed classifier maps 591 physical records to 550 classified events or to this outcome breakdown",
        }

    def check_dedup_token_totals(self):
        baseline = load_json(self.root / "precomputed" / "baseline.json")
        return {
            "pinned_dedup_correction": baseline["dedup_correction"],
            "reason": "derived from excluded raw rollout files, out of Scope Excluded",
        }

    # -- recomputed / cross-checked: corpus and session closure --
    def check_corpus_case_set_closure(self):
        schema = load_json(self.root / "schema.json")
        required_fields = set(schema["corpus_case_required"])
        cases = load_json(self.root / "precomputed" / "corpus.json")["cases"]
        assert len(cases) == 5, f"expected 5 cases, found {len(cases)}"
        ids = [case.get("case_id") for case in cases]
        assert len(set(ids)) == len(ids), f"duplicate case_id among {ids}"
        allowed_confidence = set(self.contract["allowed_confidence_values"])
        kind_counts = {}
        for case in cases:
            missing = required_fields - set(case)
            assert not missing, f"case {case.get('case_id')} missing fields {sorted(missing)}"
            assert case["confidence"] in allowed_confidence, f"case {case['case_id']} has invalid confidence {case['confidence']!r}"
            kind_counts[case["kind"]] = kind_counts.get(case["kind"], 0) + 1
        expected_kinds = self.contract["required_corpus_kinds"]
        assert kind_counts == expected_kinds, f"kind distribution {kind_counts} != expected {expected_kinds}"
        return {"case_ids": sorted(ids), "kind_counts": kind_counts}

    def check_corpus_source_path_closure(self):
        cases = load_json(self.root / "precomputed" / "corpus.json")["cases"]
        missing = []
        checked = 0
        for case in cases:
            for path in case.get("source_committed_paths", []):
                checked += 1
                if not (self.root / path).is_file():
                    missing.append({"case_id": case["case_id"], "path": path})
        assert not missing, f"{len(missing)} missing source_committed_paths: {missing}"
        return {"paths_checked": checked}

    def check_session_record_shape_closure(self):
        schema = load_json(self.root / "schema.json")
        required_fields = set(schema["session_record_required"]) | {"evidence_kind"}
        forbidden = set(self.contract["forbidden_session_keys"])
        allowed_confidence = set(self.contract["allowed_confidence_values"])
        records = load_jsonl(self.root / "sessions" / "selected-incident-events.jsonl")
        violations = []
        for record in records:
            keys = set(record)
            if keys != required_fields:
                violations.append({"case_id": record.get("case_id"), "missing": sorted(required_fields - keys), "extra": sorted(keys - required_fields)})
                continue
            if keys & forbidden:
                violations.append({"case_id": record.get("case_id"), "forbidden_keys": sorted(keys & forbidden)})
            if not SHA256_RE.match(record.get("original_sha256", "")):
                violations.append({"case_id": record.get("case_id"), "bad_sha256": record.get("original_sha256")})
            if not is_iso8601(record.get("timestamp")):
                violations.append({"case_id": record.get("case_id"), "bad_timestamp": record.get("timestamp")})
            if record.get("confidence") not in allowed_confidence:
                violations.append({"case_id": record.get("case_id"), "bad_confidence": record.get("confidence")})
        assert not violations, f"{len(violations)} session record shape violation(s): {violations}"
        return {"records_checked": len(records)}

    def check_selected_session_cross_link(self):
        sessions = load_jsonl(self.root / "sessions" / "selected-incident-events.jsonl")
        manifest = load_json(self.root / "manifests" / "selected-session-evidence.json")
        corpus = load_json(self.root / "precomputed" / "corpus.json")["cases"]
        session_ids = {r["case_id"] for r in sessions}
        manifest_ids = set(manifest.get("case_ids", []))
        corpus_ids = {c["case_id"] for c in corpus}
        assert session_ids == manifest_ids == corpus_ids, f"case_id set mismatch: sessions={sorted(session_ids)} manifest={sorted(manifest_ids)} corpus={sorted(corpus_ids)}"
        assert len(session_ids) == 5, f"expected cardinality 5, got {len(session_ids)}"
        return {"case_ids": sorted(session_ids)}

    def check_control_case_presence(self):
        cases = load_json(self.root / "precomputed" / "corpus.json")["cases"]
        controls = [c for c in cases if c.get("kind") == "control"]
        assert len(controls) == 1, f"expected exactly 1 control case, found {len(controls)}"
        assert controls[0]["case_id"] == "honest-http-clean-control", f"unexpected control case_id {controls[0]['case_id']!r}"
        return {"control_case_id": controls[0]["case_id"]}

    def check_journal_manifest_hash_cross_link(self):
        snapshots = {s["path"]: s for s in load_json(self.root / "manifests" / "journal-snapshots.json")["snapshots"]}
        bundle_entries = {e["path"]: e for e in load_json(self.root / "manifests" / "bundle-manifest.json")["entries"]}
        mismatches = []
        for path, snapshot in snapshots.items():
            entry = bundle_entries.get(path)
            if entry is None:
                mismatches.append({"path": path, "error": "absent from bundle-manifest.json"})
                continue
            for field in ("sha256", "bytes", "lines"):
                if snapshot[field] != entry[field]:
                    mismatches.append({"path": path, "field": field, "journal_snapshots": snapshot[field], "bundle_manifest": entry[field]})
        assert not mismatches, f"{len(mismatches)} cross-manifest mismatch(es): {mismatches}"
        return {"journals_cross_checked": len(snapshots)}


def build_report(results, contract):
    by_class = {}
    for assertion_id, result in results.items():
        by_class.setdefault(result["proof_class"], []).append(assertion_id)
    return {
        "schema_version": contract["schema_version"],
        "assertions": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results.values() if r["status"] == "pass"),
            "failed": sum(1 for r in results.values() if r["status"] == "fail"),
            "by_proof_class": {k: sorted(v) for k, v in sorted(by_class.items())},
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    contract = load_json(args.contract)
    verifier = Verifier(args.bundle_root.resolve(), contract)
    results = verifier.run_all()
    report = build_report(results, contract)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    failed = [aid for aid, r in results.items() if r["status"] == "fail"]
    if failed:
        print(f"ERROR: {len(failed)} assertion(s) failed: {failed}", file=sys.stderr)
        return 1
    print(f"semantic verification passed: {report['summary']['passed']}/{report['summary']['total']} assertions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
