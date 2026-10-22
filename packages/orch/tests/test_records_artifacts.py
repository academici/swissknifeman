"""records/v1, part 2 (P4.9): the kinds risk, review-strategy, process, agent-request/result/usage, review-verdict,
provider-gates, observer-report, prompt-diff and conformance-report: their examples, their writers on a fake run, the
agent records written durably, and readers that stop on a record that does not match instead of reading it as nothing."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.util import docio, schema

from orch import conformance
from orch.conductor import agents, observer, process, prompts, records
from orch.conductor.application import recovery, review_plan
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.policies import budget
from tests.test_conductor import GREEN, ConductorCase, executor_ok, report

EXAMPLES = records.CONTRACT_DIR / "examples"
PART_2 = ("agent-request", "agent-result", "agent-usage", "conformance-report", "observer-report", "process",
          "prompt-diff", "provider-gates", "review-strategy", "review-verdict", "risk")


def example(kind: str, name: str) -> dict:
    return json.loads((EXAMPLES / "valid" / kind / name).read_text(encoding="utf-8"))


class ExampleTests(unittest.TestCase):
    def test_every_kind_of_part_two_is_registered_with_its_carrier(self):
        self.assertTrue(set(PART_2) <= set(records.KINDS))
        for kind in PART_2:
            carrier, value = records.TAGS[kind]
            self.assertEqual(carrier, "schema" if kind in records.SHORT_TAGS else "$schema", kind)

    def test_valid_examples_pass_and_invalid_ones_fail_with_the_code_of_their_name(self):
        for kind in PART_2:
            valid = sorted((EXAMPLES / "valid" / kind).glob("*.json"))
            invalid = sorted((EXAMPLES / "invalid" / kind).glob("*.json"))
            self.assertTrue(valid and invalid, kind)
            for path in valid:
                with self.subTest(kind=kind, path=path.name):
                    self.assertEqual(records.problems(json.loads(path.read_text(encoding="utf-8")), kind), [])
            for path in invalid:
                with self.subTest(kind=kind, path=path.name):
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    codes = {issue.code for issue in schema.validate(doc, kind, records.registry())}
                    self.assertIn(path.name.split("-", 1)[0], codes)
                    self.assertNotEqual(records.problems(doc, kind), [])

    def test_check_names_the_place_the_pointer_and_the_hint(self):
        doc = example("risk", "review-added.json")
        self.assertIs(records.check(doc, "risk", "risk.json"), doc)
        with self.assertRaises(Stop) as caught:
            records.check(dict(doc, score="60"), "risk", "risk.json of W1", hint=records.WRITER_HINT)
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertTrue(caught.exception.message.startswith("risk.json of W1: /score: "), caught.exception.message)
        self.assertTrue(caught.exception.message.endswith(records.WRITER_HINT))


class WriterRunTests(ConductorCase):
    """A fake run writes every record of its pieces valid: the agents, process, risk, review-verdict, observer."""

    scenario = "scout-solo"
    SCHEMA = {"write": {"out/W1.txt": "ok\n", "out/schemas/W1.json": "{}\n"},
              "result": report("W1", changed_paths=["out/W1.txt", "out/schemas/W1.json"])}

    def test_a_run_with_an_added_review_writes_valid_records(self):
        self.write_config(extra="[orch.conductor.risk.weights]\nschema = 70")
        self.set_items({"W1": {"write_set": ["out/W1.txt", "out/schemas/*.json"]}})
        self.script({"executor": [self.SCHEMA], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        piece = self.run_dir(err) / "W1"
        raw = json.loads((piece / "risk.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["$schema"], records.TAGS["risk"][1])
        self.assertEqual((raw["score"], raw["added"], raw["item"]), (70, True, "W1"))
        folders = sorted((piece / agents.AGENTS).iterdir())
        self.assertTrue(folders)
        for folder in folders:
            for name, kind in (("request.json", "agent-request"), ("result.json", "agent-result"),
                               ("usage.json", "agent-usage")):
                with self.subTest(folder=folder.name, name=name):
                    self.assertEqual(json.loads((folder / name).read_text(encoding="utf-8"))["$schema"],
                                     records.TAGS[kind][1])
                    self.assertIsNotNone(records.read(folder / name, kind))
            if (folder / "process.json").exists():
                self.assertEqual(records.read(folder / "process.json", "process")["pgid"],
                                 records.read(folder / "process.json", "process")["pid"])
        verdict = json.loads((self.project / "plans/T/artifacts/W1/review-verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(verdict["schema"], "orch-conductor-review-verdict/v1")
        self.assertNotIn("$schema", verdict)
        self.assertEqual(verdict["rounds"][0]["verdict"], "GREEN")
        report_file = self.project / ".swissknifeman/orch/reports" / self.run_dir(err).name / "observer.json"
        found = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(records.problems(found, "observer-report"), [])
        self.assertNotIn("$schema", found)
        self.assertTrue(found["tokens_by_agent"])

    def test_a_batch_writes_a_valid_review_strategy(self):
        self.set_items({ref: {} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN, GREEN]})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual(code, 0, err)
        kept = records.read(self.run_dir(err) / review_plan.STRATEGY_FILE, "review-strategy")
        self.assertEqual(kept["$schema"], records.TAGS["review-strategy"][1])
        self.assertEqual({key: value for key, value in kept.items() if key != "$schema"},
                         self.state(err)["review_strategy"])


class AgentRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.item = Path(self.tmp.name) / "W1"

    def start(self, **extra) -> dict:
        return agents.start(self.item, "agent-x-1", role="executor", route={"provider": "codex"}, step="executor.1",
                            attempt=1, prompt="prompts/executor.1.md", parent=None, started_at="2026-10-22T10:00:00Z",
                            **extra)

    def test_request_result_and_usage_are_written_durably_through_records(self):
        written = []
        real = docio.durable_replace

        def durable(path, data, *, mode=None):
            written.append((Path(path).name, mode))
            return real(path, data, mode=mode)

        with mock.patch.object(docio, "durable_replace", durable):
            handle = self.start()
            agents.add_usage(handle, {"input": 3, "output": 2})
            agents.finish(handle, exit_code=0, error=None, decisions=[], duration_s=1.04, stream=None, lingered=False)
        self.assertEqual(written, [("request.json", 0o600), ("result.json", 0o600), ("usage.json", 0o600)])
        usage = records.read(handle["directory"] / "usage.json", "agent-usage")
        self.assertEqual((usage["input"], usage["output"], usage["usage_complete"]), (3, 2, None))

    def test_a_result_outside_its_schema_is_refused_and_nothing_is_written(self):
        handle = self.start()
        with self.assertRaises(Stop) as caught:
            agents.finish(handle, exit_code="0", error=None, decisions=[], duration_s=1.0, stream=None, lingered=False)
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertIn("/exit: ", caught.exception.message)
        self.assertFalse((handle["directory"] / "result.json").exists())

    def test_a_record_that_does_not_match_is_record_invalid_and_the_observer_leaves_the_piece_out(self):
        folder = self.item / agents.AGENTS / "agent-x-1"
        folder.mkdir(parents=True)
        (folder / "request.json").write_text(json.dumps({"step": 3}), encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            agents.read(self.item)
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertIn("/step: ", caught.exception.message)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            built = observer.build(Path(self.tmp.name), Path(self.tmp.name))
        self.assertEqual(built["tokens_by_agent"], [])
        self.assertIn("RECORD_INVALID: ", err.getvalue())
        self.assertIn("agent runs of W1 are left out", err.getvalue())

    def test_an_empty_or_tag_only_result_is_record_invalid_and_never_ok(self):
        handle = self.start()
        result = handle["directory"] / "result.json"
        for doc in ({}, {"$schema": records.TAGS["agent-result"][1]}, {"error": {"code": "ROLE_FAILED"}}):
            with self.subTest(doc=doc):
                with self.assertRaises(Stop) as written:
                    records.write(result, doc, "agent-result")
                self.assertIn(": /: matches 0 of 2 oneOf branches", written.exception.message)
                self.assertFalse(result.exists())
                result.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(Stop) as read:
                    agents.read(self.item)
                self.assertEqual(read.exception.code, "RECORD_INVALID")
                self.assertIn("result.json: /: matches 0 of 2 oneOf branches", read.exception.message)
                result.unlink()

    def test_finished_failed_and_orphaned_results_keep_their_status(self):
        handle = self.start()
        agents.finish(handle, exit_code=0, error=None, decisions=[], duration_s=1.0, stream=None, lingered=False)
        failed = agents.start(self.item, "agent-x-2", role="reviewer", route={"provider": "grok"}, step="review.1",
                              attempt=1, prompt="p.md", parent=None, started_at="2026-10-22T10:00:00Z")
        agents.finish(failed, exit_code=None, error={"code": "PROVIDER_UNAVAILABLE", "message": "x"}, decisions=[],
                      duration_s=0.1, stream=None, lingered=False)
        orphan = agents.start(self.item, "agent-x-3", role="executor", route={"provider": "codex"}, step="executor.2",
                              attempt=1, prompt="p.md", parent=None, started_at="2026-10-22T10:00:00Z")
        self.assertTrue(agents.orphan(orphan["directory"]))
        self.assertEqual([row["status"] for row in agents.read(self.item)], ["ok", "failed", "failed"])

    def test_an_unreadable_request_is_skipped_as_before(self):
        (self.item / agents.AGENTS / "agent-x-1" / "request.json").mkdir(parents=True)
        self.assertEqual(agents.read(self.item), [])

    def test_the_process_of_a_role_is_a_checked_record(self):
        directory = self.item / agents.AGENTS / "agent-x-1"
        run = process.run_role([sys.executable, "-I", "-c", "pass"], "", transport="text", cwd=Path(self.tmp.name),
                               timeout_s=30, raw_path=self.item / "streams" / "executor.1.txt",
                               agent_directory=directory)
        self.assertEqual(run.exit, 0)
        found = records.read(directory / "process.json", "process")
        self.assertEqual(found["$schema"], records.TAGS["process"][1])
        self.assertEqual(found["pid"], found["pgid"])


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = SimpleNamespace(directory=Path(self.tmp.name), state={"items": {"W1": {"steps": {}}}})
        self.folder = self.run.directory / "W1" / agents.AGENTS / "agent-x-1"
        agents.start(self.run.directory / "W1", "agent-x-1", role="executor", route={"provider": "codex"},
                     step="executor.1", attempt=1, prompt="p.md", parent=None, started_at="2026-10-22T10:00:00Z")

    def test_a_process_record_that_does_not_match_stops_the_resume_before_any_signal(self):
        (self.folder / "process.json").write_text(json.dumps({"pid": "4242", "pgid": 4242}), encoding="utf-8")
        with mock.patch.object(recovery.os, "killpg") as kill, self.assertRaises(Stop) as caught:
            recovery.kill_orphaned_roles(self.run)
        kill.assert_not_called()
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertIn("process.json: /pid: ", caught.exception.message)

    def test_a_request_record_that_does_not_match_stops_the_resume(self):
        records.write(self.folder / "process.json", {"pid": 4242, "pgid": 4242, "start_ticks": 1,
                                                     "started_at": "2026-10-22T10:00:01Z"}, "process")
        (self.folder / "request.json").write_text(json.dumps({"step": "executor.1", "attempt": "1"}), encoding="utf-8")
        with mock.patch.object(recovery.os, "killpg") as kill, self.assertRaises(Stop) as caught:
            recovery.kill_orphaned_roles(self.run)
        kill.assert_not_called()
        self.assertIn("request.json: /attempt: ", caught.exception.message)


class ColdStageUsageTests(unittest.TestCase):
    """policies/budget.known_stage_usage reads the agent records of a step through records (a run saved before
    stage_usage and labelled receipts): a damaged record stops, it is never zero usage that slips past the budget."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.item = Item("W1", "run", {}, Path(self.tmp.name) / "W1", {}, policy={"budgets": {"stage_tokens_max": 100}})
        self.folder = self.item.directory / agents.AGENTS / "agent-x-1"
        self.folder.mkdir(parents=True)
        self.request = {"step": "executor.1"}
        self.usage = {"input": 150, "cached": 0, "output": 3}

    def write(self, request=None, usage=None) -> None:
        for name, doc in (("request.json", request), ("usage.json", usage)):
            if doc is not None:
                (self.folder / name).write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")

    def admit(self, recovered: dict) -> None:
        actor = SimpleNamespace(state={}, run_doc={}, run_id="run", _step_tokens=recovered, _current_step="executor.1")
        budget.admit(actor, self.item, "attempt")

    def test_valid_old_records_are_recovered_and_enforce_the_stage_budget(self):
        self.write(self.request, self.usage)
        recovered = budget.known_stage_usage(self.item, "executor.1")
        self.assertEqual((recovered["input"], recovered["output"]), (150, 3))
        with self.assertRaises(Stop) as caught:
            self.admit(recovered)
        self.assertEqual(caught.exception.code, "TOKEN_BUDGET")

    def test_a_missing_usage_file_still_starts_at_zero(self):
        self.write(self.request)
        self.assertEqual(budget.known_stage_usage(self.item, "executor.1"), {"input": 0, "output": 0})

    def test_damaged_records_stop_with_their_code_and_pointer(self):
        cases = (("usage foreign tag", self.request, {**self.usage, "$schema": "other/v1"}, "RECORD_INVALID",
                  "usage.json: /$schema: unknown or conflicting record tag"),
                 ("usage text count", self.request, {**self.usage, "input": "broken"}, "RECORD_INVALID",
                  "usage.json: /input: "),
                 ("usage not JSON", self.request, "not JSON", "STATE_CORRUPT", "usage.json is not JSON"),
                 ("request foreign tag", {**self.request, "$schema": "other/v1"}, self.usage, "RECORD_INVALID",
                  "request.json: /$schema: unknown or conflicting record tag"),
                 ("request not JSON", "not JSON", self.usage, "STATE_CORRUPT", "request.json is not JSON"))
        for name, request, usage, code, where in cases:
            with self.subTest(name):
                self.write(request, usage)
                with self.assertRaises(Stop) as caught:
                    budget.known_stage_usage(self.item, "executor.1")
                self.assertEqual(caught.exception.code, code)
                self.assertIn(where, caught.exception.message)


