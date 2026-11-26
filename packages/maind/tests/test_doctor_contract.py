"""maind doctor --json: check-result/v1 documents, no writes, no secrets in the output."""
import contextlib
import io
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import aicore
from aicore.util import schema

from maind import doctor
from maind.doctor import cmd_doctor
from tests.fixtures import make_repo, write_maind_config

SENTINEL = "s3cr3t-" + uuid.uuid4().hex
CONTRACT = Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"
IDS = ["maind.environment", "maind.config", "maind.registry", "maind.memory", "maind.mcp", "maind.health"]


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
        self.root, self.env = make_repo(self._tmp.name)
        self.home = self.env.home
        self.skm = Path(self._tmp.name) / "skm"
        self.skm.mkdir()
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home), "SKM_HOME": str(self.skm),
                                             "AGENTMEMORY_SECRET": SENTINEL,
                                             "AGENTMEMORY_URL": "http://127.0.0.1:9"})
        patch.start()
        self.addCleanup(patch.stop)
        write_maind_config(self.root)

    def run_doctor(self, *argv):
        out = io.StringIO()
        previous = os.getcwd()
        os.chdir(self.project)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                try:
                    cmd_doctor(self.env, list(argv))
                except SystemExit:
                    pass
        finally:
            os.chdir(previous)
        return out.getvalue()

    def test_json_is_a_list_of_valid_check_results(self):
        documents = json.loads(self.run_doctor("--json"))
        self.assertEqual([d["check_id"] for d in documents], IDS)
        registry, kind = schema.load_contract(CONTRACT)
        for document in documents:
            self.assertEqual(schema.validate(document, kind, registry), [], document)

    def test_mcp_check_carries_the_tools_digest(self):
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json"))}
        evidence = by_id["maind.mcp"]["evidence"]
        self.assertTrue(any(line.startswith("tools_digest=sha256:") for line in evidence), evidence)
        self.assertTrue(any(line.startswith("protocol_versions=") for line in evidence), evidence)

    def test_legacy_node_file_warns_with_upgrade_remediation(self):
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json"))}
        self.assertEqual(by_id["maind.config"]["status"], "warn")
        self.assertIn("swissknifeman upgrade", by_id["maind.config"]["remediation"])

    def test_ignored_legacy_settings_are_not_reported_as_read(self):
        (self.skm / "config").mkdir(parents=True, exist_ok=True)
        (self.skm / "config" / "config.toml").write_text(
            'schema_version = 1\n[maind.node]\nname = "x"\n', encoding="utf-8")
        from maind import config as config_mod
        for argv in (["--json"], []):
            config_mod._warned_legacy.clear()
            self.assertNotIn("read from the legacy", self.run_doctor(*argv))
        config_mod._warned_legacy.clear()
        by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json"))}
        self.assertEqual(by_id["maind.config"]["status"], "warn")
        self.assertIn("ignored because [maind] is set", by_id["maind.config"]["observed"])

    def test_text_has_status_lines(self):
        text = self.run_doctor()
        for check_id in IDS:
            self.assertRegex(text, r"(?m)^(ok|warn|fail|skip) " + check_id.replace(".", r"\.") + ": ")

    def test_doctor_writes_nothing(self):
        before = snapshot(self.home, self.skm, self.project, self.root)
        self.run_doctor("--json")
        self.run_doctor()
        self.assertEqual(snapshot(self.home, self.skm, self.project, self.root), before)

    def test_missing_state_dir_is_not_created(self):
        self.assertFalse(self.env.state_dir.exists())
        self.run_doctor("--json")
        self.assertFalse(self.env.state_dir.exists())

    def test_secret_is_not_printed(self):
        secret_file = self.root / "secret.txt"
        secret_file.write_text(SENTINEL + "\n", encoding="utf-8")
        write_maind_config(self.root, memory={"http_port": 4111, "stream_port": 4112,
                                               "secret_file": str(secret_file)})
        self.assertNotIn(SENTINEL, self.run_doctor("--json"))
        self.assertNotIn(SENTINEL, self.run_doctor())

    def test_python_floor_comes_from_aicore(self):
        with mock.patch.object(doctor, "MIN_PYTHON", (99, 0)):
            by_id = {d["check_id"]: d for d in json.loads(self.run_doctor("--json"))}
        self.assertEqual(by_id["maind.environment"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
