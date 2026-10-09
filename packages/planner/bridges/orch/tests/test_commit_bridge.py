"""``bridge orch commit``: fragment shape, trailers, independent paths_digest, orch stage-result conformance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import bridge_fixture
import partner

ORCH = partner.find_orch_root()
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
        cmd = ["bridge", "orch", "commit", str(self.plan), *args]
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
        code, out = partner.orch_validate("stage-result", path)
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


if __name__ == "__main__":
    unittest.main()
