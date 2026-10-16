"""Document sync: DocsSync pull, push and script, and the ``brain docs`` commands."""
import shutil
import stat
import subprocess
import unittest
from pathlib import Path

from brain import docs, settings, vault
from tests.support import TempCase
from tests.test_cli import CliCase


def write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestPull(TempCase):
    def test_copies_by_patterns_and_keeps_relative_paths(self):
        write(self.vault, "docs/guide/a.md", "# A")
        write(self.vault, "README.md", "# readme")
        write(self.vault, "secret.txt", "nope")
        copied = docs.DocsSync(self.project, self.vault, "pull", ("docs/**/*.md", "README.md")).pull()
        self.assertEqual("# A", (self.project / "docs/guide/a.md").read_text(encoding="utf-8"))
        self.assertEqual("# readme", (self.project / "README.md").read_text(encoding="utf-8"))
        self.assertFalse((self.project / "secret.txt").exists())
        self.assertEqual(2, len(copied))

    def test_missing_vault_is_soft(self):
        self.assertEqual([], docs.DocsSync(self.project, self.root / "nope").pull())
        self.assertEqual([], docs.DocsSync(self.project, None).pull())

    def test_idempotent_updates_and_removes_nothing(self):
        write(self.vault, "README.md", "v1")
        sync = docs.DocsSync(self.project, self.vault, "pull", ("README.md",))
        sync.pull()
        write(self.vault, "README.md", "v2")
        write(self.project, "notes/local.md", "mine")
        sync.pull()
        self.assertEqual("v2", (self.project / "README.md").read_text(encoding="utf-8"))
        self.assertTrue((self.project / "notes/local.md").exists())

    def test_dry_run_writes_nothing(self):
        write(self.vault, "docs/a.md", "# A")
        copied = docs.DocsSync(self.project, self.vault, "pull", ("docs/**/*.md",)).pull(dry_run=True)
        self.assertEqual([self.project / "docs/a.md"], copied)
        self.assertFalse((self.project / "docs").exists())

    def test_patterns_cannot_leave_the_vault(self):
        write(self.root, "outside.md", "x")
        sync = docs.DocsSync(self.project, self.vault, "pull", ("../*.md", "/etc/*.md", ""))
        self.assertEqual([], sync.pull())


class TestPush(TempCase):
    def sync(self):
        return docs.DocsSync(self.project, self.vault, "push", ("docs/**/*.md",))

    def test_new_file_is_copied(self):
        write(self.project, "docs/a.md", "# A")
        sync = self.sync()
        self.assertEqual([self.vault / "docs/a.md"], sync.push())
        self.assertEqual("# A", (self.vault / "docs/a.md").read_text(encoding="utf-8"))
        self.assertEqual([], sync.conflicts)

    def test_same_content_is_left_alone(self):
        write(self.project, "docs/a.md", "# A")
        write(self.vault, "docs/a.md", "# A")
        sync = self.sync()
        self.assertEqual([], sync.push())
        self.assertEqual([], sync.conflicts)

    def test_different_content_is_a_conflict(self):
        write(self.project, "docs/a.md", "project")
        write(self.vault, "docs/a.md", "vault")
        sync = self.sync()
        self.assertEqual([], sync.push())
        self.assertEqual([self.vault / "docs/a.md"], sync.conflicts)
        self.assertEqual("vault", (self.vault / "docs/a.md").read_text(encoding="utf-8"))

    def test_force_replaces(self):
        write(self.project, "docs/a.md", "project")
        write(self.vault, "docs/a.md", "vault")
        sync = self.sync()
        self.assertEqual([self.vault / "docs/a.md"], sync.push(force=True))
        self.assertEqual("project", (self.vault / "docs/a.md").read_text(encoding="utf-8"))
        self.assertEqual([], sync.conflicts)

    def test_dry_run_writes_nothing(self):
        write(self.project, "docs/a.md", "new")
        write(self.project, "docs/b.md", "project")
        write(self.vault, "docs/b.md", "vault")
        sync = self.sync()
        self.assertEqual([self.vault / "docs/a.md"], sync.push(dry_run=True))
        self.assertFalse((self.vault / "docs/a.md").exists())
        self.assertEqual("vault", (self.vault / "docs/b.md").read_text(encoding="utf-8"))
        self.assertEqual([self.vault / "docs/b.md"], sync.conflicts)

    def test_never_deletes(self):
        write(self.vault, "docs/only-in-vault.md", "keep")
        write(self.project, "docs/a.md", "# A")
        self.sync().push(force=True)
        self.assertTrue((self.vault / "docs/only-in-vault.md").exists())

    def test_missing_vault_is_soft(self):
        write(self.project, "docs/a.md", "# A")
        self.assertEqual([], docs.DocsSync(self.project, None).push())


