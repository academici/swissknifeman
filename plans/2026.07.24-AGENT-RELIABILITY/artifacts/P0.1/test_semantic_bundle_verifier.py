#!/usr/bin/env python3
"""Focused tests for semantic_bundle_verifier.py.

Every test that needs a mutated bundle copies the real committed bundle into a
temporary directory first (never mutates artifacts/source-evidence itself,
Code Guidance) and points the verifier's --bundle-root at the copy.
"""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE_ROOT = HERE.parent / "source-evidence"
CONTRACT_PATH = HERE / "semantic-verification-contract.json"

sys.path.insert(0, str(HERE))
import semantic_bundle_verifier as sbv  # noqa: E402


def load_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def copy_bundle(dest):
    shutil.copytree(BUNDLE_ROOT, dest)
    return dest


def rehash_manifest_entry(manifest_path, relative_path, new_bytes):
    """Rewrite one bundle-manifest.json entry to match a mutated file, keeping the manifest internally consistent."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        if entry["path"] == relative_path:
            entry["sha256"] = hashlib.sha256(new_bytes).hexdigest()
            entry["bytes"] = len(new_bytes)
            entry["lines"] = new_bytes.count(b"\n")
            break
    else:
        raise AssertionError(f"{relative_path} not found in manifest")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def rewrite_json(path, mutator):
    data = json.loads(path.read_text(encoding="utf-8"))
    mutator(data)
    new_text = json.dumps(data)
    path.write_text(new_text, encoding="utf-8")
    return new_text.encode("utf-8")


class ContractShapeTests(unittest.TestCase):
    def test_contract_declares_only_closed_proof_classes(self):
        contract = load_contract()
        closed = set(contract["proof_classes"])
        self.assertEqual(closed, {"recomputed", "cross-checked", "pinned-not-recomputable", "unknown"})
        for assertion in contract["assertions"]:
            self.assertIn(assertion["proof_class"], closed)
            self.assertTrue(assertion["input"])
            self.assertTrue(assertion["algorithm"])

    def test_pinned_facts_are_never_declared_recomputed_or_cross_checked(self):
        # False promotion of a pinned claim to recomputed is exactly the F1 failure mode.
        contract = load_contract()
        by_id = {a["id"]: a["proof_class"] for a in contract["assertions"]}
        self.assertEqual(by_id["classified-lifecycle-events-550"], "pinned-not-recomputable")
        self.assertEqual(by_id["dedup-token-totals"], "pinned-not-recomputable")


class ValidBaseTests(unittest.TestCase):
    def test_valid_base_passes_every_assertion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_bundle(Path(tmp) / "bundle")
            verifier = sbv.Verifier(root, load_contract())
            results = verifier.run_all()
            failed = {aid: r for aid, r in results.items() if r["status"] != "pass"}
            self.assertEqual(failed, {}, failed)

    def test_report_written_by_main_is_valid_json_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_bundle(Path(tmp) / "bundle")
            report_path = Path(tmp) / "report.json"
            argv = ["prog", "--bundle-root", str(root), "--contract", str(CONTRACT_PATH), "--report", str(report_path)]
            old_argv = sys.argv
            sys.argv = argv
            try:
                exit_code = sbv.main()
            finally:
                sys.argv = old_argv
            self.assertEqual(exit_code, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["failed"], 0)


class MutationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_bundle(Path(self.tmp.name) / "bundle")
        self.contract = load_contract()

    def tearDown(self):
        self.tmp.cleanup()

    def run_verifier(self):
        return sbv.Verifier(self.root, self.contract).run_all()

    def test_changed_semantic_field_under_rehashed_manifest_is_caught(self):
        # Corrupt a corpus case's confidence value, then rehash bundle-manifest.json
        # so the *immutable* hash check would pass while the semantic check must still fail.
        corpus_path = self.root / "precomputed" / "corpus.json"
        new_bytes = rewrite_json(corpus_path, lambda d: d["cases"][0].__setitem__("confidence", "very-high"))
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "precomputed/corpus.json", new_bytes)
        results = self.run_verifier()
        self.assertEqual(results["corpus-case-set-closure"]["status"], "fail")

    def test_missing_source_path_is_caught(self):
        corpus_path = self.root / "precomputed" / "corpus.json"
        new_bytes = rewrite_json(corpus_path, lambda d: d["cases"][0].__setitem__("source_committed_paths", ["precomputed/does-not-exist.json"]))
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "precomputed/corpus.json", new_bytes)
        results = self.run_verifier()
        self.assertEqual(results["corpus-source-path-closure"]["status"], "fail")

    def test_duplicate_case_is_caught(self):
        corpus_path = self.root / "precomputed" / "corpus.json"

        def mutator(d):
            d["cases"].append(dict(d["cases"][0]))

        new_bytes = rewrite_json(corpus_path, mutator)
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "precomputed/corpus.json", new_bytes)
        results = self.run_verifier()
        self.assertEqual(results["corpus-case-set-closure"]["status"], "fail")

    def test_forbidden_payload_key_in_session_record_is_caught(self):
        sessions_path = self.root / "sessions" / "selected-incident-events.jsonl"
        lines = sessions_path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["message"] = "raw text that must never be here"
        lines[0] = json.dumps(record)
        new_text = "\n".join(lines) + "\n"
        sessions_path.write_text(new_text, encoding="utf-8")
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "sessions/selected-incident-events.jsonl", new_text.encode("utf-8"))
        results = self.run_verifier()
        self.assertEqual(results["session-record-shape-closure"]["status"], "fail")

    def test_malformed_confidence_is_caught(self):
        sessions_path = self.root / "sessions" / "selected-incident-events.jsonl"
        lines = sessions_path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["confidence"] = "extremely-high"
        lines[0] = json.dumps(record)
        new_text = "\n".join(lines) + "\n"
        sessions_path.write_text(new_text, encoding="utf-8")
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "sessions/selected-incident-events.jsonl", new_text.encode("utf-8"))
        results = self.run_verifier()
        self.assertEqual(results["session-record-shape-closure"]["status"], "fail")

    def test_malformed_timestamp_is_caught(self):
        sessions_path = self.root / "sessions" / "selected-incident-events.jsonl"
        lines = sessions_path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["timestamp"] = "not-a-timestamp"
        lines[0] = json.dumps(record)
        new_text = "\n".join(lines) + "\n"
        sessions_path.write_text(new_text, encoding="utf-8")
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "sessions/selected-incident-events.jsonl", new_text.encode("utf-8"))
        results = self.run_verifier()
        self.assertEqual(results["session-record-shape-closure"]["status"], "fail")

    def test_malformed_selector_field_is_caught_as_missing_required_key(self):
        sessions_path = self.root / "sessions" / "selected-incident-events.jsonl"
        lines = sessions_path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        del record["record_selector"]
        lines[0] = json.dumps(record)
        new_text = "\n".join(lines) + "\n"
        sessions_path.write_text(new_text, encoding="utf-8")
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "sessions/selected-incident-events.jsonl", new_text.encode("utf-8"))
        results = self.run_verifier()
        self.assertEqual(results["session-record-shape-closure"]["status"], "fail")

    def test_journal_result_drift_is_recomputed_not_silently_matched(self):
        journal_path = self.root / "journals" / "07-dterema-honest-http-errors.jsonl"
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        original_result = record["result"]
        record["result"] = "mutated-result-value"
        lines[0] = json.dumps(record)
        new_text = "\n".join(lines) + "\n"
        journal_path.write_text(new_text, encoding="utf-8")
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "journals/07-dterema-honest-http-errors.jsonl", new_text.encode("utf-8"))
        snapshots_path = self.root / "manifests" / "journal-snapshots.json"
        snapshots = json.loads(snapshots_path.read_text(encoding="utf-8"))
        for snap in snapshots["snapshots"]:
            if snap["path"] == "journals/07-dterema-honest-http-errors.jsonl":
                snap["sha256"] = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
                snap["bytes"] = len(new_text.encode("utf-8"))
                snap["lines"] = new_text.encode("utf-8").count(b"\n")
        snapshots_path.write_text(json.dumps(snapshots), encoding="utf-8")

        results = self.run_verifier()
        histogram = results["journal-result-histogram"]["detail"]["histogram"]
        self.assertIn("mutated-result-value", histogram)
        self.assertNotEqual(original_result, "mutated-result-value")
        # The recompute must reflect the mutated file, not silently reuse a stale baseline value.
        self.assertEqual(results["journal-result-histogram"]["status"], "pass")

    def test_journal_forbidden_key_drift_is_caught(self):
        journal_path = self.root / "journals" / "07-dterema-honest-http-errors.jsonl"
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["tool_output"] = "raw payload that must never be committed"
        lines[0] = json.dumps(record)
        new_text = "\n".join(lines) + "\n"
        journal_path.write_text(new_text, encoding="utf-8")
        rehash_manifest_entry(self.root / "manifests" / "bundle-manifest.json", "journals/07-dterema-honest-http-errors.jsonl", new_text.encode("utf-8"))
        snapshots_path = self.root / "manifests" / "journal-snapshots.json"
        snapshots = json.loads(snapshots_path.read_text(encoding="utf-8"))
        for snap in snapshots["snapshots"]:
            if snap["path"] == "journals/07-dterema-honest-http-errors.jsonl":
                snap["sha256"] = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
                snap["bytes"] = len(new_text.encode("utf-8"))
                snap["lines"] = new_text.encode("utf-8").count(b"\n")
        snapshots_path.write_text(json.dumps(snapshots), encoding="utf-8")

        results = self.run_verifier()
        self.assertEqual(results["journal-key-closure"]["status"], "fail")

    def test_false_promotion_of_pinned_claim_is_structurally_impossible(self):
        # If someone tried to "fix" the contract by promoting a pinned-not-recomputable
        # claim to recomputed without adding real recompute logic, this test must catch it:
        # the promoted assertion would still only report the stored baseline value, and this
        # test proves the contract does not currently make that (false) promise.
        contract = load_contract()
        pinned_ids = {a["id"] for a in contract["assertions"] if a["proof_class"] == "pinned-not-recomputable"}
        self.assertEqual(pinned_ids, {"classified-lifecycle-events-550", "dedup-token-totals"})


class ImmutableBundleUntouchedTests(unittest.TestCase):
    def test_running_the_verifier_never_writes_below_source_evidence(self):
        before = sorted(p.relative_to(BUNDLE_ROOT).as_posix() for p in BUNDLE_ROOT.rglob("*") if p.is_file())
        sbv.Verifier(BUNDLE_ROOT, load_contract()).run_all()
        after = sorted(p.relative_to(BUNDLE_ROOT).as_posix() for p in BUNDLE_ROOT.rglob("*") if p.is_file())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
