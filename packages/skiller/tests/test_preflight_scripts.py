"""Preflight scripts of skills emit check-result/v1 JSON (aicore schema) on fixture projects."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

PKG_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((PKG_ROOT.parent / "aicore/schemas/check-result/v1/check-result.schema.json").read_text(encoding="utf-8"))
SKILLS = PKG_ROOT / "skills"
ISOLATION = SKILLS / "laravel-testing/test-isolation-guard"
DB = SKILLS / "devops/db-test-preflight/scripts/preflight.py"
NODE = SKILLS / "devops/node-pnpm-preflight/scripts/preflight.py"

PHPUNIT = '''<phpunit bootstrap="tests/bootstrap.php"><php>
<env name="APP_ENV" value="testing"/><env name="DB_DATABASE" value="{db}"/><env name="MEDIA_DISK" value="media-test"/>
</php></phpunit>'''


def run(script, *args, env=None):
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          env=env if env is not None else os.environ.copy())
    doc = json.loads(proc.stdout)
    jsonschema.validate(doc, SCHEMA)
    return proc.returncode, doc


def laravel_fixture(root, db="app_test", with_guard=True):
    (root / "tests/Support").mkdir(parents=True)
    (root / "phpunit.xml").write_text(PHPUNIT.format(db=db), encoding="utf-8")
    snippets = ISOLATION / "snippets"
    (root / "tests/bootstrap.php").write_text((snippets / "bootstrap.php").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "tests/TestCase.php").write_text((snippets / "TestCase.php").read_text(encoding="utf-8"), encoding="utf-8")
    if with_guard:
        (root / "tests/Support/TestEnvironmentGuard.php").write_text(
            (snippets / "TestEnvironmentGuard.php").read_text(encoding="utf-8"), encoding="utf-8")


class TestIsolationPreflightTest(unittest.TestCase):
    script = ISOLATION / "scripts/preflight.py"

    def test_snippets_project_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            laravel_fixture(Path(tmp))
            code, doc = run(self.script, "--root", tmp)
        self.assertEqual((code, doc["status"]), (0, "ok"))

    def test_missing_guard_and_non_test_db_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            laravel_fixture(Path(tmp), db="app", with_guard=False)
            code, doc = run(self.script, "--root", tmp)
        self.assertEqual((code, doc["status"]), (1, "fail"))
        self.assertTrue(any("_test" in line for line in doc["evidence"]))
        self.assertTrue(any("TestEnvironmentGuard" in line for line in doc["evidence"]))
        self.assertIn("remediation", doc)

    def test_not_a_laravel_project_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, doc = run(self.script, "--root", tmp)
        self.assertEqual((code, doc["status"]), (0, "skip"))


class DbPreflightTest(unittest.TestCase):
    def test_test_db_from_phpunit_passes_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "phpunit.xml").write_text(PHPUNIT.format(db="shop_test"), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != "TEST_DB"}
            code, doc = run(DB, "--root", tmp, env=env)
        self.assertEqual((code, doc["status"]), (0, "ok"))

    def test_non_test_db_is_a_hard_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "phpunit.xml").write_text(PHPUNIT.format(db="shop"), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != "TEST_DB"}
            code, doc = run(DB, "--root", tmp, env=env)
        self.assertEqual((code, doc["status"]), (1, "fail"))
        self.assertIn("_test", doc["observed"])

    def test_unknown_target_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "TEST_DB"}
            code, doc = run(DB, "--root", tmp, env=env)
        self.assertEqual((code, doc["status"]), (1, "fail"))


class NodePnpmPreflightTest(unittest.TestCase):
    @staticmethod
    def _bin_dir(tmp, tools):
        for tool in tools:
            path = Path(tmp, tool)
            path.write_text("#!/bin/sh\necho 1.2.3\n", encoding="utf-8")
            path.chmod(0o755)
        return tmp

    def test_both_tools_present_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, doc = run(NODE, env={"PATH": self._bin_dir(tmp, ("node", "pnpm"))})
        self.assertEqual((code, doc["status"]), (0, "ok"))

    def test_missing_pnpm_fails_with_nvm_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, doc = run(NODE, env={"PATH": self._bin_dir(tmp, ("node",))})
        self.assertEqual((code, doc["status"]), (1, "fail"))
        self.assertIn("pnpm", doc["observed"])
        self.assertIn("nvm use 22", doc["remediation"])


if __name__ == "__main__":
    unittest.main()
