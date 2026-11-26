"""Review receipt binding, atomic refusals and Git content freshness (stdlib engine)."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from test_evidence import EvidenceCase, lifecycle


class ReviewReceiptTests(EvidenceCase):
    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / "a.py").write_text("base\n")
        self.git("add", "a.py")
        self.git("commit", "-qm", "base")
        (self.repo / "a.py").write_text("reviewed\n")
        self.receipt_path = "@plan/artifacts/review-receipt.json"
        self.receipt = json.loads((Path(__file__).resolve().parents[2] /
            "schemas/plan/v1/examples/valid/review-receipt.json").read_text())
        self.receipt.update(subject="PLAN1.P1.1", item="P1.1", base=self.git("rev-parse", "HEAD").strip())
        self.receipt["candidate"] = self.candidate(["a.py"])
        self.save()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def candidate(self, names):
        paths = {p: lifecycle._path_fingerprint(self.repo, p) for p in sorted(names)}
        digest = hashlib.sha256("\n".join(f"{p}\t{v}" for p, v in paths.items()).encode()).hexdigest()
        return {"head": self.git("rev-parse", "HEAD").strip(), "digest": "sha256:" + digest, "paths": paths}

    def save(self):
        target = self.root / "artifacts/review-receipt.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(self.receipt))

    def finish(self, **kw):
        return lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0}, review_receipt=self.receipt_path, **kw)

    def reject(self, code, **kw):
        self.refused(code, lifecycle.finish, "P1.1", "done", checks={"V1": 0}, review_receipt=self.receipt_path, **kw)

    def test_fresh_and_head_change_does_not_invalidate_contents(self):
        self.git("commit", "--allow-empty", "-qm", "metadata")
        self.finish()
        self.assertEqual(self.result()["review"]["freshness"], "fresh")

    def test_unreviewed_candidate_change_refuses_atomically(self):
        (self.repo / "a.py").write_text("later\n")
        self.reject("REVIEW_RECEIPT_STALE")

    def test_only_confirmed_finding_path_is_allowed(self):
        self.receipt["findings"] = [{"key": "fk-" + "a" * 16, "id": "F1", "severity": "Major",
                                     "location": "a.py:10", "status": "confirmed"}]
        self.save()
        (self.repo / "a.py").write_text("fixed\n")
        self.finish()
        self.assertEqual(self.result()["review"]["freshness"], "findings_only")

    def test_rejected_or_deferred_finding_is_no_permission_to_change(self):
        for status in ("rejected", "deferred", "open"):
            self.receipt["findings"] = [{"key": "fk-" + "a" * 16, "id": "F1", "severity": "Major",
                                         "location": "a.py:10", "status": status}]
            self.save()
            (self.repo / "a.py").write_text("later\n")
            self.reject("REVIEW_RECEIPT_STALE")

    def test_corrected_after_paths_allow_findings_only(self):
        self.receipt["corrected_after"] = {"round": 1, "paths": ["new.py"]}
        self.save()
        (self.repo / "new.py").write_text("fix\n")
        self.finish()
        self.assertEqual(self.result()["review"]["freshness"], "findings_only")

    def test_historical_corrected_finding_does_not_allow_edits_after_green_review(self):
        (self.repo / "a.py").write_text("round one finding corrected\n")
        self.receipt.update(round=2, verdict="GREEN", corrected_after=None,
            findings=[{"key": "fk-" + "a" * 16, "id": "F1", "severity": "Major",
                       "location": "a.py:10", "status": "corrected"}])
        self.receipt["candidate"] = self.candidate(["a.py"])
        self.save()
        (self.repo / "a.py").write_text("unreviewed edit after round two\n")
        self.reject("REVIEW_RECEIPT_STALE")

    def test_new_product_path_is_stale(self):
        (self.repo / "new.py").write_text("new\n")
        self.reject("REVIEW_RECEIPT_STALE")

    def test_subject_attempt_and_blockers_refuse_atomically(self):
        original = copy.deepcopy(self.receipt)
        for changes, code, kw in [({"subject": "PLAN1.P1.2"}, "REVIEW_RECEIPT_SUBJECT", {}),
                                  ({"attempt_id": "att-old"}, "REVIEW_RECEIPT_ATTEMPT", {"attempt_id": "att-new"}),
                                  ({"open": {"blocker": 1, "major": 0}}, "REVIEW_RECEIPT_OPEN_BLOCKER", {}),
                                  ({"base": "bad"}, "REVIEW_RECEIPT_INVALID", {}),
                                  ({"base": "f" * 40}, "REVIEW_RECEIPT_INVALID", {})]:
            with self.subTest(code=code):
                self.receipt = dict(original, **changes)
                self.save()
                self.reject(code, **kw)

    def test_required_gate_and_optional_legacy_flow(self):
        self.run_cli("set", "P1.1", "--json", json.dumps({"review": {"mode": "requested"}}))
        p = self.root / "plan.json"
        doc = json.loads(p.read_text())
        doc.setdefault("settings", {})["review_receipt"] = "required"
        p.write_text(json.dumps(doc))
        self.refused("REVIEW_RECEIPT_MISSING", lifecycle.finish, "P1.1", "done", checks={"V1": 0})
        doc["settings"].pop("review_receipt")
        p.write_text(json.dumps(doc))
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0})
        self.assertNotIn("review", self.result())

    def outside(self):
        p = self.repo / "audits/owner.txt"
        p.parent.mkdir()
        p.write_text("owner\n")
        self.receipt["outside"] = {"audits/owner.txt": lifecycle._path_fingerprint(self.repo, "audits/owner.txt")}
        self.save()
        return p

    def test_existing_unchanged_foreign_untracked_file_is_fresh(self):
        self.outside()
        self.finish()
        self.assertEqual(self.result()["review"]["freshness"], "fresh")

    def test_modified_or_deleted_foreign_file_is_stale(self):
        p = self.outside()
        p.write_text("modified\n")
        self.reject("REVIEW_RECEIPT_STALE")
        p.unlink()
        self.reject("REVIEW_RECEIPT_STALE")

    def test_legacy_receipt_without_outside_has_conservative_behavior(self):
        self.outside()
        self.receipt.pop("outside")
        self.save()
        self.reject("REVIEW_RECEIPT_STALE")

    def test_chmod_and_file_to_symlink_are_stale(self):
        p = self.repo / "a.py"
        p.chmod(0o755)
        self.reject("REVIEW_RECEIPT_STALE")
        p.chmod(0o644)
        content = p.read_text()
        p.unlink()
        (self.repo / "target").write_text(content)
        p.symlink_to("target")
        self.reject("REVIEW_RECEIPT_STALE")

    def test_identical_targets_retargeted_symlink_is_stale(self):
        for name in ("one", "two"):
            (self.repo / name).write_text("same\n")
        p = self.repo / "a.py"
        p.unlink()
        p.symlink_to("one")
        self.receipt["candidate"] = self.candidate(["a.py", "one", "two"])
        self.save()
        p.unlink()
        p.symlink_to("two")
        self.reject("REVIEW_RECEIPT_STALE")

    def test_fingerprint_fixture_modes_and_symlink_bytes(self):
        p = self.repo / "mode"
        p.write_bytes(b"fixture\n")
        blob = self.git("hash-object", "--no-filters", "--", "mode").strip()
        self.assertEqual(lifecycle._path_fingerprint(self.repo, "mode"), "100644 " + blob)
        p.chmod(0o755)
        self.assertEqual(lifecycle._path_fingerprint(self.repo, "mode"), "100755 " + blob)
        p.unlink()
        p.symlink_to("missing")
        expected = hashlib.sha1(b"blob 7\0missing").hexdigest()
        self.assertEqual(lifecycle._path_fingerprint(self.repo, "mode"), "120000 " + expected)
        p.unlink()
        self.assertEqual(lifecycle._path_fingerprint(self.repo, "mode"), "absent")
        p.mkdir()
        self.assertEqual(lifecycle._path_fingerprint(self.repo, "mode"), "other")

    def test_unsafe_candidate_path_and_digest_refuse(self):
        self.receipt["candidate"]["paths"] = {"../escape": "absent"}
        self.save()
        self.reject("REVIEW_RECEIPT_INVALID")

    def test_invalid_receipt_cli_flag_is_wired(self):
        self.receipt["verdict"] = "INVALID"
        self.save()
        code, out = self.run_cli("finish", "P1.1", "--status", "done", "--check", "V1=0",
                                 "--review-receipt", self.receipt_path)
        self.assertEqual(code, 1, out)
        self.assertIn("REVIEW_RECEIPT_INVALID", out)


if __name__ == "__main__":
    unittest.main()
