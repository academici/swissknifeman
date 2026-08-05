from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from artifex import scheduler, worker, worktree


class WorktreeIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "owned.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "foreign.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "--", "owned.txt", "foreign.txt")
        self.git("commit", "-qm", "base")
        self.manager = worktree.WorktreeManager(self.repo)
        self.identity = worktree.WorktreeIdentity("run-1", "P4.3", 1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *argv: str) -> str:
        return subprocess.run(["git", *argv], cwd=self.repo, text=True, capture_output=True, check=True).stdout.strip()

    def attempt(self, files: list[str] | None = None) -> worktree.LinkedWorktree:
        return self.manager.create(root=self.repo.parent / "attempts", identity=self.identity, base="HEAD",
                                   files=files or ["owned.txt"])

    def test_owned_detached_lane_commits_integrates_and_removes_without_residue(self) -> None:
        attempt = self.attempt()
        row = [row for row in self.manager.inventory() if row["worktree"] == str(attempt.path)][0]
        self.assertEqual((True, self.identity.reason), (row["detached"], row["locked"]))
        (attempt.path / "owned.txt").write_text("attempt\n", encoding="utf-8")
        self.assertEqual(("owned.txt",), self.manager.delta(attempt))
        attempt_commit = self.manager.commit(attempt)
        lane = scheduler.WorktreeIntegrationLane(self.manager, str(self.repo))
        result = lane.integrate(attempt, attempt_commit)
        self.assertEqual((attempt.base, attempt_commit), (result["base"], result["attempt_commit"]))
        self.assertEqual("attempt\n", (self.repo / "owned.txt").read_text(encoding="utf-8"))
        self.manager.remove(attempt)
        self.assertEqual(1, len(self.manager.inventory()))

    def test_scope_untracked_symlink_and_dirty_target_refuse_before_integration(self) -> None:
        attempt = self.attempt()
        (attempt.path / "foreign.txt").write_text("foreign\n", encoding="utf-8")
        (attempt.path / "untracked.txt").write_text("untracked\n", encoding="utf-8")
        (attempt.path / "link.txt").symlink_to("owned.txt")
        with self.assertRaisesRegex(worktree.WorktreeRefusal, "WORKTREE_SCOPE_VIOLATION"):
            self.manager.delta(attempt)
        self.git("status", "--porcelain")
        (self.repo / "target-dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(worktree.WorktreeRefusal, "INTEGRATION_TARGET_DIRTY"):
            self.manager.integrate(attempt, "deadbeef", target=self.repo)

    def test_foreign_lock_reason_ref_and_force_like_inputs_are_refused(self) -> None:
        with self.assertRaisesRegex(worktree.WorktreeRefusal, "WORKTREE_SCOPE_INVALID"):
            self.manager.create(root=self.repo.parent / "attempts", identity=self.identity, base="HEAD", files=["../escape"])
        with self.assertRaisesRegex(worktree.WorktreeRefusal, "WORKTREE_BASE_INVALID"):
            self.manager.create(root=self.repo.parent / "attempts", identity=self.identity, base="--force", files=["owned.txt"])
        attempt = self.attempt()
        self.manager._git(self.repo, "worktree", "unlock", "--", str(attempt.path))
        self.manager._git(self.repo, "worktree", "lock", "--reason", "foreign", "--", str(attempt.path))
        with self.assertRaisesRegex(worktree.WorktreeRefusal, "WORKTREE_OWNERSHIP_MISMATCH"):
            self.manager.delta(attempt)

    def test_conflict_abort_restores_exact_preimage_and_worker_uses_attempt_cwd(self) -> None:
        attempt = self.attempt()
        (attempt.path / "owned.txt").write_text("attempt\n", encoding="utf-8")
        attempt_commit = self.manager.commit(attempt)
        original = self.manager._git

        def crash_on_pick(cwd: Path, *argv: str, **kwargs):
            if argv[:1] == ("cherry-pick",) and "--abort" not in argv:
                raise worktree.WorktreeRefusal("GIT_COMMAND_FAILED", "simulated conflict")
            return original(cwd, *argv, **kwargs)

        with mock.patch.object(self.manager, "_git", side_effect=crash_on_pick):
            with self.assertRaisesRegex(worktree.WorktreeRefusal, "INTEGRATION_CONFLICT_ROLLED_BACK"):
                self.manager.integrate(attempt, attempt_commit, target=self.repo)
        self.assertEqual(attempt.base, self.git("rev-parse", "HEAD"))
        self.assertEqual("", self.git("status", "--porcelain"))
        result = worker.run_in_worktree(attempt, ["/bin/pwd"], env={"PATH": "/usr/bin:/bin"}, stdin=b"",
                                        timeout_ms=1_000, max_output_bytes=1_024, max_event_count=10)
        self.assertEqual("success", result["kind"])


if __name__ == "__main__":
    unittest.main()
