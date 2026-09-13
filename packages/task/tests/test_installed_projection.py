"""Installed bytes and provider migration extras are independently checked."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fixtures  # noqa: F401 — repository import fallback
from core.provider.runtime import codex_migrated_command_skill


PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "scripts/plan-session.py"
spec = importlib.util.spec_from_file_location("task_plan_session_installed", SCRIPT)
session_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session_script)


class InstalledProjectionTests(unittest.TestCase):
    def test_verifier_uses_the_shared_provider_migration_renderer(self):
        relative = ".codex-plugin/migrated-command-skills/source-command-plan-design/SKILL.md"
        self.assertEqual(session_script.migrated_command_skill(PACKAGE, relative),
                         codex_migrated_command_skill(PACKAGE, relative))

    def test_matching_managed_bytes_cannot_be_substituted_by_symlinks(self):
        for kind in ("file", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                source, installed = Path(temporary) / "source", Path(temporary) / "installed"
                (source / "commands").mkdir(parents=True)
                canonical = source / "commands/plan-design.md"
                shutil.copy2(PACKAGE / "commands/plan-design.md", canonical)
                installed.mkdir()
                if kind == "file":
                    (installed / "commands").mkdir()
                    (installed / "commands/plan-design.md").symlink_to(canonical)
                else:
                    (installed / "commands").symlink_to(source / "commands", target_is_directory=True)
                result = subprocess.run(["python3", str(SCRIPT), "installed", "--source",
                                         str(source), "--installed", str(installed)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("symlink package member", result.stderr)

    def test_provider_owned_extra_is_source_bound_and_unknown_or_mutated_files_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, installed = Path(temporary) / "source", Path(temporary) / "installed"
            (source / "commands").mkdir(parents=True)
            shutil.copy2(PACKAGE / "commands/plan-design.md", source / "commands/plan-design.md")
            shutil.copytree(source, installed)
            relative = ".codex-plugin/migrated-command-skills/source-command-plan-design/SKILL.md"
            migration = installed / relative
            migration.parent.mkdir(parents=True)
            migration.write_bytes(session_script.migrated_command_skill(source, relative))

            def probe():
                result = subprocess.run(["python3", str(SCRIPT), "installed", "--source",
                                         str(source), "--installed", str(installed)],
                                        capture_output=True, text=True)
                return result.returncode, json.loads(result.stdout)

            status, report = probe()
            self.assertEqual(status, 0, report)
            self.assertEqual(report["source_digest"], report["installed_digest"])
            self.assertEqual(report["provider_generated"][0]["path"], relative)
            original = migration.read_bytes()
            migration.write_bytes(original + b"unexpected directive\n")
            self.assertEqual(probe()[0], 1)
            migration.write_bytes(original)
            unknown = migration.parent / "unknown.txt"
            unknown.write_text("extra")
            self.assertEqual(probe()[0], 1)
            unknown.unlink()
            managed = installed / "commands/plan-design.md"
            managed.write_bytes(managed.read_bytes() + b"managed mutation\n")
            self.assertEqual(probe()[0], 1)
            managed.unlink()
            self.assertEqual(probe()[0], 1)

    def test_unknown_command_namespace_is_not_exempt(self):
        self.assertIsNone(session_script.migrated_command_skill(
            PACKAGE, ".codex-plugin/migrated-command-skills/source-command-unknown/SKILL.md"))
        self.assertIsNone(session_script.migrated_command_skill(
            PACKAGE, ".codex-plugin/migrated-command-skills/source-command-plan-design/extra.md"))


if __name__ == "__main__":
    unittest.main()