class TestScript(TempCase):
    def bash_n(self, script: Path) -> None:
        bash = shutil.which("bash")
        if bash:
            result = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_valid_executable_script(self):
        sync = docs.DocsSync(self.project, Path("/vaults/Brain"), "bidirectional", ("docs/**/*.md",))
        script = sync.write_script()
        self.assertEqual(self.project / ".claude" / "sync-brain.sh", script)
        text = script.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env bash"))
        self.assertIn("# Generated by brain docs script", text)
        self.assertIn("BRAIN='/vaults/Brain'", text)
        self.assertIn('DIRECTION="${1:-bidirectional}"', text)
        self.assertEqual(0o755, stat.S_IMODE(script.stat().st_mode))
        self.bash_n(script)

    def test_without_vault_the_script_explains(self):
        script = docs.DocsSync(self.project, None).write_script()
        self.assertIn("BRAIN is not set: run brain vault to check the vault path", script.read_text(encoding="utf-8"))
        self.bash_n(script)

    def test_quote_with_apostrophe(self):
        self.assertEqual("'it'\\''s'", docs._shell_quote("it's"))
        sync = docs.DocsSync(self.project, Path("/vaults/o'brien"), "pull", ("docs/it's.md",))
        script = sync.write_script()
        self.bash_n(script)
        text = script.read_text(encoding="utf-8")
        self.assertIn("BRAIN='/vaults/o'\\''brien'", text)
        self.assertIn("PATTERNS=('docs/it'\\''s.md')", text)

    def test_script_runs_pull_and_push(self):
        write(self.vault, "docs/from-vault.md", "v")
        write(self.project, "docs/from-project.md", "p")
        script = docs.DocsSync(self.project, self.vault, "bidirectional", ("docs/**/*.md",)).write_script()
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.project / "docs/from-vault.md").exists())
        self.assertTrue((self.vault / "docs/from-project.md").exists())

    def test_script_rejects_unknown_direction(self):
        script = docs.DocsSync(self.project, self.vault).write_script()
        result = subprocess.run(["bash", str(script), "sideways"], capture_output=True, text=True)
        self.assertEqual(2, result.returncode)

    def test_script_push_preserves_conflicts_and_copies_other_files(self):
        existing = write(self.vault, "docs/conflict.md", "user edit")
        before = existing.stat().st_mtime_ns
        write(self.project, "docs/conflict.md", "repository copy")
        write(self.project, "docs/new.md", "new")
        script = docs.DocsSync(self.project, self.vault, "push", ("docs/**/*.md",)).write_script()
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertIn("DOCS_CONFLICT", result.stderr)
        self.assertEqual("user edit", existing.read_text())
        self.assertEqual(before, existing.stat().st_mtime_ns)
        self.assertEqual("new", (self.vault / "docs/new.md").read_text())

    def test_script_push_force_replaces_a_conflict(self):
        write(self.vault, "README.md", "user edit")
        write(self.project, "README.md", "repository copy")
        script = docs.DocsSync(self.project, self.vault, patterns=("README.md",)).write_script()
        result = subprocess.run(["bash", str(script), "push", "--force"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("repository copy", (self.vault / "README.md").read_text())

    def test_script_push_leaves_identical_files_untouched(self):
        existing = write(self.vault, "README.md", "same")
        before = existing.stat().st_mtime_ns
        write(self.project, "README.md", "same")
        script = docs.DocsSync(self.project, self.vault, patterns=("README.md",)).write_script()
        result = subprocess.run(["bash", str(script), "push"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, existing.stat().st_mtime_ns)

    def test_script_rejects_unknown_option(self):
        script = docs.DocsSync(self.project, self.vault).write_script()
        result = subprocess.run(["bash", str(script), "push", "--overwrite"], capture_output=True, text=True)
        self.assertEqual(2, result.returncode)


class TestFromSettings(TempCase):
    def settings_for(self):
        return settings.load(self.project, env=self.env, home=self.home)

    def test_uses_the_configured_direction_and_patterns(self):
        self.machine_config(f'[brain]\nvault_path = "{self.vault}"\n')
        self.project_config('[brain.docs]\nenabled = true\ndirection = "push"\npatterns = ["notes/*.md"]\n')
        config = self.settings_for()
        sync = docs.DocsSync.from_settings(self.project, config, vault.resolve_vault(config, env=self.env, home=self.home))
        self.assertEqual((self.vault, "push", ("notes/*.md",)), (sync.vault, sync.direction, sync.patterns))

    def test_missing_vault_directory_gives_no_vault(self):
        self.machine_config('[brain]\nvault_path = "/does/not/exist"\n')
        config = self.settings_for()
        sync = docs.DocsSync.from_settings(self.project, config, vault.resolve_vault(config, env=self.env, home=self.home))
        self.assertIsNone(sync.vault)


class TestCli(CliCase):
    def setUp(self):
        super().setUp()
        write(self.vault, "docs/g/a.md", "a")
        write(self.vault, "README.md", "r")

    def docs_cmd(self, *args):
        return self.run_cli("docs", *args, "--project", str(self.project))

    def test_integrate_legacy_object_pulls_and_writes_the_script(self):
        self.legacy({"path": str(self.vault), "sync": {"direction": "pull"}})
        code, out, err = self.docs_cmd("integrate")
        self.assertEqual(0, code, err)
        self.assertIn("pull: copied files from the vault to the project: 2", out)
        self.assertIn("generated ", out)
        self.assertIn("(manual sync: bash sync-brain.sh [pull|push])", out)
        self.assertEqual("a", (self.project / "docs/g/a.md").read_text(encoding="utf-8"))
        script = self.project / ".claude" / "sync-brain.sh"
        self.assertEqual(0o755, stat.S_IMODE(script.stat().st_mode))
        self.assertEqual(0, subprocess.run(["bash", "-n", str(script)]).returncode)
        self.assertIn(settings.LEGACY_DOCS_WARNING, err)

    def test_integrate_push_direction_writes_only_the_script(self):
        self.legacy({"path": str(self.vault), "sync": {"direction": "push"}})
        code, out, _ = self.docs_cmd("integrate")
        self.assertEqual(0, code)
        self.assertNotIn("pull:", out)
        self.assertFalse((self.project / "docs").exists())
        self.assertTrue((self.project / ".claude" / "sync-brain.sh").exists())

    def test_integrate_legacy_string_is_off(self):
        self.legacy(str(self.vault))
        code, out, _ = self.docs_cmd("integrate")
        self.assertEqual((0, "  doc-sync is off\n"), (code, out))
        self.assertFalse((self.project / "docs").exists())
        self.assertFalse((self.project / ".claude").exists())

    def test_integrate_without_vault_is_off(self):
        self.project_config("[brain.docs]\nenabled = true\n")
        code, out, _ = self.docs_cmd("integrate")
        self.assertEqual((0, "  doc-sync is off\n"), (code, out))

    def test_integrate_with_missing_vault_directory_is_off_and_warns(self):
        self.machine_config('[brain]\nvault_path = "/does/not/exist"\n')
        self.project_config("[brain.docs]\nenabled = true\n")
        code, out, err = self.docs_cmd("integrate")
        self.assertEqual((0, "  doc-sync is off\n"), (code, out))
        self.assertIn("VAULT_MISSING", err)

    def test_integrate_disabled_by_default_is_off(self):
        self.machine_config(f'[brain]\nvault_path = "{self.vault}"\n')
        code, out, _ = self.docs_cmd("integrate")
        self.assertEqual((0, "  doc-sync is off\n"), (code, out))
        self.assertFalse((self.project / "README.md").exists())

    def test_integrate_dry_run_writes_nothing(self):
        self.legacy({"path": str(self.vault), "sync": {"direction": "bidirectional"}})
        code, out, _ = self.docs_cmd("integrate", "--dry-run")
        self.assertEqual(0, code)
        self.assertIn("[dry-run] would pull files from the vault", out)
        self.assertIn("[dry-run] would generate .claude/sync-brain.sh", out)
        self.assertEqual([".swissknife.json"], sorted(p.name for p in self.project.iterdir() if p.name != ".git"))

    def test_configuration_beats_the_legacy_object(self):
        other = self.root / "other"
        write(other, "docs/o.md", "o")
        self.legacy({"path": str(self.vault), "sync": {"direction": "pull"}})
        self.machine_config(f'[brain]\nvault_path = "{other}"\n')
        self.project_config('[brain.docs]\nenabled = true\npatterns = ["docs/**/*.md"]\n')
        code, out, err = self.docs_cmd("integrate")
        self.assertEqual(0, code, err)
        self.assertTrue((self.project / "docs/o.md").exists())
        self.assertFalse((self.project / "docs/g/a.md").exists())
        self.assertFalse((self.project / "README.md").exists())
        self.assertNotIn(settings.LEGACY_DOCS_WARNING, err)

    def test_pull_counts_and_lists_in_dry_run(self):
        self.configure_vault()
        code, out, _ = self.docs_cmd("pull", "--dry-run")
        self.assertEqual(0, code)
        self.assertIn("[dry-run] would copy README.md", out)
        self.assertFalse((self.project / "README.md").exists())
        code, out, _ = self.docs_cmd("pull")
        self.assertEqual(0, code)
        self.assertIn("copied 2 files", out)
        self.assertTrue((self.project / "README.md").exists())

    def test_pull_and_push_without_vault_fail(self):
        for command in ("pull", "push"):
            code, _, err = self.docs_cmd(command)
            self.assertEqual(1, code)
            self.assertIn("VAULT_NOT_FOUND", err)

    def test_push_new_same_conflict_force(self):
        self.configure_vault()
        write(self.project, "README.md", "r")
        write(self.project, "docs/new.md", "n")
        code, out, _ = self.docs_cmd("push")
        self.assertEqual(0, code)
        self.assertIn("copied docs/new.md", out)
        self.assertEqual("n", (self.vault / "docs/new.md").read_text(encoding="utf-8"))
        code, out, _ = self.docs_cmd("push")
        self.assertEqual((0, True), (code, "copied 0 files" in out))
        write(self.project, "README.md", "changed")
        code, out, err = self.docs_cmd("push")
        self.assertEqual(1, code)
        self.assertIn("DOCS_CONFLICT", err)
        self.assertIn("README.md", err)
        self.assertEqual("r", (self.vault / "README.md").read_text(encoding="utf-8"))
        code, _, err = self.docs_cmd("push", "--force")
        self.assertEqual(0, code, err)
        self.assertEqual("changed", (self.vault / "README.md").read_text(encoding="utf-8"))

    def test_push_dry_run_reports_conflicts_and_writes_nothing(self):
        self.configure_vault()
        write(self.project, "README.md", "changed")
        code, out, err = self.docs_cmd("push", "--dry-run")
        self.assertEqual(1, code)
        self.assertIn("DOCS_CONFLICT", err)
        self.assertEqual("r", (self.vault / "README.md").read_text(encoding="utf-8"))

    def test_script_command(self):
        self.configure_vault()
        code, out, _ = self.docs_cmd("script")
        self.assertEqual(0, code)
        self.assertEqual(str(self.project / ".claude" / "sync-brain.sh"), out.strip())
        self.assertIn(str(self.vault), (self.project / ".claude" / "sync-brain.sh").read_text(encoding="utf-8"))

    def test_usage_errors(self):
        for argv in (["docs"], ["docs", "integrate"], ["docs", "pull", "--force", "--project", "x"],
                     ["docs", "script", "--dry-run", "--project", "x"]):
            with self.assertRaises(SystemExit) as caught:
                self.run_cli(*argv)
            self.assertEqual(2, caught.exception.code)

    def test_invalid_configuration_exits_1(self):
        self.project_config('[brain.docs]\ndirection = "sideways"\n')
        code, _, err = self.docs_cmd("integrate")
        self.assertEqual(1, code)
        self.assertIn("direction", err)


if __name__ == "__main__":
    unittest.main()
