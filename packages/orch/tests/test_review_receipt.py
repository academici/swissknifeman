"""Review receipts on fake roles, including persistence, correction and registration."""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shlex
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor import checks, contract, engine, records
from orch.conductor.domain.report import finding_key
from orch.conductor.stages import review
from orch.worksource_file import FileWorkSource
from tests.test_conductor import ConductorCase, FINDING, GREEN, ROOT, executor_ok, report, reproduced


class ReceiptTests(ConductorCase):
    def receipt(self):
        return json.loads((self.project / "plans/T/artifacts/W1/review-receipt.json").read_text())

    @contextmanager
    def review_before_red_check(self):
        """Let the real fake-role review complete before the first check can report red."""
        ready = threading.Event()
        write = engine.Conductor._verdict_file
        run = checks.run_checks

        def written(conductor, item, *args, **kwargs):
            write(conductor, item, *args, **kwargs)
            ready.set()

        def checked(input_doc, **kwargs):
            if kwargs["run_env"]["SKM_CHECK_ROUND"] == "1":
                self.assertTrue(ready.wait(20), "the overlapping review did not finish")
            return run(input_doc, **kwargs)

        with mock.patch.object(engine.Conductor, "_verdict_file", autospec=True, side_effect=written), \
                mock.patch.object(checks, "run_checks", side_effect=checked):
            yield

    def assert_blocked_registration(self, err, reason):
        self.assertEqual(self.outcome(err), ("stopped", "ITEM_BLOCKED"), err)
        registered = next(c for c in self.source()["calls"] if c["op"] == "register")
        self.assertEqual(registered["status"], "blocked")
        self.assertNotIn("review_receipt", registered)
        self.assertTrue(any(reason in issue["text"] for issue in registered["report"]["open_issues"]), registered)
        self.assertNotIn("REGISTER_REFUSED", err)

    def test_red_checks_after_review_correction_register_blocked_without_stale_receipt(self):
        self.set_items({"W1": {"checks": [{"id": "V1", "kind": "acceptance", "expect": "exit 0",
            "cmd": "test \"$(cat out/W1.txt)\" = ok"}], "options": [{"source": "item:W1", "options": {
                "limits": {"check_fixes": 0}}}]}})
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {
            "cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.calls("reviewer"), 1)
        self.assertNotEqual(self.receipt()["candidate"]["paths"]["out/W1.txt"], checks.path_fingerprint(self.project, "out/W1.txt"))
        self.assert_blocked_registration(err, "CHECKS_RED")

    def test_new_attempt_blocked_before_review_omits_previous_attempt_receipt(self):
        target = self.project / "plans/T/artifacts/W1/review-receipt.json"
        target.parent.mkdir(parents=True)
        old = json.loads((ROOT / "schemas/conductor/v1/examples/valid/review-receipt.json").read_text())
        old["attempt_id"] = "att-previous"
        target.write_text(json.dumps(old))
        self.git("add", "plans/T/artifacts/W1/review-receipt.json")
        self.git("commit", "-qm", "previous attempt receipt")
        blocked = report("W1", status="blocked", changed_paths=[], open_issues=[{
            "kind": "escalation", "text": "NEEDS_OWNER: missing input", "impact": "blocked", "next": "owner supplies input"}])
        self.script({"executor": [{"result": blocked}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.calls("reviewer"), 0)
        self.assertEqual(self.receipt()["attempt_id"], "att-previous")
        self.assert_blocked_registration(err, "NEEDS_OWNER")

    def overlap_check_fix(self, first=GREEN, triage=None, rounds=2):
        self.set_items({"W1": {"checks": [{"id": "V1", "kind": "acceptance", "expect": "exit 0",
            "cmd": "test \"$(cat out/W1.txt)\" = done"}], "options": [{"source": "item:W1", "options": {
                "checks": {"overlap_review": True}, "limits": {"review_rounds": rounds}}}]}})
        script = {"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                  "reviewer": [first, GREEN]}
        if triage:
            script["triager"] = [triage]
        self.script(script)
        with self.review_before_red_check():
            return self.run_items("W1")

    def assert_corrected_candidate_reviewed(self, result):
        code, _, err = result
        self.assertEqual(code, 0, err)
        self.assertEqual((self.calls("reviewer"), self.calls("executor")), (2, 2))
        doc = self.receipt()
        self.assertEqual((doc["round"], doc["verdict"]), (2, "GREEN"))
        self.assertEqual(doc["candidate"]["paths"]["out/W1.txt"], checks.path_fingerprint(self.project, "out/W1.txt"))
        self.assertIn("done", self.prompt("reviewer", 2))
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        self.assertNotIn("REGISTER_REFUSED", err)

    def test_green_overlap_review_is_repeated_after_check_fix(self):
        self.assert_corrected_candidate_reviewed(self.overlap_check_fix())

    def test_rejected_only_overlap_review_is_repeated_after_check_fix(self):
        triage = {"result": {"confirmed": [], "rejected": [{"finding": "F1", "reason": "not reproduced",
            "reproduction": {"cmd": "false", "exit": 1, "observed": "the claimed error did not reproduce"}}]}}
        with reproduced(exit_code=1):
            self.assert_corrected_candidate_reviewed(self.overlap_check_fix(FINDING, triage))

    def test_below_threshold_overlap_review_is_repeated_after_check_fix(self):
        minor = {"result": {"verdict": "ATTENTION", "findings": [dict(FINDING["result"]["findings"][0], severity="Minor")]}}
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {
            "cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}, "fix": "write done"}], "rejected": []}}
        self.assert_corrected_candidate_reviewed(self.overlap_check_fix(minor, triage))

    def test_stale_overlap_review_does_not_bypass_review_limit(self):
        code, _, err = self.overlap_check_fix(rounds=1)
        self.assertEqual(code, 1, err)
        self.assertEqual(self.calls("reviewer"), 1)
        self.assert_blocked_registration(err, "REVIEW_LIMIT")

    def test_green_candidate_and_register(self):
        green = {"result": dict(GREEN["result"], questions=["Confirm deployment timing?"], residual_risk="No live probe.")}
        self.script({"executor": [executor_ok("W1")], "reviewer": [green]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        doc = self.receipt()
        self.assertEqual((doc["verdict"], doc["open"]), ("GREEN", {"blocker": 0, "major": 0}))
        self.assertEqual(set(doc["candidate"]["paths"]), {"out/W1.txt"})
        self.assertEqual(doc["candidate"]["digest"], checks.candidate(self.project, ["out/W1.txt"])["digest"])
        register = next(c for c in self.source()["calls"] if c["op"] == "register")
        self.assertEqual(register["review_receipt"], "plans/T/artifacts/W1/review-receipt.json")
        self.assertEqual(contract.problems(doc, "review-receipt"), [])
        self.assertEqual((doc["questions"], doc["residual_risk"]), (["Confirm deployment timing?"], "No live probe."))
        records.read(self.project / "plans/T/artifacts/W1/review-verdict.json", "review-verdict")
        state = records.read(self.run_dir(err) / "state.json", "state")
        result = state["items"]["W1"]["steps"]["review.1"]["result"]
        self.assertEqual(result["finding_keys"], {})

    def correction(self, final=False, combined=False):
        options = {"limits": {"review_rounds": 1 if final else 2}, "review": {"final_correction": True}}
        if combined:
            options["checks"] = {"overlap_review": True, "parallel": 1}
        item = {"options": [{"source": "item:W1", "options": options}]}
        if combined:
            item["checks"] = [{"id": "V1", "cmd": "test -f out/W1.txt", "expect": "exit 0", "kind": "acceptance"}]
        self.set_items({"W1": item})
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {
            "cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING] if final else [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        return self.receipt(), err

    def test_second_green_retains_corrected_finding(self):
        doc, _ = self.correction()
        self.assertEqual((doc["round"], doc["verdict"]), (2, "GREEN"))
        self.assertEqual(doc["findings"][0]["status"], "corrected")
        self.assertEqual(doc["findings"][0]["key"], finding_key(FINDING["result"]["findings"][0]))

    def test_deferred_major_still_counts_as_open(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "review": {"correct_min_severity": "Blocker"}}}]}})
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {
            "cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1")], "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.receipt()["findings"][0]["status"], "deferred")
        self.assertEqual(self.receipt()["open"]["major"], 1)

    def test_final_correction_keeps_reviewed_candidate(self):
        doc, _ = self.correction(final=True)
        self.assertEqual(doc["corrected_after"], {"round": 1, "paths": ["out/W1.txt"]})
        self.assertEqual(doc["findings"][0]["status"], "corrected")
        self.assertEqual(doc["open"]["major"], 0)
        self.assertNotEqual(doc["candidate"]["paths"]["out/W1.txt"], checks.path_fingerprint(self.project, "out/W1.txt"))

    def test_combined_correction_at_limit_records_actual_paths(self):
        marker_wait = ("from pathlib import Path; import time; "
                       "p=Path('plans/T/artifacts/W1/review-receipt.json'); end=time.monotonic()+20; "
                       "exec('while not p.exists() and time.monotonic()<end:\\n time.sleep(0.01)'); "
                       "assert p.exists()")
        check = {"id": "V1", "kind": "acceptance", "expect": "exit 0",
                 "cmd": "python3 -c " + shlex.quote(marker_wait) + " && test \"$(cat out/W1.txt)\" = done"}
        self.set_items({"W1": {"checks": [check], "options": [{"source": "item:W1", "options": {
            "checks": {"overlap_review": True}, "limits": {"review_rounds": 1}}}]}})
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": {
            "cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}, "fix": "write done"}], "rejected": []}}
        self.script({"executor": [executor_ok("W1"), {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}],
                     "reviewer": [FINDING], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        doc = self.receipt()
        self.assertEqual((self.calls("reviewer"), self.calls("executor")), (1, 2))
        self.assertEqual(doc["corrected_after"], {"round": 1, "paths": ["out/W1.txt"]})
        self.assertEqual(doc["findings"][0]["status"], "corrected")

    def test_old_and_new_review_step_save_load_resume(self):
        self.set_items({"W1": {}}, refuse=["register"])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        path = self.run_dir(err) / "state.json"
        run_id = path.parent.name
        state = records.read(path, "state")
        for old in (True, False):
            saved = copy.deepcopy(state)
            result = saved["items"]["W1"]["steps"]["review.1"]["result"]
            if old:
                for key in ("base", "candidate", "outside", "finding_keys"):
                    result.pop(key, None)
            records.write(path, saved, "state")
            self.assertEqual(records.read(path, "state"), saved)
            code, _, err = self.conduct("resume", "--run", run_id, "--json-lines")
            self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("reviewer"), 1)


class ReceiptUnitTests(unittest.TestCase):
    def test_key_ignores_line_numbers_and_numeric_examples(self):
        found = {"location": "a.py:12", "basis": "Correctness", "failure_scenario": "  VALUE 23\n fails  "}
        same = dict(found, location="a.py:99", failure_scenario="value 456 fails")
        self.assertEqual(finding_key(found), finding_key(same))
        self.assertNotEqual(finding_key(found), finding_key(dict(found, location="b.py:12")))

    def test_fingerprint_fixture_modes_and_symlink_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "mode"
            p.write_bytes(b"fixture\n")
            blob = hashlib.sha1(b"blob 8\0fixture\n").hexdigest()
            self.assertEqual(checks.path_fingerprint(root, "mode"), "100644 " + blob)
            p.chmod(0o755)
            self.assertEqual(checks.path_fingerprint(root, "mode"), "100755 " + blob)
            p.unlink()
            p.symlink_to("missing")
            self.assertEqual(checks.path_fingerprint(root, "mode"), "120000 " + hashlib.sha1(b"blob 7\0missing").hexdigest())
            p.unlink()
            self.assertEqual(checks.path_fingerprint(root, "mode"), "absent")
            p.mkdir()
            self.assertEqual(checks.path_fingerprint(root, "mode"), "other")

    def test_batched_fingerprints_match_git_for_odd_names_and_modes(self):
        import subprocess
        from orch.conductor.infrastructure.review_tree import fingerprints
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            paths = ["plain", "space name", '"quoted', "line\nbreak", "-leading", "executable", "carriage", "carriage\r"]
            for index, path in enumerate(paths):
                (root / path).write_bytes(("content " + str(index)).encode())
            (root / "executable").chmod(0o755)
            (root / "link").symlink_to("plain")
            (root / "directory").mkdir()
            paths += ["link", "directory", "absent"]
            self.assertEqual(fingerprints(root, paths), {path: checks.path_fingerprint(root, path)
                                                        for path in sorted(paths)})

    def test_outside_and_deterministic_candidate(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@example.invalid",
                            "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "base"], check=True)
            (root / "file").write_text("x")
            (root / "file").chmod(0o755)
            (root / "link").symlink_to("file")
            (root / "owner").write_text("outside")
            a = checks.candidate(root, ["link", "file"])
            self.assertEqual(a, checks.candidate(root, ["file", "link"]))
            self.assertTrue(a["paths"]["file"].startswith("100755 "))
            self.assertTrue(a["paths"]["link"].startswith("120000 "))
            self.assertEqual(set(checks.review_outside(root, a["head"], a["paths"])), {"owner"})

    def test_invalid_receipt_is_not_written(self):
        writer = SimpleNamespace(_write_artifact=mock.Mock())
        with self.assertRaisesRegex(ValueError, "invalid review-receipt"):
            review.write_receipt(writer, SimpleNamespace(), {"verdict": "GREEN"})
        writer._write_artifact.assert_not_called()

    def test_file_source_copies_receipt_and_validates_on_read(self):
        doc = json.loads((ROOT / "schemas/conductor/v1/examples/valid/review-receipt.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            receipt = project / "review.json"
            receipt.write_text(json.dumps(doc))
            source = FileWorkSource(project / "input.json", project=project)
            request = {"run_id": "run", "attempt_id": "att-test", "status": "done", "evidence": {},
                       "review_receipt": "review.json", "report": {k: v for k, v in report("W1").items() if k != "status"}}
            with mock.patch("orch.worksource_file.read_input", return_value={"input_id": "input"}):
                result = source._register(request)
                self.assertEqual(result["outcome"], "recorded")
                kept = project / result["receipt"]["artifacts"] / "review-receipt.json"
                self.assertEqual(json.loads(kept.read_text()), doc)
                receipt.write_text('{}')
                self.assertEqual(source._register(request)["outcome"], "refused")


if __name__ == "__main__":
    unittest.main()
