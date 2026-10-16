"""Bridge dispatcher: manifest discovery, validation, verb passthrough and refusals."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from planner import integration
from planner.plan import bridges, schema
from planner.plan.model import PlanError

try:
    from . import test_envelope
except ImportError:
    import test_envelope

# Records its argv and selected environment into the file named by BRIDGE_PROBE, then exits with argv[1] when numeric.
PROBE = """import json, os, sys
with open(os.environ["BRIDGE_PROBE"], "w", encoding="utf-8") as handle:
    json.dump({"args": sys.argv[1:], "env": {k: os.environ.get(k) for k in
               ("PLANNER_ROOT", "PLANNER_PLAN_PY", "TASK_ROOT", "TASK_PLAN_PY", "PYTHONPATH", "BRIDGE_PROBE")}}, handle)
sys.exit(int(sys.argv[1]) if sys.argv[1:] and sys.argv[1].isdigit() else 0)
"""


def manifest(name: str, **overrides) -> dict:
    document = {"$schema": "urn:swissknifeman:task:plan:bridge:v1", "name": name, "partner": "partner-x",
                "direction": "out", "contract": "partner-x/v1", "summary": "Test bridge.",
                "entrypoints": {"probe": "probe.py", "echo": "probe.py"}}
    document.update(overrides)
    return document


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve() / "project"
        self.root = self.project / "bridges"
        self.probe_out = Path(self.tmp.name) / "probe.json"
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_")}
        env.update(HOME=str(home), SKM_HOME=str(home))
        environment = mock.patch.dict(os.environ, env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        for name, value in (("default_root", mock.Mock(return_value=self.root)),
                            ("project_root", mock.Mock(return_value=self.project))):
            patcher = mock.patch.object(bridges, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def add(self, name: str, document: dict | None = None, raw: str | None = None) -> Path:
        directory = self.root / name
        directory.mkdir(parents=True)
        (directory / "probe.py").write_text(PROBE, encoding="utf-8")
        text = raw if raw is not None else json.dumps(document if document is not None else manifest(name))
        (directory / "bridge.json").write_text(text, encoding="utf-8")
        return directory

    def probe(self) -> dict:
        return json.loads(self.probe_out.read_text(encoding="utf-8"))


class ListTests(BridgeCase):
    def test_missing_root_lists_nothing(self):
        self.assertEqual(bridges.listing(), {"bridges": []})
        code, out, _ = test_envelope.run("--output", "json", "bridge", "list")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": True, "data": {"bridges": []}})

    def test_one_bridge_is_listed_with_sorted_verbs(self):
        self.add("alpha")
        row = {"name": "alpha", "partner": "partner-x", "direction": "out", "contract": "partner-x/v1",
               "verbs": ["echo", "probe"], "path": "bridges/alpha"}
        self.assertEqual(bridges.listing(), {"bridges": [row]})
        code, out, _ = test_envelope.run("bridge", "list")
        self.assertEqual((code, out), (0, "alpha partner-x out echo probe\n"))

    def test_list_takes_no_arguments(self):
        code, _, err = test_envelope.run("bridge", "list", "extra")
        self.assertEqual(code, 2)
        self.assertIn("takes no arguments", err)

    def test_invalid_manifests_are_refused(self):
        cases = {
            "broken": ("broken", None, "{not json"),
            "schema": ("schema", manifest("schema", direction="sideways"), None),
            "extra": ("extra", manifest("extra", owner="me"), None),
            "name": ("name", manifest("other"), None),
            "empty": ("empty", manifest("empty", entrypoints={}), None),
            "verb": ("verb", manifest("verb", entrypoints={"Bad_Verb": "probe.py"}), None),
            "missing": ("missing", manifest("missing", entrypoints={"go": "nothing.py"}), None),
            "parent": ("parent", manifest("parent", entrypoints={"go": "../outside.py"}), None),
            "absolute": ("absolute", manifest("absolute", entrypoints={"go": "/bin/sh"}), None),
        }
        for label, (name, document, raw) in cases.items():
            with self.subTest(label):
                directory = self.add(name, document, raw)
                (directory.parent / "outside.py").write_text("", encoding="utf-8")
                with self.assertRaises(PlanError) as caught:
                    bridges.listing()
                self.assertEqual(caught.exception.code, "BRIDGE_INVALID")
                code, out, _ = test_envelope.run("--output", "json", "bridge", "list")
                self.assertEqual((code, json.loads(out)["error"]["code"]), (1, "BRIDGE_INVALID"))
                for child in directory.iterdir():
                    child.unlink()
                directory.rmdir()

    def test_entrypoint_symlink_leaving_the_bridge_is_refused(self):
        outside = Path(self.tmp.name) / "outside.py"
        outside.write_text("", encoding="utf-8")
        directory = self.add("link", manifest("link", entrypoints={"go": "go.py"}))
        (directory / "go.py").symlink_to(outside)
        with self.assertRaises(PlanError) as caught:
            bridges.listing()
        self.assertEqual(caught.exception.code, "BRIDGE_INVALID")


class RunTests(BridgeCase):
    def setUp(self):
        super().setUp()
        self.add("alpha")
        env = mock.patch.dict(os.environ, {"BRIDGE_PROBE": str(self.probe_out), "PYTHONPATH": "/earlier"})
        env.start()
        self.addCleanup(env.stop)

    def test_verb_receives_its_arguments_and_environment(self):
        args = ["PLAN2", "P7.1", "--out", "x.json", "--output", "json", "--", "-v"]
        self.assertEqual(bridges.run("alpha", "probe", args), 0)
        result = self.probe()
        self.assertEqual(result["args"], args)
        root = bridges.PLANNER_ROOT
        self.assertEqual(result["env"]["PLANNER_ROOT"], str(root))
        self.assertEqual(result["env"]["PLANNER_PLAN_PY"], str(root / "scripts" / "plan.py"))
        # Compatibility alias: remove in the next minor release.
        self.assertEqual(result["env"]["TASK_ROOT"], str(root))
        self.assertEqual(result["env"]["TASK_PLAN_PY"], str(root / "scripts" / "plan.py"))
        self.assertEqual(result["env"]["PYTHONPATH"], f"{root / 'lib'}{os.pathsep}/earlier")
        self.assertEqual(result["env"]["BRIDGE_PROBE"], str(self.probe_out))

    def test_cli_passes_options_after_the_verb_and_returns_the_bridge_exit(self):
        code, _, _ = test_envelope.run("bridge", "alpha", "echo", "7", "--plans-root", "elsewhere", "--help")
        self.assertEqual(code, 7)
        self.assertEqual(self.probe()["args"], ["7", "--plans-root", "elsewhere", "--help"])

    def test_json_output_does_not_wrap_the_bridge(self):
        code, out, _ = test_envelope.run("--output", "json", "bridge", "alpha", "probe", "3")
        self.assertEqual((code, out), (3, ""))
        self.assertEqual(self.probe()["args"], ["3"])

    def test_unknown_bridge_and_verb_are_refused(self):
        with self.assertRaises(PlanError) as caught:
            bridges.run("beta", "probe", [])
        self.assertEqual(caught.exception.code, "BRIDGE_UNKNOWN")
        for verb in ("nope", None):
            with self.subTest(verb):
                with self.assertRaises(PlanError) as caught:
                    bridges.run("alpha", verb, [])
                self.assertEqual(caught.exception.code, "BRIDGE_VERB_UNKNOWN")
                self.assertIn("echo, probe", caught.exception.message)
        code, out, _ = test_envelope.run("--output", "json", "bridge", "alpha", "nope")
        document = json.loads(out)
        self.assertEqual(schema.validate(document, "envelope"), [])
        self.assertEqual((code, document["error"]["code"]), (1, "BRIDGE_VERB_UNKNOWN"))
        code, _, err = test_envelope.run("bridge", "beta", "probe")
        self.assertEqual(code, 1)
        self.assertIn("BRIDGE_UNKNOWN", err)
        self.assertFalse(self.probe_out.exists())


class RootsTests(BridgeCase):
    """``bridges.roots`` of the configuration, the built-in root, shadowing and the foundation hand-over."""

    def configure(self, *roots: str) -> None:
        folder = self.project / ".swissknifeman"
        folder.mkdir(parents=True, exist_ok=True)
        listed = ", ".join(json.dumps(r) for r in roots)
        (folder / "config.toml").write_text(f"schema_version = 1\n[planner.bridges]\nroots = [{listed}]\n",
                                            encoding="utf-8")

    def add_to(self, root: Path, name: str) -> Path:
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "probe.py").write_text(PROBE, encoding="utf-8")
        (directory / "bridge.json").write_text(json.dumps(manifest(name)), encoding="utf-8")
        return directory

    def names(self) -> list:
        return [row["name"] for row in bridges.listing()["bridges"]]

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_relative_root_is_taken_from_the_project_and_listed_relative(self):
        self.add_to(self.project / "hub-bridges", "gamma")
        self.configure("hub-bridges")
        self.assertEqual(bridges.roots(), [(self.project / "hub-bridges").resolve()])
        self.assertEqual(bridges.listing()["bridges"][0]["path"], "hub-bridges/gamma")

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_absolute_root_outside_the_project_is_listed_absolute(self):
        outside = Path(self.tmp.name).resolve() / "outside"
        self.add_to(outside, "delta")
        self.configure(str(outside))
        row, = bridges.listing()["bridges"]
        self.assertEqual(row["path"], (outside / "delta").as_posix())

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_home_is_expanded(self):
        home = Path(os.environ["HOME"])
        self.add_to(home / "mine", "epsilon")
        self.configure("~/mine")
        self.assertEqual(bridges.roots(), [(home / "mine").resolve()])
        self.assertEqual(self.names(), ["epsilon"])

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_configured_root_comes_before_the_built_in_one(self):
        self.add_to(self.root, "alpha")
        self.add_to(self.project / "more", "beta")
        self.configure("more")
        self.assertEqual(bridges.roots(), [(self.project / "more").resolve(), self.root.resolve()])
        self.assertEqual(self.names(), ["alpha", "beta"])

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_first_root_wins_and_the_shadowed_bridge_is_reported(self):
        first = self.add_to(self.project / "first", "alpha")
        self.add_to(self.root, "alpha")
        self.configure("first")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            found = bridges.scan()
        self.assertEqual([directory for directory, _ in found], [first.resolve()])
        self.assertIn(f"BRIDGE_SHADOWED: alpha in {(self.root / 'alpha').resolve()} is shadowed by {first.resolve()}",
                      err.getvalue())

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_a_shadowed_manifest_is_not_validated(self):
        first = self.add_to(self.project / "first", "alpha")
        broken = self.add_to(self.root, "alpha")
        (broken / "bridge.json").write_text(json.dumps(manifest("alpha", entrypoints={"go": "missing.py"})),
                                            encoding="utf-8")
        self.configure("first")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            found = bridges.scan()
        self.assertEqual([directory for directory, _ in found], [first.resolve()])
        self.assertIn("BRIDGE_SHADOWED: alpha", err.getvalue())

    def test_without_configuration_only_the_built_in_root_counts(self):
        self.add_to(self.root, "alpha")
        self.assertEqual(bridges.roots(), [self.root.resolve()])
        self.assertEqual(self.names(), ["alpha"])

    def test_without_aicore_the_configured_roots_are_not_read(self):
        self.add_to(self.root, "alpha")
        self.add_to(self.project / "more", "beta")
        self.configure("more")
        with mock.patch.dict(integration._PROBE, {"available": False, "root": None, "reason": "AICORE_NOT_FOUND"},
                             clear=True):
            self.assertEqual(self.names(), ["alpha"])

    def test_a_missing_built_in_root_is_not_listed(self):
        self.assertEqual(bridges.roots(), [])
        self.assertEqual(bridges.listing(), {"bridges": []})

    @unittest.skipUnless(integration.available(), "needs the aicore foundation")
    def test_environment_hands_over_the_foundation_root(self):
        self.assertEqual(bridges.environment().get("AICORE_ROOT"), integration.status()["root"])

    def test_environment_without_aicore_sets_no_foundation_root(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.dict(integration._PROBE, {"available": False, "root": None, "reason": "x"}, clear=True):
            os.environ.pop("AICORE_ROOT", None)
            self.assertNotIn("AICORE_ROOT", bridges.environment())


class SchemaTests(unittest.TestCase):
    def test_schema_kind_is_registered_and_served(self):
        self.assertIn("bridge", schema.KINDS)
        code, out, _ = test_envelope.run("schema", "bridge")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["$id"], "urn:swissknifeman:task:plan:bridge:v1")
        self.assertEqual(schema.validate(manifest("alpha", requires={"cli": "x", "env": "X_ROOT"}), "bridge"), [])


if __name__ == "__main__":
    unittest.main()
