#!/usr/bin/env python3
"""Tests scripts/version-guard.py — pure helpers and a bump on a synthetic package in tmpdir."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "version_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "version-guard.py")
)
version_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(version_guard)


def unit(unit_id, version, digest):
    return {"id": unit_id, "version": version, "tree_digest": digest, "version_source": "x"}


class ChangedUnits(unittest.TestCase):
    def test_flags_changed_content_under_same_version(self):
        previous = {"units": [unit("a", "1.0.0", "d1"), unit("b", "1.0.0", "d1"), unit("c", "1.0.0", "d1")]}
        current = {"units": [unit("a", "1.0.0", "d2"), unit("b", "1.0.1", "d2"),
                             unit("c", "1.0.0", "d1"), unit("d", "0.1.0", "d1")]}
        states = {row["id"]: row["state"] for row in version_guard.changed_units(previous, current)}
        self.assertEqual(states, {"a": "NOT-BUMPED", "b": "bumped", "d": "new"})


class ReleaseIntegration(unittest.TestCase):
    def test_brain_plugin_and_runtime_have_package_owned_versions(self):
        root = version_guard.ROOT
        current = version_guard.attestation.build(root, None, package_root=root / "packages/skiller")
        units = {u["id"]: u for u in current["units"]}
        expected = json.loads((root / "packages/brain/unit.json").read_text())["version"]
        for name in ("brain", "package.brain"):
            with self.subTest(unit=name):
                self.assertEqual(expected, units[name]["version"])
                self.assertEqual(expected, units[name]["expected_version"])
                self.assertEqual("packages/brain/package.json", units[name]["version_source"])


class NextVersion(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(version_guard.next_version("0.4.9", "patch"), "0.4.10")
        self.assertEqual(version_guard.next_version("0.4.9", "minor"), "0.5.0")
        self.assertEqual(version_guard.next_version("0.4.9", "1.2.3"), "1.2.3")
        with self.assertRaises(SystemExit):
            version_guard.next_version("0.4.9", "major")


class SetJsonVersion(unittest.TestCase):
    def test_keeps_non_canonical_formatting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugin.json"
            path.write_text('{\n    "name": "x",\n    "version": "0.4.9"\n}\n', encoding="utf-8")
            self.assertTrue(version_guard.set_json_version(path, "0.4.10"))
            self.assertEqual(path.read_text(encoding="utf-8"),
                             '{\n    "name": "x",\n    "version": "0.4.10"\n}\n')

    def test_lock_updates_root_package_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package-lock.json"
            path.write_text(json.dumps({"name": "x", "version": "1.0.0", "packages": {"": {"version": "1.0.0"}}},
                                       indent=2) + "\n", encoding="utf-8")
            version_guard.set_json_version(path, "1.0.1", lock=True)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual((data["version"], data["packages"][""]["version"]), ("1.0.1", "1.0.1"))

    def test_missing_file_is_skipped(self):
        self.assertFalse(version_guard.set_json_version(Path("/nonexistent/plugin.json"), "1.0.0"))


if __name__ == "__main__":
    unittest.main()
