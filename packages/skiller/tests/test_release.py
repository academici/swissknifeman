"""Тесты `skiller release` (P5.3) — сборка предложения релиза монорепо.

Юнит-уровень (classify_bump/bump_version/секция Unreleased) — без git, чистые
функции на синтетических данных. Интеграционный уровень (cmd_release,
`bin/swissknifeman release`) — на СИНТЕТИЧЕСКОМ tmp-git-репо (никогда не касается
реального корневого CHANGELOG.md — он permission-deny этой среды, прецедент P2.4)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from skiller.common import Env
from skiller.release import (bump_version, classify_bump, cmd_release,
                             read_unreleased_section, unreleased_is_empty)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # packages/skiller
MONOREPO_ROOT = PACKAGE_ROOT.parents[1]              # корень репо (swissknifeman)
SKILLER_BIN = PACKAGE_ROOT / "bin" / "skiller"
SWISSKNIFEMAN_BIN = MONOREPO_ROOT / "bin" / "swissknifeman"


class ClassifyBumpCase(unittest.TestCase):
    def test_feat_gives_minor(self):
        bump, reason = classify_bump([("feat: новая команда", ""),
                                      ("fix: мелкий баг", "")])
        self.assertEqual(bump, "minor")
        self.assertIsNone(reason)

    def test_only_fix_gives_patch(self):
        bump, reason = classify_bump([("fix: баг", ""), ("perf: ускорение", "")])
        self.assertEqual(bump, "patch")
        self.assertIsNone(reason)

    def test_bang_marker_is_breaking(self):
        bump, reason = classify_bump([("feat!: смена контракта", "")])
        self.assertEqual(bump, "breaking")
        self.assertEqual(reason, "feat!: смена контракта")

    def test_breaking_change_in_body_is_breaking(self):
        commits = [("feat: X", "BREAKING CHANGE: контракт поменялся")]
        bump, reason = classify_bump(commits)
        self.assertEqual(bump, "breaking")

    def test_breaking_short_circuits_even_with_earlier_feat(self):
        # breaking где-то в диапазоне — отказ независимо от порядка коммитов
        commits = [("feat: A", ""), ("fix!: B", "")]
        bump, _ = classify_bump(commits)
        self.assertEqual(bump, "breaking")

    def test_no_conventional_commits_gives_none(self):
        bump, reason = classify_bump([("случайный коммит без типа", "")])
        self.assertIsNone(bump)
        self.assertIsNone(reason)

    def test_docs_and_chore_do_not_trigger_bump(self):
        commits = [("docs: правка", ""), ("chore: уборка", "")]
        bump, _ = classify_bump(commits)
        self.assertIsNone(bump)

    def test_empty_range_gives_none(self):
        bump, reason = classify_bump([])
        self.assertIsNone(bump)
        self.assertIsNone(reason)


class BumpVersionCase(unittest.TestCase):
    def test_minor_bump_from_tag(self):
        self.assertEqual(bump_version("v0.7.1", "minor"), "v0.8.0")

    def test_patch_bump_from_tag(self):
        self.assertEqual(bump_version("v0.7.1", "patch"), "v0.7.2")

    def test_no_tag_minor_is_first_release(self):
        self.assertEqual(bump_version(None, "minor"), "v0.1.0")

    def test_no_tag_patch_is_first_release(self):
        self.assertEqual(bump_version(None, "patch"), "v0.0.1")

    def test_unparseable_tag_returns_none(self):
        self.assertIsNone(bump_version("not-a-tag", "minor"))


class UnreleasedSectionCase(unittest.TestCase):
    def test_reads_body_between_headings(self):
        text = ("# Changelog\n\n## [Unreleased]\n### Added\n- новая штука\n\n"
                "## [0.7.1] - 2026-06-28\n### Fixed\n- старое\n")
        lines, start, end, body = read_unreleased_section(text)
        self.assertIn("- новая штука", body)
        self.assertNotIn("- старое", body)

    def test_missing_section_returns_none(self):
        self.assertIsNone(read_unreleased_section("# Changelog\n\nnothing here\n"))

    def test_empty_section_detected(self):
        text = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n- x\n"
        _, _, _, body = read_unreleased_section(text)
        self.assertTrue(unreleased_is_empty(body))

    def test_section_with_only_group_headers_is_empty(self):
        text = "# Changelog\n\n## [Unreleased]\n### Added\n### Fixed\n\n## [0.1.0]\n"
        _, _, _, body = read_unreleased_section(text)
        self.assertTrue(unreleased_is_empty(body))

    def test_section_with_entry_is_not_empty(self):
        text = "# Changelog\n\n## [Unreleased]\n### Added\n- запись\n\n## [0.1.0]\n"
        _, _, _, body = read_unreleased_section(text)
        self.assertFalse(unreleased_is_empty(body))


def _init_repo(root):
    """Мини git-репо: init + первый коммит + CHANGELOG.md с заполненным
    [Unreleased], stdlib subprocess (без сети, без реальных remote)."""
    for cmd in (["git", "init", "-q"],
                ["git", "config", "user.email", "test@example.com"],
                ["git", "config", "user.name", "Test"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n### Added\n- заглушка\n\n"
        "## [0.7.1] - 2026-06-28\n### Fixed\n- старое\n", encoding="utf-8")
    subprocess.run(["git", "add", "CHANGELOG.md"], cwd=root, check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "chore: init"], cwd=root,
                   check=True, capture_output=True)
    subprocess.run(["git", "tag", "v0.7.1"], cwd=root, check=True,
                   capture_output=True)


def _commit(root, message):
    (root / f"file-{message[:8].replace(':', '')}.txt").write_text(message,
                                                                    encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True,
                   capture_output=True)


def _run_cli(fn, env, argv):
    import contextlib
    import io
    buf = io.StringIO()
    exc = None
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            fn(env, argv)
        except SystemExit as e:
            exc = e
    return exc, buf.getvalue()


@unittest.skipIf(subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
                 "git недоступен в окружении")
class CmdReleaseCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _init_repo(self.root)
        # env.root = каталог пакета (как в реальном запуске skiller <root=пакет> release);
        # find_monorepo_root в release.py обязан подняться к self.root по маркеру `packages/`
        # либо `core/` — здесь просто указываем root = сам git-репо (monorepo-корень).
        self.env = Env(self.root, home=self.root / "home")

    def tearDown(self):
        self._tmp.cleanup()

    def test_feat_commit_proposes_minor_dry_run_does_not_write(self):
        _commit(self.root, "feat: новая фича")
        exc, out = _run_cli(cmd_release, self.env, ["--dry-run"])
        self.assertIsNone(exc)
        self.assertIn("v0.7.1 -> v0.8.0", out)
        self.assertIn("[dry-run]", out)
        # CHANGELOG не тронут
        text = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]\n### Added\n- заглушка", text)

    def test_only_fix_commits_propose_patch(self):
        _commit(self.root, "fix: баг раз")
        exc, out = _run_cli(cmd_release, self.env, ["--dry-run"])
        self.assertIsNone(exc)
        self.assertIn("v0.7.1 -> v0.7.2", out)

    def test_breaking_marker_refuses_with_nonzero_exit(self):
        _commit(self.root, "feat!: смена контракта")
        exc, out = _run_cli(cmd_release, self.env, [])
        self.assertIsNotNone(exc)
        self.assertNotEqual(exc.code, 0)
        self.assertIn("MAJOR", out)

    def test_empty_range_says_nothing_to_release(self):
        _commit(self.root, "docs: правка")
        exc, out = _run_cli(cmd_release, self.env, [])
        self.assertIsNone(exc)
        self.assertIn("нечего релизить", out)

    def test_without_dry_run_moves_unreleased_section(self):
        _commit(self.root, "feat: новая фича")
        exc, out = _run_cli(cmd_release, self.env, [])
        self.assertIsNone(exc)
        text = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [v0.8.0] -", text)
        self.assertIn("- заглушка", text)
        # старая секция [Unreleased] освобождена
        section = text.split("## [Unreleased]", 1)[1].split("## [v0.8.0]", 1)[0]
        self.assertNotIn("- заглушка", section)

    def test_git_tag_command_is_only_printed_never_executed(self):
        _commit(self.root, "feat: новая фича")
        exc, out = _run_cli(cmd_release, self.env, [])
        self.assertIsNone(exc)
        self.assertIn("git tag -a v0.8.0", out)
        tags = subprocess.run(["git", "tag", "-l"], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout
        self.assertNotIn("v0.8.0", tags)  # тег НЕ создан автоматом


class SwissknifemanReleaseFacadeCase(unittest.TestCase):
    """Root-фасад `bin/swissknifeman release` → skiller (тестируем через реальный
    репозиторий swissknifeman, --dry-run: read-only, ничего не пишет)."""

    def test_help_mentions_release(self):
        proc = subprocess.run([str(SWISSKNIFEMAN_BIN), "--help"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("release", proc.stdout)

    def test_dry_run_reaches_skiller_without_error(self):
        proc = subprocess.run([str(SWISSKNIFEMAN_BIN), "release", "--dry-run"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_env_doctor_still_works(self):
        # риск среза: добавление группы release не должно ломать соседние (env).
        proc = subprocess.run([str(SWISSKNIFEMAN_BIN), "env", "doctor"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
