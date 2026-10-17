"""``bridge planner-orch commit``: fragment shape, trailers, independent paths_digest, orch stage-result conformance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import bridge_fixture
import partners

PID = "prj_01JC0Z8Q3M5T7V9XABCDEFGHJM"
# The workspace tests exercise the planner of this checkout: a run can point PLANNER_ROOT at a frozen older copy.
CHECKOUT_PLANNER = Path(__file__).resolve().parents[3] / "packages" / "planner"
ORCH = partners.find_orch_root()
FIXTURE = (ORCH / "fixtures/exec/v1/valid/stage-result/with-commits.json") if ORCH else None


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class CommitBridge(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name) / "repo"
        self.tmp.mkdir()
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": tmp.name, "GIT_CONFIG_GLOBAL": os.devnull}
        self.env.pop("GIT_INDEX_FILE", None)
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                           ("commit.gpgsign", "false")):
            self.git("config", key, value)
        self.plan = bridge_fixture.demo_plan(self.tmp)
        (self.plan / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        (self.plan / ".gitattributes").write_text("log.jsonl merge=union\n")
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "base")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.tmp, env=self.env, text=True, capture_output=True,
                              check=True).stdout

    def bridge(self, *args):
        cmd = ["bridge", "planner-orch", "commit", str(self.plan), *args]
        return subprocess.run([bridge_fixture.sys.executable, str(bridge_fixture.PLAN_PY), *cmd], cwd=self.tmp,
                              env=self.env, capture_output=True, text=True, encoding="utf-8", check=False)

    def test_executor_commit_fragment_and_trailers(self):
        (self.tmp / "lib/pkg/config.py").write_text("DEFAULT = 2\n", encoding="utf-8")
        done = self.bridge("P1.2", "--role", "executor")
        self.assertEqual(done.returncode, 0, done.stderr)
        fragment = json.loads(done.stdout)
        self.assertEqual(list(fragment), ["commits"])
        (entry,) = fragment["commits"]
        self.assertEqual(set(entry), {"sha", "role", "ref", "paths_digest"})
        self.assertEqual((entry["role"], entry["ref"]), ("executor", "P1.2"))
        self.assertEqual(entry["sha"], self.git("rev-parse", "HEAD").strip())
        paths = self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD").rstrip("\0").split("\0")
        self.assertEqual(paths, ["lib/pkg/config.py"])
        self.assertEqual(entry["paths_digest"], hashlib.sha256("\n".join(sorted(paths)).encode()).hexdigest())
        message = self.git("log", "-1", "--format=%B")
        plan_id = json.loads((self.plan / "plan.json").read_text(encoding="utf-8"))["id"]
        for line in ("Plan: " + plan_id, "Plan-Ref: P1.2", "Plan-Role: executor"):
            self.assertIn(line, message)
        self.assertEqual(self.git("status", "--porcelain").strip(), "")

    @unittest.skipUnless(ORCH, "orch not found")
    def test_fragment_passes_orch_stage_result_validation(self):
        (self.tmp / "lib/pkg/config.py").write_text("DEFAULT = 3\n", encoding="utf-8")
        fragment = json.loads(self.bridge("P1.2", "--role", "executor").stdout)
        document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        document["commits"] = fragment["commits"]
        path = self.tmp.parent / "stage-result.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        code, out = partners.orch_validate("stage-result", path)
        self.assertEqual(code, 0, out)

    def test_task_refusal_is_passed_on(self):
        done = self.bridge("P1.2", "--role", "executor")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, "")
        self.assertTrue(done.stderr.startswith("NOTHING_TO_COMMIT:"), done.stderr)
        (self.tmp / "lib/pkg/config.py").write_text("DEFAULT = 4\n", encoding="utf-8")
        dry = self.bridge("P1.2", "--role", "executor", "--dry-run")
        self.assertEqual((dry.returncode, dry.stdout), (1, ""))
        self.assertTrue(dry.stderr.startswith("COMMIT_RESULT_INVALID:"), dry.stderr)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), "1")


@unittest.skipUnless(shutil.which("git"), "git is not installed")
@unittest.skipUnless((CHECKOUT_PLANNER / "scripts/plan.py").is_file(), "planner of this checkout not found")
class WorkspaceCommitBridge(unittest.TestCase):
    """A plan in the portable workspace: the fragment names the product commit, ``op_commit`` also the workspace one."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.src, self.ws, self.home = base / "src-repo", base / "ws", base / "home"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_") and k != "GIT_INDEX_FILE"}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, HOME=str(base), SKM_HOME=str(self.home),
                        SKM_WORKSPACE_ROOT=str(self.ws), SKM_AICORE_EVENTS__DELIVERY="off",
                        SKM_PLANNER_BRIDGES__ROOTS=os.environ.get("SKM_PLANNER_BRIDGES__ROOTS", ""),
                        PLANNER_ROOT=str(CHECKOUT_PLANNER), PLANNER_PLAN_PY=str(CHECKOUT_PLANNER / "scripts/plan.py"))
        for repo in (self.src, self.ws):
            repo.mkdir()
            self.git(repo, "init", "-q", "-b", "main")
            for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                               ("commit.gpgsign", "false"), ("gc.auto", "0"), ("maintenance.auto", "false")):
                self.git(repo, "config", key, value)
        (self.src / ".git/info/exclude").write_text(".swissknifeman/state/\n")
        marker = self.src / ".swissknifeman/project.json"
        marker.parent.mkdir()
        marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "project_id": PID,
                                      "plans_store": "workspace"}))
        (self.src / "lib/pkg").mkdir(parents=True)
        (self.src / "lib/pkg/config.py").write_text("DEFAULT = 1\n", encoding="utf-8")
        self.git(self.src, "add", "-A")
        self.git(self.src, "commit", "-q", "-m", "base")
        state = self.home / "state" / "workspace"
        state.mkdir(parents=True)
        (state / "bindings.json").write_text(json.dumps({
            "$schema": "urn:swissknifeman:aicore:workspace-bindings:v1",
            "projects": {PID: {"paths": [str(self.src)], "primary": str(self.src), "bound_at": "2026-10-17T09:30:00Z"}}}))
        self.plan = self.ws / "projects" / PID / "plans" / bridge_fixture.PLAN_NAME
        shutil.copytree(bridge_fixture.DEMO, self.plan)
        (self.plan / ".gitignore").write_text("views/\ncontext/\n.lock\n")
        (self.plan / ".gitattributes").write_text("log.jsonl merge=union\n")
        self.git(self.ws, "add", "-A")
        self.git(self.ws, "commit", "-q", "-m", "base")

    def git(self, repo, *args):
        return subprocess.run(["git", *args], cwd=repo, env=self.env if hasattr(self, "env") else None, text=True,
                              capture_output=True, check=True).stdout

    def change(self):
        (self.src / "lib/pkg/config.py").write_text("DEFAULT = 2\n", encoding="utf-8")
        item = self.plan / "phases/P1/P1.2.json"
        document = json.loads(item.read_text(encoding="utf-8"))
        document["title"] = "Validate types again"  # bookkeeping of the item
        item.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_fragment_names_the_product_commit(self):
        self.change()
        cmd = ["bridge", "planner-orch", "commit", str(self.plan), "P1.2", "--role", "executor"]
        done = subprocess.run([bridge_fixture.sys.executable, str(CHECKOUT_PLANNER / "scripts/plan.py"), *cmd],
                              cwd=self.src, env=self.env, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        (entry,) = json.loads(done.stdout)["commits"]
        self.assertEqual(entry["sha"], self.git(self.src, "rev-parse", "HEAD").strip())
        paths = self.git(self.src, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD").rstrip("\0").split("\0")
        self.assertEqual(paths, ["lib/pkg/config.py"])
        self.assertEqual(entry["paths_digest"], hashlib.sha256("\n".join(paths).encode()).hexdigest())
        self.assertIn(f"Plan-Source-Commit: {entry['sha']}", self.git(self.ws, "log", "-1", "--format=%B"))

    def op(self, **fields):
        import worksource
        with mock.patch.dict(os.environ, self.env, clear=True):
            return worksource.op_commit({"plan": str(self.plan), "ref": "P1.2", **fields})

    def test_op_commit_passes_the_workspace_fields_on(self):
        self.change()
        answer = self.op()
        self.assertEqual(answer["outcome"], "committed", answer)
        self.assertEqual(answer["sha"], self.git(self.src, "rev-parse", "HEAD").strip())
        self.assertEqual((answer["repo"], answer["workspace_commit"]), ("source", {"status": "committed"}))
        self.assertEqual(answer["workspace_sha"], self.git(self.ws, "rev-parse", "HEAD").strip())
        self.assertNotIn("message", answer)

    def test_op_commit_of_plan_files_only_answers_with_the_workspace_commit(self):
        item = self.plan / "phases/P1/P1.2.json"
        document = json.loads(item.read_text(encoding="utf-8"))
        document["title"] = "Only the item"
        item.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        answer = self.op()
        self.assertEqual((answer["outcome"], answer["repo"]), ("committed", "workspace"), answer)
        self.assertEqual(answer["sha"], answer["workspace_sha"])

    def test_op_commit_reports_a_failed_workspace_part_next_to_the_product_commit(self):
        self.change()
        hook = self.ws / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        answer = self.op()
        self.assertEqual(answer["outcome"], "committed", answer)
        self.assertEqual(answer["sha"], self.git(self.src, "rev-parse", "HEAD").strip())
        self.assertEqual(answer["workspace_commit"]["status"], "failed")
        self.assertIsNone(answer["workspace_sha"])
        self.assertIn("workspace commit failed", answer["message"])

    def test_op_commit_without_a_marker_keeps_the_legacy_answer(self):
        from types import SimpleNamespace
        import worksource
        answer = {"sha": "abc1234", "repo": "source", "workspace_sha": None,
                  "workspace_commit": {"status": "skipped-legacy"}}
        done = SimpleNamespace(returncode=0, stdout=json.dumps(answer), stderr="")
        with mock.patch.object(worksource, "plan_py", return_value=done):
            self.assertEqual(worksource.op_commit({"plan": "PLAN1", "ref": "P1.1"}),
                             {"op": "commit", "outcome": "committed", "sha": "abc1234"})


if __name__ == "__main__":
    unittest.main()
