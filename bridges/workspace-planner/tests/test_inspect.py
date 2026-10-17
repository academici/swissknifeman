"""``inspect``: classes, derived files, digests, items in progress, symlinks, and the plugin protocol of the bridge."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import workspace_fixture as fx
from workspace_fixture import PLAN_NAME, ARCHIVED_NAME, SECRET, BridgeCase

import inspector  # noqa: E402
import partners  # noqa: E402

from aicore.ext import plugins  # noqa: E402
from aicore.util import schema  # noqa: E402

WORKSPACE = partners.workspace_module_root()
CONTRACT = WORKSPACE / "schemas" / "plans-migrator" / "v1" if WORKSPACE is not None else None


class InspectTests(BridgeCase):
    def test_classes_and_names(self):
        manifest = inspector.inspect(self.checkout)
        by_name = {plan["name"]: plan for plan in manifest["plans"]}
        self.assertEqual(sorted(by_name), sorted([PLAN_NAME, ARCHIVED_NAME, "old-thing", "only-artifacts"]))
        self.assertEqual(by_name[PLAN_NAME]["class"], "v4")
        self.assertEqual(by_name[ARCHIVED_NAME]["class"], "v4")
        self.assertEqual(by_name["old-thing"]["class"], "legacy")
        self.assertEqual(by_name["only-artifacts"]["class"], "legacy")
        self.assertEqual([entry["path"] for entry in manifest["top_level"]], ["README.md", "archive/NOTE.md"])
        self.assertTrue(manifest["present"])
        self.assertEqual(manifest["symlinks"], [])

    def test_derived_files_are_not_in_the_manifest(self):
        manifest = inspector.inspect(self.checkout)
        files = {entry["path"] for plan in manifest["plans"] for entry in plan["files"]}
        for left_out in ("views/roadmap.md", "context/P1.1.json", ".lock", "__pycache__/x.pyc"):
            self.assertNotIn(f"{PLAN_NAME}/{left_out}", files)
        self.assertIn(f"{PLAN_NAME}/artifacts/P1.1/out.txt", files)
        self.assertIn(f"{PLAN_NAME}/plan.json", files)
        self.assertGreaterEqual(manifest["derived_skipped"], 4)

    def test_derived_rule_is_for_the_plan_folder_only(self):
        fx.write(self.plans / "old-thing/views/keep.md", "legacy views are data\n")
        fx.write(self.plans / PLAN_NAME / "artifacts/P1.1/views/keep.md", "nested views are data\n")
        manifest = inspector.inspect(self.checkout)
        files = {entry["path"] for plan in manifest["plans"] for entry in plan["files"]}
        self.assertIn("old-thing/views/keep.md", files)
        self.assertIn(f"{PLAN_NAME}/artifacts/P1.1/views/keep.md", files)

    def test_digest_follows_content_and_not_derived_files(self):
        before = inspector.inspect(self.checkout)
        fx.write(self.plans / PLAN_NAME / "views/new.md", "more derived\n")
        self.assertEqual(inspector.inspect(self.checkout)["digest"], before["digest"])
        fx.write(self.plans / "old-thing/notes.txt", "changed\n")
        after = inspector.inspect(self.checkout)
        self.assertNotEqual(after["digest"], before["digest"])
        digests = {plan["name"]: plan["digest"] for plan in before["plans"]}
        changed = {plan["name"]: plan["digest"] for plan in after["plans"]}
        self.assertNotEqual(changed["old-thing"], digests["old-thing"])
        self.assertEqual(changed[PLAN_NAME], digests[PLAN_NAME])

    def test_plan_digest_is_the_same_wherever_the_folder_lives(self):
        manifest = inspector.inspect(self.checkout)
        plan = next(item for item in manifest["plans"] if item["name"] == PLAN_NAME)
        self.assertEqual(inspector.scan_digest(self.plans / PLAN_NAME, "v4"), plan["digest"])

    def test_file_entries_have_size_and_sha256_and_no_content(self):
        manifest = inspector.inspect(self.checkout)
        notes = next(entry for plan in manifest["plans"] for entry in plan["files"] if entry["path"] == "old-thing/notes.txt")
        content = (self.plans / "old-thing/notes.txt").read_bytes()
        self.assertEqual(notes["bytes"], len(content))
        self.assertEqual(notes["sha256"], inspector.sha256_file(self.plans / "old-thing/notes.txt"))
        self.assertNotIn(SECRET, fx.dump(manifest))
        self.assertNotIn(str(self.checkout), fx.dump(manifest))

    def test_items_in_progress(self):
        manifest = inspector.inspect(self.checkout)
        by_name = {plan["name"]: plan for plan in manifest["plans"]}
        self.assertEqual(by_name[PLAN_NAME]["in_progress"], [f"{PLAN_NAME}/P2.1"])
        self.assertEqual(by_name["old-thing"]["in_progress"], [])

    def test_legacy_plan_json_with_another_schema_is_legacy(self):
        fx.write(self.plans / "v3-plan/plan.json", json.dumps({"$schema": "urn:old:plan:v3"}))
        fx.write(self.plans / "broken/plan.json", "{not json")
        classes = {plan["name"]: plan["class"] for plan in inspector.inspect(self.checkout)["plans"]}
        self.assertEqual(classes["v3-plan"], "legacy")
        self.assertEqual(classes["broken"], "legacy")

    def test_symlinks_are_listed_and_not_followed(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        os.symlink(outside, self.plans / "old-thing/link.txt")
        os.symlink(self.tmp, self.plans / "linked-dir")
        os.symlink(outside, self.plans / "top-link.md")
        manifest = inspector.inspect(self.checkout)
        self.assertEqual(manifest["symlinks"], ["linked-dir", "old-thing/link.txt", "top-link.md"])
        files = {entry["path"] for plan in manifest["plans"] for entry in plan["files"]}
        self.assertNotIn("old-thing/link.txt", files)
        self.assertNotIn("linked-dir", {plan["name"] for plan in manifest["plans"]})

    def test_symlink_inside_a_derived_folder_does_not_block(self):
        os.symlink(self.tmp, self.plans / PLAN_NAME / "views/link")
        self.assertEqual(inspector.inspect(self.checkout)["symlinks"], [])

    def test_missing_plans_folder(self):
        empty = self.tmp / "bare"
        empty.mkdir()
        manifest = inspector.inspect(empty)
        self.assertFalse(manifest["present"])
        self.assertEqual((manifest["plans"], manifest["top_level"]), ([], []))


class ProtocolTests(BridgeCase):
    """The bridge as aicore starts it: ``migrator.py`` with one JSON request on stdin."""

    def call(self, document: dict) -> dict:
        done = subprocess.run([sys.executable, str(partners.BRIDGE / "migrator.py")], input=json.dumps(document),
                              capture_output=True, text=True, encoding="utf-8", check=False, cwd=self.tmp,
                              env=dict(os.environ, AICORE_ROOT=str(partners.aicore_lib().parent)))
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def invoke(self, **fields) -> dict:
        return self.call({"protocol": "1", "request_id": "r1", "op": "invoke", "point": "workspace:plans-migrator",
                          "input": fields})

    def test_describe(self):
        answer = self.call({"protocol": "1", "request_id": "r1", "op": "describe"})
        self.assertEqual(answer["status"], "ok")
        self.assertEqual(answer["output"]["id"], "workspace-planner")
        self.assertEqual(answer["request_id"], "r1")

    def test_manifest_is_valid_for_aicore(self):
        manifest = plugins.load_manifest(partners.BRIDGE / "extension.json")
        self.assertEqual(manifest.id, "workspace-planner")
        self.assertEqual(list(manifest.points), ["workspace:plans-migrator"])
        self.assertEqual(manifest.timeout_seconds, 3600)

    @unittest.skipIf(CONTRACT is None, "workspace module not found (set SKM_WORKSPACE_MODULE_ROOT)")
    def test_inspect_answer_matches_the_contract(self):
        answer = self.invoke(op="inspect", project_root=str(self.checkout))
        self.assertEqual(answer["status"], "ok", answer)
        registry = schema.load_contract_set(CONTRACT)[0]
        self.assertEqual(schema.validate(answer["output"], "response", registry), [])
        self.assertEqual(answer["output"]["digest"], inspector.inspect(self.checkout)["digest"])
        request = {"op": "inspect", "project_root": str(self.checkout)}
        self.assertEqual(schema.validate(request, "request", registry), [])

    def test_unknown_point_and_bad_input_are_errors(self):
        answer = self.call({"protocol": "1", "request_id": "r1", "op": "invoke", "point": "other:point",
                            "input": {"op": "inspect"}})
        self.assertEqual(answer["status"], "error")
        bad = self.invoke(op="inspect", project_root="relative/path")
        self.assertEqual((bad["status"], bad["error"]["code"]), ("error", "INPUT_INVALID"))
        self.assertEqual(self.call({"protocol": "2", "request_id": "r1", "op": "describe"})["error"]["code"],
                         "PROTOCOL_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
