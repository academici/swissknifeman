"""``bridge planner-orch commit``: fragment shape, trailers, independent paths_digest, orch stage-result conformance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import bridge_fixture
import partners

PID = "billium"
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
        self.src, self.ws, self.home = base / "src-repo", base / "wss" / "axioma", base / "home"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_") and k != "GIT_INDEX_FILE"}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, HOME=str(base), SKM_HOME=str(self.home),
                        SKM_WORKSPACES_ROOT=str(self.ws.parent), SKM_AICORE_EVENTS__DELIVERY="off",
                        SKM_PLANNER_BRIDGES__ROOTS=os.environ.get("SKM_PLANNER_BRIDGES__ROOTS", ""),
                        PLANNER_ROOT=str(CHECKOUT_PLANNER), PLANNER_PLAN_PY=str(CHECKOUT_PLANNER / "scripts/plan.py"))
        for repo in (self.src, self.ws):
            repo.mkdir(parents=True)
            self.git(repo, "init", "-q", "-b", "main")
            for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                               ("commit.gpgsign", "false"), ("gc.auto", "0"), ("maintenance.auto", "false")):
                self.git(repo, "config", key, value)
        (self.src / ".git/info/exclude").write_text(".swissknifeman/state/\n")
        marker = self.src / ".swissknifeman/project.json"
        marker.parent.mkdir()
        marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "axioma", "project_id": PID,
                                      "plans_store": "workspace"}))
        (self.src / "lib/pkg").mkdir(parents=True)
        (self.src / "lib/pkg/config.py").write_text("DEFAULT = 1\n", encoding="utf-8")
        self.git(self.src, "add", "-A")
        self.git(self.src, "commit", "-q", "-m", "base")
        state = self.home / "state" / "workspaces" / "axioma"
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

    def local_evidence(self, check="V1") -> str:
        doc = json.loads((self.plan / "plan.json").read_text(encoding="utf-8"))
        (self.plan / "plan.json").write_text(json.dumps({**doc, "id": self.plan.name}, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")  # a plan API write needs the id of its folder
        path = self.src / ".swissknifeman/orch-artifacts/cnd-run/P1.2/evidence" / f"{check}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"check_id": check, "exit": 0}), encoding="utf-8")
        return path.relative_to(self.src).as_posix()

    def test_the_evidence_of_a_workspace_plan_is_kept_with_the_plan(self):
        """W4: the conductor's copy is a local record; the plan keeps the evidence and the item refers to it there."""
        import worksource
        local = self.local_evidence()
        fields = {"plan": str(self.plan), "ref": "P1.2", "run_id": "orch-run-1", "evidence": {"V1": local}}
        with mock.patch.dict(os.environ, self.env, clear=True):
            cwd = Path.cwd()
            os.chdir(self.src)
            try:
                kept = worksource._kept_evidence(fields)
                again = worksource._kept_evidence(fields)  # a repeated register is a no-op
            finally:
                os.chdir(cwd)
        self.assertEqual(kept, {"V1": "@plan/artifacts/P1.2/orch-run-1/evidence/V1.json"})
        self.assertEqual(again, kept)
        target = self.plan / "artifacts/P1.2/orch-run-1/evidence/V1.json"
        self.assertEqual(target.read_bytes(), (self.src / local).read_bytes())
        artifacts = json.loads((self.plan / "phases/P1/P1.2.json").read_text(encoding="utf-8"))["artifacts"]
        self.assertEqual([entry for entry in artifacts if entry["path"] == kept["V1"]],
                         [{"path": kept["V1"], "role": "output"}])

    def test_register_hands_the_kept_evidence_to_the_planner_and_names_it(self):
        import worksource
        local = self.local_evidence()
        seen = {}

        def bounded(argv, **kwargs):
            seen["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, json.dumps({"calls": [{"result": "recorded"}],
                                                                   "gate": {"verdict": "pass", "checks": {"V1": 0}}}), "")

        fields = {"plan": str(self.plan), "ref": "P1.2", "run_id": "orch-run-1", "attempt_id": "att-orch-run-1-P1.2",
                  "status": "done", "report": {"summary": "s"}, "evidence": {"V1": local},
                  "registrar": {"provider": "orch", "model": "conductor"}, "executed_by": {"provider": "codex", "model": "m"}}
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(worksource, "_supersede_blocked_attempt"), \
                mock.patch.object(worksource.partners, "run_bounded", bounded):
            cwd = Path.cwd()
            os.chdir(self.src)
            try:
                answer = worksource.op_register(fields)
            finally:
                os.chdir(cwd)
        self.assertEqual(answer["evidence"], {"V1": "@plan/artifacts/P1.2/orch-run-1/evidence/V1.json"})
        self.assertIn("V1=@plan/artifacts/P1.2/orch-run-1/evidence/V1.json", seen["argv"])
        self.assertNotIn(f"V1={local}", seen["argv"])

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

    def test_repeat_after_source_commit_finishes_workspace_without_second_source_commit(self):
        self.change()
        source_before = int(self.git(self.src, "rev-list", "--count", "HEAD"))
        workspace_before = int(self.git(self.ws, "rev-list", "--count", "HEAD"))
        hook = self.ws / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        first = self.op(attempt_id="att-split")
        self.assertEqual((first["outcome"], first["workspace_commit"]["status"]), ("committed", "failed"), first)
        source_sha = self.git(self.src, "rev-parse", "HEAD").strip()
        self.assertEqual(source_before + 1, int(self.git(self.src, "rev-list", "--count", "HEAD")))
        self.assertEqual(workspace_before, int(self.git(self.ws, "rev-list", "--count", "HEAD")))
        hook.unlink()
        second = self.op(attempt_id="att-split")
        self.assertEqual((second["outcome"], second["repo"], second["workspace_commit"]["status"]),
                         ("committed", "workspace", "committed"), second)
        self.assertEqual((first["attempt"], second["attempt"]), ("att-split", "att-split"))
        self.assertEqual(source_sha, self.git(self.src, "rev-parse", "HEAD").strip())
        self.assertEqual(source_before + 1, int(self.git(self.src, "rev-list", "--count", "HEAD")))
        self.assertEqual(workspace_before + 1, int(self.git(self.ws, "rev-list", "--count", "HEAD")))
        third = self.op(attempt_id="att-split")
        self.assertEqual((third["outcome"], third["attempt"]), ("no-op", "att-split"), third)
        self.assertEqual(source_before + 1, int(self.git(self.src, "rev-list", "--count", "HEAD")))
        self.assertEqual(workspace_before + 1, int(self.git(self.ws, "rev-list", "--count", "HEAD")))

    @unittest.skipUnless(ORCH, "orch not found")
    def test_sigkill_after_source_commit_repeats_only_workspace_part(self):
        self.assert_split_crash(incomplete=True)

    @unittest.skipUnless(ORCH, "orch not found")
    def test_sigkill_after_split_receipt_closes_without_call(self):
        self.assert_split_crash(incomplete=False)

    @unittest.skipUnless(ORCH, "orch not found")
    def test_second_sigkill_after_workspace_repeat_receipt_retains_source_sha(self):
        self.assert_split_crash(incomplete=True, repeat_crash=True)

    def assert_split_crash(self, *, incomplete, repeat_crash=False):
        self.change()
        source_before = int(self.git(self.src, "rev-list", "--count", "HEAD"))
        workspace_before = int(self.git(self.ws, "rev-list", "--count", "HEAD"))
        hook = self.ws / ".git/hooks/pre-commit"
        if incomplete:
            hook.write_text("#!/bin/sh\nexit 1\n")
            hook.chmod(0o755)
        fields = {"plan": str(self.plan), "ref": "P1.2", "run_id": "run-split-receipts",
                  "attempt_id": "att-split-receipts", "paths": ["lib/pkg/config.py"]}
        config = self.src.parent / "crash.json"
        config.write_text(json.dumps({"project": str(self.src), "fields": fields,
                                      "source_argv": [sys.executable, str(partners.BRIDGE / "worksource.py")]}))
        boot = "import sys; sys.path[:0] = " + repr([str(ORCH), str(ORCH / "lib"), str(partners.aicore_lib())])
        boot += "; from tests.test_resume_receipts import external_commit_worker; external_commit_worker(*sys.argv[1:])"
        def kill_worker(mode):
            with open(self.src.parent / (mode + ".log"), "w+") as log:
                child = subprocess.Popen([sys.executable, "-I", "-u", "-c", boot, str(config), mode], cwd=self.src,
                                     env={**self.env, "SKM_ORCH_ROOT": str(ORCH)}, stdout=subprocess.PIPE, stderr=log, text=True)
                try:
                    self.assertTrue(select.select([child.stdout], [], [], 30)[0], "split receipt barrier not reached")
                    line = child.stdout.readline().strip()
                    if line != "ready":
                        log.seek(0)
                        self.fail("worker exited before its barrier: " + log.read())
                    child.kill()
                    self.assertEqual(-signal.SIGKILL, child.wait(timeout=15))
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=15)
                    child.stdout.close()

        kill_worker("crash")
        self.assertEqual(source_before + 1, int(self.git(self.src, "rev-list", "--count", "HEAD")))
        self.assertEqual(workspace_before + (0 if incomplete else 1),
                         int(self.git(self.ws, "rev-list", "--count", "HEAD")))
        if incomplete:
            hook.unlink()
        if repeat_crash:
            kill_worker("resume-crash")
        resumed = subprocess.run([sys.executable, "-I", "-c", boot, str(config), "resume"], cwd=self.src,
                                 env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        recovered = json.loads(resumed.stdout)
        self.assertEqual("repeated: workspace part incomplete" if incomplete and not repeat_crash else "closed from receipt", recovered["message"])
        self.assertEqual(1 if incomplete and not repeat_crash else 0, recovered["calls"])
        result = recovered["result"]
        self.assertEqual("committed", result["outcome"])
        self.assertEqual({"outcome", "sha"} | ({"message"} if result.get("message") else set()), set(result))
        source_sha = self.git(self.src, "rev-parse", "HEAD").strip()
        workspace_sha = self.git(self.ws, "rev-parse", "HEAD").strip()
        self.assertEqual(source_sha, result["sha"])
        self.assertNotEqual(workspace_sha, result["sha"])
        self.assertEqual("commit", self.git(self.src, "cat-file", "-t", result["sha"]).strip())
        self.assertEqual(source_before + 1, int(self.git(self.src, "rev-list", "--count", "HEAD")))
        self.assertEqual(workspace_before + 1, int(self.git(self.ws, "rev-list", "--count", "HEAD")))

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
