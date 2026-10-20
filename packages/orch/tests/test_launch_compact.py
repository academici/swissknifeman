"""The launch catalog file states only what is specific (defaults, shared role fields, named argv parts, per-provider
differences); the resolved catalog every reader sees is unchanged and is pinned by a reviewed snapshot."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from orch import launch

GOLDEN = Path(__file__).resolve().parent / "golden" / "launch-catalog-resolved.json"


def compact() -> dict:
    return {"catalog_version": "1.0.0", "defaults": {"transport": "jsonl", "model_set": "supported"},
            "parts": {"codex.exec": ["codex", "-a", "never", "exec"], "codex.model": ["--model", "{model}"]},
            "roles": {"executor": {"model_class": "implementation", "effort": "high", "timeout_s": 3600, "providers": {
                "codex": {"argv": ["@codex.exec", "--json", "--sandbox", "workspace-write", "@codex.model", "-"]}}},
                      "scout": {"model_class": "economy", "effort": "low", "transport": "text", "timeout_s": 300,
                                "providers": {"codex": {"timeout_s": 60, "argv": [
                                    "@codex.exec", "--sandbox", "read-only", "@codex.model", "-"]}}}}}


def expanded(doc: dict) -> dict:
    return launch.expand_catalog(copy.deepcopy(doc))


class ShippedFileTests(unittest.TestCase):
    def test_the_resolved_catalog_is_the_reviewed_snapshot(self):
        """Any change of a command line, a sandbox flag, a class, an effort, a transport or a timeout shows up here, whatever
        the way the file states it. Update the snapshot only as the review of that change."""
        self.assertEqual(launch.load_catalog(), json.loads(GOLDEN.read_text(encoding="utf-8")))

    def test_the_file_is_compact_and_every_part_is_used(self):
        raw = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertIn("roles", raw)
        self.assertNotIn("launch", raw)
        self.assertLess(len(launch.CATALOG_PATH.read_text(encoding="utf-8")), GOLDEN.stat().st_size * 0.6)

    def test_the_sandbox_of_every_codex_role_is_stated_in_its_own_entry(self):
        raw = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        for role, body in raw["roles"].items():
            argv = body["providers"].get("codex", {}).get("argv")
            if argv:
                with self.subTest(role=role):
                    self.assertIn("--sandbox", argv)  # the confinement is never hidden inside a shared part

    def test_claude_research_roles_keep_the_invocation_config_query(self):
        catalog = launch.load_catalog()
        for role in ("researcher", "advisor"):
            argv = catalog["launch"][role]["claude-code"]["argv"]
            self.assertIn("Bash(python3 *orch.py --config * research query *)", argv)


class ExpandTests(unittest.TestCase):
    def test_defaults_then_role_then_provider_then_parts(self):
        found = expanded(compact())["launch"]
        self.assertEqual(found["executor"]["codex"], {
            "model_class": "implementation", "effort": "high", "timeout_s": 3600, "transport": "jsonl",
            "model_set": "supported",
            "argv": ["codex", "-a", "never", "exec", "--json", "--sandbox", "workspace-write", "--model", "{model}", "-"]})
        scout = found["scout"]["codex"]
        self.assertEqual((scout["transport"], scout["timeout_s"], scout["model_set"]), ("text", 60, "supported"))

    def test_a_catalog_in_the_resolved_form_is_returned_as_it_is(self):
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertIs(launch.expand_catalog(golden), golden)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.json"
            path.write_text(json.dumps(golden), encoding="utf-8")
            self.assertEqual(launch.load_catalog(path), golden)

    def test_an_at_sign_argument_is_written_twice(self):
        doc = compact()
        doc["roles"]["executor"]["providers"]["codex"]["argv"] = ["@codex.exec", "@@file", "@codex.model"]
        doc["roles"]["scout"]["providers"]["codex"]["argv"] = ["@codex.exec", "@codex.model", "-"]
        self.assertEqual(expanded(doc)["launch"]["executor"]["codex"]["argv"][-3:], ["@file", "--model", "{model}"])

    def refused(self, mutate, text: str):
        doc = compact()
        mutate(doc)
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(expanded(doc))
        self.assertEqual(raised.exception.code, "LAUNCH_INVALID")
        self.assertIn(text, str(raised.exception))

    def test_malformed_compact_catalogs_are_refused_with_the_place(self):
        self.refused(lambda d: d["roles"]["executor"]["providers"]["codex"]["argv"].append("@nope"), "unknown part '@nope'")
        self.refused(lambda d: d["parts"].update({"spare": ["x"]}), "unused part(s) ['spare']")
        self.refused(lambda d: d["parts"].update({"outer": ["@codex.exec"]}), "cannot name another part")
        self.refused(lambda d: d.update({"launch": {}}), "no launch")
        self.refused(lambda d: d.update({"extra": 1}), "no launch")
        self.refused(lambda d: d["roles"]["executor"].update({"argv": ["x"]}), "/roles/executor")
        self.refused(lambda d: d["roles"]["executor"]["providers"]["codex"].pop("argv"), "must hold argv")
        self.refused(lambda d: d["roles"]["executor"]["providers"]["codex"].update({"bogus": 1}), "must hold argv")
        self.refused(lambda d: d["defaults"].update({"argv": ["x"]}), "/defaults")

    def test_an_entry_the_compact_form_leaves_incomplete_is_refused_by_the_catalog_rules(self):
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        del doc["roles"]["executor"]["effort"]  # no default states it
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(expanded(doc))
        self.assertIn("/launch/executor/", str(raised.exception))

    def test_the_shipped_file_with_a_changed_field_changes_only_that_field(self):
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        doc["roles"]["reviewer"]["effort"] = "xhigh"
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        found = expanded(doc)
        for provider in golden["launch"]["reviewer"]:
            golden["launch"]["reviewer"][provider]["effort"] = "xhigh"
        self.assertEqual(found, golden)

    def test_the_overrides_of_the_configuration_work_on_the_resolved_form(self):
        merged = launch.apply_entries(launch.load_catalog(), {"executor_codex": {"timeout_s": 7200}})
        self.assertEqual(merged["launch"]["executor"]["codex"]["timeout_s"], 7200)


if __name__ == "__main__":
    unittest.main()
