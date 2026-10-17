"""Scoped Git commits: ownership, literal paths, refusal atomicity and plan locking."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from planner.plan import gitops, lifecycle, store, units
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
        # The project journal of planner events lives in .swissknifeman/state, which the gitignore policy ignores.
        (self.repo / ".git" / "info" / "exclude").write_text(".swissknifeman/state/\n")
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
            with mock.patch.object(store, "PlanLock", side_effect=lambda root, **_: real_lock(root, timeout=0)):
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


PID = "prj_01JC0Z8Q3M5T7V9XABCDEFGHJM"


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class WorkspaceCommitTests(unittest.TestCase):
    """A plan in the portable workspace: product in the source repository, plan files in the workspace repository (D7)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.src, self.ws, self.home = base / "src-repo", base / "ws", base / "home"
        env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_") and k != "GIT_INDEX_FILE"}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, HOME=str(base), SKM_HOME=str(self.home),
                   SKM_WORKSPACE_ROOT=str(self.ws))
        patch = mock.patch.dict(os.environ, env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        for repo in (self.src, self.ws):
            repo.mkdir()
            self.git(repo, "init", "-q", "-b", "main")
            for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                               ("commit.gpgsign", "false"), ("gc.auto", "0"), ("maintenance.auto", "false")):
                self.git(repo, "config", key, value)  # no detached maintenance process writing during the cleanup
        (self.src / ".git/info/exclude").write_text(".swissknifeman/state/\n")
        self.write(self.src, ".swissknifeman/project.json", json.dumps({
            "$schema": "urn:swissknifeman:aicore:project-marker:v1", "project_id": PID, "plans_store": "workspace"}))
        self.write(self.src, "src/old.txt", "old\n")
        self.write(self.src, "foreign.txt", "owner\n")
        self.git(self.src, "add", "-A")
        self.git(self.src, "commit", "-q", "-m", "base")
        state = self.home / "state" / "workspace"
        state.mkdir(parents=True)
        (state / "bindings.json").write_text(json.dumps({
            "$schema": "urn:swissknifeman:aicore:workspace-bindings:v1",
            "projects": {PID: {"paths": [str(self.src)], "primary": str(self.src), "bound_at": "2026-10-17T09:30:00Z"}}}))
        self.root = demo.make_demo_plan(self.ws / "projects" / PID / "plans")
        (self.root / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        store.ensure_gitattributes(self.root)
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(
            task_files=[{"path": "src/**", "change": "modify"}], reads=[], status="todo", result=None))
        self.other = self.ws / "projects" / PID / "plans" / "other-plan"
        self.write(self.other, "plan.json", "{}\n")
        self.git(self.ws, "add", "-A")
        self.git(self.ws, "commit", "-q", "-m", "base")
        self.prefix = self.root.relative_to(self.ws).as_posix()

    def git(self, repo, *args):
        return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout

    def write(self, repo, path, text="changed\n"):
        p = Path(repo) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def commit(self, ref="P1.1", role="executor", **kwargs):
        return gitops.commit(self.root, ref, role=role, **kwargs)

    def changed(self, repo):
        return set(self.git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD").rstrip("\0").split("\0"))

    def head(self, repo):
        return self.git(repo, "rev-parse", "HEAD").strip()

    def start(self):
        """Bookkeeping dirt of an item and its journal. Written by hand: ``lifecycle.start`` would also spawn the detached
        delivery of the project event journal, which writes into the temporary directory while it is removed."""
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(status="in_progress"))
        event = store.new_event("note", "started", demo.AUTHORING)
        with (self.root / "log.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    def test_product_and_bookkeeping_are_two_linked_commits(self):
        self.write(self.src, "src/old.txt")
        self.start()
        result = self.commit()
        self.assertEqual((result["repo"], result["sha"], result["workspace_sha"]),
                         ("source", self.head(self.src), self.head(self.ws)))
        self.assertEqual(result["workspace_commit"], {"status": "committed"})
        self.assertEqual(result["paths"], ["src/old.txt"])
        self.assertEqual(self.changed(self.src), {"src/old.txt"})
        self.assertEqual(self.changed(self.ws), {f"{self.prefix}/phases/P1/P1.1.json", f"{self.prefix}/log.jsonl"})
        self.assertEqual(set(result["workspace_paths"]), self.changed(self.ws))
        source_message = self.git(self.src, "log", "-1", "--format=%B")
        ws_message = self.git(self.ws, "log", "-1", "--format=%B")
        self.assertEqual(ws_message.splitlines()[0], source_message.splitlines()[0])
        for line in (f"Plan: {demo.PLAN_ID}", "Plan-Ref: P1.1", "Plan-Role: executor"):
            self.assertIn(line, source_message)
            self.assertIn(line, ws_message)
        self.assertNotIn("Plan-Project", source_message)
        self.assertIn(f"Plan-Project: {PID}", ws_message)
        self.assertIn(f"Plan-Source-Commit: {result['sha']}", ws_message)
        self.assertEqual(self.git(self.src, "status", "--porcelain"), "")
        self.assertEqual(self.git(self.ws, "status", "--porcelain"), "")

    def test_reviewer_commits_plan_files_in_the_workspace_only(self):
        note = self.write(self.root, "knowledge/report.json", "{}\n")
        source_head = self.head(self.src)
        self.write(self.src, "src/old.txt")  # product dirt is not a reviewer's concern and is not even looked at
        result = self.commit(role="reviewer")
        self.assertEqual((result["repo"], result["sha"]), ("workspace", self.head(self.ws)))
        self.assertEqual(result["workspace_sha"], result["sha"])
        self.assertEqual(self.changed(self.ws), {note.relative_to(self.ws).as_posix()})
        self.assertEqual(set(result["paths"]), self.changed(self.ws))
        self.assertEqual(self.head(self.src), source_head)
        self.assertNotIn("Plan-Source-Commit", self.git(self.ws, "log", "-1", "--format=%B"))
        self.assertIn(f"Plan-Project: {PID}", self.git(self.ws, "log", "-1", "--format=%B"))

    def test_workspace_without_git_skips_the_plan_files(self):
        self.write(self.src, "src/old.txt")
        shutil.rmtree(self.ws / ".git")
        result = self.commit()
        self.assertEqual(result["sha"], self.head(self.src))
        self.assertEqual((result["workspace_sha"], result["workspace_commit"]), (None, {"status": "skipped-no-git"}))

    def test_busy_git_lock_leaves_the_plan_files_for_later(self):
        self.write(self.src, "src/old.txt")
        self.start()
        state = self.home / "state" / "workspace"
        fd = os.open(state / "git.lock", os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        workspace_head = self.head(self.ws)
        with mock.patch.object(gitops, "WORKSPACE_LOCK_TIMEOUT", 0.2):
            result = self.commit()
        self.assertEqual(result["sha"], self.head(self.src))
        self.assertEqual((result["workspace_sha"], result["workspace_commit"]["status"]), (None, "locked"))
        self.assertIn("WORKSPACE_GIT_LOCKED", result["workspace_commit"]["error"])
        self.assertEqual(self.head(self.ws), workspace_head)
        fcntl.flock(fd, fcntl.LOCK_UN)
        self.assertEqual(self.commit(role="fix")["workspace_commit"]["status"], "committed")  # the next commit takes them

    def test_dirty_files_of_other_plans_never_enter_the_workspace_commit(self):
        self.start()
        self.write(self.other, "plan.json", "dirty\n")
        self.write(self.other, "notes/new.txt")
        self.write(self.ws, "workspace.json", "{}\n")
        self.write(self.root, "context/pack.json", "{}\n")
        self.write(self.src, "src/old.txt")
        result = self.commit()  # no OUTSIDE_SCOPE for the workspace part
        self.assertEqual(result["workspace_commit"], {"status": "committed"})
        self.assertEqual(self.changed(self.ws), {f"{self.prefix}/phases/P1/P1.1.json", f"{self.prefix}/log.jsonl"})
        other = self.other.relative_to(self.ws).as_posix()
        self.assertEqual(set(result["workspace_outside"]), {f"{other}/plan.json", f"{other}/notes/new.txt", "workspace.json"})
        self.assertIn("workspace.json", self.git(self.ws, "status", "--porcelain"))

    def test_foreign_product_dirt_refuses_before_any_commit(self):
        self.write(self.src, "src/old.txt")
        self.write(self.src, "foreign.txt")
        self.start()
        heads = (self.head(self.src), self.head(self.ws))
        with self.assertRaises(PlanError) as cm:
            self.commit()
        self.assertEqual(cm.exception.code, "OUTSIDE_SCOPE")
        self.assertEqual((self.head(self.src), self.head(self.ws)), heads)
        result = self.commit(leave_outside=True)
        self.assertEqual(result["outside"], ["foreign.txt"])
        self.assertEqual(result["workspace_commit"]["status"], "committed")

    def test_failed_workspace_commit_keeps_the_product_commit(self):
        self.write(self.src, "src/old.txt")
        self.start()
        hook = self.ws / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\necho nope >&2\nexit 1\n")
        hook.chmod(0o755)
        workspace_head = self.head(self.ws)
        result = self.commit()
        self.assertEqual(result["sha"], self.head(self.src))
        self.assertEqual(result["workspace_commit"]["status"], "failed")
        self.assertTrue(result["workspace_commit"]["error"].startswith("GIT_FAILED:"), result["workspace_commit"])
        self.assertEqual(self.head(self.ws), workspace_head)
        self.assertFalse((self.ws / ".git/index.lock").exists())

    def test_nothing_in_both_repositories(self):
        with self.assertRaises(PlanError) as cm:
            self.commit()
        self.assertEqual(cm.exception.code, "NOTHING_TO_COMMIT")
        self.write(self.src, "src/old.txt")  # product only: the workspace part has nothing
        result = self.commit()
        self.assertEqual(result["workspace_commit"], {"status": "nothing"})
        self.assertEqual(result["workspace_sha"], None)

    def test_dry_run_shows_both_parts_and_writes_nothing(self):
        self.write(self.src, "src/old.txt")
        self.start()
        heads = (self.head(self.src), self.head(self.ws))
        status = (self.git(self.src, "status", "--porcelain"), self.git(self.ws, "status", "--porcelain"))
        result = self.commit(dry_run=True)
        self.assertEqual((result["sha"], result["workspace_sha"]), (None, None))
        self.assertEqual(result["paths"], ["src/old.txt"])
        self.assertEqual(set(result["workspace_paths"]), {f"{self.prefix}/phases/P1/P1.1.json", f"{self.prefix}/log.jsonl"})
        self.assertEqual((self.head(self.src), self.head(self.ws)), heads)
        self.assertEqual((self.git(self.src, "status", "--porcelain"), self.git(self.ws, "status", "--porcelain")), status)

    def test_plan_paths_route_to_the_workspace_and_product_paths_to_the_source(self):
        self.write(self.src, "foreign.txt")
        extra = self.write(self.root, "research/R1.json", "{}\n")
        result = self.commit(paths=["foreign.txt", "@plan/research/R1.json"])
        self.assertEqual(result["paths"], ["foreign.txt"])
        self.assertEqual(self.changed(self.ws), {extra.relative_to(self.ws).as_posix()})
        with self.assertRaises(PlanError) as cm:
            self.commit(role="reviewer", paths=["foreign.txt"])
        self.assertEqual(cm.exception.code, "PATH_INVALID")
        with self.assertRaises(PlanError) as cm:
            self.commit(paths=["../escape"])
        self.assertEqual(cm.exception.code, "PATH_INVALID")

    def test_unbound_source_refuses_an_executor_but_not_a_reviewer(self):
        (self.home / "state" / "workspace" / "bindings.json").unlink()
        self.write(self.root, "knowledge/report.json", "{}\n")
        with self.assertRaises(PlanError) as cm:
            self.commit()
        self.assertEqual(cm.exception.code, "PLAN_SOURCE_UNBOUND")
        self.assertEqual(self.commit(role="reviewer")["repo"], "workspace")

    def test_identity_trailers_of_the_workspace_part_cannot_be_overridden(self):
        self.write(self.src, "src/old.txt")
        for trailer in ("Plan-Project: spoofed", "Plan-Source-Commit: abc1234"):
            with self.subTest(trailer=trailer), self.assertRaises(PlanError) as cm:
                self.commit(trailers=[trailer])
            self.assertEqual(cm.exception.code, "CONTENT_INVALID")

    def test_cli_json_carries_the_split(self):
        self.write(self.src, "src/old.txt")
        code, out, err = test_envelope.run("commit", self.root, "P1.1", "--role", "executor", "--json")
        self.assertEqual((code, err), (0, ""))
        doc = json.loads(out)
        self.assertEqual((doc["repo"], doc["workspace_commit"]["status"]), ("source", "nothing"))

    def test_legacy_plan_reports_the_new_keys_as_skipped(self):
        # a plan folder outside the workspace keeps its single commit
        (self.src / ".swissknifeman/project.json").unlink()  # no marker: the checkout keeps its plans
        legacy = self.src / "plans"
        root = demo.make_demo_plan(legacy)
        demo.rewrite(root, "phases/P1/P1.1.json", lambda d: d.update(
            task_files=[{"path": "src/**", "change": "modify"}], reads=[], status="todo", result=None))
        (root / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        store.ensure_gitattributes(root)
        self.write(self.src, "src/old.txt")
        result = gitops.commit(root, "P1.1", role="executor", leave_outside=True)
        self.assertEqual((result["repo"], result["workspace_sha"], result["workspace_commit"]),
                         ("source", None, {"status": "skipped-legacy"}))
        self.assertNotIn("workspace_paths", result)
        self.assertIn("src/old.txt", result["paths"])
        self.assertTrue(any(path.startswith("plans/") for path in result["paths"]))


if __name__ == "__main__":
    unittest.main()


class CliWorkspaceCommitExitTests(unittest.TestCase):
    """``plan.py commit`` in text mode fails when the workspace commit failed or was locked, and says why."""

    def run_cli(self, workspace_commit: dict, sha=None) -> tuple:
        import argparse
        import contextlib
        import io
        from planner.plan import cli
        args = argparse.Namespace(ref="P1.1", role="executor", path=[], leave_outside=False, dry_run=False, type=None,
                                  scope=None, summary=None, trailer=[], actor=None, json=False, output="text")
        result = {"sha": sha, "ref": "P1.1", "role": "executor", "paths": [], "workspace_sha": None,
                  "workspace_commit": workspace_commit}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_plan_dir", return_value=Path(".")), mock.patch.object(gitops, "commit", return_value=result), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.cmd_commit(args)
        return code, err.getvalue()

    def test_a_locked_or_failed_workspace_commit_exits_non_zero_with_the_reason(self):
        code, err = self.run_cli({"status": "locked", "error": "workspace lock held"})
        self.assertEqual(code, 1)
        self.assertIn("workspace commit locked: workspace lock held", err)
        self.assertEqual(self.run_cli({"status": "failed", "error": "x"})[0], 1)

    def test_a_committed_or_skipped_workspace_commit_exits_zero(self):
        self.assertEqual(self.run_cli({"status": "committed"}, sha="abc")[0], 0)
        self.assertEqual(self.run_cli({"status": "skipped-no-git"})[0], 0)
