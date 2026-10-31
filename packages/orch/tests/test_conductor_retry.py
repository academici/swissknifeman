"""Retry invalidates dependent checks even when completion stamps share a second."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor.application import run_service
from orch.conductor.infrastructure import clock
from tests.test_conductor import ConductorCase, GREEN, executor_ok, report


STAMP = "2026-10-31T09:29:57Z"


def completed(status="done", *, ended=STAMP):
    return {"status": "done", "ended": ended, "result": {"report": {"status": status}}}


class RetrySelectionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)

    def retry(self, steps, *, questions=None, **extra):
        # The persisted state sorts keys: insertion order is not execution order.
        item = {"outcome": "blocked", "steps": dict(sorted(steps.items())), **extra}
        state = {"items": {"W1": item}, "tokens": {"input": 123, "output": 45}, "questions": questions or {}}
        service = SimpleNamespace(state=state, directory=self.directory, _save=mock.Mock(),
                                  progress=SimpleNamespace(emit=mock.Mock()))
        run_service.retry(service, "W1")
        self.assertEqual(state["tokens"], {"input": 123, "output": 45})
        service._save.assert_called_once()
        return item

    def test_equal_stamps_drop_dependent_checks_and_keep_earlier_rounds_and_counters(self):
        steps = {"brief": completed(), "prepare": completed(), "executor.1": completed(),
                 "checks.1": completed(), "review.1": completed(), "executor.2": completed("done_pending_checks"),
                 "checks.2": completed(), "checks.3": completed(), "register": completed(),
                 "review.2": completed(ended="2026-10-31T09:29:58Z"), "unfinished": {"status": "started"}}
        counters = {"check_fixes_used": 1, "corrections_used": 2, "retries_used": 3,
                    "check_fixes_at": [1], "corrections_at": [1, 2], "review_rounds_used": 2,
                    "tokens": {"input": 123, "output": 45, "cached": 900},
                    "stage_usage": {"executor.2": {"input": 100}},
                    "usage_by_agent": {"old-agent": {"input": 123}}}
        old_attempt = {"n": 1, "steps": {"executor.1": {"report_status": "blocked"}}}
        archived = self.directory / "W1" / "attempts" / "1" / "reports" / "executor.1.json"
        archived.parent.mkdir(parents=True)
        archived.write_text("prior attempt\n")
        kept_log = self.directory / "W1" / "checks" / "1" / "V1.log"
        dropped_log = self.directory / "W1" / "checks" / "2" / "V1.log"
        for path in (kept_log, dropped_log):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(path))
        receipt = self.directory / "artifacts" / "evidence" / "V1.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text('{"exit": 0, "producer": {"kind": "engine"}}\n')
        receipt_before = receipt.read_bytes()
        expected = copy.deepcopy(counters)
        item = self.retry(steps, attempts=[copy.deepcopy(old_attempt)], **counters)
        self.assertEqual(item["steps"], {key: steps[key] for key in ("executor.1", "checks.1", "review.1")})
        self.assertEqual({key: item[key] for key in expected}, expected)
        self.assertEqual(item["attempts"][0], old_attempt)
        self.assertEqual(archived.read_text(), "prior attempt\n")
        self.assertEqual(kept_log.read_text(), str(kept_log))
        self.assertEqual(receipt.read_bytes(), receipt_before)
        moved = self.directory / "W1" / "attempts" / "2" / "checks" / "2" / "V1.log"
        self.assertEqual(moved.read_text(), str(dropped_log))
        self.assertFalse(dropped_log.exists())
        self.assertEqual(set(item["attempts"][1]["steps"]),
                         {"brief", "prepare", "executor.2", "checks.2", "checks.3", "register", "review.2"})

    def test_latest_executor_uses_numeric_round_order_when_stamps_tie(self):
        steps = {f"{kind}.{n}": completed("done_pending_checks")
                 for n in range(1, 11) for kind in ("executor", "checks")}
        item = self.retry(steps)
        self.assertEqual(set(item["steps"]), set(steps) - {"executor.10", "checks.10"})

    def test_first_blocked_executor_uses_numeric_round_order_when_stamps_tie(self):
        item = self.retry({"executor.2": completed("blocked"), "executor.10": completed("blocked"),
                           "checks.2": completed(), "checks.10": completed()})
        self.assertIn("executor.2", item["attempts"][0]["steps"])
        self.assertEqual(item["steps"], {})

    def test_policy_continuation_keeps_preceding_executor_and_checks_rounds(self):
        steps = {"executor.1": completed(), "checks.1": completed(), "executor.2": completed("blocked"),
                 "executor.2-q1": completed("done_pending_checks"), "checks.2": completed()}
        item = self.retry(steps)
        self.assertEqual(set(item["steps"]), {"executor.1", "checks.1", "executor.2"})

    def test_advice_hold_keeps_completed_rounds_in_the_same_second(self):
        steps = {"brief": completed(), "executor.1": completed(), "checks.1": completed(),
                 "review.1": completed(), "advice.1": completed(), "register": completed()}
        item = self.retry(steps, questions={"W1": {"orch-advice-1": {"status": "answered"}}})
        self.assertEqual(set(item["steps"]), {"executor.1", "checks.1", "review.1", "advice.1"})

    def test_distinct_stamps_keep_existing_retry_boundary(self):
        steps = {"executor.1": completed(ended="2026-10-31T09:29:55Z"),
                 "checks.1": completed(ended="2026-10-31T09:29:56Z"), "executor.2": completed("blocked"),
                 "checks.2": completed(ended="2026-10-31T09:29:58Z")}
        self.assertEqual(set(self.retry(steps)["steps"]), {"executor.1", "checks.1"})


class ManualPendingRetryTests(ConductorCase):
    def test_retry_reruns_same_second_checks_and_consumes_new_manual_v2_verdict(self):
        procedure = "observe the retained output"
        self.set_items({"W1": {"checks": [
            {"id": "V1", "cmd": "test -f out/W1.txt", "kind": "acceptance", "expect": "exit 0"},
            {"id": "V2", "procedure": procedure, "kind": "acceptance", "expect": "pass"}]}})
        blocked = report("W1", "blocked", changed_paths=[], checks_run=[],
                         open_issues=[{"text": "needs clarification", "kind": "escalation"}])
        pending = report("W1", "done_pending_checks", checks_run=[],
                         open_issues=[{"text": "V1 and V2 await the conductor", "kind": "pending"}])
        observed = copy.deepcopy(pending)
        observed["checks_run"] = [{"id": "V2", "procedure": procedure, "verdict": "pass"}]
        self.script({"executor": [{"result": blocked}, dict(executor_ok("W1"), result=pending),
                                  {"result": observed}], "reviewer": [GREEN]})

        def reopen_and_retry(directory):
            source = self.source()
            source["items"]["W1"]["status"] = "todo"
            self.state_file.write_text(json.dumps(source), encoding="utf-8")
            return self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")

        with mock.patch.object(clock, "utc_now", return_value=STAMP):
            code, _, err = self.run_items("W1")
            self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
            directory = self.run_dir(err)
            code, _, err = reopen_and_retry(directory)
            self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
            before = self.state(err)
            item_before = before["items"]["W1"]
            steps = item_before["steps"]
            self.assertEqual(steps["executor.1"]["ended"], steps["checks.1"]["ended"])
            self.assertIsNone(steps["checks.1"]["result"][1]["verdict"])
            self.assertIn("MANUAL_PENDING", (directory / "W1" / "register-report.json").read_text())
            piece = directory / "W1"
            old_attempt = {path.relative_to(piece / "attempts" / "1"): path.read_bytes()
                           for path in (piece / "attempts" / "1").rglob("*") if path.is_file()}
            previous_files = {name: (piece / name).read_bytes() for name in
                              ("reports/executor.1.json", "streams/executor.1.jsonl", "checks/1/V1.log")}
            command_evidence = self.project / steps["checks.1"]["result"][0]["evidence"]
            manual_evidence = command_evidence.with_name("V2.json")
            self.assertFalse(manual_evidence.exists())
            code, _, err = reopen_and_retry(directory)

        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 3)
        self.assertEqual((self.project / "out" / "W1.txt").read_text(), "ok\n")
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        self.assertIn("checks.1", [line.get("stage") for line in self.lines(err) if line["event"] == "stage.start"])
        after = self.state(err)
        item_after = after["items"]["W1"]
        self.assertEqual(item_after["attempts"][0], item_before["attempts"][0])
        for name, content in old_attempt.items():
            self.assertEqual((piece / "attempts" / "1" / name).read_bytes(), content)
        for name, content in previous_files.items():
            self.assertEqual((piece / "attempts" / "2" / name).read_bytes(), content)
        for counter in ("check_fixes_used", "corrections_used", "check_fixes_at", "corrections_at"):
            self.assertEqual(item_after[counter], item_before[counter])
        self.assertEqual(after["resumes"], before["resumes"] + 1)
        for state_before, state_after in ((before, after), (item_before, item_after)):
            self.assertGreaterEqual(state_after["tokens"]["input"], state_before["tokens"]["input"] + 100)
            self.assertGreaterEqual(state_after["tokens"]["output"], state_before["tokens"]["output"] + 10)
        rows = item_after["steps"]["checks.1"]["result"]
        self.assertEqual((rows[0]["exit"], rows[0]["green"]), (0, True))
        self.assertEqual(json.loads(command_evidence.read_text())["producer"]["kind"], "engine")
        self.assertEqual((rows[1]["verdict"], rows[1]["green"]), ("pass", True))
        receipt = json.loads(manual_evidence.read_text())
        self.assertEqual((receipt["verdict"], receipt["producer"]["kind"]), ("pass", "executor"))


if __name__ == "__main__":
    unittest.main()
