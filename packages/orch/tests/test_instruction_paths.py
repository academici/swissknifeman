"""Instruction files cannot escape their roots, exceed byte caps, or bypass auto selection integrity."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.util import schema

from orch.conductor import options, prompts
from orch.conductor.policies import paths
from orch.conductor.stages import scout
from tests import test_conductor_skills_checks as fixtures


class InstructionPathPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.inside = self.root / "skills"
        self.inside.mkdir()
        self.file = self.inside / "SKILL.md"
        self.file.write_bytes(b"exact\r\nbytes\n")

    def test_contained_returns_canonical_internal_files_only(self):
        self.assertEqual(paths.contained(self.file, [self.inside]), self.file)
        link = self.inside / "alias.md"
        link.symlink_to(self.file)
        self.assertEqual(paths.contained(link, [self.inside]), self.file)
        self.assertIsNone(paths.contained(self.root / "missing", [self.inside]))
        sibling = self.root / "skills-other"
        sibling.mkdir()
        outside = sibling / "SKILL.md"
        outside.write_text("outside")
        self.assertIsNone(paths.contained(outside, [self.inside]))
        self.assertIsNone(paths.contained(self.inside / ".." / "skills-other" / "SKILL.md", [self.inside]))

    def test_neither_a_link_nor_a_root_link_grants_an_outside_directory(self):
        link = self.inside / "escape"
        link.symlink_to(self.root, target_is_directory=True)
        self.assertIsNone(paths.contained(link / "skills" / "SKILL.md", [self.inside]))
        alias = self.root / "alias"
        alias.symlink_to(self.inside, target_is_directory=True)
        self.assertIsNone(paths.contained(alias / "SKILL.md", [alias]))
        loop = self.inside / "loop"
        loop.symlink_to(loop)
        self.assertIsNone(paths.contained(loop, [self.inside]))

    def test_capped_read_preserves_exact_utf8_bytes_and_accepts_the_limit(self):
        data = self.file.read_bytes()
        self.assertEqual(paths.read_capped(self.file, len(data)).encode("utf-8"), data)

    def test_oversized_file_is_rejected_before_any_open(self):
        self.file.write_bytes(b"x" * (70 * 1024))
        with mock.patch.object(paths.os, "open") as opened:
            with self.assertRaisesRegex(ValueError, "^too_large$"):
                paths.read_capped(self.file, 64 * 1024)
        opened.assert_not_called()

    def test_invalid_utf8_and_nonregular_files_are_refused(self):
        self.file.write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "^not_utf8$"):
            paths.read_capped(self.file, 64 * 1024)
        fifo = self.inside / "fifo"
        os.mkfifo(fifo)
        with mock.patch.object(paths.os, "open") as opened:
            with self.assertRaisesRegex(ValueError, "^outside$"):
                paths.read_capped(fifo, 64 * 1024)
        opened.assert_not_called()

    def test_descriptor_size_is_checked_after_stat(self):
        old_stat = self.file.stat()
        self.file.write_bytes(b"x" * 100)
        with mock.patch.object(paths.os, "stat", return_value=old_stat):
            with self.assertRaisesRegex(ValueError, "^too_large$"):
                paths.read_capped(self.file, 50)

    def test_growth_after_both_stats_still_uses_a_bounded_read(self):
        original = self.file.stat()
        self.file.write_bytes(b"x" * 10000)
        with mock.patch.object(paths.os, "stat", return_value=original), \
                mock.patch.object(paths.os, "fstat", return_value=original):
            with self.assertRaisesRegex(ValueError, "^too_large$"):
                paths.read_capped(self.file, 50)

    def test_read_never_follows_a_replaced_file_or_parent_link(self):
        link = self.root / "link"
        link.symlink_to(self.inside, target_is_directory=True)
        with self.assertRaises(OSError):
            paths.read_capped(link / "SKILL.md", 64 * 1024)
        original = self.file.stat()
        self.file.unlink()
        self.file.symlink_to(self.root / "outside")
        with mock.patch.object(paths.os, "stat", return_value=original):
            with self.assertRaises(OSError):
                paths.read_capped(self.file, 64 * 1024)


class InstructionPathsTests(unittest.TestCase):
    setUp = fixtures.SkillChecksTests.setUp
    skill = fixtures.SkillChecksTests.skill
    use = fixtures.SkillChecksTests.use
    excluded = fixtures.SkillChecksTests.excluded

    def auto(self, path, **extra):
        self.use("auto")
        row = {"name": "x", "id": "bucket/x", "path": str(path),
               "digest": "sha256:" + "0" * 64,
               "skill_md_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), **extra}
        self.item.state.clear()
        self.item.state["skills_auto"] = {"executor": {"skills": [row]}}

    def assert_path_excluded(self, skill_id, reason):
        self.assertEqual(self.excluded(), {skill_id: reason})
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {})
        beacons = [row for row in self.eng.progress.lines if row.get("reason_code") == "SKILL_PATH_INVALID"]
        self.assertTrue(beacons)
        self.assertIn(reason, beacons[-1]["message"])
        self.assertIn(skill_id, beacons[-1]["message"])
        blocks = prompts.scout(fixtures.INPUT, item="W1", step="scout.1", skills=self.eng._skills(self.item, "executor"))
        manifest = prompts.manifest(blocks, step="scout.1", role="executor", route=fixtures.ROUTE,
                                    excluded=self.eng._skills_excluded(self.item, "executor"))
        self.assertEqual(manifest["excluded"], [{"id": skill_id, "reason": reason}])

    def test_named_skill_directory_symlink_outside_is_excluded(self):
        outside = self.dir / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("Outside instruction.")
        root = self.dir / ".claude/skills"
        root.mkdir(parents=True)
        (root / "x").symlink_to(outside, target_is_directory=True)
        self.use("x")
        with mock.patch.object(paths, "read_capped", side_effect=AssertionError("must not read outside")):
            self.assert_path_excluded("x", "symlink")

    def test_named_skill_root_symlink_outside_is_excluded(self):
        outside = self.dir / "outside"
        (outside / "x").mkdir(parents=True)
        (outside / "x/SKILL.md").write_text("Outside instruction.")
        (self.dir / ".agents").mkdir()
        (self.dir / ".agents/skills").symlink_to(outside, target_is_directory=True)
        self.use("x")
        self.assert_path_excluded("x", "symlink")

    def test_internal_named_symlink_keeps_its_canonical_file(self):
        self.skill("real")
        root = self.dir / ".claude/skills"
        (root / "x").symlink_to(root / "real", target_is_directory=True)
        self.use("x")
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"x": "Do the thing."})

    def test_agents_skill_root_accepts_a_namespaced_name(self):
        folder = self.dir / ".agents/skills/core/context-economy"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("A namespaced skill.")
        self.use("core/context-economy")
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"core/context-economy": "A namespaced skill."})

    def test_oversized_skill_and_invalid_utf8_are_excluded(self):
        self.skill("x")
        path = self.dir / ".claude/skills/x/SKILL.md"
        self.use("x")
        path.write_bytes(b"x" * (70 * 1024))
        with mock.patch.object(paths.os, "open") as opened:
            self.assert_path_excluded("x", "too_large")
        opened.assert_not_called()
        self.item.state.clear()
        path.write_bytes(b"\xff")
        self.assert_path_excluded("x", "not_utf8")

    def test_a_skill_growing_before_the_scout_fingerprint_is_unavailable_then_excluded(self):
        self.skill("x")
        self.use("x")
        self.assertEqual(self.eng._skills(self.item, "executor"), ["x"])
        path = self.dir / ".claude/skills/x/SKILL.md"
        path.write_bytes(b"x" * (70 * 1024))
        who = SimpleNamespace(roles_dir=None, _skills=lambda *args: ["x"],
                              _skill_files=lambda *args: [("x", "x", path)], _skill_body=self.eng._skill_body,
                              _stub=lambda *args: ("", ""))
        route = {"provider": "fake", "model": "m", "effort": "low"}
        key = scout.cache_key(who, self.item, route)
        who._skill_body = mock.Mock(side_effect=OSError("unavailable"))
        self.assertEqual(key, scout.cache_key(who, self.item, route))
        self.assert_path_excluded("x", "too_large")

    def test_auto_digest_uses_skill_md_bytes_not_the_directory_digest(self):
        path = self.dir / "SKILL.md"
        path.write_bytes(b"---\r\nname: x\r\n---\r\nExact bytes.\r\n")
        self.auto(path)
        self.assertEqual(self.eng._skills(self.item, "executor"), ["x"])
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"x": "Exact bytes."})
        path.write_text("Changed after selection.")
        self.assert_path_excluded("bucket/x", "digest_mismatch")

    def test_auto_digest_missing_in_an_old_bridge_is_excluded(self):
        path = self.dir / "SKILL.md"
        path.write_text("Skill.")
        self.auto(path, skill_md_sha256=None)
        self.assert_path_excluded("bucket/x", "digest_missing")

    def test_auto_can_read_an_external_canonical_skill_and_its_valid_sidecar(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        folder = Path(external.name).resolve()
        path = folder / "SKILL.md"
        path.write_text("Selected external skill.")
        (folder / "selection.json").write_text(json.dumps({"schema": "skill-selection/v1", "kind": "domain",
                                                         "decision": "KEEP", "requires_tools": ["Read"]}))
        self.auto(path)
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"x": "Selected external skill."})
        self.assertEqual(self.excluded(), {})

    def test_auto_rejects_symlink_relative_noncanonical_and_wrong_filename(self):
        path = self.dir / "SKILL.md"
        path.write_text("Skill.")
        self.auto(path)
        row = self.item.state["skills_auto"]["executor"]["skills"][0]
        link = self.dir / "alias"
        link.symlink_to(self.dir, target_is_directory=True)
        (self.dir / "folder").mkdir()
        for raw, reason in ((str(link / "SKILL.md"), "symlink"), ("SKILL.md", "outside"),
                            (str(self.dir / "folder/../SKILL.md"), "outside"),
                            (str(self.dir) + "/./SKILL.md", "outside"),
                            (str(self.dir) + "//SKILL.md", "outside"),
                            (str(self.dir / "other.md"), "outside"),
                            (str(self.dir / "missing/SKILL.md"), "outside")):
            with self.subTest(path=raw):
                row["path"] = raw
                self.item.state.pop("skills_checked", None)
                self.assert_path_excluded("bucket/x", reason)

    def test_invalid_selection_json_and_schema_are_excluded(self):
        self.skill("x")
        self.use("x")
        sidecar = self.dir / ".claude/skills/x/selection.json"
        valid = {"schema": "skill-selection/v1", "kind": "domain", "decision": "KEEP"}
        for text in ("not json", "[]", "{}", "[" * 2000 + "]" * 2000, json.dumps({**valid, "max_tokens": 0}),
                     json.dumps({**valid, "unknown": True}), json.dumps({**valid, "requires_tools": "Bash"})):
            with self.subTest(text=text):
                self.item.state.clear()
                sidecar.write_text(text)
                self.assert_path_excluded("x", "selection_invalid")

    def test_selection_sidecar_cannot_escape_its_root(self):
        self.skill("x")
        self.use("x")
        sidecar = self.dir / ".claude/skills/x/selection.json"
        outside = self.dir / "selection.json"
        outside.write_text('{"schema":"skill-selection/v1","kind":"domain","decision":"KEEP"}')
        sidecar.symlink_to(outside)
        self.assert_path_excluded("x", "symlink")
        path = self.dir / ".claude/skills/x/SKILL.md"
        self.auto(path)  # auto sidecars belong to the selected skill directory, even outside the project
        self.assert_path_excluded("bucket/x", "symlink")

    def test_selection_caps_and_encoding_are_checked_on_later_reads(self):
        self.skill("x")
        self.use("x")
        self.assertEqual(self.eng._skills(self.item, "executor"), ["x"])
        sidecar = self.dir / ".claude/skills/x/selection.json"
        sidecar.write_bytes(b" " * (16 * 1024 + 1))
        self.assert_path_excluded("x", "too_large")
        self.item.state.clear()
        sidecar.write_bytes(b"\xff")
        self.assert_path_excluded("x", "not_utf8")

    def test_rule_carrier_symlinks_and_invalid_files_emit_rules_path_invalid(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        outside = Path(external.name) / "outside.md"
        outside.write_text("## demo.module-folders\nOutside rule.\n")
        folder = self.dir / "packages/demo"
        folder.mkdir(parents=True)
        self.item.input_doc = {"scope": {"write_set": ["packages/demo/file.py"]}}
        self.item.options["instructions"]["module_rules"] = ["module-folders"]
        for name in ("CLAUDE.md", "AGENTS.md"):
            carrier = folder / name
            carrier.symlink_to(outside)
            with mock.patch.object(paths, "read_capped", side_effect=AssertionError("must not read outside")):
                self.assertEqual(self.eng._repo_rules(self.item, "executor"), "")
            self.assertEqual(self.eng.progress.lines[-1]["reason_code"], "RULES_PATH_INVALID")
            self.assertIn("symlink", self.eng.progress.lines[-1]["message"])
            carrier.unlink()
        carrier.write_bytes(b"x" * (256 * 1024 + 1))
        with mock.patch.object(paths.os, "open") as opened:
            self.assertEqual(self.eng._repo_rules(self.item, "executor"), "")
        opened.assert_not_called()
        self.assertIn("too_large", self.eng.progress.lines[-1]["message"])
        carrier.write_bytes(b"\xff")
        self.assertEqual(self.eng._repo_rules(self.item, "executor"), "")
        self.assertIn("not_utf8", self.eng.progress.lines[-1]["message"])
        carrier.write_text("## demo.module-folders\nA valid rule.\n")
        self.assertIn("A valid rule.", self.eng._repo_rules(self.item, "executor"))


class SkillNameSchemaTests(unittest.TestCase):
    def test_both_schemas_refuse_traversal_and_keep_bucket_names(self):
        root = Path(__file__).resolve().parents[3]
        contracts = (root / "packages/orch/schemas/conductor/v1/run-options.schema.json",
                     root / "bridges/planner-orch/schemas/run-options.schema.json")
        for path in contracts:
            registry = schema.load_schema_file(path, urn_prefix="urn:swissknifeman:orch:conductor:", kind="run-options")
            for name in ("docs-maintenance/../../x", "x/../../..", "../x", "/x", "x/./y", "x..y", "x//y", "x/", "x\n"):
                doc = {"skills": [{"role": "executor", "names": [name]}]}
                with self.subTest(schema=path, invalid=name):
                    self.assertTrue(schema.validate(doc, "run-options", registry))
                    with self.assertRaises(options.OptionsError) as caught:
                        options.effective({}, {}, [{"source": "input", "options": doc}])
                    self.assertEqual(caught.exception.code, "OPTIONS_INVALID")
            for name in ("bucket:name", "core/context-economy", "auto", "a.b/c_d:e-f"):
                with self.subTest(schema=path, valid=name):
                    self.assertFalse(schema.validate({"skills": [{"role": "executor", "names": [name]}]},
                                                     "run-options", registry))


if __name__ == "__main__":
    unittest.main()
