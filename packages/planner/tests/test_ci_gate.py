import json
import subprocess
import sys
import unittest
from pathlib import Path
import fixtures  # layout guard: hub-only tests are skipped in a standalone copy


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/modules.yml"
MATRIX = ROOT / "scripts/ci-matrix.py"


def _matrix(*args):
    done = subprocess.run([sys.executable, str(MATRIX), *args], cwd=str(ROOT), capture_output=True, text=True)
    return done


@fixtures.hub_only
class PlannerCiGateTests(unittest.TestCase):
    def test_planner_validator_is_one_matrix_step(self):
        # The workflow never repeats a command; the validate step of planner lives in scripts/ci-matrix.py only.
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/ci-matrix.py list --json", text)
        self.assertNotIn("packages/planner/scripts/validate.sh", text)
        steps = _matrix("steps", "planner")
        self.assertEqual(steps.returncode, 0, steps.stderr)
        validates = [line for line in steps.stdout.splitlines() if line.startswith("validate")]
        self.assertEqual(len(validates), 1)
        self.assertIn("scripts/validate.sh", validates[0])

    def test_planner_is_in_the_test_matrix_on_the_oldest_and_newest_python(self):
        done = _matrix("list", "--json", "--step", "test", "--python", "3.11,3.14")
        self.assertEqual(done.returncode, 0, done.stderr)
        versions = sorted(item["python"] for item in json.loads(done.stdout)["include"] if item["unit"] == "planner")
        self.assertEqual(versions, ["3.11", "3.14"])

    def test_planner_sources_and_tests_are_in_the_authoritative_ruff_step(self):
        steps = _matrix("steps", "planner").stdout.splitlines()
        lint = [line for line in steps if line.startswith("lint")]
        self.assertEqual(len(lint), 1)
        self.assertIn("scripts/lint.sh", lint[0])
        self.assertIn("packages/planner/lib", lint[0])
        self.assertIn("packages/planner/tests", lint[0])
        script = (ROOT / "scripts/lint.sh").read_text(encoding="utf-8")
        self.assertEqual(script.count('pipx run "ruff==$RUFF_VERSION" check'), 1)


if __name__ == "__main__":
    unittest.main()
