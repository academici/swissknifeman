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
    """``doctor`` is True (one text check) or a list of provides.doctor entries."""
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
    if isinstance(doctor, list):
        provides["doctor"] = doctor
    elif doctor:
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


def check(check_id, status="ok", category="environment", observed="fine", **extra):
    return {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": check_id, "status": status,
            "category": category, "observed": observed, **extra}


def probe_unit(hub: "Hub", unit_id: str, body: str, ids, categories=None) -> Path:
    """A module whose probe ``bin/<id> doctor`` runs a python ``body``; ``ids`` are the declared check ids."""
    folder = make_unit(hub.packages, unit_id, [f"bin/{unit_id}"], doctor=[
        {"id": check_id, "category": (categories or {}).get(check_id, "environment"),
         "probe": [f"bin/{unit_id}", "doctor"], "output": "check-result/v1"} for check_id in ids])
    (folder / "bin" / unit_id).write_text(f"#!/usr/bin/env python3\nimport json, sys, time\n{body}\n", encoding="utf-8")
    return folder


def snapshot(*roots: Path):
    state = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                state[str(path)] = (path.stat().st_mtime_ns, path.read_bytes())
    return state


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(ids=())
        self.addCleanup(self.hub.close)

    def json(self, *args):
        result = self.hub.run("doctor", "--json", *args)
        return result.returncode, json.loads(result.stdout)

    def test_ok_and_warn_exit_zero_and_follow_the_schema(self):
        rows = [check("good.one"), check("good.two", "warn", "config", "meh", remediation="fix it")]
        probe_unit(self.hub, "good", f"print(json.dumps({rows!r}))", ["good.one", "good.two"])
        rc, doc = self.json()
        self.assertEqual(0, rc)
        self.assertEqual("umbrella-doctor/v1", doc["schema"])
        self.assertEqual([("good.one", "ok", "good"), ("good.two", "warn", "good")],
                         [(r["check_id"], r["status"], r["unit"]) for r in doc["results"]])
        schema = json.loads((ROOT / "configs" / "schemas" / "umbrella-doctor.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("umbrella-doctor/v1", schema["properties"]["schema"]["const"])
        item = schema["properties"]["results"]["items"]
        for row in doc["results"]:
            self.assertLessEqual(set(row), set(item["properties"]))
            self.assertTrue(set(item["required"]) <= set(row))
        self.assertEqual(set(schema["required"]), set(doc))

    def test_single_object_output_is_accepted(self):
        probe_unit(self.hub, "solo", f"print(json.dumps({check('solo.one')!r}))", ["solo.one"])
        rc, doc = self.json()
        self.assertEqual((0, ["solo.one"]), (rc, [r["check_id"] for r in doc["results"]]))

    def test_shared_probe_runs_once(self):
        log = self.hub.home / "runs.log"
        rows = [check("many.a"), check("many.b"), check("many.c")]
        probe_unit(self.hub, "many", f"open({str(log)!r}, 'a').write('x')\nprint(json.dumps({rows!r}))",
                   ["many.a", "many.b", "many.c"])
        rc, doc = self.json()
        self.assertEqual(3, len(doc["results"]))
        self.assertEqual("x", log.read_text())

    def test_declared_id_without_result_is_a_synthetic_fail(self):
        probe_unit(self.hub, "gap", f"print(json.dumps([{check('gap.one')!r}]))", ["gap.one", "gap.two"])
        rc, doc = self.json()
        self.assertEqual(1, rc)
        by_id = {r["check_id"]: r for r in doc["results"]}
        self.assertEqual("ok", by_id["gap.one"]["status"])
        self.assertEqual(("fail", "probe printed no result for this check"),
                         (by_id["gap.two"]["status"], by_id["gap.two"]["observed"]))
        self.assertIn("bin/gap doctor", by_id["gap.two"]["remediation"])

    def test_undeclared_foreign_result_is_dropped(self):
        rows = [check("other.thing"), check("keep.extra"), check("keep.one")]
        probe_unit(self.hub, "keep", f"print(json.dumps({rows!r}))", ["keep.one"])
        _, doc = self.json()
        self.assertEqual(["keep.extra", "keep.one"], sorted(r["check_id"] for r in doc["results"]))

    def test_invalid_json_and_schema_violation_and_crash(self):
        probe_unit(self.hub, "junk", "print('not json at all')", ["junk.one"])
        probe_unit(self.hub, "badshape", "print(json.dumps([{'check_id': 'badshape.one', 'status': 'great'}]))", ["badshape.one"])
        probe_unit(self.hub, "crash", "sys.stderr.write('boom\\n'); sys.exit(3)", ["crash.one"])
        rc, doc = self.json()
        self.assertEqual(1, rc)
        by_id = {r["check_id"]: r for r in doc["results"]}
        self.assertEqual({"junk.doctor", "badshape.doctor", "crash.doctor"}, set(by_id))
        for row in by_id.values():
            self.assertEqual("fail", row["status"])
        self.assertIn("not JSON", by_id["junk.doctor"]["observed"])
        self.assertIn("check-result/v1", by_id["badshape.doctor"]["observed"])
        self.assertIn("boom", by_id["crash.doctor"]["observed"])

    def test_timeout_gives_a_synthetic_fail_and_does_not_hang(self):
        probe_unit(self.hub, "slow", "time.sleep(30)", ["slow.one"])
        probe_unit(self.hub, "fast", f"print(json.dumps([{check('fast.one')!r}]))", ["fast.one"])
        rc, doc = self.json("--timeout", "1")
        self.assertEqual(1, rc)
        by_id = {r["check_id"]: r for r in doc["results"]}
        self.assertEqual("fail", by_id["slow.doctor"]["status"])
        self.assertIn("timed out", by_id["slow.doctor"]["observed"])
        self.assertEqual("ok", by_id["fast.one"]["status"])

    def test_units_without_doctor_are_listed(self):
        make_unit(self.hub.packages, "plain", ["bin/plain"])
        probe_unit(self.hub, "good", f"print(json.dumps([{check('good.one')!r}]))", ["good.one"])
        _, doc = self.json()
        self.assertEqual(["plain"], doc["units_without_doctor"])
        text = self.hub.run("doctor")
        self.assertEqual(0, text.returncode)
        self.assertIn("info plain: no doctor checks declared", text.stdout)
        self.assertIn("ok good.one: fine", text.stdout)
        self.assertIn("1 ok, 0 warn, 0 fail", text.stdout)

    def test_text_prints_remediation_and_exit_one_on_fail(self):
        rows = [check("bad.one", "fail", "state", "broken", remediation="run the repair")]
        probe_unit(self.hub, "bad", f"print(json.dumps({rows!r}))", ["bad.one"])
        result = self.hub.run("doctor")
        self.assertEqual(1, result.returncode)
        self.assertIn("fail bad.one: broken", result.stdout)
        self.assertIn("bad.one: run the repair", result.stdout)

    def test_unit_and_category_filters(self):
        log = self.hub.home / "runs.log"
        for name in ("aa", "bb"):
            rows = [check(f"{name}.env"), check(f"{name}.cfg", category="config")]
            probe_unit(self.hub, name, f"open({str(log)!r}, 'a').write({name!r})\nprint(json.dumps({rows!r}))",
                       [f"{name}.env", f"{name}.cfg"], {f"{name}.cfg": "config"})
        _, doc = self.json("--unit", "aa", "--category", "config")
        self.assertEqual(["aa.cfg"], [r["check_id"] for r in doc["results"]])
        self.assertEqual("aa", log.read_text())
        self.assertEqual(["bb"], self.json("--unit=bb")[1]["results"][0]["unit"] and ["bb"])

    def test_usage_errors_exit_two(self):
        probe_unit(self.hub, "good", "print('[]')", [])
        for args in (["--unit", "nope"], ["--category", "x"], ["--timeout", "abc"], ["--timeout", "0"], ["--bogus"],
                     ["--unit"]):
            with self.subTest(args=args):
                result = self.hub.run("doctor", *args)
                self.assertEqual(2, result.returncode)
                self.assertEqual("", result.stdout)

    def test_doctor_writes_nothing(self):
        rows = [check("good.one")]
        probe_unit(self.hub, "good", f"print(json.dumps({rows!r}))", ["good.one"])
        make_unit(self.hub.packages, "plain", ["bin/plain"])
        before = snapshot(self.hub.home, self.hub.packages)
        self.assertEqual(0, self.hub.run("doctor").returncode)
        self.assertEqual(0, self.hub.run("doctor", "--json").returncode)
        self.assertEqual(before, snapshot(self.hub.home, self.hub.packages))
        self.assertFalse((self.hub.home.parent / "skm").exists())


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
