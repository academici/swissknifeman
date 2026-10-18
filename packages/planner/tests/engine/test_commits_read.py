"""plan.py commits: trailer filter, unit-under-item, legacy result.commits, merge and empty result."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from planner.plan import gitops, lifecycle, schema, store, units
from planner.plan.model import PlanError

try:
    from . import demo, test_envelope
except ImportError:
    import demo
    import test_envelope


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class CommitsReadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": tmp.name, "GIT_CONFIG_GLOBAL": os.devnull}
        env.pop("GIT_INDEX_FILE", None)
        patch = mock.patch.dict(os.environ, env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
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
        self.write("src/a.txt", "0\n")
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "base")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True, check=True).stdout

    def write(self, path, text):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def op(self, ref, role, text):
        self.write("src/a.txt", text)
        return gitops.commit(self.root, ref, role=role)["sha"]

    def populate(self):
        lifecycle.start(self.root, ["P1.1"], actor=demo.AUTHORING)
        units.add_unit(self.root, "P1.1", "Unit", {"files": ["src/**"]})
        shas = [self.op("P1.1", "executor", "1\n"), self.op("P1.1", "fix", "2\n"), self.op("P1.1/U1", "executor", "3\n")]
        self.write("src/a.txt", "foreign\n")
        self.git("commit", "-q", "-am", "foreign\n\nPlan: other-plan\nPlan-Ref: P1.1\nPlan-Role: executor")
        return shas

    def test_filters_by_ref_role_and_unit_under_item(self):
        shas = self.populate()
        everything = gitops.list_commits(self.root)
        self.assertEqual(schema.validate(everything, "read-commits"), [])
        self.assertEqual([c["sha"] for c in everything["commits"]], shas[::-1])
        self.assertEqual({c["source"] for c in everything["commits"]}, {"trailer"})
        item = gitops.list_commits(self.root, "P1.1")
        self.assertEqual(len(item["commits"]), 3)
        self.assertEqual(item["ref"], "P1.1")
        self.assertEqual([c["ref"] for c in gitops.list_commits(self.root, "P1.1/U1")["commits"]], ["P1.1/U1"])
        fix = gitops.list_commits(self.root, "P1.1", role="fix")["commits"]
        self.assertEqual([(c["sha"], c["role"]) for c in fix], [(shas[1], "fix")])
        self.assertEqual(gitops.list_commits(self.root, "P1.1", role="reviewer")["commits"], [])

    def test_legacy_result_commits_merge_with_trailers_and_dedupe(self):
        shas = self.populate()
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(
            result={**(d.get("result") or {}), "commits": [shas[0], "abcdef1"]}))
        rows = gitops.list_commits(self.root, "P1.1")["commits"]
        self.assertEqual([r["sha"] for r in rows], [*shas[::-1], "abcdef1"])
        self.assertEqual(rows[-1], {"sha": "abcdef1", "ref": "P1.1", "role": None, "subject": "", "source": "finish"})
        self.assertEqual(rows[-2]["source"], "trailer")
        self.assertEqual(gitops.list_commits(self.root, "P1.1", role="fix")["commits"][0]["sha"], shas[1])

    def test_empty_result_unknown_ref_and_cli_envelope(self):
        self.assertEqual(gitops.list_commits(self.root), {"plan": demo.PLAN_ID, "ref": None, "commits": []})
        for ref, code in (("P1.99", "REF_UNKNOWN"), ("D1", "REF_INVALID")):
            with self.subTest(ref=ref), self.assertRaises(PlanError) as cm:
                gitops.list_commits(self.root, ref)
            self.assertEqual(cm.exception.code, code)
        self.populate()
        status, out, err = test_envelope.run("commits", self.root, "P1.1", "--role", "executor", "--json")
        self.assertEqual(status, 0, err)
        doc = json.loads(out)
        self.assertEqual(schema.validate(doc, "envelope"), [])
        self.assertEqual(len(doc["data"]["commits"]), 2)


PID = "billium"


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class WorkspacePlanCommitsTests(unittest.TestCase):
    """``commits`` of a plan in the portable workspace reads the history of its checkout, not of the workspace."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.src, self.ws, self.home = base / "src-repo", base / "wss" / "axioma", base / "home"
        env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_") and k != "GIT_INDEX_FILE"}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, HOME=str(base), SKM_HOME=str(self.home),
                   SKM_WORKSPACES_ROOT=str(self.ws.parent))
        patch = mock.patch.dict(os.environ, env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        for repo in (self.src, self.ws):
            repo.mkdir(parents=True)
            self.git(repo, "init", "-q", "-b", "main")
            for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                               ("commit.gpgsign", "false"), ("gc.auto", "0"), ("maintenance.auto", "false")):
                self.git(repo, "config", key, value)  # no detached maintenance process writing during the cleanup
        (self.src / ".git/info/exclude").write_text(".swissknifeman/state/\n")
        self.write(self.src / ".swissknifeman/project.json", json.dumps({
            "$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "axioma", "project_id": PID, "plans_store": "workspace"}))
        self.write(self.src / "src/a.txt", "0\n")
        self.git(self.src, "add", "-A")
        self.git(self.src, "commit", "-q", "-m", "base")
        self.bindings = self.home / "state" / "workspaces" / "axioma" / "bindings.json"
        self.write(self.bindings, json.dumps({
            "$schema": "urn:swissknifeman:aicore:workspace-bindings:v1",
            "projects": {PID: {"paths": [str(self.src)], "primary": str(self.src), "bound_at": "2026-10-17T09:30:00Z"}}}))
        self.root = demo.make_demo_plan(self.ws / "projects" / PID / "plans")
        (self.root / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        store.ensure_gitattributes(self.root)
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(
            task_files=[{"path": "src/**", "change": "modify"}], reads=[], status="todo", result=None))
        self.git(self.ws, "add", "-A")
        self.git(self.ws, "commit", "-q", "-m", "base")

    def git(self, repo, *args):
        return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def bookkeeping(self):
        # by hand: ``lifecycle.start`` spawns the detached delivery of the event journal, which writes into the
        # temporary directory while it is removed
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(status="in_progress"))
        event = store.new_event("note", "started", demo.AUTHORING)
        with (self.root / "log.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    def test_reads_the_checkout_and_ignores_workspace_commits(self):
        self.bookkeeping()
        self.write(self.src / "src/a.txt", "1\n")
        done = gitops.commit(self.root, "P1.1", role="executor")
        self.assertEqual(done["workspace_commit"], {"status": "committed"})
        self.assertIn("Plan: " + demo.PLAN_ID, self.git(self.ws, "log", "-1", "--format=%B"))
        listed = gitops.list_commits(self.root)
        self.assertEqual(schema.validate(listed, "read-commits"), [])
        self.assertEqual([c["sha"] for c in listed["commits"]], [done["sha"]])
        self.assertNotIn("source_unbound", listed)
        self.assertEqual(gitops.list_commits(self.root, "P1.1", role="reviewer")["commits"], [])
        status, out, err = test_envelope.run("commits", self.root, "P1.1", "--json")
        self.assertEqual(status, 0, err)
        self.assertEqual(len(json.loads(out)["data"]["commits"]), 1)

    def test_a_reviewer_commit_lives_in_the_workspace_and_is_not_listed(self):
        self.write(self.root / "knowledge/report.json", "{}\n")
        done = gitops.commit(self.root, "P1.1", role="reviewer")
        self.assertEqual(done["repo"], "workspace")
        self.assertEqual(gitops.list_commits(self.root, "P1.1")["commits"], [])

    def test_without_a_checkout_the_list_is_empty_and_marked(self):
        self.bookkeeping()
        self.write(self.src / "src/a.txt", "1\n")
        gitops.commit(self.root, "P1.1", role="executor")
        self.bindings.unlink()
        listed = gitops.list_commits(self.root)
        self.assertEqual(listed, {"plan": demo.PLAN_ID, "ref": None, "commits": [], "source_unbound": True})
        self.assertEqual(schema.validate(listed, "read-commits"), [])


if __name__ == "__main__":
    unittest.main()
