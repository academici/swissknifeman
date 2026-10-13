"""Two lanes in two worktrees: claim -> finish+commit in each -> sequential merge or rebase -> reconcile."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from planner.plan import check, gitops, lifecycle, ops, store  # noqa: E402

OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
LANES = {"P1.1": "src/a.txt", "P1.2": "src/b.txt"}


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class ParallelIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": tmp.name, "GIT_CONFIG_GLOBAL": os.devnull}
        env.pop("GIT_INDEX_FILE", None)
        patcher = mock.patch.dict(os.environ, env, clear=True)  # gitops runs git with os.environ
        patcher.start()
        self.addCleanup(patcher.stop)
        self.git("init", "-q", "-b", "main")
        # The project journal of planner events lives in .swissknifeman/state, which the gitignore policy ignores.
        (self.repo / ".git" / "info" / "exclude").write_text(".swissknifeman/state/\n")
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                           ("commit.gpgsign", "false"), ("gc.auto", "0"), ("maintenance.auto", "false")):
            self.git("config", key, value)
        plan = ops.new_plan("LANES", "Lanes", plans_root=self.repo / "plans", repository="demo", owner="o",
                            authoring=OPUS, message="Two lanes.", date="2026.10.07")
        self.root, self.plan_id = plan.root, plan.plan["id"]
        self.rel = self.root.relative_to(self.repo)
        ops.add_phase(plan, "Lanes")
        ops.patch(plan, "P1", {"goal": "g"})
        for n, (item_id, path) in enumerate(LANES.items(), 1):
            ops.add_item(plan, "P1", f"Lane {n}")
            ops.patch(plan, item_id, {
                "summary": "s", "why": "w", "scope": {"include": [path]}, "deliverables": [path],
                "task_files": [{"path": path, "change": "modify"}],
                "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]})
            self.write(self.repo, path, "base\n")
        ops.set_batches(plan, "P1", [{"id": "B1", "items": list(LANES), "mode": "recommended"}])
        lifecycle.design_done(self.root, "P1", actor=OPUS)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.claim()
        self.trees = {item_id: self.worktree(item_id) for item_id in LANES}

    # ---- helpers
    def git(self, *args, cwd=None, check=True):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, text=True, capture_output=True, check=check)

    @staticmethod
    def write(base, path, text):
        target = base / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def branch(self, item_id):
        return f"plan/PLAN1/{item_id}"

    def claim(self):
        """§integration 1: start both lanes in the main tree and commit the claim before branching."""
        lifecycle.start(self.root, list(LANES), OPUS)
        gitops.commit(self.root, "P1.1", role="executor", commit_type="chore", summary="взять P1.1 P1.2 в работу",
                      trailers=["Plan-Op: claim"], paths=["@plan/phases/P1/P1.2.json"], leave_outside=True)
        self.assertEqual(self.dirty(self.repo), [])

    def worktree(self, item_id):
        """§integration 2: one branch and one tree per lane; removed at cleanup (the test owns them)."""
        path = self.tmp / f"wt-{item_id}"
        self.git("worktree", "add", "-q", "-b", self.branch(item_id), str(path), "HEAD")
        self.addCleanup(self.git, "worktree", "remove", "--force", str(path), check=False)
        return path

    def lane(self, item_id):
        """§integration 3: the lane agent changes its product file, finishes and commits in its own tree."""
        tree = self.trees[item_id]
        root = tree / self.rel
        self.write(tree, LANES[item_id], f"{item_id} done\n")
        result = lifecycle.finish(root, item_id, "done", checks={"V1": 0}, notes="lane")
        self.assertIsNone(result.phase_closed)  # the other lane is in_progress in this tree
        gitops.commit(root, item_id, role="executor")
        self.assertEqual(self.dirty(tree), [])

    def dirty(self, tree):
        return [line for line in self.git("status", "--porcelain", cwd=tree).stdout.splitlines() if line]

    def plan(self):
        return store.load_plan(self.root)

    def integrated(self):
        """After both lanes landed on main: terminal, unclosed, next names reconcile; reconcile closes."""
        plan = self.plan()
        self.assertEqual({i: plan.items[i]["status"] for i in LANES}, {"P1.1": "done", "P1.2": "done"})
        for item_id, path in LANES.items():
            self.assertEqual((self.repo / path).read_text(encoding="utf-8"), f"{item_id} done\n")
        self.assertIsNone(plan.phases["P1"].get("closed"))
        self.assertEqual(lifecycle.next(plan).exact, f"waiting: P1 closure: plan.py reconcile {self.plan_id}")
        self.assertEqual([i.code for i in check.check(plan) if i.code.startswith("phase_")], ["phase_unclosed"])
        finishes = [e["item"] for e in store.read_log(self.root) if e["type"] == "finish"]
        self.assertEqual(sorted(finishes), ["P1.1", "P1.2"])  # union kept both lanes' events

        result = lifecycle.reconcile(self.root, actor=OPUS)
        self.assertEqual((result.closed, result.plan_done), ((("P1", "done"),), True))
        plan = self.plan()
        self.assertEqual((plan.phases["P1"]["closed"]["result"], plan.plan["status"]), ("done", "done"))
        self.assertEqual([i for i in check.check(plan) if i.level == "error"], [])
        self.assertEqual([i for i in check.check(plan) if i.code.startswith("phase_")], [])
        # §integration 6: the integrator commits what reconcile wrote.
        gitops.commit(self.root, "P1.2", role="executor", commit_type="chore", summary="закрыть фазы (reconcile)",
                      trailers=["Plan-Op: reconcile"], leave_outside=True)
        self.assertEqual(self.dirty(self.repo), [])
        changed = self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD").stdout.rstrip("\0").split("\0")
        self.assertEqual(sorted(changed), sorted(f"{self.rel.as_posix()}/{name}"
                                                 for name in ("log.jsonl", "phases/P1/phase.json", "plan.json")))
        self.assertEqual(lifecycle.reconcile(self.root).closed, ())  # idempotent after the commit
        self.assertEqual(self.dirty(self.repo), [])
        # §integration 7: merged trees are clean and removable without --force.
        for item_id, tree in self.trees.items():
            self.git("worktree", "remove", str(tree))
            self.git("branch", "-d", self.branch(item_id))

    # ---- scenarios
    def test_sequential_merge_then_reconcile(self):
        for item_id in LANES:
            self.lane(item_id)
        for item_id in LANES:
            merged = self.git("merge", "--no-ff", "--no-edit", self.branch(item_id), check=False)
            self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        self.integrated()

    def test_rebase_then_fast_forward_then_reconcile(self):
        for item_id in LANES:
            self.lane(item_id)
        first, second = LANES
        self.git("merge", "--no-ff", "--no-edit", self.branch(first))
        rebased = self.git("rebase", "main", cwd=self.trees[second], check=False)
        self.assertEqual(rebased.returncode, 0, rebased.stdout + rebased.stderr)
        self.git("merge", "--ff-only", self.branch(second))
        self.integrated()


if __name__ == "__main__":
    unittest.main()
