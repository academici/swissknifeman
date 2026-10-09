"""Scoped Git commits: ownership, literal paths, refusal atomicity and plan locking."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from planner.plan import cli, gitops, lifecycle, store, units
from planner.plan.model import PlanError

try:
    from . import demo, test_envelope
except ImportError:
    import demo
    import test_envelope


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class CommitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": tmp.name,
                    "GIT_CONFIG_GLOBAL": os.devnull}
        self.env.pop("GIT_INDEX_FILE", None)
        self.patch = mock.patch.dict(os.environ, self.env, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                           ("commit.gpgsign", "false")):
            self.git("config", key, value)
        self.root = demo.make_demo_plan(self.repo / "plans")
        (self.root / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        store.ensure_gitattributes(self.root)
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(
            task_files=[{"path": "src/**", "change": "modify"}], reads=[], status="todo", result=None))
        self.write("src/old.txt", "old\n")
        self.write("foreign.txt", "owner\n")
        self.git("add", "--", "plans", "src", "foreign.txt")
        self.git("commit", "-q", "-m", "base")

    def git(self, *args, check=True):
        return subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True, check=check)

    def write(self, path, text="changed\n"):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def commit(self, ref="P1.1", role="executor", **kwargs):
        return gitops.commit(self.root, ref, role=role, **kwargs)

    def changed(self):
        return set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD").stdout.rstrip("\0").split("\0"))

    def snapshot(self):
        return (self.git("rev-parse", "HEAD").stdout, (self.repo / ".git/index").read_bytes(),
                {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in self.repo.rglob("*")
                 if p.is_file() and ".git" not in p.relative_to(self.repo).parts and p.name != ".lock"})

    def refusal(self, code, **kwargs):
        before = self.snapshot()
        with self.assertRaises(PlanError) as cm:
            self.commit(**kwargs)
        self.assertEqual(cm.exception.code, code, str(cm.exception))
        self.assertEqual(self.snapshot(), before)

    def test_executor_finish_commits_exact_paths_and_trailers(self):
        self.write("src/old.txt")
        lifecycle.start(self.root, ["P1.1"], actor=demo.AUTHORING)
        lifecycle.finish(self.root, "P1.1", status="done", checks={"V1": 0}, notes="done")
        before_log = (self.root / "log.jsonl").read_bytes()
        result = self.commit()
        self.assertEqual(result["sha"], self.git("rev-parse", "HEAD").stdout.strip())
        self.assertEqual(set(result["paths"]), self.changed())
        self.assertIn("src/old.txt", result["paths"])
        self.assertIn(str(self.root.relative_to(self.repo) / "phases/P1/P1.1.json"), result["paths"])
        self.assertEqual(result["paths_digest"], hashlib.sha256("\n".join(sorted(result["paths"])).encode()).hexdigest())
        message = self.git("log", "-1", "--format=%B").stdout
        for line in (f"Plan: {demo.PLAN_ID}", "Plan-Ref: P1.1", "Plan-Role: executor",
                     "Plan-Actor: claude-code/claude-opus-5-5/high"):
            self.assertIn(line, message)
        self.assertEqual((self.root / "log.jsonl").read_bytes(), before_log)
        self.assertEqual(self.git("status", "--porcelain").stdout, "")

    def test_outside_refusal_leaves_head_index_and_tree_unchanged(self):
        self.write("src/old.txt")
        self.write("foreign.txt")
        (self.root / ".gitattributes").unlink()
        self.refusal("OUTSIDE_SCOPE")

    def test_leave_outside_preserves_foreign_staged_and_unstaged_changes(self):
        self.write("foreign.txt", "staged\n")
        self.git("add", "--", "foreign.txt")
        self.write("foreign.txt", "unstaged\n")
        staged = self.git("show", ":foreign.txt").stdout
        self.write("src/old.txt")
        result = self.commit(leave_outside=True)
        self.assertEqual(result["outside"], ["foreign.txt"])
        self.assertEqual(self.changed(), {"src/old.txt"})
        self.assertEqual(self.git("show", ":foreign.txt").stdout, staged)
        self.assertEqual((self.repo / "foreign.txt").read_text(), "unstaged\n")

    def test_new_deleted_and_literal_unusual_filenames(self):
        (self.repo / "src/old.txt").unlink()
        names = ["src/new.txt", "src/a [*].txt", "src/line\nbreak.txt", "src/юникод.txt"]
        for name in names:
            self.write(name)
        result = self.commit()
        self.assertEqual(set(result["paths"]), {"src/old.txt", *names})
        self.assertEqual(self.changed(), set(result["paths"]))

    def test_rename_requires_both_paths_in_scope(self):
        self.git("mv", "src/old.txt", "src/new.txt")
        self.assertEqual(set(self.commit()["paths"]), {"src/old.txt", "src/new.txt"})

    def test_cross_scope_rename_is_entirely_outside(self):
        self.git("mv", "src/old.txt", "outside.txt")
        self.refusal("OUTSIDE_SCOPE")
        self.write("src/another.txt")
        result = self.commit(leave_outside=True)
        self.assertEqual(result["outside"], ["outside.txt", "src/old.txt"])
        self.assertEqual(self.changed(), {"src/another.txt"})
        self.assertEqual(self.git("diff", "--cached", "--name-status").stdout.strip(), "R100\tsrc/old.txt\toutside.txt")

    def test_cross_scope_rename_with_recreated_source_stays_outside(self):
        self.git("mv", "src/old.txt", "outside.txt")
        self.write("src/old.txt", "recreated\n")
        self.write("src/another.txt")
        result = self.commit(leave_outside=True)
        self.assertEqual(result["outside"], ["outside.txt", "src/old.txt"])
        self.assertEqual(result["paths"], ["src/another.txt"])
        self.assertEqual(self.changed(), {"src/another.txt"})
        self.assertEqual((self.repo / "src/old.txt").read_text(), "recreated\n")
        self.assertEqual(self.git("diff", "--cached", "--name-status").stdout.strip(), "R100\tsrc/old.txt\toutside.txt")

    def test_renamed_attributes_outside_are_not_recreated(self):
        path = self.root.relative_to(self.repo) / ".gitattributes"
        self.git("mv", "--", str(path), "outside-attributes")
        self.write("src/another.txt")
        result = self.commit(leave_outside=True)
        self.assertEqual(self.changed(), {"src/another.txt"})
        self.assertIn(str(path), result["outside"])
        self.assertFalse((self.root / ".gitattributes").exists())

    def test_staged_only_deletion_and_explicit_extra_path(self):
        (self.repo / "src/old.txt").unlink()
        self.git("add", "-u", "--", "src/old.txt")
        self.assertEqual(self.commit()["paths"], ["src/old.txt"])
        self.write("foreign.txt")
        self.assertEqual(self.commit(paths=["foreign.txt"])["paths"], ["foreign.txt"])

    def test_repository_path_with_trailing_space(self):
        relative = self.root.relative_to(self.repo)
        renamed = self.repo.with_name("repo ")
        self.repo.rename(renamed)
        self.repo, self.root = renamed, renamed / relative
        self.write("src/old.txt")
        self.assertEqual(self.commit()["paths"], ["src/old.txt"])

    def test_invalid_attributes_encoding_is_a_clean_refusal(self):
        (self.root / ".gitattributes").write_bytes(b"\xff\n")
        self.refusal("CONTENT_INVALID")

    def test_failed_hook_preserves_existing_attribute_mode(self):
        attr = self.root / ".gitattributes"
        attr.write_text("*.json text\n")
        attr.chmod(0o755)
        before_mode = attr.stat().st_mode
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.refusal("GIT_FAILED")
        self.assertEqual(attr.stat().st_mode, before_mode)

    def test_reviewer_only_commits_plan_material(self):
        self.write("src/old.txt")
        self.refusal("OUTSIDE_SCOPE", role="reviewer")
        note = self.root / "knowledge/report.json"
        note.parent.mkdir(exist_ok=True)
        note.write_text("{}\n")
        result = self.commit(role="reviewer", leave_outside=True)
        self.assertEqual(self.changed(), {note.relative_to(self.repo).as_posix()})
        self.assertTrue(result["message"].startswith("docs(demo):"))
        self.refusal("PATH_INVALID", role="reviewer", paths=["foreign.txt"])

    def test_unit_uses_unit_files_not_item_task_files(self):
        lifecycle.start(self.root, ["P1.1"], actor=demo.AUTHORING)
        units.add_unit(self.root, "P1.1", "Unit", {"files": ["unit.txt"]})
        self.write("unit.txt")
        self.write("src/old.txt")
        result = self.commit(ref="P1.1/U1", leave_outside=True)
        self.assertIn("unit.txt", result["paths"])
        self.assertEqual(result["outside"], ["src/old.txt"])
        self.assertIn("Plan-Ref: P1.1/U1", result["message"])

    def test_nothing_to_commit_and_unknown_or_invalid_ref(self):
        self.refusal("NOTHING_TO_COMMIT")
        for ref, code in (("P1.99", "REF_UNKNOWN"), ("P1.1/U99", "REF_UNKNOWN"),
                          ("D1", "REF_INVALID"), ("PLAN7.P1.1", "REF_INVALID"), ("bad", "REF_INVALID")):
            with self.subTest(ref=ref):
                self.refusal(code, ref=ref)

    def test_busy_git_and_index_lock_refuse_without_changes(self):
        self.write("src/old.txt")
        for marker in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply"):
            p = self.repo / ".git" / marker
            p.mkdir() if marker.startswith("rebase-") else p.write_text("busy\n")
            self.refusal("GIT_BUSY")
            p.rmdir() if p.is_dir() else p.unlink()
        (self.repo / ".git/index.lock").touch()
        self.refusal("GIT_FAILED")

    def test_unmerged_refuses_before_any_write(self):
        self.git("checkout", "-q", "-b", "other")
        self.write("src/old.txt", "other\n")
        self.git("add", "--", "src/old.txt")
        self.git("commit", "-qm", "other")
        self.git("checkout", "-q", "main")
        self.write("src/old.txt", "main\n")
        self.git("add", "--", "src/old.txt")
        self.git("commit", "-qm", "main")
        self.git("merge", "other", check=False)
        (self.repo / ".git/MERGE_HEAD").unlink()  # test porcelain u independently of busy marker
        self.refusal("GIT_CONFLICT")

    def test_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = demo.make_demo_plan(Path(tmp) / "plans")
            with self.assertRaises(PlanError) as cm:
                gitops.commit(root, "P1.1", role="executor")
            self.assertEqual(cm.exception.code, "GIT_UNAVAILABLE")

    def test_attributes_are_created_or_appended_and_committed(self):
        for content in (None, "*.json text"):
            with self.subTest(content=content):
                p = self.root / ".gitattributes"
                if content is None:
                    self.git("rm", "--", str(p))
                    self.git("commit", "-qm", "legacy plan without attributes")
                else:
                    p.write_text(content)
                result = self.commit()
                self.assertIn(p.relative_to(self.repo).as_posix(), result["paths"])
                self.assertEqual(p.read_text(), (content + "\n" if content else "") + "log.jsonl merge=union\n")

    def test_dry_run_does_not_write_attributes_or_git(self):
        (self.root / ".gitattributes").unlink()
        self.write("src/old.txt")
        before = self.snapshot()
        result = self.commit(dry_run=True)
        self.assertIsNone(result["sha"])
        self.assertIn("src/old.txt", result["paths"])
        self.assertEqual(self.snapshot(), before)

    def test_hook_failure_restores_index_and_generated_attributes(self):
        self.write("src/new.txt")
        self.write("foreign.txt", "staged\n")
        self.git("add", "--", "foreign.txt")
        (self.root / ".gitattributes").unlink()
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.refusal("GIT_FAILED", leave_outside=True)

    def test_lock_held_through_head_read_and_refusal_on_contention(self):
        self.write("src/old.txt")
        real_git = gitops._git
        def checked(repo, *args, **kwargs):
            if args == ("rev-parse", "HEAD"):
                self.assertTrue((self.repo / ".git/index.lock").exists())
                with self.assertRaises(PlanError) as cm:
                    with store.PlanLock(self.root, timeout=0):
                        pass
                self.assertEqual(cm.exception.code, "PLAN_LOCKED")
            return real_git(repo, *args, **kwargs)
        with mock.patch.object(gitops, "_git", side_effect=checked):
            self.commit()
        with store.PlanLock(self.root):
            real_lock = store.PlanLock
            with mock.patch.object(store, "PlanLock", side_effect=lambda root: real_lock(root, timeout=0)):
                self.refusal("PLAN_LOCKED")

    def test_failed_add_preserves_the_original_index(self):
        self.write("src/new.txt")
        (self.root / ".gitattributes").unlink()
        real_git = gitops._git
        def fail(repo, *args, **kwargs):
            if args[:2] == ("--literal-pathspecs", "add"):
                real_git(repo, *args, **kwargs)
                raise PlanError("GIT_FAILED", "injected failure after private staging")
            return real_git(repo, *args, **kwargs)
        with mock.patch.object(gitops, "_git", side_effect=fail):
            self.refusal("GIT_FAILED")

    def test_competing_plan_cannot_enter_the_index_transaction(self):
        other = demo.make_demo_plan(self.repo / "other-plans")
        (other / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        self.write("src/new.txt")
        real_git = gitops._git
        attempted = []
        def compete(repo, *args, **kwargs):
            if args[:2] == ("--literal-pathspecs", "add") and not attempted:
                attempted.append(True)
                before = self.snapshot()
                with self.assertRaises(PlanError) as cm:
                    gitops.commit(other, "P1.1", role="executor", leave_outside=True)
                self.assertEqual(cm.exception.code, "GIT_FAILED")
                self.assertEqual(self.snapshot(), before)
            return real_git(repo, *args, **kwargs)
        with mock.patch.object(gitops, "_git", side_effect=compete):
            self.commit(leave_outside=True)
        self.assertEqual(attempted, [True])

    def test_segment_globs_and_directory_prefixes(self):
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(task_files=[
            {"path": "src/*.txt", "change": "modify"}, {"path": "deep/**/x?.txt", "change": "create"},
            {"path": "folder/", "change": "create"}]))
        for path in ("src/top.txt", "src/nested/x.txt", "deep/x1.txt", "deep/a/b/x2.txt", "folder/sub/y"):
            self.write(path)
        result = self.commit(leave_outside=True)
        self.assertEqual(result["outside"], ["src/nested/x.txt"])
        self.assertTrue({"deep/x1.txt", "deep/a/b/x2.txt", "folder/sub/y"} <= set(result["paths"]))

    def test_explicit_paths_never_allow_runtime_plan_files(self):
        p = self.root / "context/private.txt"
        p.parent.mkdir(exist_ok=True)
        p.write_text("runtime\n")
        self.git("add", "-f", "--", str(p))
        self.refusal("OUTSIDE_SCOPE", paths=[str(self.root.relative_to(self.repo)) + "/"])
        self.refusal("PATH_INVALID", paths=["../escape"])

    def test_message_settings_overrides_and_protected_trailers(self):
        demo.rewrite(self.root, "plan.json", lambda d: d["settings"].update(commit={
            "scope": "task", "trailers": ["Co-Authored-By: Test <test@example.invalid>"]}))
        result = self.commit(role="fix", summary="one\ntwo", commit_type="refactor", scope="custom",
                             actor={"provider": "codex", "model": "gpt-6.1-sol", "effort": "high"},
                             trailers=["Reviewed-By: Test"])
        self.assertTrue(result["message"].startswith("refactor(custom): one two (PLAN7.P1.1)"))
        self.assertIn("Co-Authored-By:", result["message"])
        self.assertIn("Reviewed-By: Test", result["message"])
        for trailer in ("Plan: spoofed", "Plan-Role: reviewer", "Extra: ok\nPlan: spoofed"):
            self.refusal("CONTENT_INVALID", trailers=[trailer])

    def test_cli_json_and_envelope(self):
        self.write("src/old.txt")
        args = ("commit", str(self.root), "P1.1", "--role", "executor", "--dry-run", "--json")
        code, out, err = test_envelope.run(*args)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["role"], "executor")
        code, out, err = test_envelope.run("--output", "json", *args)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(json.loads(out)["ok"])


if __name__ == "__main__":
    unittest.main()
