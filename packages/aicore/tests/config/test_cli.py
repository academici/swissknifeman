"""The ``aicore config`` command line, in process and through ``python3 -m aicore``."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aicore import cli

from .support import FIXTURES

PACKAGE = Path(__file__).resolve().parents[2]
UNITS = FIXTURES / "units"


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.project = self.tmp / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"),
                    "SKM_UNITS_PATH": str(UNITS)}
        self.machine_file = self.tmp / "skm" / "config" / "config.toml"
        self.project_file = self.project / ".swissknifeman" / "config.toml"

    def run_cli(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(list(argv), env=env or self.env, cwd=self.project, out=out, err=err)
        return code, out.getvalue(), err.getvalue()


class TestShowExplain(CliCase):
    def test_show_defaults_and_layers(self):
        self.machine_file.parent.mkdir(parents=True)
        self.machine_file.write_text('schema_version = 1\n[demo]\nmode = "fast"\n', encoding="utf-8")
        code, out, _ = self.run_cli("config", "show", "demo")
        self.assertEqual(0, code)
        self.assertIn(f'mode = "fast"  # machine {self.machine_file}:3\n', out)
        self.assertIn("verbose = false  # defaults\n", out)
        self.assertNotIn("retries", out)  # no default, not set

    def test_show_json(self):
        code, out, _ = self.run_cli("config", "show", "demo", "--json")
        self.assertEqual(0, code)
        doc = json.loads(out)
        self.assertEqual("demo", doc["module"])
        self.assertEqual(15, doc["values"]["recompute"]["candidate_min_n"])

    def test_explain_text_and_json(self):
        self.machine_file.parent.mkdir(parents=True)
        self.machine_file.write_text("schema_version = 1\n[demo.recompute]\ncandidate_min_n = 18\n", encoding="utf-8")
        self.project_file.parent.mkdir(parents=True)
        self.project_file.write_text("schema_version = 1\n[demo.recompute]\ncandidate_min_n = 20\n", encoding="utf-8")
        code, out, _ = self.run_cli("config", "explain", "demo", "recompute.candidate_min_n")
        self.assertEqual(0, code)
        self.assertIn("recompute.candidate_min_n = 20", out)
        self.assertIn(f"from project {self.project_file}:3", out)
        self.assertIn(f"overrides machine {self.machine_file}:3 = 18", out)
        code, out, _ = self.run_cli("config", "explain", "demo", "--json")
        doc = json.loads(out)
        self.assertEqual("urn:swissknifeman:aicore:config-explain:v1", doc["$schema"])
        self.assertEqual(str(self.project), doc["project"])

    def test_env_and_config_flag_layers(self):
        extra = self.tmp / "extra.toml"
        extra.write_text('schema_version = 1\n[demo]\nmode = "fast"\n', encoding="utf-8")
        env = dict(self.env, SKM_DEMO_VERBOSE="yes")
        code, out, _ = self.run_cli("config", "show", "demo", "--config", str(extra), env=env)
        self.assertEqual(0, code)
        self.assertIn("verbose = true  # env SKM_DEMO_VERBOSE", out)
        self.assertIn(f"mode = \"fast\"  # invocation {extra}:3", out)

    def test_root_option(self):
        other = self.tmp / "other"
        (other / ".swissknifeman").mkdir(parents=True)
        (other / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[demo]\nverbose = true\n", encoding="utf-8")
        code, out, _ = self.run_cli("config", "show", "demo", "--root", str(other))
        self.assertEqual(0, code)
        self.assertIn("verbose = true  # project", out)

    def test_unknown_module_and_key(self):
        code, _, err = self.run_cli("config", "show", "nope")
        self.assertEqual(1, code)
        self.assertIn("unknown module 'nope'", err)
        self.assertIn("demo", err)
        code, _, err = self.run_cli("config", "explain", "demo", "nope.key")
        self.assertEqual(1, code)
        self.assertIn("CONFIG_UNKNOWN_KEY", err)

    def test_broken_layer_reports_file_and_line(self):
        self.machine_file.parent.mkdir(parents=True)
        self.machine_file.write_text("schema_version = 1\n[demo]\nmode = 5\n", encoding="utf-8")
        code, _, err = self.run_cli("config", "show", "demo")
        self.assertEqual(1, code)
        self.assertIn(f"{self.machine_file}:3", err)
        self.assertIn("CONFIG_TYPE", err)


class TestSetUnset(CliCase):
    def test_set_creates_machine_file(self):
        code, out, _ = self.run_cli("config", "set", "demo.recompute.candidate_min_n", "25", "--machine")
        self.assertEqual(0, code)
        self.assertIn("set demo.recompute.candidate_min_n", out)
        text = self.machine_file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("schema_version = 1\n"))
        self.assertIn("candidate_min_n = 25", text)
        code, out, _ = self.run_cli("config", "show", "demo")
        self.assertIn("recompute.candidate_min_n = 25  # machine", out)

    def test_set_project_keeps_comments_and_backs_up(self):
        self.project_file.parent.mkdir(parents=True)
        original = '# mine\nschema_version = 1\n\n[demo]\nmode = "safe"  # keep\n'
        self.project_file.write_text(original, encoding="utf-8")
        code, out, _ = self.run_cli("config", "set", "demo.mode", "fast", "--project")
        self.assertEqual(0, code)
        text = self.project_file.read_text(encoding="utf-8")
        self.assertIn('mode = "fast"  # keep', text)
        self.assertTrue(text.startswith("# mine\n"))
        backups = list((self.project / ".swissknifeman" / "backups").rglob("config.toml"))
        self.assertEqual(1, len(backups))
        self.assertEqual(original, backups[0].read_text(encoding="utf-8"))

    def test_set_rejects_bad_values_without_writing(self):
        for key, value in (("recompute.candidate_min_n", "abc"), ("recompute.candidate_min_n", "0"),
                           ("mode", "turbo"), ("verbose", "maybe"), ("nope", "1")):
            code, _, err = self.run_cli("config", "set", f"demo.{key}", value, "--machine")
            self.assertEqual(1, code, (key, value))
            self.assertIn("CONFIG_", err)
        self.assertFalse(self.machine_file.exists())

    def test_set_forbidden_layer(self):
        code, _, err = self.run_cli("config", "set", "demo.cache_dir", "/x", "--project")
        self.assertEqual(1, code)
        self.assertIn("CONFIG_LAYER_FORBIDDEN", err)

    def test_set_secret_needs_reference_and_never_echoes(self):
        code, out, err = self.run_cli("config", "set", "demo.token", "hunter2", "--machine")
        self.assertEqual(1, code)
        self.assertNotIn("hunter2", out + err)
        code, out, err = self.run_cli("config", "set", "demo.token", "env://DEMO_TOKEN", "--machine")
        self.assertEqual(0, code)
        self.assertNotIn("env://DEMO_TOKEN", out)

    def test_set_array_by_json_and_unchanged_value(self):
        code, _, _ = self.run_cli("config", "set", "demo.sources", '["a", "b"]', "--machine")
        self.assertEqual(0, code)
        code, out, _ = self.run_cli("config", "set", "demo.sources", '["a", "b"]', "--machine")
        self.assertEqual(0, code)
        self.assertIn("already has this value", out)

    def test_unset_removes_line(self):
        self.run_cli("config", "set", "demo.mode", "fast", "--machine")
        code, out, _ = self.run_cli("config", "unset", "demo.mode", "--machine")
        self.assertEqual(0, code)
        self.assertNotIn("mode", self.machine_file.read_text(encoding="utf-8"))
        code, out, _ = self.run_cli("config", "unset", "demo.mode", "--machine")
        self.assertEqual(0, code)
        self.assertIn("already unset", out)

    def test_set_json_output(self):
        code, out, _ = self.run_cli("config", "set", "demo.mode", "fast", "--machine", "--json")
        doc = json.loads(out)
        self.assertEqual((0, True, "machine"), (code, doc["changed"], doc["layer"]))

    def test_usage_errors(self):
        for argv in (("config", "set", "demo.mode", "fast"),  # no layer
                     ("config", "set", "demo.mode", "fast", "--machine", "--project"),
                     ("config", "set", "demo", "x", "--machine"),  # no key
                     ("config", "bogus"), ("config",), ("nope",), ()):
            code, _, _ = self.run_cli(*argv)
            self.assertEqual(2, code, argv)


class TestInit(CliCase):
    def test_init_machine_all_modules(self):
        code, out, _ = self.run_cli("config", "init", "--machine")
        self.assertEqual(0, code)
        text = self.machine_file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("schema_version = 1\n"))
        self.assertEqual(1, text.count("schema_version"))
        self.assertIn("[demo.recompute]", text)
        self.assertIn("# candidate_min_n = 15", text)
        code, _, _ = self.run_cli("config", "show", "demo")
        self.assertEqual(0, code)  # the generated file is a valid layer

    def test_init_refuses_existing_without_force(self):
        self.project_file.parent.mkdir(parents=True)
        self.project_file.write_text("schema_version = 1\n# mine\n", encoding="utf-8")
        code, _, err = self.run_cli("config", "init", "--project")
        self.assertEqual(1, code)
        self.assertIn("--force", err)
        self.assertEqual("schema_version = 1\n# mine\n", self.project_file.read_text(encoding="utf-8"))

    def test_init_force_backs_up(self):
        self.project_file.parent.mkdir(parents=True)
        self.project_file.write_text("schema_version = 1\n# mine\n", encoding="utf-8")
        code, _, _ = self.run_cli("config", "init", "--project", "--force", "--module", "demo")
        self.assertEqual(0, code)
        self.assertIn("[demo]", self.project_file.read_text(encoding="utf-8"))
        saved = list((self.project / ".swissknifeman" / "backups").rglob("config.toml"))
        self.assertEqual("schema_version = 1\n# mine\n", saved[0].read_text(encoding="utf-8"))

    def test_init_unknown_module_or_none_found(self):
        code, _, err = self.run_cli("config", "init", "--machine", "--module", "nope")
        self.assertEqual(1, code)
        self.assertFalse(self.machine_file.exists())
        code, _, err = self.run_cli("config", "init", "--machine", env=dict(self.env, SKM_UNITS_PATH=str(self.tmp)))
        self.assertEqual(1, code)
        self.assertIn("no module", err)


class TestExample(CliCase):
    def setUp(self):
        super().setUp()
        self.unit = self.tmp / "demo"
        shutil.copytree(UNITS / "demo", self.unit)

    def test_print_write_check(self):
        code, out, _ = self.run_cli("config", "example", str(self.unit))
        self.assertEqual(0, code)
        self.assertTrue(out.startswith("# demo configuration"))
        code, _, err = self.run_cli("config", "example", str(self.unit), "--check")
        self.assertEqual((1, True), (code, "--write" in err))  # no file yet
        code, _, _ = self.run_cli("config", "example", str(self.unit), "--write")
        self.assertEqual(0, code)
        self.assertEqual(out, (self.unit / "config.example.toml").read_text(encoding="utf-8"))
        code, _, _ = self.run_cli("config", "example", str(self.unit), "--check")
        self.assertEqual(0, code)
        (self.unit / "config.example.toml").write_text(out.replace("= 15", "= 16"), encoding="utf-8")
        code, diff, _ = self.run_cli("config", "example", str(self.unit), "--check")
        self.assertEqual(1, code)
        self.assertIn("-# candidate_min_n = 16", diff)
        self.assertIn("+# candidate_min_n = 15", diff)

    def test_unit_without_config(self):
        code, _, err = self.run_cli("config", "example", str(UNITS / "plain"))
        self.assertEqual(1, code)
        self.assertIn("provides.config", err)

    def test_write_and_check_exclude_each_other(self):
        code, _, _ = self.run_cli("config", "example", str(self.unit), "--write", "--check")
        self.assertEqual(2, code)


class TestPaths(CliCase):
    def test_json_and_text(self):
        code, out, _ = self.run_cli("config", "paths", "--json")
        doc = json.loads(out)
        self.assertEqual(0, code)
        self.assertTrue(doc["isolated"])
        self.assertEqual(str(self.tmp / "skm" / "state"), doc["state"])
        self.assertEqual(str(self.machine_file), doc["machine_config_file"])
        self.assertEqual(str(self.project), doc["project"]["root"])
        self.assertEqual(str(self.project_file), doc["project"]["config_file"])
        code, out, _ = self.run_cli("config", "paths")
        self.assertIn(f"state: {self.tmp / 'skm' / 'state'}", out)
        self.assertIn("isolated: true", out)

    def test_relative_skm_home_is_an_error(self):
        code, _, err = self.run_cli("config", "paths", env=dict(self.env, SKM_HOME="rel"))
        self.assertEqual(1, code)
        self.assertIn("SKM_HOME", err)


class TestLauncher(CliCase):
    """The shipped bin/aicore and ``python3 -m aicore`` in a throwaway environment."""

    def launch(self, *argv):
        env = {"PATH": os.environ["PATH"], **self.env}
        return subprocess.run([str(PACKAGE / "bin" / "aicore"), *argv], env=env, cwd=str(self.project),
                              capture_output=True, text=True)

    def test_launcher_is_executable_and_runs(self):
        self.assertTrue(os.access(PACKAGE / "bin" / "aicore", os.X_OK))
        result = self.launch("config", "paths", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["isolated"])

    def test_help_and_exit_codes(self):
        self.assertEqual(0, self.launch("config", "--help").returncode)
        self.assertEqual(0, self.launch("--help").returncode)
        self.assertEqual(2, self.launch("bogus").returncode)
        self.assertEqual(2, self.launch("config", "bogus").returncode)

    def test_module_entry_point(self):
        env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(PACKAGE / "lib"), **self.env}
        result = subprocess.run([sys.executable, "-m", "aicore", "config", "show", "demo", "--json"],
                                env=env, cwd=str(self.project), capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("demo", json.loads(result.stdout)["module"])


if __name__ == "__main__":
    unittest.main()
