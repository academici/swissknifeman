"""harness doctor --json: check-result/v1 documents, no writes, no secrets in the output."""
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

import aicore
from aicore.util import schema

PACKAGE = Path(__file__).resolve().parents[1]
HARNESS = PACKAGE / "bin" / "harness"
CONTRACT = Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"
SENTINEL = "s3cr3t-" + uuid.uuid4().hex
IDS = ["harness.environment", "harness.hooks", "harness.hooks-env", "harness.safe-dirs"]


def snapshot(*roots):
    seen = {}
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            seen[str(path)] = path.read_bytes() if path.is_file() else None
    return seen


class DoctorContractCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.home, self.skm, self.project = tmp / "home", tmp / "skm", tmp / "project"
        for path in (self.home, self.skm, self.project):
            path.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), SKM_HOME=str(self.skm), GITHUB_TOKEN=SENTINEL)

    def run_doctor(self, *args):
        return subprocess.run([str(HARNESS), "doctor", *args], cwd=self.project, env=self.env,
                              text=True, capture_output=True, check=False)

    def test_json_is_a_list_of_valid_check_results(self):
        result = self.run_doctor("--json")
        self.assertIn(result.returncode, (0, 1), result.stderr)
        documents = json.loads(result.stdout)
        self.assertEqual([d["check_id"] for d in documents], IDS)
        registry, kind = schema.load_contract(CONTRACT)
        for document in documents:
            self.assertEqual(schema.validate(document, kind, registry), [], document)

    def test_text_has_status_lines(self):
        text = self.run_doctor().stdout
        for check_id in IDS:
            self.assertRegex(text, r"(?m)^(ok|warn|fail|skip) " + check_id.replace(".", r"\.") + ": ")

    def test_stale_hooks_env_carries_a_repair(self):
        config = self.project / ".swissknifeman" / "config.toml"
        config.parent.mkdir()
        config.write_text('schema_version = 1\n[harness.hooks.plan_guard]\nmode = "strict"\n', encoding="utf-8")
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json").stdout)}
        check = by_id["harness.hooks-env"]
        self.assertEqual(check["status"], "warn")
        self.assertEqual(check["repair"]["plan"][:3], ["bin/harness", "hooks", "sync"])
        self.assertIn("--dry-run", check["repair"]["plan"])
        self.assertNotIn("--dry-run", check["repair"]["apply"])

    def test_legacy_safe_dirs_warns(self):
        legacy = self.home / ".swissknifeman" / "safe-dirs.json"
        legacy.parent.mkdir()
        legacy.write_text("{}", encoding="utf-8")
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json").stdout)}
        self.assertEqual(by_id["harness.safe-dirs"]["status"], "warn")

    def test_new_safe_dirs_with_leftover_legacy_is_not_a_wrong_location(self):
        legacy = self.home / ".swissknifeman" / "safe-dirs.json"
        legacy.parent.mkdir()
        legacy.write_text("{}", encoding="utf-8")
        current = self.skm / "config" / "harness" / "safe-dirs.json"
        current.parent.mkdir(parents=True)
        current.write_text("{}", encoding="utf-8")
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json").stdout)}
        check = by_id["harness.safe-dirs"]
        self.assertEqual(check["status"], "warn")
        self.assertNotIn("not the current location", check["observed"])
        self.assertIn("legacy", check["observed"])
        self.assertIn("Remove the legacy file", check["remediation"])

    def test_doctor_writes_nothing(self):
        config = self.project / ".swissknifeman" / "config.toml"
        config.parent.mkdir()
        config.write_text('schema_version = 1\n[harness.hooks.plan_guard]\nmode = "strict"\n', encoding="utf-8")
        before = snapshot(self.home, self.skm, self.project)
        self.run_doctor("--json")
        self.run_doctor()
        self.assertEqual(snapshot(self.home, self.skm, self.project), before)

    def test_secret_is_not_printed(self):
        (self.project / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {"github": {"command": "x", "env": {"GITHUB_TOKEN": SENTINEL}}}}), encoding="utf-8")
        for args in (("--json",), ()):
            result = self.run_doctor(*args)
            self.assertNotIn(SENTINEL, result.stdout)
            self.assertNotIn(SENTINEL, result.stderr)


if __name__ == "__main__":
    unittest.main()