class ReviewStrategyTests(unittest.TestCase):
    PLAN = {"mode": "groups", "groups": [["W1", "W2"]], "reviewer": {"effort": "high"}, "reason": "one contract",
            "source": "rules", "decided_at": "2026-10-22T10:00:00Z"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = SimpleNamespace(state={}, directory=Path(self.tmp.name), _save=mock.Mock())

    def test_a_kept_strategy_file_is_taken_when_the_state_lost_it(self):
        records.write(self.run.directory / review_plan.STRATEGY_FILE, self.PLAN, "review-strategy")
        review_plan.decide(self.run, [{"ref": "W1"}, {"ref": "W2"}])
        self.assertEqual(self.run.state["review_strategy"], self.PLAN)
        self.run._save.assert_called_once()

    def test_a_kept_strategy_that_does_not_match_is_record_invalid(self):
        (self.run.directory / review_plan.STRATEGY_FILE).write_text(json.dumps(dict(self.PLAN, mode="pairs")),
                                                                    encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            review_plan.decide(self.run, [{"ref": "W1"}, {"ref": "W2"}])
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertIn("/mode: ", caught.exception.message)
        self.assertEqual(self.run.state, {})


class OutputTests(unittest.TestCase):
    """observer.json, prompt diff and conformance are checked before they leave; their bytes stay as they were."""

    def test_the_observer_report_is_checked_and_keeps_its_serialization(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        good = example("observer-report", "slow-run-with-agents.json")
        with mock.patch.object(observer, "build", return_value=good):
            observer.write_report(tmp / "run", tmp, tmp / "out")
        self.assertEqual((tmp / "out/observer.json").read_text(encoding="utf-8"),
                         json.dumps(good, ensure_ascii=False, indent=2) + "\n")
        bad = dict(good, beacons={"RUN_SLOW": "1"})
        with mock.patch.object(observer, "build", return_value=bad), self.assertRaises(Stop) as caught:
            observer.write_report(tmp / "run", tmp, tmp / "bad")
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertIn("/beacons/RUN_SLOW: ", caught.exception.message)
        self.assertFalse((tmp / "bad/observer.json").exists())

    def test_a_prompt_diff_is_checked(self):
        block = {"kind": "role", "origin": "roles/executor.md", "sha256": "a" * 64, "tokens": 10}
        base = {"step": "executor.1", "prompt_sha256": "1" * 64, "estimated_tokens": 10, "blocks": [block]}
        doc = prompts.diff_manifests(base, dict(base, step="executor.2"))
        self.assertEqual((doc["schema"], doc["counts"]["same"]), ("prompt-diff/v1", 1))
        with self.assertRaises(Stop) as caught:
            prompts.diff_manifests(dict(base, estimated_tokens=1.5), base)
        self.assertIn("/tokens/from: ", caught.exception.message)

    def test_conformance_rows_are_checked_and_returned_as_they_are(self):
        rows = example("conformance-report", "cao.json")["rows"]
        self.assertIs(conformance.report_rows(rows), rows)
        with self.assertRaises(conformance.ConformanceError) as caught:
            conformance.report_rows([dict(rows[0], status="covered")])
        self.assertIn("RECORD_INVALID: orch conformance: /rows/0/status: ", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
