"""Verdict table of `harness/run/gate.py` over a real git repo and a v3 plan."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "harness" / "lib"))

from harness.run import gate  # noqa: E402
from packages.harness.tests.plan_fixture import ACTOR, run_plan, write_plan  # noqa: E402

PHASE_ID = "P1"
ITEM_ID = "P1.1"
MEDIUM = ("implementation", "medium")


def _ok_outcome(**overrides):
    base = {"outcome": "ok", "permission_denials": [], "result_text": "Status: done"}
    base.update(overrides)
    return base


class _Repo:
    """A git repo whose `plans/` holds one v3 plan with a started item."""

    def __init__(self, tmp):
        self.root = Path(tmp)
        self.plans = self.root / "plans"
        self._run(["init", "-q"])
        self._run(["config", "user.email", "gate-test@example.com"])
        self._run(["config", "user.name", "gate-test"])
        (self.root / ".gitkeep").write_text("")
        self._run(["add", ".gitkeep"])
        self.pre_plan_sha = self.commit("until the plan directory appears")
        self.plan_dir, _ = write_plan(self.root, items=[("in_progress", MEDIUM)])
        self.plan_id = self.plan_dir.name

    def _run(self, args):
        proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git {args} failed: {proc.stderr}")
        return proc

    def finish(self, status="done", *extra):
        run_plan("finish", "PLAN1", ITEM_ID, "--status", status, *extra, plans_root=self.plans)

    def write_scope_file(self, content="x = 1\n"):
        scope = self.root / "src" / "module.py"
        scope.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text(content)
        return scope

    def commit(self, message="fixture", *paths):
        self._run(["add", *[str(p) for p in paths]] if paths else ["add", "-A"])
        self._run(["commit", "-q", "-m", message, "--allow-empty"])
        return self._run(["rev-parse", "HEAD"]).stdout.strip()

    def commit_scope(self, message="item-commit", content="x = 1\n"):
        scope = self.write_scope_file(content)
        return self.commit(message, scope)

    def item_path(self):
        return self.plan_dir / "phases" / PHASE_ID / f"{ITEM_ID}.json"

    def snapshot(self):
        return gate.snapshot_before(self.plan_dir)


class GateVerdictTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = _Repo(self._tmp.name)
        self.before = self.repo.snapshot()

    def _verdict(self, outcome=None, *, before=None, monorepo_root=REPO_ROOT):
        return gate.verdict(self.repo.plan_id, ITEM_ID, PHASE_ID, self.repo.plan_dir,
                            before or self.before, outcome or _ok_outcome(),
                            monorepo_root=monorepo_root)

    def _closed(self, status="done", *extra):
        self.repo.commit_scope()
        self.repo.finish(status, "--check", "V1=0", *extra)

    # --- GREEN ----------------------------------------------------------------

    def test_clean_close_is_green(self):
        self._closed("done", "--notes", "Done.")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["signals_matched"], ["all-clear"])
        self.assertEqual(result["lint_class"], "clean")

    def test_plan_json_bookkeeping_outside_git_is_not_a_dirty_remainder(self):
        self._closed("done")
        self.assertEqual(self._verdict()["raw"]["closure"]["dirty_remainder"], [])

    # --- ATTENTION ------------------------------------------------------------

    def test_status_deviations_is_attention(self):
        self._closed("done_with_deviations", "--deviation", "Overkill effort.")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("status-deviations", result["signals_matched"])
        self.assertIn("known-deviations", result["signals_matched"])

    def test_permission_denials_is_attention(self):
        self._closed("done")
        result = self._verdict(_ok_outcome(permission_denials=["Bash(rm)"]))
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("permission-denials", result["signals_matched"])

    def test_pending_work_nonempty_is_attention(self):
        self._closed("done", "--pending", "One WARN linter outside Scope.")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("pending-work", result["signals_matched"])

    def test_check_warning_is_attention(self):
        self._closed("done")
        path = self.repo.item_path()
        item = json.loads(path.read_text(encoding="utf-8"))
        item["task_files"].append({"path": "src/missing.py", "change": "modify"})
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("check-warnings", result["signals_matched"])
        self.assertEqual(result["lint_class"], "warnings")

    # --- RED ------------------------------------------------------------------

    def test_worker_outcomes_other_than_ok_are_red(self):
        self._closed("done")
        for kind in ("timeout", "transport", "quota", "error"):
            with self.subTest(outcome=kind):
                result = self._verdict(_ok_outcome(outcome=kind, result_text=None))
                self.assertEqual(result["verdict"], gate.RED)
                self.assertIn("outcome-not-ok", result["signals_matched"])

    def test_check_error_is_red(self):
        self._closed("done")
        path = self.repo.item_path()
        item = json.loads(path.read_text(encoding="utf-8"))
        item["status"] = "BROKEN"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("check-errors", result["signals_matched"])
        self.assertEqual(result["lint_class"], "errors")

    def test_blocked_item_with_escalation_is_red(self):
        self.repo.commit_scope()
        self.repo.finish("blocked", "--escalation", "Owner must decide.")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("status-blocked", result["signals_matched"])
        self.assertIn("escalation-needed-yes", result["signals_matched"])

    def test_escalation_in_report_is_red(self):
        self._closed("done")
        result = self._verdict(_ok_outcome(result_text="... ESCALATION-REQUIRED: P1.1 — conflict"))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("escalation-in-report", result["signals_matched"])

    def test_no_commits_at_all_is_red(self):
        self.repo.finish("done", "--check", "V1=0")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("no-commits", result["signals_matched"])

    def test_dirty_remainder_after_clean_close_is_red(self):
        self._closed("done")
        (self.repo.root / "src" / "leftover.py").write_text("y = 1\n")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("dirty-remainder", result["signals_matched"])
        self.assertEqual(result["raw"]["closure"]["dirty_remainder"], ["?? src/leftover.py"])

    def test_preexisting_foreign_diff_does_not_cause_false_red(self):
        (self.repo.root / "foreign-owner-edit.md").write_text("owner works in parallel\n")
        before = self.repo.snapshot()
        self._closed("done")
        (self.repo.root / "foreign-owner-edit.md").write_text("owner works in parallel, more\n")
        result = self._verdict(before=before)
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertNotIn("dirty-remainder", result["signals_matched"])

    def test_no_op_status_not_terminal_is_red(self):
        self.repo.commit_scope("no-op: there is a commit, the status has not changed")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("no-op", result["signals_matched"])

    def test_unreadable_item_is_red(self):
        self._closed("done")
        result = gate.verdict(self.repo.plan_id, "P1.9", PHASE_ID, self.repo.plan_dir,
                              self.before, _ok_outcome(), monorepo_root=REPO_ROOT)
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("item-fields-unavailable", result["signals_matched"])

    def test_degraded_plan_api_is_not_green(self):
        self._closed("done")
        with tempfile.TemporaryDirectory() as empty:
            result = self._verdict(monorepo_root=empty)
        self.assertNotEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["lint_class"], "degraded")

    def test_totality_default_is_red(self):
        signals = {
            "outcome_class": "ok", "permission_denials": [], "result_text": "",
            "check_clean": True, "check_errors": False, "check_warnings": False,
            "commit_count": 1, "dirty_remainder": [], "item_fields_available": True,
            "item_status": "skipped",
            "pending_work_nonempty": False, "known_deviations_nonempty": False,
            "escalation_needed_yes": False,
        }
        klass, matched = gate._classify(signals)
        self.assertEqual(klass, gate.RED)
        self.assertEqual(matched, ["no-signal-matched-default"])

    def test_commit_count_and_order_are_not_judged(self):
        self.repo.commit_scope("scope-commit 1/2", "x = 1\n")
        self.repo.commit_scope("scope-commit 2/2 (item-commit)", "x = 2\n")
        self.repo.finish("done", "--check", "V1=0")
        self.repo.commit_scope("review-fix over topology", "x = 3\n")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["raw"]["closure"]["commit_count"], 3)


class PreLaunchVerdictTest(unittest.TestCase):
    def test_not_drivable_is_red_without_spawning_worker(self):
        queue_item = {"item_id": ITEM_ID, "drivable": False,
                      "refusal": "PHASE-NOT-DETAILED", "refusal_detail": "phase is a skeleton"}
        result = gate.pre_launch_verdict(queue_item)
        self.assertEqual(result["verdict"], gate.RED)
        self.assertEqual(result["raw"]["refusal"], "PHASE-NOT-DETAILED")

    def test_drivable_item_raises(self):
        with self.assertRaises(ValueError):
            gate.pre_launch_verdict({"drivable": True})


if __name__ == "__main__":
    sys.exit(unittest.main())
