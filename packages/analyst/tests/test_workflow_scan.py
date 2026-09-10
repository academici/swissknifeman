"""P5.2 workflow fleet: bounded, static and deterministic evidence."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from analyst.common import Env
from analyst import workflow_scan


class TestWorkflowScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.local = self.base / "local"
        self.vault = self.base / "vault"
        self.local.mkdir(); self.vault.mkdir()
        (self.base / "config.json").write_text(json.dumps({"projects": [{
            "id": "alpha", "enabled": True, "local_path": str(self.local), "vault_path": str(self.vault),
        }]}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _script(self, root, relative, body):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_extractor_is_string_comment_and_brace_aware(self):
        source = "// export const meta = { ignored }\nexport const meta = { title: '} //', nested: { ok: true } };\nconst review = 'yes';"
        extracted = workflow_scan.extract_features(source)
        self.assertEqual(extracted["status"], "qualified")
        self.assertIn("review", extracted["features"])

    def test_inventory_deduplicates_mirror_and_includes_archive_without_absolute_paths(self):
        body = "export const meta = { name: 'safe' }; const review = true; const commit = true;"
        self._script(self.local, "plans/A/workflows/wf-a.js", body)
        self._script(self.vault, "plans/A/workflows/wf-a.js", body)
        self._script(self.local, "plans/archive/B/workflows/wf-b.js", "export const meta = { name: 'archive' }; const verify = true;")
        sources, missing, diagnostics = workflow_scan.inventory(workflow_scan.load_projects(self.base / "config.json"))
        self.assertFalse(missing or diagnostics)
        self.assertEqual(len(sources), 2)
        mirrored = next(row for row in sources if len(row["aliases"]) == 2)
        self.assertEqual(mirrored["plans"], ["alpha:A"])
        self.assertTrue(all(str(self.base) not in alias for row in sources for alias in row["aliases"]))
        self.assertIn("alpha:B", {plan for row in sources for plan in row["plans"]})

    def test_unsupported_and_malformed_are_not_absence(self):
        self.assertEqual(workflow_scan.extract_features("const x = 1")["status"], "unsupported")
        self.assertEqual(workflow_scan.extract_features("export const meta = { name: 'x' ")["status"], "malformed")

    def test_rule_of_three_counts_distinct_plans_after_digest_deduplication(self):
        sources = [
            {"status": "qualified", "features": ["review"], "plans": ["a:P1"]},
            {"status": "qualified", "features": ["review"], "plans": ["a:P2"]},
            {"status": "qualified", "features": ["review"], "plans": ["a:P3"]},
        ]
        candidates, _ = workflow_scan.synthesize(sources, [])
        self.assertEqual(candidates, [{"feature": "review", "plans": ["a:P1", "a:P2", "a:P3"],
                                       "distinct_plan_count": 3, "outcome": "refine-existing"}])

    def test_command_is_reproducible_and_writes_only_requested_report(self):
        self._script(self.local, "plans/A/workflows/wf-a.js", "export const meta = { name: 'x' }; const review = true;")
        env = Env(self.base, "workflow-scan", home=self.base / "home")
        output = self.base / "report"
        first = io.StringIO()
        with redirect_stdout(first):
            workflow_scan.cmd_workflow_scan(env, ["--output", str(output), "--now", "2026-09-09T00:00:00Z", "--json"])
        one = (output / "workflow-fleet-report.json").read_bytes()
        second = io.StringIO()
        with redirect_stdout(second):
            workflow_scan.cmd_workflow_scan(env, ["--output", str(output), "--now", "2026-09-09T00:00:00Z", "--json"])
        self.assertEqual(one, (output / "workflow-fleet-report.json").read_bytes())
        self.assertEqual(json.loads(first.getvalue()), json.loads(second.getvalue()))
        self.assertTrue((output / "workflow-fleet-report.md").is_file())


if __name__ == "__main__":
    unittest.main()
