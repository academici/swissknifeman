"""Custom skills (P8.5): `skiller.custom_dirs` (machine), `<project>/.swissknifeman/skills`, collisions and origin."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller import custom
from skiller import select as sel
from skiller.common import Env
from skiller.describe import cmd_describe

PKG_ROOT = Path(__file__).resolve().parents[1]


def write_skill(root, bucket, folder, name=None, selection=None):
    skill_dir = Path(root) / bucket / folder
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name or folder}\nversion: 0.1.0\ndescription: Use when testing {folder}.\n---\n\n# {folder}\n\nBody.\n",
        encoding="utf-8")
    if selection is not None:
        (skill_dir / "selection.json").write_text(
            json.dumps({"schema": "skill-selection/v1", "kind": "domain", "decision": "KEEP", **selection}), encoding="utf-8")
    return skill_dir


def library_entry(bucket, name, **selection):
    row = {"name": name, "bucket": bucket, "path": f"skills/{bucket}/{name}/SKILL.md"}
    if selection:
        row["selection"] = selection
    return row


class CollisionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def layer(self, origin, bucket, folder, **selection):
        root = self.tmp_path / origin
        write_skill(root, bucket, folder, selection=selection or None)
        return custom.scan(root, origin)

    def test_same_id_without_replaces_is_extension_ambiguous(self):
        library = [library_entry("php", "database")]
        with self.assertRaises(custom.ExtensionAmbiguous) as ctx:
            custom.merge(library, [self.layer("machine", "php", "database")])
        self.assertIn("EXTENSION_AMBIGUOUS", str(ctx.exception))
        self.assertIn("php/database", str(ctx.exception))

    def test_same_id_with_replaces_overrides_and_is_visible(self):
        library = [library_entry("php", "database")]
        merged, notes = custom.merge(library, [self.layer("machine", "php", "database", replaces="php/database")])
        self.assertEqual([(e["name"], e["origin"]) for e in merged], [("database", "machine")])
        self.assertTrue(any(n["code"] == "OVERRIDE" and n["id"] == "php/database" for n in notes))

    def test_replaces_of_another_id_does_not_count(self):
        library = [library_entry("php", "database")]
        with self.assertRaises(custom.ExtensionAmbiguous):
            custom.merge(library, [self.layer("project", "php", "database", replaces="php/other")])

    def test_project_overrides_machine_only_with_replaces(self):
        machine = self.layer("machine", "team", "style")
        with self.assertRaises(custom.ExtensionAmbiguous):
            custom.merge([], [machine, self.layer("project", "team", "style")])
        merged, _ = custom.merge([], [machine, self.layer("project2", "team", "style", replaces="team/style")])
        self.assertEqual(merged[0]["origin"], "project2")

    def test_other_id_with_the_same_triggers_warns(self):
        library = [library_entry("php", "database", triggers={"paths": ["database/**"]})]
        merged, notes = custom.merge(library, [self.layer("project", "team", "db", triggers={"paths": ["database/**"]})])
        self.assertEqual(len(merged), 2)
        self.assertTrue(any(n["code"] == "TRIGGER_OVERLAP" for n in notes))

    def test_replacing_a_deprecated_skill_and_a_deprecated_custom_skill_warn(self):
        library = [library_entry("general", "old", decision="DEPRECATE")]
        library[0]["selection"] = {"kind": "domain", "decision": "DEPRECATE"}
        merged, notes = custom.merge(library, [self.layer("project", "general", "old", replaces="general/old")])
        self.assertTrue(any(n["code"] == "DEPRECATED_REPLACED" for n in notes))
        deprecated = self.layer("machine", "team", "legacy", decision="DEPRECATE")
        _, notes = custom.merge([], [deprecated])
        self.assertTrue(any(n["code"] == "DEPRECATED" for n in notes))

    def test_origin_and_digest_of_a_scanned_skill(self):
        entry = self.layer("machine", "team", "style")[0]
        self.assertEqual((entry["origin"], entry["id"]), ("machine", "team/style"))
        self.assertTrue(entry["digest"].startswith("sha256:"))


class DiscoveryCase(unittest.TestCase):
    def test_project_skills_dir_and_machine_custom_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            project, machine_dir = tmp / "project", tmp / "machine-skills"
            write_skill(project / ".swissknifeman" / "skills", "team", "style")
            write_skill(machine_dir, "team", "tone")
            layers = custom.discover(project, [str(machine_dir)])
        self.assertEqual([(o, [e["id"] for e in es]) for o, es in layers],
                         [("machine", ["team/tone"]), ("project", ["team/style"])])

    def test_missing_dirs_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            layers = custom.discover(Path(tmp), [str(Path(tmp) / "nope")])
        self.assertEqual(layers, [("machine", []), ("project", [])])

    def test_custom_dirs_setting_is_machine_invocation_flags_only(self):
        schema = json.loads((PKG_ROOT / "configs" / "config.schema.json").read_text(encoding="utf-8"))
        layers = schema["properties"]["custom_dirs"]["x-skm-layers"]
        self.assertEqual(layers, ["defaults", "machine", "invocation", "flags"])


class CommandCase(unittest.TestCase):
    def run_select(self, env, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sel.cmd_select(env, list(argv))
        return json.loads(out.getvalue())

    def make_env(self, tmp):
        patch = mock.patch.dict(os.environ, {"SKM_HOME": str(Path(tmp) / "skm-home")})
        patch.start()
        self.addCleanup(patch.stop)
        return Env(PKG_ROOT, "select")

    def test_custom_dir_flag_adds_a_machine_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            extra = Path(tmp) / "extra"
            write_skill(extra, "team", "tone")
            result = self.run_select(self.make_env(tmp), "--role", "executor", "--project", tmp,
                                     "--custom-dirs", str(extra), "--include", "team/tone", "--json")
        self.assertEqual((result["included"][0]["id"], result["included"][0]["origin"]), ("team/tone", "machine"))

    def test_select_explain_shows_origin_and_digest_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            write_skill(project / ".swissknifeman" / "skills", "general", "git-safety",
                        selection={"replaces": "general/git-safety"})
            write_skill(project / ".swissknifeman" / "skills", "team", "style")
            result = self.run_select(self.make_env(tmp), "--role", "executor", "--project", str(project),
                                     "--include", "general/git-safety", "team/style", "--json", "--explain")
        rows = {row["id"]: row for row in result["included"]}
        self.assertEqual((rows["team/style"]["origin"], rows["general/git-safety"]["origin"]), ("project", "project"))
        self.assertTrue(rows["team/style"]["digest"].startswith("sha256:"))
        self.assertTrue(any(n["code"] == "OVERRIDE" for n in result["explain"]["custom"]))

    def test_library_skill_has_library_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_select(self.make_env(tmp), "--role", "executor", "--project", tmp,
                                     "--include", "general/git-safety", "--json")
        self.assertEqual(result["included"][0]["origin"], "library")

    def test_select_fails_with_extension_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            write_skill(project / ".swissknifeman" / "skills", "general", "git-safety")
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                self.run_select(self.make_env(tmp), "--role", "executor", "--project", str(project), "--json")
        self.assertIn("EXTENSION_AMBIGUOUS", err.getvalue())

    def test_describe_shows_origin(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_describe(Env(PKG_ROOT, "describe"), ["git-safety", "--json"])
        self.assertEqual(json.loads(out.getvalue())["origin"], "library")


    def test_describe_of_a_project_skill_shows_project_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_env(tmp)
            project = Path(tmp) / "project"
            write_skill(project / ".swissknifeman" / "skills", "team", "style")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cmd_describe(Env(PKG_ROOT, "describe"), ["team/style", "--project", str(project), "--json"])
        document = json.loads(out.getvalue())
        self.assertEqual((document["origin"], document["id"]), ("project", "team/style"))
        self.assertTrue(document["digest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
