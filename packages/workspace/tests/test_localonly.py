"""The local-only index and the `.git/info/exclude` block."""
import json
import os
import subprocess
import unittest
from unittest import mock

from aicore.util import schema
from aicore.workspace import WorkspaceError, new_id, write_project

from tests import MODULE_ROOT, TempCase, git
from workspace import layout, localonly, safety

SMALL = safety.Settings(max_tracked_bytes=1000, max_binary_tracked_bytes=100)
DEVICE_A = "dev_01JC0Z8Q3M5T7V9XABCDEFGHJK"
DEVICE_B = "dev_01JC0Z8Q3M5T7V9XABCDEFGHJM"


class LocalOnlyCase(TempCase):
    def setUp(self):
        super().setUp()
        layout.init()
        self.pid = new_id("prj")
        write_project(self.ws, self.pid, "demo")
        self.folder = self.ws / "projects" / self.pid
        self.exclude = self.ws / ".git" / "info" / "exclude"

    def put(self, relative, content="x" * 2000):
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return relative

    def ignored(self, relative):
        done = subprocess.run(["git", "-C", str(self.ws), "check-ignore", "-q", f"projects/{self.pid}/{relative}"])
        return done.returncode == 0

    def valid(self, document):
        registry, kind = schema.load_contract(
            MODULE_ROOT.parent / "aicore" / "schemas" / "workspace-local-only" / "v1")
        self.assertEqual(schema.validate(document, kind, registry), [])


