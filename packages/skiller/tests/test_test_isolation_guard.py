"""Contract checks for lifecycle-aware Laravel isolation snippets (no Composer runtime)."""
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/laravel-testing/test-isolation-guard"
SNIPPETS = SKILL / "snippets"
FIXTURE = ROOT / "tests/fixtures_data/laravel-parallel-isolation/fixture.php"


class TestIsolationGuard(unittest.TestCase):
    def test_lifecycle_contract_names_exact_callbacks_and_fail_closed_outcome(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        parallel = (SNIPPETS / "ParallelTestingIsolation.php").read_text(encoding="utf-8")
        self.assertIn("setUpTestDatabaseBeforeMigrating()", skill)
        self.assertIn("setUpProcess()", skill)
        self.assertIn("FRAMEWORK_LIFECYCLE_CONFLICT", skill)
        self.assertIn("$resolved !== $selectedDatabase", parallel)
        self.assertIn("($config['driver'] ?? null) !== 'local'", parallel)
        self.assertIn("is_link($root)", parallel)

    def test_serial_guard_never_guesses_parallel_database(self):
        testcase = (SNIPPETS / "TestCase.php").read_text(encoding="utf-8")
        guard = (SNIPPETS / "TestEnvironmentGuard.php").read_text(encoding="utf-8")
        self.assertIn("canonicalTestDatabase", testcase)
        self.assertIn("assertCanonicalTestDatabase", guard)
        self.assertIn("setUpTestDatabaseBeforeMigrating", guard)

    def test_php_snippets_and_stub_fixture_are_syntax_valid(self):
        for path in [*sorted(SNIPPETS.glob("*.php")), FIXTURE]:
            result = subprocess.run(["php", "-l", str(path)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_stub_proves_callback_order_and_distinct_owned_roots(self):
        result = subprocess.run(["php", str(FIXTURE)], capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["events"], ["createApplication", "setUpTestDatabaseBeforeMigrating", "RefreshDatabase"])
        self.assertNotEqual(payload["workers"]["1"], payload["workers"]["2"])
        self.assertEqual(payload["wrong_token_refused"], "FRAMEWORK_LIFECYCLE_CONFLICT")
        self.assertTrue(payload["outside_sentinel_preserved"])


if __name__ == "__main__":
    unittest.main()
