#!/usr/bin/env python3
"""Tests of the umbrella CLI (scripts/umbrella.py): routing by unit.json, aliases as data, units, version (stdlib).

Modules are fake folders in a temporary hub; nothing runs with the real HOME.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "aicore" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))
import umbrella  # noqa: E402

UMBRELLA = ROOT / "scripts" / "umbrella.py"


def make_unit(packages: Path, unit_id: str, cli=None, kind="capability", doctor=False, extra=None) -> Path:
    folder = packages / unit_id
    (folder / "bin").mkdir(parents=True)
    provides = dict(extra or {})
    if cli:
        provides["cli"] = cli
        for entry in cli:
            path = folder / entry
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"#!/bin/sh\necho \"{unit_id}:$*\"\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
    if doctor:
        provides["doctor"] = [{"id": f"{unit_id}.environment", "category": "environment",
                               "probe": [cli[0], "doctor"], "output": "text"}]
    doc = {"$schema": "urn:swissknifeman:aicore:unit:v1", "id": unit_id, "title": f"Fake {unit_id}", "kind": kind,
           "version": "1.2.3", "stability": "alpha", "destination": "hub", "requires": [], "provides": provides}
    (folder / "unit.json").write_text(json.dumps(doc), encoding="utf-8")
    return folder


class Hub:
    """A temporary hub: packages/ with fake modules, an environment for discovery."""

    def __init__(self, ids=("skiller", "harness", "maind", "analyst", "aicore")):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.home = base / "home"
        self.home.mkdir()
        self.packages = base / "packages"
        self.packages.mkdir()
        for unit_id in ids:
            make_unit(self.packages, unit_id, [f"bin/{unit_id}"], doctor=True)
        self.env = {**os.environ, "HOME": str(self.home), "SKM_HOME": str(base / "skm"),
                    "SKM_UNITS_PATH": str(self.packages), "PYTHONPATH": str(ROOT / "packages" / "aicore" / "lib")}

    def close(self):
        self._tmp.cleanup()

    def run(self, *argv):
        return subprocess.run([sys.executable, str(UMBRELLA), *argv], env=self.env, capture_output=True,
                              text=True, check=False)


class RouteCase(unittest.TestCase):
    def setUp(self):
        self.hub = Hub()
        self.addCleanup(self.hub.close)
        self.units = umbrella.load_units(self.hub.env)

    def exec_of(self, *argv):
        """(head path, rest) of what route() would exec."""
        with mock.patch.object(umbrella.os, "execv", side_effect=lambda path, args: None) as execv:
            umbrella.route(list(argv), self.units, umbrella.load_config())
        self.assertEqual(1, execv.call_count, argv)
        _, args = execv.call_args[0]
        return args

    def unit_cli(self, unit_id):
        return str(umbrella.cli_of(self.units[unit_id]))


class TestLegacyGroups(RouteCase):
    """Every group of the former help gives the same exec as the bash launcher did."""

    def test_groups(self):
        script = lambda name: str(ROOT / "scripts" / name)  # noqa: E731
        cases = [
            (["skills", "list"], "skiller", ["list"]),
            (["skills"], "skiller", []),
            (["env", "mcp", "x"], "harness", ["mcp", "x"]),
            (["wf", "status"], "harness", ["wf", "status"]),
            (["release", "--dry-run"], "skiller", ["release", "--dry-run"]),
            (["maind", "health"], "maind", ["health"]),
            (["hub", "health"], "maind", ["health"]),
            (["analyst", "digest"], "analyst", ["digest"]),
            (["config", "show"], "aicore", ["config", "show"]),
            (["setup", "proj"], "maind", ["onboard", "proj"]),
            (["setup"], "maind", ["onboard"]),
            (["status"], "skiller", ["status"]),
            (["status", "--json"], "skiller", ["status", "--json"]),
            (["status", "--target", "x"], "skiller", ["status", "--target", "x"]),
            (["status", "--all"], "maind", ["projects", "status", "--all"]),
            (["status", "--namespace", "n"], "maind", ["projects", "status", "--namespace", "n"]),
            (["status", "--project", "p"], "maind", ["projects", "status", "--project", "p"]),
            (["status", "proj", "--json"], "maind", ["projects", "status", "--project", "proj", "--json"]),
        ]
        for verb in ("connect", "vendor", "integrate", "update", "init", "sync", "lock", "list", "registry", "topology"):
            cases.append(([verb, "a", "--b"], "skiller", [verb, "a", "--b"]))
        for argv, unit_id, rest in cases:
            with self.subTest(argv=argv):
                self.assertEqual([self.unit_cli(unit_id), *rest], self.exec_of(*argv))
        scripts = [
            (["release-fleet", "--x"], "release-fleet.sh", ["--x"]),
            (["setup", "--machine", "--dry-run"], "bootstrap-machine.sh", ["--dry-run"]),
        ]
        for argv, name, rest in scripts:
            with self.subTest(argv=argv):
                self.assertEqual([script(name), *rest], self.exec_of(*argv))

    def test_doctor_fan_out_argv_and_order(self):
        for extra in ("brain", "orch"):
            make_unit(self.hub.packages, extra, [f"bin/{extra}"], doctor=True)
        units = umbrella.load_units(self.hub.env)
        with mock.patch.object(umbrella.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(0, umbrella.doctor_command(units, umbrella.load_config()))
        calls = [c.args[0] for c in run.call_args_list]
        self.assertEqual([[self.unit_cli(i), "doctor"] for i in ("skiller", "harness", "maind", "analyst")], calls)

    def test_every_alias_of_the_config_is_covered(self):
        covered = {"skills", "env", "wf", "release", "release-fleet", "hub", "config", "setup", "status", "connect",
                   "vendor", "integrate", "update", "init", "sync", "lock", "list", "registry", "topology"}
        self.assertEqual(covered, set(umbrella.load_config()["aliases"]))

    def test_help_lists_the_former_groups(self):
        text = umbrella.help_text(self.units, umbrella.load_config())
        for word in ("skills", "env", "wf", "release", "release-fleet", "hub", "config", "setup", "status", "doctor",
                     "units", "--version"):
            self.assertIn(word, text)


class TestModuleGroups(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(ids=("alpha", "beta"))
        self.addCleanup(self.hub.close)

    def test_group_by_unit_id(self):
        result = self.hub.run("alpha", "one", "two")
        self.assertEqual((0, "alpha:one two\n"), (result.returncode, result.stdout))
        self.assertEqual("beta:\n", self.hub.run("beta").stdout)

    def test_new_module_appears_without_code_change(self):
        self.assertEqual(1, self.hub.run("gamma").returncode)
        make_unit(self.hub.packages, "gamma", ["bin/gamma"])
        result = self.hub.run("gamma", "x")
        self.assertEqual((0, "gamma:x\n"), (result.returncode, result.stdout))
        self.assertIn("gamma", self.hub.run("help").stdout)

    def test_cli_path_is_the_first_provides_cli_entry(self):
        make_unit(self.hub.packages, "delta", ["scripts/delta.sh", "scripts/other.sh"])
        self.assertEqual("delta:q\n", self.hub.run("delta", "q").stdout)

    def test_python_cli_without_exec_bit_runs_through_the_interpreter(self):
        folder = make_unit(self.hub.packages, "pyu", ["scripts/pyu.py"])
        (folder / "scripts" / "pyu.py").write_text("import sys\nprint('py', *sys.argv[1:])\n", encoding="utf-8")
        (folder / "scripts" / "pyu.py").chmod(0o644)
        self.assertEqual("py a b\n", self.hub.run("pyu", "a", "b").stdout)

    def test_bridge_is_not_a_group_but_is_listed(self):
        make_unit(self.hub.packages, "br", ["helper.py"], kind="bridge")
        self.assertEqual(1, self.hub.run("br").returncode)
        listed = {u["id"]: u for u in json.loads(self.hub.run("units", "--json").stdout)["units"]}
        self.assertEqual("bridge", listed["br"]["kind"])

    def test_unknown_command(self):
        result = self.hub.run("no-such-subcommand")
        self.assertEqual((1, ""), (result.returncode, result.stdout))
        self.assertTrue(result.stderr.startswith("Unknown command: no-such-subcommand\n"))
        self.assertIn("Usage:", result.stderr)

    def test_missing_launcher(self):
        (self.hub.packages / "alpha" / "bin" / "alpha").unlink()
        result = self.hub.run("alpha")
        self.assertEqual(1, result.returncode)
        self.assertIn("launcher not found", result.stderr)

    def test_doctor_fan_out_reports_missing_launcher(self):
        result = self.hub.run("doctor")
        self.assertEqual(1, result.returncode)
        self.assertIn("== skiller ==", result.stdout)
        self.assertIn("launcher not found", result.stderr)


class TestUnits(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(ids=("alpha", "beta"))
        self.addCleanup(self.hub.close)
        make_unit(self.hub.packages, "gamma", ["bin/gamma"], extra={
            "plugins": [{"name": "gp", "manifest": ".claude-plugin/plugin.json"}], "install": ["install.sh"]})

    def test_list_text(self):
        lines = self.hub.run("units").stdout.splitlines()
        self.assertEqual("alpha capability 1.2.3 alpha hub bin/alpha", lines[0])
        self.assertEqual(["alpha", "beta", "gamma"], [line.split()[0] for line in lines])
        self.assertEqual(lines, self.hub.run("units", "list").stdout.splitlines())

    def test_json_follows_the_schema(self):
        doc = json.loads(self.hub.run("units", "--json").stdout)
        self.assertEqual("umbrella-units/v1", doc["schema"])
        schema = json.loads((ROOT / "configs" / "schemas" / "umbrella-units.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("umbrella-units/v1", schema["properties"]["schema"]["const"])
        item = schema["properties"]["units"]["items"]
        for row in doc["units"]:
            self.assertEqual(set(item["properties"]), set(row))
            self.assertEqual(set(item["required"]), set(row))
        gamma = {row["id"]: row for row in doc["units"]}["gamma"]
        self.assertEqual((["bin/gamma"], ["gp"], 0, True), (gamma["cli"], gamma["plugins"], gamma["doctor"], gamma["install"]))
        alpha = {row["id"]: row for row in doc["units"]}["alpha"]
        self.assertEqual((1, False), (alpha["doctor"], alpha["install"]))

    def test_show(self):
        result = self.hub.run("units", "show", "alpha", "--json")
        self.assertEqual(0, result.returncode)
        self.assertEqual("alpha", json.loads(result.stdout)["id"])

    def test_show_unknown(self):
        result = self.hub.run("units", "show", "nope")
        self.assertEqual(2, result.returncode)
        self.assertIn("UNIT_UNKNOWN", result.stderr)

    def test_real_hub_lists_bridges(self):
        env = {**os.environ, "HOME": tempfile.mkdtemp(), "PYTHONPATH": str(ROOT / "packages" / "aicore" / "lib")}
        env.pop("SKM_UNITS_PATH", None)
        out = subprocess.run([sys.executable, str(UMBRELLA), "units", "--json"], env=env, capture_output=True,
                             text=True, check=True).stdout
        kinds = {row["id"]: row["kind"] for row in json.loads(out)["units"]}
        self.assertIn("bridge", set(kinds.values()))


class TestVersion(unittest.TestCase):
    def test_version_word_forms(self):
        for word in ("-V", "--version", "version"):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, umbrella.route([word], {}, {}))
            self.assertTrue(out.getvalue().startswith("swissknifeman "), word)

    def test_fallback_to_the_configured_file(self):
        failed = subprocess.CompletedProcess([], 128, "", "fatal")
        with mock.patch.object(umbrella.subprocess, "run", return_value=failed):
            self.assertRegex(umbrella.version(), r"^\d+\.\d+\.\d+")

    def test_git_describe_wins(self):
        done = subprocess.CompletedProcess([], 0, "v9.9.9-1-gabc\n", "")
        with mock.patch.object(umbrella.subprocess, "run", return_value=done):
            self.assertEqual("v9.9.9-1-gabc", umbrella.version())


class TestSources(unittest.TestCase):
    def test_no_module_ids_in_the_umbrella_source(self):
        text = "\n".join(line for line in (ROOT / "scripts" / "umbrella.py").read_text(encoding="utf-8").splitlines()
                         if not re.match(r"\s*(from|import) aicore", line))  # the foundation is imported, not routed
        ids = sorted(path.parent.name for path in (ROOT / "packages").glob("*/unit.json"))
        self.assertGreaterEqual(len(ids), 8)
        found = [i for i in ids if re.search(r"(?<![A-Za-z0-9_-])" + re.escape(i) + r"(?![A-Za-z0-9_-])", text)]
        self.assertEqual([], found)

    def test_config_shape(self):
        config = json.loads((ROOT / "configs" / "umbrella.json").read_text(encoding="utf-8"))
        self.assertEqual("umbrella-config/v1", config["schema"])
        for name, alias in config["aliases"].items():
            for route in alias["routes"]:
                with self.subTest(alias=name):
                    self.assertEqual(1, len({"unit", "script"} & set(route)))
                    if "script" in route:
                        self.assertTrue((ROOT / route["script"]).is_file())

    def test_config_matches_umbrella_schema(self):
        schema = json.loads((ROOT / "configs" / "umbrella.schema.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / "configs" / "umbrella.json").read_text(encoding="utf-8"))
        self.assertLessEqual(set(config), set(schema["properties"]))
        self.assertTrue(set(schema["required"]) <= set(config))
        route = schema["$defs"]["route"]["properties"]
        for name, alias in config["aliases"].items():
            self.assertLessEqual(set(alias), set(schema["properties"]["aliases"]["additionalProperties"]["properties"]))
            for item in alias["routes"]:
                with self.subTest(alias=name):
                    self.assertLessEqual(set(item), set(route))
                    self.assertLessEqual(set(item.get("when", {})), set(route["when"]["properties"]))

    def test_launcher_is_thin(self):
        text = (ROOT / "bin" / "swissknifeman").read_text(encoding="utf-8")
        self.assertIn('exec python3 "$ROOT/scripts/umbrella.py" "$@"', text)
        self.assertLess(text.index("dev-clone guard"), text.index("exec python3"))
        self.assertLess(len(text.splitlines()), 30)

    def test_launcher_end_to_end_in_a_temporary_home(self):
        home = tempfile.mkdtemp()
        env = {**os.environ, "HOME": home, "SKM_HOME": home + "/skm"}
        env.pop("SKM_UNITS_PATH", None)
        result = subprocess.run([str(ROOT / "bin" / "swissknifeman"), "help"], env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Built-in:", result.stdout)
        guarded = subprocess.run([str(ROOT / "bin" / "swissknifeman"), "help"],
                                 env={**env, "HOME": str(Path(os.path.expanduser("~")))}, capture_output=True, text=True)
        if (ROOT / ".swissknifeman-dev").exists() and os.environ.get("SKM_DEV_ALLOW_LIVE") != "1":
            self.assertEqual(3, guarded.returncode)


if __name__ == "__main__":
    unittest.main()
