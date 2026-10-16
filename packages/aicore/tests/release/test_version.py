"""Release versions: the semver bump from commits, the last tag, free versions, the version files."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from aicore.release.version import (bump_version, classify_bump, commits_since, last_tag,
                                    next_available_version, sync_version_files)


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                   cwd=root, check=True, capture_output=True)


def _commit(root, message, name="file"):
    path = Path(root) / (name + str(len(list(Path(root).iterdir()))) + ".txt")
    path.write_text(message, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


class ClassifyBumpTests(unittest.TestCase):
    def test_feat_gives_minor(self):
        self.assertEqual(classify_bump([("feat: new command", ""), ("fix: bug", "")]), ("minor", None))

    def test_only_fix_and_perf_give_patch(self):
        self.assertEqual(classify_bump([("fix: bug", ""), ("perf(core): faster", "")]), ("patch", None))

    def test_bang_marker_is_breaking(self):
        self.assertEqual(classify_bump([("feat(api)!: change of contract", "")]),
                         ("breaking", "feat(api)!: change of contract"))

    def test_breaking_change_in_body_is_breaking(self):
        self.assertEqual(classify_bump([("feat: X", "BREAKING CHANGE: contract has changed")]),
                         ("breaking", "feat: X"))

    def test_breaking_wins_over_an_earlier_feat(self):
        self.assertEqual(classify_bump([("feat: A", ""), ("fix!: B", "")])[0], "breaking")

    def test_commits_without_signal_give_nothing(self):
        self.assertEqual(classify_bump([("random commit", ""), ("docs: edit", ""), ("chore: x", "")]),
                         (None, None))
        self.assertEqual(classify_bump([]), (None, None))


class BumpVersionTests(unittest.TestCase):
    def test_minor_and_patch_from_a_tag(self):
        self.assertEqual(bump_version("v0.7.1", "minor"), "v0.8.0")
        self.assertEqual(bump_version("v0.7.1", "patch"), "v0.7.2")

    def test_the_first_release_has_no_tag(self):
        self.assertEqual(bump_version(None, "minor"), "v0.1.0")
        self.assertEqual(bump_version(None, "patch"), "v0.0.1")

    def test_unparseable_tag_gives_none(self):
        self.assertIsNone(bump_version("not-a-tag", "minor"))


class GitHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def test_without_tags_there_is_no_last_tag_and_the_log_is_whole(self):
        _commit(self.root, "feat: first")
        self.assertIsNone(last_tag(self.root))
        self.assertEqual(commits_since(self.root, None), [("feat: first", "")])

    def test_outside_a_repository_there_is_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(last_tag(folder))
            self.assertEqual(commits_since(folder, None), [])

    def test_commits_since_the_tag_carry_subject_and_body(self):
        _commit(self.root, "chore: init")
        _git(self.root, "tag", "v0.7.1")
        _commit(self.root, "feat: new thing\n\nBREAKING CHANGE: contract")
        _commit(self.root, "fix: bug")
        self.assertEqual(last_tag(self.root), "v0.7.1")
        self.assertEqual(commits_since(self.root, "v0.7.1"),
                         [("fix: bug", ""), ("feat: new thing", "BREAKING CHANGE: contract")])

    def test_a_published_successor_moves_the_proposal_to_the_next_free_version(self):
        _commit(self.root, "chore: init")
        _git(self.root, "tag", "v0.7.1")
        _git(self.root, "tag", "v0.7.2")
        _git(self.root, "tag", "not-a-version")
        self.assertEqual(next_available_version(self.root, "v0.7.1", "patch"), "v0.7.3")
        self.assertEqual(next_available_version(self.root, "v0.7.1", "minor"), "v0.8.0")

    def test_an_unparseable_tag_gives_no_version(self):
        self.assertIsNone(next_available_version(self.root, "weird", "patch"))


class _Entry:
    def __init__(self, path, key):
        self.path, self.key = path, key


class SyncVersionFilesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_the_version_without_prefix_is_written_under_the_key(self):
        (self.root / "catalog.json").write_text('{"plugin_version": "0.1.0", "other": 1}', encoding="utf-8")
        sync_version_files(self.root, "v1.3.0", [_Entry("catalog.json", "plugin_version")])
        self.assertEqual(json.loads((self.root / "catalog.json").read_text()),
                         {"plugin_version": "1.3.0", "other": 1})

    def test_missing_files_are_skipped_and_current_ones_are_not_rewritten(self):
        path = self.root / "same.json"
        path.write_text('{"v":"1.3.0"}', encoding="utf-8")
        sync_version_files(self.root, "1.3.0", [_Entry("absent.json", "v"), _Entry("same.json", "v")])
        self.assertEqual(path.read_text(), '{"v":"1.3.0"}')
        self.assertFalse((self.root / "absent.json").exists())
