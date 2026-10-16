"""log.jsonl merge=union: parallel branches append events and integrate without conflict."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from planner.plan import check, ops, store
try:
    from . import demo
except ImportError:
    import demo


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class LogUnionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": tmp.name, "GIT_CONFIG_GLOBAL": os.devnull}
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        plans = self.repo / "plans"
        plans.mkdir()
        self.root = ops.new_plan("UNION", "Union", plans_root=plans, repository="demo", owner="repository owner",
                                 authoring=demo.AUTHORING, message="Merge logs.", date="2026.10.05").root
        self.log_path = self.root.relative_to(self.repo) / store.LOG
        self.commit("base")

    def git(self, *args, check=True):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, text=True, capture_output=True,
                              check=check)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def summaries(self):
        return [e["summary"] for e in store.read_log(self.root)]

    def diverge(self):
        self.git("checkout", "-q", "-b", "a")
        self.append_here("event a", "2026-10-06T10:00:00Z")
        self.git("checkout", "-q", "main")
        self.git("checkout", "-q", "-b", "b")
        self.append_here("event b", "2026-10-06T09:00:00Z")  # earlier ts on the later-integrated branch

    def append_here(self, summary, ts):
        event = store.new_event("note", summary, demo.AUTHORING)
        event["ts"] = ts
        store.append_log(self.root, event)
        self.commit(summary)

    def test_attribute_is_union(self):
        out = self.git("check-attr", "merge", "--", str(self.log_path)).stdout
        self.assertIn("merge: union", out)

    def test_merge_keeps_both_sides(self):
        self.diverge()
        self.git("checkout", "-q", "a")
        self.git("merge", "-q", "--no-edit", "b")
        self.assertEqual(sorted(self.summaries()[1:]), ["event a", "event b"])
        self.assertEqual(len(self.summaries()), 3)
        self.assertEqual([i for i in check.check(store.load_plan(self.root)) if i.level == "error"], [])

    def test_rebase_keeps_both_sides(self):
        self.diverge()
        self.git("rebase", "-q", "a")
        self.assertEqual(sorted(self.summaries()[1:]), ["event a", "event b"])
        self.assertEqual(len(self.summaries()), 3)

    def test_ensure_gitattributes_is_idempotent_and_preserves_content(self):
        path = self.root / ".gitattributes"
        path.write_text("*.json text", encoding="utf-8")
        self.assertTrue(store.ensure_gitattributes(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "*.json text\nlog.jsonl merge=union\n")
        self.assertFalse(store.ensure_gitattributes(self.root))
        self.assertEqual(path.read_text(encoding="utf-8"), "*.json text\nlog.jsonl merge=union\n")


if __name__ == "__main__":
    unittest.main()
