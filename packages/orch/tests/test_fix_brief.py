"""Bounded review delivery, stable queue identity and persisted records."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from orch.conductor import contract, options, records
from tests.test_conductor import ConductorCase, GREEN, executor_ok, report
from orch.conductor.domain import fix_brief
from orch.conductor.domain.report import finding_key
from orch.conductor.domain.fix_brief import correction_inputs
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.prompts.corrections import check_correction, _bounded_log


def documents(count=40):
    findings, confirmed = [], []
    for n in range(count):
        name = f"F{n + 1}"
        severity = "Blocker" if n < 5 else "Major" if n < 25 else "Minor"
        findings.append({"id": name, "severity": severity, "confidence": "high", "location": f"src/a{n}.py:1",
                         "failure_scenario": "problem " * 600, "basis": "correctness"})
        confirmed.append({"finding": name, "reproduction": {"cmd": "repro " * 200, "exit": 1,
                         "observed": "failure " * 500}, "fix": "fix " * 600})
    return {"verdict": "RED", "findings": findings}, {"confirmed": confirmed, "rejected": []}


def refs():
    return {"review": {"run": "R", "item": "W1", "round": 1, "receipt": "artifacts/review-receipt.json"},
            "base": "a" * 40, "findings": "artifacts/review-verdict.json", "scope_constraints": ["Stay in scope"],
            "required_checks": ["V1"]}


class FixBriefTests(unittest.TestCase):
    def test_long_fields_are_clipped_all_blockers_survive_and_every_other_finding_is_counted(self):
        findings, triage = documents()
        original = copy.deepcopy((findings, triage))
        doc = fix_brief.build(findings, triage, {}, {}, refs())
        self.assertEqual([], contract.problems(doc, "fix-brief"))
        self.assertEqual(original, (findings, triage))
        self.assertEqual(5, sum(row["severity"] == "Blocker" for row in doc["findings"]))
        self.assertLessEqual(len(doc["findings"]), 12)
        self.assertLessEqual(len(fix_brief.render(doc)), 24000)
        self.assertEqual(40 - len(doc["findings"]), doc["deferred"]["count"])
        self.assertEqual(doc["deferred"]["count"], sum(doc["deferred"]["by_severity"].values()))
        self.assertGreater(doc["deferred"]["by_severity"]["Major"], 0)
        for row in doc["findings"]:
            self.assertEqual(set(row["clipped"]), {"problem", "fix", "observed", "cmd"})
            for field, maximum in fix_brief.FIELD_LIMITS.items():
                value = row["reproduction"][field] if field in ("cmd", "observed") else row[field]
                self.assertLessEqual(len(value), maximum)
                self.assertIn(f"full: artifacts/review-verdict.json#{row['id']}", value)

    def test_blockers_exceed_both_limits_and_are_never_dropped(self):
        findings, triage = documents()
        doc = fix_brief.build(findings, triage, {}, {"max_findings": 1, "max_chars": 100}, refs())
        self.assertEqual(5, len(doc["findings"]))
        self.assertTrue(all(row["severity"] == "Blocker" for row in doc["findings"]))
        self.assertEqual(35, doc["deferred"]["count"])

    def test_count_admission_includes_the_deferred_summary_and_confidence_order(self):
        findings, triage = documents(8)
        for row in findings["findings"]:
            row.update(severity="Major", failure_scenario="p", confidence="low")
        findings["findings"][-1]["confidence"] = "high"
        doc = fix_brief.build(findings, triage, {}, {"max_findings": 2}, refs())
        self.assertEqual(["F8", "F1"], [row["id"] for row in doc["findings"]])
        limit = len(fix_brief.render(doc)) - 1
        smaller = fix_brief.build(findings, triage, {}, {"max_findings": 2, "max_chars": limit}, refs())
        self.assertLessEqual(len(fix_brief.render(smaller)), limit)
        self.assertLess(len(smaller["findings"]), 2)

    def test_partial_option_layer_keeps_the_other_default(self):
        merged = options.merge(options.DEFAULTS, {"review": {"fix_brief": {"max_findings": 3}}})
        self.assertEqual({"max_findings": 3, "max_chars": 24000}, merged["review"]["fix_brief"])
        self.assertTrue(options.layer_problems({"review": {"fix_brief": {"max_chars": 0}}}))

    def test_a_budget_too_small_for_the_required_frame_fails_closed_without_dropping_evidence(self):
        findings, triage = documents(1)
        findings["findings"][0]["severity"] = "Major"
        with self.assertRaisesRegex(ValueError, "max_chars cannot hold"):
            fix_brief.build(findings, triage, {}, {"max_chars": 1}, refs())

    def test_check_tail_and_header_samples_are_bounded_with_full_log_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "checks/1/V1.log"
            log.parent.mkdir(parents=True)
            log.write_text("FAIL: first\n" + "x" * 100000 + "\nERROR: last\n")
            tail = "start" + "x" * 100000 + "end"
            bounded = _bounded_log(tail, log)
            self.assertLessEqual(len(bounded), 4000)
            self.assertTrue(bounded.startswith("start"))
            self.assertTrue(bounded.endswith("end"))
            many = _bounded_log("line\n" * 100, log)
            self.assertLessEqual(len(many.splitlines()), 40)
            text = check_correction([{"id": "V1", "cmd": "test", "exit": 1, "tail": tail, "log": str(log)}])
            self.assertNotIn(tail, text)
            self.assertIn(str(log), text)
            self.assertIn("chars omitted; full log:", text)

    def test_no_brief_is_published_when_its_queue_cannot_be_saved(self):
        from types import SimpleNamespace
        from unittest import mock
        from orch.conductor.stages.review import review_correction
        findings, triage = documents(6)
        with tempfile.TemporaryDirectory() as tmp:
            item = Item("W1", "R", {"steps": {}}, Path(tmp), {})
            item.artifacts = Path(tmp) / "artifacts"
            item.options = {"review": {"fix_brief": {"max_findings": 1, "max_chars": 24000}}}
            item.input_doc = {"acceptance": {"checks": []}}
            sources = {row["id"]: {"key": finding_key(row), "round": 1, "id": row["id"]}
                       for row in findings["findings"]}
            owner = SimpleNamespace(run_id="R", _relative=str, _save=mock.Mock(side_effect=OSError("disk")))
            with self.assertRaises(OSError):
                review_correction(owner, item, 2, 1, findings, triage, sources)
            self.assertFalse((Path(tmp) / "fix-briefs/executor.2.json").exists())

    def test_interrupted_combined_round_restores_the_durable_brief_into_its_correction(self):
        from types import SimpleNamespace
        from unittest import mock
        from orch.conductor.stages.execute import execute
        findings, triage = documents(1)
        doc = fix_brief.build(findings, triage, {}, {}, refs())
        with tempfile.TemporaryDirectory() as tmp:
            item = Item("W1", "R", {"steps": {}, "combined_done": [1]}, Path(tmp), {})
            path = Path(tmp) / "fix-briefs/executor.2.json"
            path.parent.mkdir()
            path.write_text(json.dumps(doc))
            report = {"status": "done"}
            owner = SimpleNamespace(_round=mock.Mock(return_value=report),
                                    _questioned=mock.Mock(return_value=(report, False)))
            self.assertEqual(report, execute(owner, item, 2, "", "red check V1"))
            correction = owner._round.call_args.args[5]
            self.assertIn("red check V1", correction)
            self.assertIn(fix_brief.render(doc), correction)

    def test_old_and_new_state_save_load_and_resume_queue(self):
        findings, triage = documents(6)
        key = finding_key(findings["findings"][-1])
        state = {"items": {"W1": {"steps": {
            "review.1": {"status": "done", "result": {"findings": findings}},
            "triage.1": {"status": "done", "result": {"triage": triage}}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            records.write(path, state, "state")
            old = records.read(path, "state")
            self.assertNotIn("deferred_findings", old["items"]["W1"])
            state["items"]["W1"]["deferred_findings"] = [{"key": key, "round": 1, "id": "F6"}]
            records.write(path, state, "state")
            new = records.read(path, "state")
            item = Item("W1", "R", new["items"]["W1"], Path(tmp), {})
            merged, checked, sources = correction_inputs(item.state, 2, {"verdict": "GREEN", "findings": []},
                                                        {"confirmed": [], "rejected": []})
            self.assertEqual(["F6"], [row["id"] for row in merged["findings"]])
            self.assertEqual("F6", checked["confirmed"][0]["finding"])
            self.assertEqual(key, sources["F6"]["key"])
            damaged = json.loads(path.read_text())
            damaged["items"]["W1"]["deferred_findings"][0]["round"] = 0
            with self.assertRaises(Stop):
                records.write(path, damaged, "state")




class FixBriefLoopTests(ConductorCase):
    def setup_findings(self, count=2):
        findings, triage = documents(count)
        for index, row in enumerate(findings["findings"]):
            row.update(severity="Major", location=f"out/W1.txt:{index + 1}", failure_scenario=f"failure letter {chr(65 + index)}")
        return findings, triage

    def test_deferred_major_reaches_the_next_correction_even_after_a_clean_review(self):
        findings, triage = self.setup_findings()
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "review": {"fix_brief": {"max_findings": 1}}, "limits": {"corrections": 2, "review_rounds": 3}}}]}})
        self.script({"executor": [executor_ok("W1"),
                     {"write": {"out/W1.txt": "first fix\n"}, "result": report("W1")},
                     {"write": {"out/W1.txt": "second fix\n"}, "result": report("W1")}],
                     "reviewer": [{"result": findings}, GREEN, GREEN], "triager": [{"result": triage}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual((3, 3), (self.calls("executor"), self.calls("reviewer")))
        self.assertIn("failure letter A", self.prompt("executor", 2))
        self.assertNotIn("failure letter B", self.prompt("executor", 2))
        self.assertIn("failure letter B", self.prompt("executor", 3))
        self.assertEqual([], self.state(err)["items"]["W1"]["deferred_findings"])

    def test_large_stream_is_absent_from_correction_and_manifest_names_the_brief(self):
        findings, triage = documents()
        for row in findings["findings"]:
            row["location"] = "out/W1.txt:" + row["id"][1:]
        self.script({"executor": [executor_ok("W1"),
                     {"write": {"out/W1.txt": "fixed\n"}, "result": report("W1")}],
                     "reviewer": [{"result": findings, "stream": ["PRIVATE_STREAM_" * 150000]}, GREEN],
                     "triager": [{"result": triage}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 2)
        self.assertNotIn("PRIVATE_STREAM_", prompt)
        path = self.run_dir(err) / "W1/fix-briefs/executor.2.json"
        doc = json.loads(path.read_text())
        self.assertEqual(5, sum(row["severity"] == "Blocker" for row in doc["findings"]))
        manifest = json.loads((self.run_dir(err) / "W1/prompts/executor.2.manifest.json").read_text())
        block = next(row for row in manifest["blocks"] if row["kind"] == "correction")
        self.assertTrue(block["origin"].endswith("fix-briefs/executor.2.json"))
        self.assertLessEqual(block["tokens"], 8000)

    def test_same_finding_keys_with_line_drift_do_not_count_as_progress(self):
        findings, triage = self.setup_findings(1)
        later = copy.deepcopy(findings)
        later["findings"][0]["location"] = "out/W1.txt:999"
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "review": {"final_correction": False}, "limits": {"review_rounds": 3, "corrections": 1}}}]}})
        self.script({"executor": [executor_ok("W1"),
                     {"write": {"out/W1.txt": "attempted fix\n"}, "result": report("W1")}],
                     "reviewer": [{"result": findings}, {"result": later}], "triager": [{"result": triage}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((1, ("stopped", "ITEM_BLOCKED")), (code, self.outcome(err)), err)
        self.assertEqual(2, self.calls("executor"))
        self.assertIn("REVIEW_LIMIT", err)
