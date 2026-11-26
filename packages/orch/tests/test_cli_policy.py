from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from orch.cli import main

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ["frontend-bounded", "full", "review-only", "scout-solo", "solo"]


class PolicyCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        (self.home / "skm").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.cwd)

    def run_cli(self, *argv: str) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def config(self, text: str) -> str:
        path = self.root / "invocation.toml"
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return str(path)

    def external_pack(self, name: str = "custom") -> Path:
        base = self.root / "packs"
        shutil.copytree(ROOT / "configs" / "run-policies" / "solo", base / name)
        path = base / name / "policy.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["policy_id"] = name
        path.write_text(json.dumps(document), encoding="utf-8")
        return base


class ListShowTests(PolicyCliCase):
    def test_list_json(self):
        code, out, err = self.run_cli("policy", "list", "--json")
        self.assertEqual((code, err), (0, ""))
        rows = json.loads(out)
        self.assertEqual([r["policy_id"] for r in rows], SHIPPED)
        self.assertTrue(all(r["source"] == "shipped" and r["cases"] >= 2 for r in rows))
        self.assertEqual({r["policy_id"]: r["version"] for r in rows if r["version"] != "1.0.0"}, {"full": "1.1.0"})

    def test_list_text(self):
        code, out, _ = self.run_cli("policy", "list")
        self.assertEqual(code, 0)
        self.assertEqual([line.split("\t")[0] for line in out.splitlines()], SHIPPED)

    def test_show_prints_the_policy(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                code, out, _ = self.run_cli("policy", "show", name)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["policy_id"], name)

    def test_show_of_an_unknown_id_exits_1(self):
        code, out, err = self.run_cli("policy", "show", "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("POLICY_UNKNOWN: "))


class ConfigTests(PolicyCliCase):
    def test_the_config_file_adds_a_pack_folder(self):
        base = self.external_pack()
        code, out, _ = self.run_cli("--config", self.config(f'[orch.profiles]\ndirs = ["{base}"]\n'), "policy", "show",
                                    "custom")
        self.assertEqual((code, json.loads(out)["policy_id"]), (0, "custom"))

    def test_a_shadowed_pack_is_reported_on_stderr(self):
        base = self.external_pack("solo")
        code, out, err = self.run_cli("--config", self.config(f'[orch.profiles]\ndirs = ["{base}"]\n'), "policy",
                                      "list", "--json")
        self.assertEqual(code, 0)
        self.assertIn("POLICY_SHADOWED: solo in ", err)
        self.assertEqual(sorted(r["policy_id"] for r in json.loads(out)), SHIPPED)

    def test_profile_folders_from_the_project_file_are_refused(self):
        (self.root / ".swissknifeman").mkdir()
        (self.root / ".swissknifeman" / "config.toml").write_text(
            'schema_version = 1\n[orch.profiles]\ndirs = ["/tmp/elsewhere"]\n', encoding="utf-8")
        code, out, err = self.run_cli("policy", "list")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("CONFIG_LAYER_FORBIDDEN", err)

    def test_a_relative_pack_folder_is_an_error(self):
        code, out, err = self.run_cli("--config", self.config('[orch.profiles]\ndirs = ["packs"]\n'), "policy", "list")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("PROFILES_DIR_RELATIVE: "))

    def test_a_missing_config_file_is_an_error(self):
        code, _, err = self.run_cli("--config", str(self.root / "absent.toml"), "policy", "list")
        self.assertEqual(code, 1)
        self.assertIn("CONFIG_FILE_INVALID", err)


class TestVerbTests(PolicyCliCase):
    def test_all_shipped_cases_pass(self):
        code, out, err = self.run_cli("policy", "test")
        self.assertEqual((code, err), (0, ""))
        lines = [line.split("\t") for line in out.splitlines()]
        self.assertEqual({line[0] for line in lines}, {"PASS"})
        self.assertEqual(sorted({line[1] for line in lines}), SHIPPED)

    def test_one_policy_json(self):
        code, out, _ = self.run_cli("policy", "test", "solo", "--json")
        rows = json.loads(out)
        self.assertEqual((code, {r["policy_id"] for r in rows}, {r["status"] for r in rows}), (0, {"solo"}, {"pass"}))

    def test_a_failing_case_exits_1_and_says_why(self):
        base = self.external_pack()
        case = {"input": "fixtures/exec/v1/valid/execution-input/plan-bound.json", "provider": "claude-code",
                "expect": {"result": "refused"}}
        (base / "custom" / "cases").mkdir(exist_ok=True)
        (base / "custom" / "cases" / "wrong.json").write_text(json.dumps(case), encoding="utf-8")
        code, out, err = self.run_cli("--config", self.config(f'[orch.profiles]\ndirs = ["{base}"]\n'), "policy",
                                      "test", "custom")
        self.assertEqual(code, 1)
        self.assertIn("FAIL\tcustom\twrong", out)
        self.assertIn('result: expected "refused", got "ok"', err)

    def test_an_unknown_id_exits_1(self):
        code, _, err = self.run_cli("policy", "test", "nope")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("POLICY_UNKNOWN: "))


if __name__ == "__main__":
    unittest.main()
