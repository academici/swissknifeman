"""Dry-run native workflow templates without dispatching real agents."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "workflow dry-run requires Node")
class WorkflowReviewBoundaryTests(unittest.TestCase):
    def run_template(self, name, substitutions=()):
        source = (Path(__file__).parents[1] / "workflows" / name).read_text()
        for old, new in substitutions:
            source = source.replace(old, new)
        runner = """
const fs = require('fs');
const source = fs.readFileSync(0, 'utf8').replace(/^export /gm, '');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const calls = [];
const agent = async (prompt, opts) => {
  calls.push({label: opts.label, model: opts.model, effort: opts.effort});
  if (opts.label.startsWith('review:')) return {verdict: 'FIX_REQUIRED', findings: [{risk_class: 'concurrency', area: 'tree'}]};
  return {files_changed: [], commits: [], tests_green: true, validation: 'exit=0', issues: [], summary: 'done'};
};
(async () => {
  try {
    const result = await new AsyncFunction('agent','parallel','pipeline','log',source)(agent, async tasks => Promise.all(tasks.map(t => t())), null, () => {});
    process.stdout.write(JSON.stringify({calls, result}));
  } catch (error) { process.stdout.write(JSON.stringify({calls, error: error.message})); }
})();
"""
        result = subprocess.run([shutil.which("node"), "-e", runner], input=source,
                                capture_output=True, text=True, timeout=10, check=True)
        return json.loads(result.stdout)

    def test_missing_reviewer_refuses_before_author_or_finder(self):
        for name in ("wf-dev-slice.js", "wf-audit-adversarial.js"):
            result = self.run_template(name)
            self.assertIn("REVIEWER_REQUIRED", result["error"])
            self.assertEqual(result["calls"], [])

    def test_review_finding_returns_once_without_nested_fix_or_review(self):
        result = self.run_template("wf-dev-slice.js", (("const REVIEWER = null", "const REVIEWER = {model: 'selected-reviewer', effort: 'high'}"),))
        self.assertEqual([call["label"].split(":")[0] for call in result["calls"]], ["impl", "review"])
        self.assertEqual(result["calls"][1]["model"], "selected-reviewer")
        self.assertFalse(result["result"]["all_green"])
        self.assertEqual(result["result"]["slices"][0]["stopped"], "review-fix-required")

    def test_low_risk_execution_does_not_add_independent_review(self):
        result = self.run_template("wf-dev-slice.js", (("risk: 'medium'", "risk: 'low'"),))
        self.assertNotIn("error", result)
        self.assertTrue(result["result"]["all_green"])
        self.assertFalse(any(call["label"].startswith("review:") for call in result["calls"]))
