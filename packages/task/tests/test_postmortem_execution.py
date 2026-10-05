"""End-to-end repository fixtures for the P10.6 runtime ownership failures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fixtures import write_valid_plan
from task import (evidence_runner, journal, plan_item_state, plan_status, plan_work,
                  review_job, review_packet, review_sources, route_evidence)


class ExecutionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = write_valid_plan(self.root, "FLOW")
        self.spec = self.plan / "phases/P1/P1.1.md"
        text = self.spec.read_text()
        text = text.replace("**Validation:** bash scripts/test.sh — green.",
                            "**Validation:** `python3 scripts/check.py` — green.")
        self.spec.write_text(text)
        (self.root / "scripts").mkdir()
        (self.root / "scripts/check.py").write_text(
            "from pathlib import Path\nassert 'value' in Path('plans/FLOW/lib/pkg/config.py').read_text()\n")
        (self.plan / "lib/pkg/config.py").write_text("value = 1\n")
        (self.plan / "journal.jsonl").write_text("")
        core = self.plan / "plan.md"
        core.write_text(core.read_text().replace("## 3. Routing", """## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Why |
|:--|:--|:--|:--|:--|:--|
| solo | P1.1 | implementation/medium | run | light | recommended: bounded work |
"""))
        plan_item_state.build_states(self.plan, item_id="P1.1")
        plan_status.build_status(self.plan)
        for argv in (["init", "-q"], ["add", "."], ["-c", "user.name=Fixture", "-c",
                     "user.email=fixture@example.test", "commit", "-qm", "baseline"]):
            subprocess.run(["git", *argv], cwd=self.root, check=True, capture_output=True)
        self.actual = route_evidence.capture_actual("implementation", "medium",
            source="provider-thread-state", model="fixture")
        self.actual.update(thread_id="executor", source_version="fixture", cwd=str(self.root),
                           invocation="task:plan-run FLOW P1.1")

    def prepare(self, *, reviewer=None):
        actual = dict(self.actual)
        if reviewer:
            actual["invocation"] += " --reviewer " + reviewer
        return plan_work.prepare(self.plan, "P1.1", command="plan-run", actor="fixture/medium",
            actual_route=actual, session_id="executor", reviewer=reviewer)

    def test_no_helpers_prepare_validate_close_and_resume(self):
        prepared = self.prepare()
        self.assertEqual(prepared["action"], "implement")
        validated = plan_work.validate(self.plan, "P1.1", attempt_id="full-001")
        self.assertTrue(validated["complete"])
        closed = plan_work.close(self.plan, "P1.1", note="Fixture passed.")
        self.assertEqual(closed["action"], "complete")
        before = (self.plan / "journal.jsonl").read_bytes()
        self.assertEqual(plan_work.close(self.plan, "P1.1")["action"], "complete")
        self.assertEqual((self.plan / "journal.jsonl").read_bytes(), before)
        rows = journal.read_authoritative_entries(self.plan)
        terminal = next(row for row in rows if row["result"] == "closed-green")
        self.assertEqual(terminal["decision"]["write_site"]["pre_final"], "allow")

    def test_same_candidate_reuses_green_and_check_inputs_remain_bound(self):
        self.prepare()
        first = plan_work.validate(self.plan, "P1.1", attempt_id="original")
        second = plan_work.validate(self.plan, "P1.1", attempt_id="not-needed")
        self.assertTrue(second["reused"])
        self.assertEqual(second["receipt"], first["receipt"])
        self.assertFalse(any(self.plan.rglob("not-needed")))

    def test_failed_read_binds_absence_without_aborting_native_review(self):
        ledger = review_sources.ReadLedger(self.root)
        update = {"sessionUpdate": "tool_call", "title": "read_file", "toolCallId": "missing",
                  "rawInput": {"target_file": str(self.root / "not-present.json")}}
        ledger.observe(update)
        ledger.verify()
        self.assertIsNone(ledger.result()["reads"][0]["member"]["sha256"])
        (self.root / "not-present.json").write_text("new dependency\n")
        with self.assertRaisesRegex(ValueError, "REVIEW_DEPENDENCY_STALE"):
            ledger.verify()

    def test_changed_candidate_requires_validation_and_cli_red_is_nonzero(self):
        self.prepare()
        plan_work.validate(self.plan, "P1.1", attempt_id="first")
        (self.plan / "lib/pkg/config.py").write_text("value = 2\n")
        result = plan_work.close(self.plan, "P1.1")
        self.assertEqual(result["reason"], "VALIDATION_RECEIPT_STALE")
        (self.plan / "lib/pkg/config.py").write_text("broken\n")
        with patch("sys.stdout"):
            code = plan_work.main(["validate", "--plan-dir", str(self.plan), "--item", "P1.1",
                                   "--attempt-id", "red"])
        self.assertEqual(code, 1)
        self.assertNotIn("P1.1", __import__('task.plan_recovery', fromlist=['']).terminal_items(self.plan))

    def test_red_stops_expensive_independent_check_and_generation_is_ordered(self):
        product = "plans/FLOW/lib/pkg/config.py"
        checks = [{"id": "fast", "argv": [sys.executable, "-c", "raise SystemExit(1)"], "depends_on": []},
                  {"id": "expensive", "argv": [sys.executable, "-c", "raise AssertionError('must not run')"],
                   "depends_on": []}]
        result = evidence_runner.run(self.root, self.root / "evidence", paths=[product],
                                     checks=checks, attempt_id="red")
        self.assertFalse(result["complete"])
        self.assertEqual(result["results"]["expensive"]["status"], "stopped-after-red")
        checks = [{"id": "generate", "argv": [sys.executable, "-c",
                    "from pathlib import Path; Path('generated.txt').write_text('done')"], "depends_on": []},
                  {"id": "lint", "argv": [sys.executable, "-c",
                    "from pathlib import Path; assert Path('generated.txt').read_text() == 'done'"],
                   "depends_on": ["generate"]}]
        result = evidence_runner.run(self.root, self.root / "evidence", paths=[product],
                                     checks=checks, attempt_id="ordered")
        self.assertTrue(result["complete"])

    def test_durable_unknown_attempt_blocks_duplicate_prompt(self):
        self.prepare(reviewer="grok/grok-4.7")
        packet = review_packet.packet(self.plan, "P1.1", selector="grok/grok-4.7", executor_session="executor")
        manifest = json.loads(Path(packet["manifest"]).read_text())
        directory = review_packet._location(self.plan, "P1.1")
        attempt = review_job.create(directory, manifest)
        started = json.loads((attempt / "started.json").read_text())
        started["owner"] = {"pid": 99999999, "start_ticks": "1"}
        review_job.write(attempt / "started.json", started)
        self.assertEqual(review_packet.job_status(self.plan, "P1.1")["status"], "unknown")
        with patch("task.review_grok_acp.run") as transport:
            with self.assertRaisesRegex(review_packet.ReviewError, "REVIEW_OUTCOME_UNKNOWN"):
                review_packet.run(self.plan, packet["manifest"])
            transport.assert_not_called()

    def test_timeout_with_clean_signal_exit_is_not_green(self):
        command = [sys.executable, "-u", "-c",
                   "import signal,time,sys; signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
                   "print('ready', flush=True); time.sleep(30)"]
        result = evidence_runner.run(self.root, self.root / "evidence",
            paths=["plans/FLOW/lib/pkg/config.py"], attempt_id="timeout",
            checks=[{"id": "timed", "argv": command, "depends_on": [], "timeout": .5}])
        self.assertEqual(result["results"]["timed"]["exit_code"], 0)
        self.assertEqual(result["results"]["timed"]["status"], "timeout")
        self.assertFalse(result["complete"])

    def test_typed_write_site_renders_without_repairing_journal_prose(self):
        self.prepare()
        plan_work.validate(self.plan, "P1.1", attempt_id="green")
        plan_work.close(self.plan, "P1.1")
        path = self.plan / "journal.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if row["result"] == "closed-green":
                row["note"] = "Legacy producer has no printed write-site."
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        before = path.read_bytes()
        plan_item_state.build_states(self.plan, item_id="P1.1", materialize_successor=False)
        self.assertIn("write-site: pre_mutation: allow · pre_final: allow",
                      (self.plan / "phases/P1/P1.1.state.md").read_text())
        self.assertEqual(path.read_bytes(), before)

    def test_large_machine_manifest_keeps_full_delta_outside_prompt(self):
        self.spec.write_text(self.spec.read_text().replace(
            "**Files:** lib/pkg/config.py", "**Files:** `src/**`"))
        source = self.root / "src"
        source.mkdir()
        for number in range(350):
            (source / f"client-{number:04d}.py").write_text("value = 1\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                        "commit", "-qm", "broad files"], cwd=self.root, check=True)
        (source / "client-0000.py").write_text("value = 2\n")
        evidence = self.root / "logs"
        evidence.mkdir()
        logs = []
        for number in range(100):
            path = evidence / f"validation-{number:04d}.log"
            path.write_text("\x1b[32mGREEN\x1b[0m \n")
            logs.append(path.relative_to(self.root).as_posix())
        packet = review_packet.packet(self.plan, "P1.1", selector="grok/grok-4.7/500k",
                                      executor_session="executor", evidence=logs)
        manifest = json.loads(Path(packet["manifest"]).read_text())
        self.assertGreater(Path(packet["manifest"]).stat().st_size, review_packet.PACKET_BYTES_MAX)
        self.assertLess(packet["packet_bytes"], review_packet.PACKET_BYTES_MAX)
        self.assertEqual(manifest["review_paths"], ["src/client-0000.py"])
        self.assertEqual(len(manifest["snapshot"]["product"]), 350)
        self.assertNotIn("external_sources", Path(packet["packet"]).read_text())

    def test_terminal_transport_before_receipt_reconciles_without_new_prompt(self):
        self.prepare(reviewer="grok/grok-4.7")
        packet = review_packet.packet(self.plan, "P1.1", selector="grok/grok-4.7", executor_session="executor")
        manifest = json.loads(Path(packet["manifest"]).read_text())
        directory = review_packet._location(self.plan, "P1.1")
        attempt = review_job.create(directory, manifest)
        started = json.loads((attempt / "started.json").read_text())
        started["owner"] = {"pid": 99999999, "start_ticks": "1"}
        review_job.write(attempt / "started.json", started)
        verdict = {"schema_version": "review-verdict/v1", "candidate_sha256": manifest["candidate_sha256"],
                   "reviewer": manifest["reviewer"], "verdict": "GREEN", "findings": []}
        (attempt / "output.json").write_text(json.dumps(verdict))
        (attempt / "provider-output.jsonl").write_text("terminal\n")
        (attempt / "stderr.log").write_text("")
        review_job.write(attempt / "transport-result.json", {"session": "native-independent", "complete": True,
            "detail": "ACP stopReason=end_turn", "observed_context": None, "provider_route": {},
            "heartbeats": [], "read_ledger": {}, "argv": ["grok"]})
        with patch("task.review_grok_acp.run") as transport:
            result = review_packet.job_status(self.plan, "P1.1", reconcile=True)
            transport.assert_not_called()
        self.assertEqual(result["action"], "accept-candidate")
        self.assertEqual(len(list(directory.glob("attempt-*"))), 1)


if __name__ == "__main__":
    unittest.main()
