"""aicore.ext.units: what unit.json files declare for events, subscriptions, overlays and extension points."""
import json
import os
import unittest

from aicore.ext import units
from aicore.util import schema

from tests.ext.support import UNITS, TempCase

import io
from contextlib import redirect_stderr
from pathlib import Path

UNIT_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "unit" / "v1"


class TestDemoFixture(TempCase):
    def test_fixture_is_a_valid_unit(self):
        registry, kind = schema.load_contract(UNIT_SCHEMA)
        doc = json.loads((UNITS / "demo" / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual(schema.validate(doc, kind, registry), [])
        self.assertTrue(os.access(UNITS / "demo" / "bin" / "demo-sub", os.X_OK))

    def test_declarations(self):
        found = units.discover_units({"SKM_UNITS_PATH": str(UNITS)})
        self.assertEqual(list(found), ["demo"])
        self.assertEqual(found["demo"].root, UNITS / "demo")
        self.assertEqual(units.declared_events(found), {"demo.thing.happened": "demo"})
        self.assertEqual(units.overlay_slots(found), {"demo:plan": "demo"})
        self.assertEqual(units.extension_points(found), {
            "demo:check": {"module": "demo", "id": "check", "description": "Extra checks of a demo run."}})
        subscriptions = units.module_subscriptions(found)
        self.assertEqual(list(subscriptions), ["demo:log"])
        entry = subscriptions["demo:log"]
        self.assertEqual((entry["module"], entry["id"], entry["on"]), ("demo", "log", ["demo.*"]))
        self.assertEqual(entry["run"], [str(UNITS / "demo" / "bin" / "demo-sub")])
        self.assertIsNone(entry["timeout_seconds"])


class TestDiscovery(TempCase):
    def write(self, name, doc, raw=None):
        folder = self.tmp / "mods" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "unit.json").write_text(raw if raw is not None else json.dumps(doc), encoding="utf-8")
        return folder

    def discover(self, *roots):
        env = {"SKM_UNITS_PATH": os.pathsep.join(str(root) for root in roots)}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            found = units.discover_units(env)
        return found, stderr.getvalue()

    def test_modules_folder_and_single_module_roots(self):
        one = self.write("one", {"id": "one"})
        self.write("two", {"id": "two"})
        found, warnings = self.discover(self.tmp / "mods")
        self.assertEqual(sorted(found), ["one", "two"])
        self.assertEqual(warnings, "")
        found, _ = self.discover(one)
        self.assertEqual(list(found), ["one"])

    def test_first_root_wins_for_a_repeated_id(self):
        self.write("a", {"id": "same", "title": "first"})
        other = self.tmp / "other" / "b"
        other.mkdir(parents=True)
        (other / "unit.json").write_text(json.dumps({"id": "same", "title": "second"}), encoding="utf-8")
        found, _ = self.discover(self.tmp / "mods", self.tmp / "other")
        self.assertEqual(found["same"].doc["title"], "first")

    def test_broken_unit_files_are_skipped_with_one_warning_each(self):
        self.write("good", {"id": "good"})
        self.write("badjson", None, raw="{not json")
        self.write("noid", {"title": "x"})
        self.write("list", None, raw="[1]")
        found, warnings = self.discover(self.tmp / "mods")
        self.assertEqual(list(found), ["good"])
        self.assertEqual(warnings.count("UNIT_INVALID"), 3)

    def test_bad_entries_are_ignored(self):
        self.write("odd", {"id": "odd", "provides": {"events": ["odd.a.b", 5, None, ""],
                                                      "overlay_slots": "plan", "extension_points": [
                                                          {"id": "ok"}, {"id": 7}, "text", {"description": "x"}]},
                           "subscribes": ["x", {"id": "s"}, {"id": "t", "on": ["a"], "run": ["bin/t"]},
                                          {"id": "up", "on": ["a"], "run": ["../escape"]},
                                          {"id": "abs", "on": ["a"], "run": ["/bin/true"]},
                                          {"id": "tm", "on": ["a"], "run": ["bin/t", "--x"], "timeout_seconds": 9}]})
        found, _ = self.discover(self.tmp / "mods")
        self.assertEqual(units.declared_events(found), {"odd.a.b": "odd"})
        self.assertEqual(units.overlay_slots(found), {})
        self.assertEqual(list(units.extension_points(found)), ["odd:ok"])
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            subscriptions = units.module_subscriptions(found)
        warnings = stderr.getvalue()
        self.assertEqual(sorted(subscriptions), ["odd:t", "odd:tm"])
        self.assertEqual(subscriptions["odd:tm"]["run"][1:], ["--x"])
        self.assertEqual(subscriptions["odd:tm"]["timeout_seconds"], 9)
        self.assertIn("UNIT_INVALID", warnings)

    def test_symlink_escape_is_refused(self):
        folder = self.write("link", {"id": "link", "subscribes": [{"id": "s", "on": ["a"], "run": ["bin/out"]}]})
        (folder / "bin").mkdir()
        (folder / "bin" / "out").symlink_to("/bin/true")
        found, _ = self.discover(self.tmp / "mods")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(units.module_subscriptions(found), {})
        self.assertIn("inside the module folder", stderr.getvalue())

    def test_symlink_loop_skips_one_entry_only(self):
        self.write("good", {"id": "good", "subscribes": [{"id": "s", "on": ["a"], "run": ["bin/ok"]}]})
        folder = self.write("loop", {"id": "loop", "subscribes": [{"id": "s", "on": ["a"], "run": ["bin/x"]}]})
        (folder / "bin").mkdir()
        (folder / "bin" / "x").symlink_to(folder / "bin" / "x")
        found, _ = self.discover(self.tmp / "mods")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            subscriptions = units.module_subscriptions(found)
        self.assertEqual(list(subscriptions), ["good:s"])
        self.assertIn("loop:s", stderr.getvalue())

    def test_the_real_repository_units_are_readable(self):
        found = units.discover_units(None if "SKM_UNITS_PATH" not in os.environ else {})
        self.assertIn("aicore", found)


if __name__ == "__main__":
    unittest.main()
