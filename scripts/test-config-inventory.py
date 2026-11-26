#!/usr/bin/env python3
"""Config inventory guard: every config has one owner and a live consumer (stdlib)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "configs/config-inventory.json"
EXCLUDED_SEGMENTS = {"tests", "fixtures", "node_modules"}
ROOT_OWNERS = {"root"}


def glob_to_regex(glob):
    """`**/` -> any dirs (or none), `**` -> anything, `*` -> no slash, `?` -> one non-slash char."""
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out))


def glob_match(glob, path):
    return glob_to_regex(glob).fullmatch(path) is not None


def tracked(patterns):
    result = subprocess.run(
        ["git", "ls-files", "--", *patterns],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return sorted(
        line for line in result.stdout.splitlines()
        if line and not EXCLUDED_SEGMENTS.intersection(line.split("/"))
    )


def load():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def entry_matches(entry, path):
    if "path" in entry:
        return entry["path"] == path
    return glob_match(entry["glob"], path)


def entry_label(entry):
    return entry.get("path") or entry.get("glob")


class ConfigInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load()
        cls.entries = cls.data["entries"]
        cls.files = tracked(cls.data["scope"])

    def test_scope_covered(self):
        self.assertTrue(glob_match("a/**/*.json", "a/b/c/d.json"))
        self.assertTrue(glob_match("a/**/*.json", "a/d.json"))
        self.assertTrue(glob_match("a/*.json", "a/d.json"))
        self.assertFalse(glob_match("a/*.json", "a/b/d.json"))
        self.assertFalse(glob_match("a/?.json", "a/ab.json"))
        uncovered = [
            f for f in self.files
            if not any(entry_matches(e, f) for e in self.entries)
        ]
        self.assertEqual(uncovered, [], "configs without an inventory entry")

    def test_entries_exist(self):
        dead = []
        for entry in self.entries:
            label = entry_label(entry)
            if "path" in entry:
                if not (ROOT / entry["path"]).is_file():
                    dead.append(label)
            elif not any(glob_match(entry["glob"], f) for f in self.files):
                dead.append(label)
        self.assertEqual(dead, [], "inventory entries matching no tracked file")

    def test_owner_valid(self):
        self.assertEqual(self.data["schema_version"], 1)
        for entry in self.entries:
            with self.subTest(entry=entry_label(entry)):
                self.assertNotEqual("path" in entry, "glob" in entry)
                self.assertIsInstance(entry["released"], bool)
                self.assertTrue(entry["consumers"])
        owners = ROOT_OWNERS | {p.name for p in (ROOT / "packages").iterdir() if p.is_dir()}
        bad = [entry_label(e) for e in self.entries if e["owner"] not in owners]
        self.assertEqual(bad, [], f"owner must be one of {sorted(owners)}")

    def test_consumers_exist(self):
        missing = [
            (entry_label(e), c)
            for e in self.entries for c in e["consumers"]
            if not c.startswith("user:") and not (ROOT / c).is_file()
        ]
        self.assertEqual(missing, [], "consumers that are not files")

    def test_consumers_reference(self):
        stale = []
        for entry in self.entries:
            if "path" not in entry or entry.get("dynamic"):
                continue
            path = entry["path"]
            name = Path(path).name
            needles = {path, name[:-5] if name.endswith(".json") else name}
            files = [c for c in entry["consumers"] if not c.startswith("user:")]
            if not files:
                continue
            texts = [(ROOT / c).read_text(encoding="utf-8", errors="replace") for c in files]
            if not any(n in t for n in needles for t in texts):
                stale.append(path)
        self.assertEqual(stale, [], "no consumer file mentions the config")

    def test_descriptors_valid(self):
        """kind/format/schema/generated/live_path are optional; when given, they are well formed and the schema exists."""
        bad = []
        for entry in self.entries:
            label = entry_label(entry)
            for key in ("kind", "format"):
                if key in entry and not (isinstance(entry[key], str) and entry[key]):
                    bad.append((label, key))
            if "generated" in entry and not isinstance(entry["generated"], bool):
                bad.append((label, "generated"))
            if "live_path" in entry and not (entry["live_path"] is None or isinstance(entry["live_path"], str)):
                bad.append((label, "live_path"))
            schema = entry.get("schema")
            if schema is not None and schema != "native" and not (ROOT / schema).is_file():
                bad.append((label, "schema"))
        self.assertEqual(bad, [], "malformed optional descriptors")

    def test_no_stale_root_profile_catalog(self):
        self.assertFalse((ROOT / "configs/profile-catalog.json").exists())


if __name__ == "__main__":
    if "--uncovered" in sys.argv:
        data = load()
        for f in tracked(data["scope"]):
            if not any(entry_matches(e, f) for e in data["entries"]):
                print(f)
        sys.exit(0)
    unittest.main()
