"""Prelaunch checks use source options, report every refusal and never claim work."""
import json
import os
from unittest import mock

from orch.conductor import checks, review_batch
from orch import contracts
from orch.conductor.infrastructure.preflight import PluginWorkSource
from tests.test_conductor import ConductorCase, INPUT, GREEN, executor_ok


class PreflightTests(ConductorCase):
    def inspected(self, ref, provider="claude-code", model="claude-opus-5-5"):
        doc = json.loads(INPUT.read_text())
        doc["route"] = {"minimum": {"class": "implementation", "effort": "high"}}
        doc["review_mode"] = "requested"
        doc["digest"] = contracts.canonical_digest(doc)
        doc["input_id"] = doc["input_id"].split("@")[0] + "@" + doc["digest"][:12]
        return {"op": "inspect", "outcome": "ok", "ref": ref, "scenario": "full", "options": [
            {"source": "item", "options": {"stages": [{"role": "executor", "provider": provider,
                "model": model, "effort": "high"}], "reviewer": "codex/gpt-6-astra/high", "fallback_routes": []}}],
                "input": doc}

    def test_reads_each_items_layers_and_reports_all_refusals_without_a_claim(self):
        before = self.state_file.read_bytes()
        def inspect(**fields):
            result = self.inspected(fields["ref"])
            if fields["ref"] == "W2":
                result["options"][0]["options"]["reviewer"] = "antigravity/gemini-4-argon-high/high"
            return result
        with mock.patch.object(PluginWorkSource, "inspect", side_effect=inspect) as source, \
             mock.patch.object(PluginWorkSource, "claim", side_effect=AssertionError("must not claim")), \
             mock.patch.dict(os.environ, {"SKM_ORCH_AGY_UNSAFE_REVIEWER": ""}):
            code, out, err = self.conduct("preflight", "--plan", "T", "--items", "W1", "W2")
        self.assertEqual(code, 1, err)
        result = json.loads(out)
        self.assertFalse(result["admitted"])
        self.assertEqual([r["ref"] for r in result["items"]], ["W1", "W2"])
        self.assertTrue(result["items"][0]["admitted"], result["items"][0])
        self.assertIn("AGY_MODEL_CLASS_UNVERIFIED", result["items"][1]["unavailable"].get("reviewer", ""), result)
        self.assertEqual(source.call_count, 2)
        self.assertEqual(self.state_file.read_bytes(), before)
        self.assertFalse((self.project / ".swissknifeman" / "orch-artifacts").exists())

    def test_source_failure_does_not_hide_later_items(self):
        refused = {"op": "inspect", "outcome": "refused", "ref": "W1", "reason_code": "READ_MISSING", "message": "missing"}
        with mock.patch.object(PluginWorkSource, "inspect", side_effect=[refused, refused]):
            code, out, err = self.conduct("preflight", "--plan", "T", "--items", "W1", "W2")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(json.loads(out)["items"]), 2)

    def test_source_route_minimum_is_checked_before_claim(self):
        inspected = self.inspected("W1", "codex", "gpt-6.1-sol")
        inspected["input"]["route"]["minimum"]["class"] = "frontier"
        doc = inspected["input"]
        doc["digest"] = contracts.canonical_digest(doc)
        doc["input_id"] = doc["input_id"].split("@")[0] + "@" + doc["digest"][:12]
        with mock.patch.object(PluginWorkSource, "inspect", return_value=inspected), \
             mock.patch.object(PluginWorkSource, "claim", side_effect=AssertionError("must not claim")):
            code, out, err = self.conduct("preflight", "--plan", "T", "--items", "W1")
        self.assertEqual(code, 1, err)
        self.assertIn("ROUTE_UNDERSHOOT", json.loads(out)["items"][0]["unavailable"]["item"])


class ReviewDiffTests(ConductorCase):
    def test_two_native_pieces_receive_new_contents_and_preserve_foreign_files(self):
        self.write_config(extra='[orch.conductor]\nforeign_untracked = "keep"')
        self.set_items({ref: {"review_mode": "requested", "options": [{"source": "item", "options": {
            "review": {"strategy": "each"}, "session": {"executor": "handoff"}}}]} for ref in ("W1", "W2")})
        (self.project / "foreign.txt").write_text("FOREIGN_CONTENT_MUST_NOT_ENTER_REVIEW")
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN, GREEN]})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("reviewer"), 2)
        for number, ref in enumerate(("W1", "W2"), 1):
            prompt = self.prompt("reviewer", number)
            self.assertIn(f'+++ "out/{ref}.txt"', prompt)
            self.assertIn("+ok", prompt)
            self.assertNotIn("FOREIGN_CONTENT_MUST_NOT_ENTER_REVIEW", prompt)
        self.assertNotIn('+++ "out/W1.txt"', self.prompt("reviewer", 2))
        commits = self.source()["commits"]
        self.assertEqual(len(commits), 2)
        self.assertTrue(all("foreign.txt" not in c["paths"] for c in commits))
        self.assertEqual((self.project / "foreign.txt").read_text(), "FOREIGN_CONTENT_MUST_NOT_ENTER_REVIEW")

    def test_new_candidate_contents_are_delivered_with_scoped_paths(self):
        (self.project / "new.txt").write_text("new implementation\n")
        (self.project / "foreign.txt").write_text("foreign secret\n")
        shown = checks.diff(self.project, "HEAD", paths=["new.txt"])
        self.assertIn("+new implementation", shown)
        self.assertNotIn("foreign secret", shown)

    def test_new_symlink_shows_target_without_reading_it_and_large_content_is_marked(self):
        secret = self.project.parent / "secret"
        secret.write_text("DO-NOT-READ-HOST-CONTENT")
        (self.project / "link").symlink_to(secret)
        shown = checks.diff(self.project, "HEAD", paths=["link"])
        self.assertIn(str(secret), shown)
        self.assertNotIn("DO-NOT-READ-HOST-CONTENT", shown)
        (self.project / "large").write_text("a\n" * 1000)
        shown = checks.diff(self.project, "HEAD", limit=250, paths=["large"])
        self.assertIn("cut", shown)
        self.assertLess(len(shown), 400)

    def test_group_review_keeps_docs_and_acceptance_tests(self):
        (self.project / "tests").mkdir()
        (self.project / "tests" / "acceptance.py").write_text("assert result == 42\n")
        (self.project / "README.md").write_text("mandatory public contract\n")
        self.git("add", "tests", "README.md")
        self.git("commit", "-qm", "docs and tests")
        shown = review_batch.diff_of(self.project, [self.git("rev-parse", "HEAD").strip()],
                                     review_batch.INCLUDE, review_batch.EXCLUDED)
        self.assertIn("assert result == 42", shown)
        self.assertIn("mandatory public contract", shown)
