import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/test.yml"


def _jobs(text):
    """Parse the small jobs/steps subset this repository owns without a YAML dependency."""
    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line == "jobs:") + 1
    except StopIteration as exc:
        raise AssertionError("workflow has no jobs mapping") from exc
    result = {}
    current = None
    for line in lines[start:]:
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
        if match:
            current = match.group(1)
            result[current] = {"runs": [], "python_versions": None}
            continue
        if current is None:
            continue
        version = re.fullmatch(r"\s{8}python-version:\s*(\[.*\])", line)
        if version:
            result[current]["python_versions"] = tuple(ast.literal_eval(version.group(1)))
        run = re.fullmatch(r"\s+-?\s*run:\s*(.+)", line)
        if run:
            result[current]["runs"].append(run.group(1).strip())
    return result


class TaskCiGateTests(unittest.TestCase):
    def setUp(self):
        self.jobs = _jobs(WORKFLOW.read_text(encoding="utf-8"))

    def test_task_validator_is_one_authoritative_matrix_job(self):
        command = "bash packages/task/scripts/validate.sh"
        owners = [name for name, job in self.jobs.items() if command in job["runs"]]
        self.assertEqual(owners, ["task"])
        self.assertEqual(
            self.jobs["task"]["python_versions"],
            ("3.9", "3.11", "3.13"),
        )
        self.assertEqual(self.jobs["task"]["runs"].count(command), 1)

    def test_task_sources_and_tests_are_in_the_authoritative_ruff_step(self):
        # The lint job calls scripts/lint.sh; the pinned ruff command and the path list live in that script.
        runs = self.jobs["lint"]["runs"]
        self.assertEqual([command for command in runs if "scripts/lint.sh" in command], ["bash scripts/lint.sh"])
        script = (ROOT / "scripts/lint.sh").read_text(encoding="utf-8")
        self.assertEqual(script.count('pipx run "ruff==$RUFF_VERSION" check'), 1)
        self.assertIn("packages/task/lib", script)
        self.assertIn("packages/task/tests", script)


if __name__ == "__main__":
    unittest.main()