class IndexTests(LocalOnlyCase):
    def test_update_writes_a_sorted_valid_portable_index(self):
        self.put("plans/p1/b.log", b"b" * 2000)
        self.put("plans/p1/a.log", b"a" * 3000)
        document = localonly.update(self.ws, self.pid, [{"path": "plans/p1/b.log", "reason": "size"},
                                                         {"path": "plans/p1/a.log", "reason": "binary"}], DEVICE_A)
        self.valid(document)
        self.assertEqual([item["path"] for item in document["files"]], ["plans/p1/a.log", "plans/p1/b.log"])
        first = document["files"][0]
        import hashlib
        self.assertEqual((first["bytes"], first["sha256"], first["device_id"], first["reason"]),
                         (3000, hashlib.sha256(b"a" * 3000).hexdigest(), DEVICE_A, "binary"))
        on_disk = json.loads((self.folder / "local-only.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, document)
        self.assertEqual(localonly.read(self.ws, self.pid), document)
        text = (self.folder / "local-only.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), text)
        self.assertEqual(safety.scan(self.ws, [f"projects/{self.pid}/local-only.json"]).block, [])

    def test_an_unchanged_update_does_not_rewrite_the_file(self):
        self.put("big.log")
        entry = [{"path": "big.log", "reason": "size"}]
        localonly.update(self.ws, self.pid, entry, DEVICE_A)
        with mock.patch.object(localonly, "atomic_write_text") as write:
            localonly.update(self.ws, self.pid, entry, DEVICE_A)
        write.assert_not_called()

    def test_other_devices_are_kept_and_this_device_is_replaced(self):
        self.put("one.log")
        self.put("two.log")
        localonly.update(self.ws, self.pid, [{"path": "one.log", "reason": "size"}], DEVICE_A)
        localonly.update(self.ws, self.pid, [{"path": "one.log", "reason": "size"}, {"path": "two.log", "reason": "size"}],
                         DEVICE_B)
        files = localonly.read(self.ws, self.pid)["files"]
        self.assertEqual([(item["path"], item["device_id"]) for item in files],
                         [("one.log", DEVICE_A), ("one.log", DEVICE_B), ("two.log", DEVICE_B)])
        document = localonly.update(self.ws, self.pid, [{"path": "two.log", "reason": "size"}], DEVICE_A)
        self.assertEqual([(item["path"], item["device_id"]) for item in document["files"]],
                         [("one.log", DEVICE_B), ("two.log", DEVICE_A), ("two.log", DEVICE_B)])
        document = localonly.update(self.ws, self.pid, [], DEVICE_B)
        self.assertEqual([item["device_id"] for item in document["files"]], [DEVICE_A])

    def test_no_entries_and_no_index_writes_nothing_but_an_existing_index_is_emptied(self):
        self.assertEqual(localonly.update(self.ws, self.pid, [], DEVICE_A)["files"], [])
        self.assertFalse((self.folder / "local-only.json").exists())
        self.put("big.log")
        localonly.update(self.ws, self.pid, [{"path": "big.log", "reason": "size"}], DEVICE_A)
        self.assertEqual(localonly.update(self.ws, self.pid, [], DEVICE_A)["files"], [])
        self.assertEqual(json.loads((self.folder / "local-only.json").read_text(encoding="utf-8"))["files"], [])

    def test_bad_entries_are_refused_and_change_nothing(self):
        self.put("big.log")
        os.symlink("big.log", self.folder / "link.log")
        for path in ("missing.log", "../escape", "/abs/path", "a//b", "./big.log", "a\\b", "", "link.log"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                localonly.update(self.ws, self.pid, [{"path": path, "reason": "size"}], DEVICE_A)
        with self.assertRaises(ValueError):
            localonly.update(self.ws, self.pid, [{"path": "big.log", "reason": "huge"}], DEVICE_A)
        self.assertFalse((self.folder / "local-only.json").exists())

    def test_an_unknown_project_and_a_damaged_index(self):
        with self.assertRaises(WorkspaceError) as caught:
            localonly.update(self.ws, new_id("prj"), [], DEVICE_A)
        self.assertEqual(caught.exception.code, "PROJECT_UNKNOWN")
        (self.folder / "local-only.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            localonly.read(self.ws, self.pid)
        self.assertEqual(caught.exception.code, "WORKSPACE_LAYOUT_INVALID")
        with self.assertRaises(WorkspaceError):
            localonly.update(self.ws, self.pid, [], DEVICE_A)

    def test_entries_by_project_and_device_paths(self):
        self.put("plans/p1/big.log")
        self.put("plans/p1/other.bin")
        other = new_id("prj")
        write_project(self.ws, other, "other")
        report = safety.Report(local_only=[
            {"path": f"projects/{self.pid}/plans/p1/big.log", "bytes": 2000, "reason": "size"},
            {"path": f"projects/{self.pid}/plans/p1/other.bin", "bytes": 200, "reason": "binary"},
            {"path": f"projects/{other}/plans/x.log", "bytes": 1, "reason": "size"},
            {"path": "stray.bin", "bytes": 1, "reason": "size"}])
        grouped = localonly.entries_by_project(report)
        self.assertEqual(sorted(grouped), sorted([self.pid, other]))
        self.assertEqual(grouped[self.pid], [{"path": "plans/p1/big.log", "reason": "size"},
                                             {"path": "plans/p1/other.bin", "reason": "binary"}])
        localonly.update(self.ws, self.pid, grouped[self.pid], DEVICE_A)
        self.assertEqual(localonly.device_paths(self.ws, DEVICE_A),
                         [f"projects/{self.pid}/plans/p1/big.log", f"projects/{self.pid}/plans/p1/other.bin"])
        self.assertEqual(localonly.device_paths(self.ws, DEVICE_B), [])


class ExcludeTests(LocalOnlyCase):
    def indexed(self, device=DEVICE_A, **files):
        for relative in files:
            self.put(relative)
        localonly.update(self.ws, self.pid, [{"path": relative, "reason": "size"} for relative in files], device)

    def test_the_block_hides_the_files_of_this_device_from_git(self):
        self.indexed(**{"plans/p1/big.log": 1})
        self.assertFalse(self.ignored("plans/p1/big.log"))
        patterns = localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertEqual(patterns, [f"/projects/{self.pid}/plans/p1/big.log"])
        text = self.exclude.read_text(encoding="utf-8")
        self.assertIn(f"{localonly.BEGIN}\n/projects/{self.pid}/plans/p1/big.log\n{localonly.END}\n", text)
        self.assertTrue(self.ignored("plans/p1/big.log"))
        self.assertNotIn(f"projects/{self.pid}/plans/p1/big.log", safety.changed_paths(self.ws))

    def test_lines_outside_the_block_are_never_touched(self):
        self.exclude.write_text("# my own\n*.scratch\n\n", encoding="utf-8")
        self.indexed(**{"a.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.exclude.write_text(self.exclude.read_text(encoding="utf-8") + "tail-line\n", encoding="utf-8")
        self.indexed(**{"a.log": 1, "b.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        lines = self.exclude.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:3], ["# my own", "*.scratch", ""])
        self.assertEqual(lines[-1], "tail-line")
        block = lines[lines.index(localonly.BEGIN):lines.index(localonly.END) + 1]
        self.assertEqual(block, [localonly.BEGIN, f"/projects/{self.pid}/a.log", f"/projects/{self.pid}/b.log", localonly.END])
        self.assertEqual(lines.count(localonly.BEGIN), 1)

    def test_rebuild_is_idempotent_and_replaces_the_whole_block(self):
        self.indexed(**{"a.log": 1, "b.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        before = self.exclude.read_text(encoding="utf-8")
        with mock.patch.object(localonly, "atomic_write_text") as write:
            localonly.rebuild_exclude(self.ws, DEVICE_A)
        write.assert_not_called()
        self.assertEqual(self.exclude.read_text(encoding="utf-8"), before)
        self.indexed(**{"b.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertNotIn("a.log", self.exclude.read_text(encoding="utf-8"))
        self.assertFalse(self.ignored("a.log"))
        self.assertTrue(self.ignored("b.log"))

    def test_with_no_entries_an_existing_block_becomes_empty_and_no_block_is_not_created(self):
        before = self.exclude.read_text(encoding="utf-8")
        self.assertEqual(localonly.rebuild_exclude(self.ws, DEVICE_A), [])
        self.assertEqual(self.exclude.read_text(encoding="utf-8"), before)
        self.indexed(**{"a.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        localonly.update(self.ws, self.pid, [], DEVICE_A)
        self.assertEqual(localonly.rebuild_exclude(self.ws, DEVICE_A), [])
        self.assertIn(f"{localonly.BEGIN}\n{localonly.END}\n", self.exclude.read_text(encoding="utf-8"))

    def test_only_the_files_of_the_current_device_are_excluded(self):
        self.indexed(DEVICE_A, **{"mine.log": 1})
        self.put("theirs.log")
        localonly.update(self.ws, self.pid, [{"path": "mine.log", "reason": "size"}], DEVICE_A)
        localonly.update(self.ws, self.pid, [{"path": "theirs.log", "reason": "size"}], DEVICE_B)
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertTrue(self.ignored("mine.log"))
        self.assertFalse(self.ignored("theirs.log"))

    def test_special_characters_are_escaped(self):
        names = ["a[1].bin", "#hash.log", "with space.log", "star*.log", "q?.log", "trail "]
        self.indexed(**{name: 1 for name in names})
        patterns = localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertEqual(len(patterns), len(names))
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(self.ignored(name), name)
        self.put("a1.bin")  # a bracket pattern would have matched this
        self.put("starX.log")
        self.assertFalse(self.ignored("a1.bin"))
        self.assertFalse(self.ignored("starX.log"))

    def test_a_begin_without_an_end_is_refused_and_the_file_is_untouched(self):
        self.exclude.write_text(f"keep\n{localonly.BEGIN}\n/x\n", encoding="utf-8")
        self.indexed(**{"a.log": 1})
        with self.assertRaises(WorkspaceError) as caught:
            localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertEqual(caught.exception.code, "WORKSPACE_LAYOUT_INVALID")
        self.assertEqual(self.exclude.read_text(encoding="utf-8"), f"keep\n{localonly.BEGIN}\n/x\n")

    def test_two_blocks_become_one_at_the_place_of_the_first(self):
        self.exclude.write_text(f"head\n{localonly.BEGIN}\n/old\n{localonly.END}\nmiddle\n{localonly.BEGIN}\n/older\n"
                                f"{localonly.END}\ntail\n", encoding="utf-8")
        self.indexed(**{"a.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertEqual(self.exclude.read_text(encoding="utf-8").splitlines(),
                         ["head", localonly.BEGIN, f"/projects/{self.pid}/a.log", localonly.END, "middle", "tail"])

    def test_a_missing_exclude_file_and_a_folder_that_is_not_a_repository(self):
        self.exclude.unlink()
        self.assertEqual(localonly.rebuild_exclude(self.ws, DEVICE_A), [])
        self.assertFalse(self.exclude.exists())
        self.indexed(**{"a.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.assertTrue(self.exclude.is_file())
        with self.assertRaises(WorkspaceError):
            localonly.rebuild_exclude(self.root / "home", DEVICE_A)

    def test_the_whole_cycle_keeps_a_large_file_out_of_the_next_commit(self):
        relative = self.put("plans/p1/artifacts/dump.sql", "x" * 6000)
        small = self.put("plans/p1/plan.json", "{}")
        first = safety.check(self.ws, env=None, home=None)
        report = safety.scan(self.ws, safety.changed_paths(self.ws), SMALL)
        self.assertEqual([item["path"] for item in report.local_only], [f"projects/{self.pid}/{relative}"])
        for project_id, entries in localonly.entries_by_project(report).items():
            localonly.update(self.ws, project_id, entries, DEVICE_A)
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        after = safety.scan(self.ws, safety.changed_paths(self.ws), SMALL)
        self.assertEqual(after.local_only, [])
        self.assertNotIn(f"projects/{self.pid}/{relative}", safety.changed_paths(self.ws))
        self.assertIn(f"projects/{self.pid}/local-only.json", safety.changed_paths(self.ws))
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "plans")
        tracked = git(self.ws, "ls-files").split("\n")
        self.assertNotIn(f"projects/{self.pid}/{relative}", tracked)
        self.assertIn(f"projects/{self.pid}/plans/p1/plan.json", tracked)
        self.assertEqual(first.verdict, "ok")

    def test_an_already_tracked_file_is_reported_not_untracked(self):
        relative = self.put("big.log", "x" * 6000)
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "big")
        self.indexed(**{"big.log": 1})
        localonly.rebuild_exclude(self.ws, DEVICE_A)
        self.put("big.log", "y" * 6000)
        git(self.ws, "ls-files", "--error-unmatch", f"projects/{self.pid}/big.log")  # still tracked
        report = safety.scan(self.ws, safety.changed_paths(self.ws), SMALL)
        self.assertIn(("PS-TRACKED-LOCAL-ONLY", f"projects/{self.pid}/{relative}"),
                      [(item["rule"], item["path"]) for item in report.warn])
        self.assertIn(f"projects/{self.pid}/big.log", git(self.ws, "ls-files").split("\n"))  # nothing removed from the index


if __name__ == "__main__":
    unittest.main()
