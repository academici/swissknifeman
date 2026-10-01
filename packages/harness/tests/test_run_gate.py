"""Internal documentation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "harness" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "task" / "lib"))

from harness.run import gate  # noqa: E402


PLAN_ID = "GATE-FIXTURE"
PHASE_ID = "P1"
ITEM_ID = "P1.1"


def _plan_md(*, done, phase_status):
    return f"""# {PLAN_ID} — Fixture plan for gate (P4.4)

## 0. Meta

| Field | Meaning |
|:--|:--|
| Plan ID | {PLAN_ID} |
| Title | Fixture plan for gate |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Repository | swissknifeman |
| Approval Owner | dv |

## 1. Context

Synthetic plan for unit tests `harness/run/gate.py` (P4.4). NOT a battle plan.

## 2. Execution Rules

- One item at a time.

## 3. Routing

| Items | Model class/effort | Exec | Why |
|:--|:--|:--|:--|
| {ITEM_ID} | implementation/medium | run | gate fixture |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/total | Status |
|:--|:--|:--|:--|
| {PHASE_ID} | Phase times | {done}/1 | {phase_status} |

## 5. Decision Log

| D# | Date | Solution | Why |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | Closed set fittings | cover gate without a second parser |

## 6. Update Log

| Date | Who (role/model) | What |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | Fixture created (P4.4) |
"""


def _phase_md(*, status, completion_notes="—", pending_work="—", known_deviations="—",
             escalation_needed="no", escalation_blockquote=False):
    blockquote = (f"> 🔴 ESCALATION {ITEM_ID}: test block | trigger: contradictory evidence "
                 f"| needed: plan-design\n\n") if escalation_blockquote else ""


    if status in ("🟢 Done", "🟠 Done with deviations"):
        completion_notes = f"{completion_notes}\n\nwrite-site: pre_mutation: allow · pre_final: allow"
    return f"""# {PHASE_ID} — Phase times

## Phase Context

Synthetic phase of fixture `gate` (P4.4).

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| {ITEM_ID} | Basic item | {status} | 2026-08-01 |

### {ITEM_ID} — Basic item

{blockquote}**Status:** {status}
**Intent:** Demonstrates gate.
**Why:** Basic case.
**Scope Included:** nothing - fixture.
**Scope Excluded:** real logic.
**Inputs:** —
**Files:** —
**Required Reads:** 1) not applicable (fixture).
**Implementation Rules:** no - fixture.
**Code Guidance:** no - fixture.
**Validation:** not applicable - fixture is read by tests `gate`.
**Deliverables:** synthetic data for `test_run_gate.py`.
**Completion Notes:** {completion_notes}
**Pending Work:** {pending_work}
**Known Deviations:** {known_deviations}
**Escalation Needed:** {escalation_needed}

## Phase Handoff

Fixture: the phase does not really give up, it is used by tests `gate`.
"""


def _bootstrap_handoff_md():
    """Internal documentation."""
    return f"""# HANDOFF — 2026-08-01 — after P0.0

**Next:** exec-items: task:plan-run {PLAN_ID} {ITEM_ID}

| Parameter | Meaning |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Context | continue (/clear) |
| The bottom line | fixture - the plan has not yet been touched |

```
/task:plan-run {PLAN_ID} {ITEM_ID}
```

**Done:** —
**Remaining:** {ITEM_ID}.
**Sources of truth:** plans/{PLAN_ID}/plan.md · plans/{PLAN_ID}/phases/{PHASE_ID}.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def _handoff_md():
    return f"""# HANDOFF — 2026-08-01 — after {ITEM_ID}

**Next:** run-items: task:plan-run {PLAN_ID} {ITEM_ID}

| Parameter | Meaning |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Context | continue (/clear) |
| The bottom line | fixture - read by tests `gate` |

```
/task:plan-run {PLAN_ID} {ITEM_ID}
```

**Done:** fixture created (P4.4).
**Remaining:** nothing - the plan is not a combat one.
**Sources of truth:** plans/{PLAN_ID}/plan.md · plans/{PLAN_ID}/phases/{PHASE_ID}.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def _ok_outcome(**overrides):
    base = {"outcome": "ok", "permission_denials": [], "result_text": "Status: 🟢 Done"}
    base.update(overrides)
    return base


class _Repo:
    """Internal documentation."""

    def __init__(self, tmp):
        self.root = Path(tmp)
        self.plan_dir = self.root / "plans" / PLAN_ID
        self._run(["init", "-q"])
        self._run(["config", "user.email", "gate-test@example.com"])
        self._run(["config", "user.name", "gate-test"])





        (self.root / ".gitkeep").write_text("")
        self._run(["add", ".gitkeep"])
        self.pre_plan_sha = self.commit("until the plan directory appears")
        (self.plan_dir / "phases").mkdir(parents=True)

    def _run(self, args, check=True):
        proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {args} failed: {proc.stderr}")
        return proc

    def write_plan(self, *, done=0, phase_status="🟡 In progress"):



        self._plan_writes = getattr(self, "_plan_writes", 0) + 1
        text = (self.plan_dir / "plan.md").read_text()
        text += f"\n<!-- write #{self._plan_writes}: {done}/{phase_status} -->\n"
        (self.plan_dir / "plan.md").write_text(text)

    def write_phase(self, **kwargs):
        self._phase_writes = getattr(self, "_phase_writes", 0) + 1
        status = kwargs.get("status", "🟡 In progress")
        self._status_valid = status in {"🟢 Done", "🟠 Done with deviations", "🔴 Blocked", "🟡 In progress"}
        result = {
            "🟢 Done": "closed-green",
            "🟠 Done with deviations": "closed-deviations",
            "🔴 Blocked": "blocked",
        }.get(status, "in-progress")
        event = {
            "actor": "implementation/medium", "attempt": 1, "command": "plan-run",
            "cost_usd": None, "duration_ms": None, "friction": [], "item_id": ITEM_ID,
            "note": "v2 gate fixture", "num_turns": None, "plan_id": PLAN_ID,
            "result": result, "run_id": f"{self._phase_writes:064x}", "session_id": "fixture",
            "ts": f"2026-08-01T00:00:{self._phase_writes:02d}Z",
        }
        (self.plan_dir / "journal.jsonl").write_text(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        )
        from task import plan_decisions, plan_item_state, plan_status
        plan_item_state.build_states(self.plan_dir, item_id=ITEM_ID)
        state = self.plan_dir / "phases" / PHASE_ID / f"{ITEM_ID}.state.md"
        state_text = state.read_text()
        if status not in {"🟢 Done", "🟠 Done with deviations", "🔴 Blocked", "🟡 In progress"}:
            state_text = state_text.replace("**Status:** 🟡 In progress", f"**Status:** {status}")
        replacements = {
            "Completion Notes": kwargs.get("completion_notes", "—"),
            "Pending Work": kwargs.get("pending_work", "—"),
            "Known Deviations": kwargs.get("known_deviations", "—"),
            "Escalation Needed": kwargs.get("escalation_needed", "no"),
        }
        for field, value in replacements.items():
            state_text = state_text.replace(f"**{field}:** —", f"**{field}:** {value}")
        state.write_text(state_text)
        if self._status_valid:
            plan_status.build_status(self.plan_dir)
        plan_decisions.build_views(self.plan_dir)
        phase = self.plan_dir / "phases" / PHASE_ID / f"{PHASE_ID}.md"
        phase_text = phase.read_text() + f"\n<!-- state: {status} -->\n"
        if kwargs.get("escalation_blockquote"):
            item_spec = self.plan_dir / "phases" / PHASE_ID / f"{ITEM_ID}.md"
            item_spec.write_text(item_spec.read_text() + (
                f"> 🔴 ESCALATION {ITEM_ID}: fixture block | trigger: contradictory evidence "
                "| needed: plan-design\n"
            ))
        phase.write_text(phase_text)

    def write_handoff(self):
        handoff = self.plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text() + "\n<!-- bookkeeping -->\n")

    def write_bootstrap_handoff(self):
        return None

    def write_scope_file(self, content="x = 1\n"):
        scope = self.root / "src" / "module.py"
        scope.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text(content)
        return scope

    def add(self, *paths):
        self._run(["add", *[str(p) for p in paths]])

    def commit(self, message="fixture"):
        self._run(["commit", "-q", "-m", message])
        return self._run(["rev-parse", "HEAD"]).stdout.strip()

    def commit_bookkeeping(self, message="bookkeeping"):
        plan_path = self.plan_dir / "plan.md"
        if self._run(["status", "--porcelain", "--", str(plan_path)]).stdout.strip():
            self.add(plan_path)
            self.commit("fixture scope")
        if getattr(self, "_status_valid", True):
            from task import plan_status
            plan_status.build_status(self.plan_dir)
        self.add(
            self.plan_dir / "handoff.md",
            self.plan_dir / "journal.jsonl",
            self.plan_dir / "status.md",
            self.plan_dir / "decisions",
            self.plan_dir / "phases" / PHASE_ID / f"{PHASE_ID}.md",
            self.plan_dir / "phases" / PHASE_ID / f"{ITEM_ID}.md",
            self.plan_dir / "phases" / PHASE_ID / f"{ITEM_ID}.state.md",
        )
        return self.commit(message)

    def initial_commit(self):
        from packages.harness.tests.v2_plan_fixture import write_v2_plan
        self.plan_dir = write_v2_plan(
            self.root, plan_id=PLAN_ID, items=[(ITEM_ID, "🟡 In progress")],
            routing_rows=[f"| {ITEM_ID} | implementation/medium | run | fixture |"],
            next_line=f"exec-items: task:plan-run {PLAN_ID} {ITEM_ID}",
        )
        self.write_plan()
        self.write_phase(status="🟡 In progress")
        self.write_bootstrap_handoff()
        self.add(self.plan_dir)
        return self.commit("initial")

    def snapshot(self):
        return gate.snapshot_before(self.plan_dir)


class LayoutBookkeepingTest(unittest.TestCase):
    def test_v2_status_and_decisions_are_bookkeeping(self):
        root = "plans/V2"
        layout = {"bookkeeping_patterns": ["status.md", "decisions/<D-id>.md"]}
        self.assertTrue(gate._is_bookkeeping(f"{root}/status.md", root, layout))
        self.assertTrue(gate._is_bookkeeping(f"{root}/decisions/D001-test.md", root, layout))
        self.assertFalse(gate._is_bookkeeping(f"{root}/notes.md", root, layout))

    def test_v2_uses_task_resolver_for_real_carrier_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "V2"
            phase = plan / "phases" / "P1"
            phase.mkdir(parents=True)
            (plan / "plan.md").write_text(
                "## 0. Meta\n\n| Field | Meaning |\n|:--|:--|\n| Layout | v2 |\n")
            (phase / "P1.md").write_text("# P1\n")
            resolved = gate._call_plan_layout(plan, "P1", REPO_ROOT)
            self.assertEqual(resolved["layout"], "v2")
            self.assertEqual(Path(resolved["phase"]), phase / "P1.md")
            self.assertTrue(gate._is_bookkeeping(
                f"plans/V2/{Path(resolved['journal']).name}", "plans/V2", resolved))


class GateVerdictTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _Repo(self._tmp.name)
        self.repo.initial_commit()
        self.before = self.repo.snapshot()

    def tearDown(self):
        self._tmp.cleanup()

    def _verdict(self, outcome=None):
        return gate.verdict(PLAN_ID, ITEM_ID, PHASE_ID, self.repo.plan_dir, self.before,
                           outcome or _ok_outcome(), monorepo_root=REPO_ROOT)

    # --- GREEN --------------------------------------------------------------

    def test_clean_close_is_green(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["signals_matched"], ["all-clear"])
        self.assertEqual(result["lint_class"], "clean")

    # --- ATTENTION ------------------------------------------------------------

    def test_status_deviations_is_attention(self):
        self.repo.write_plan(done=0, phase_status="🟡 In progress")
        self.repo.write_phase(status="🟠 Done with deviations",
                              completion_notes="Submitted with a caveat.",
                              known_deviations="Overkill effort.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("status-deviations", result["signals_matched"])

    def test_permission_denials_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(permission_denials=["Bash(rm)"]))
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("permission-denials", result["signals_matched"])

    def test_pending_work_nonempty_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.",
                              pending_work="One WARN linter out Scope.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("pending-work", result["signals_matched"])

    def test_known_deviations_nonempty_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.",
                              known_deviations="Overkill effort (implementation/high instead medium).")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("known-deviations", result["signals_matched"])

    def test_bundle_is_attention_not_red(self):
        """Internal documentation."""
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        scope = self.repo.write_scope_file()
        self.repo.add(scope, self.repo.plan_dir)
        self.repo.commit("bundle: scope + bookkeeping in one commit")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("bundle", result["signals_matched"])

    def test_only_new_warning_is_attention(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        # Reordering canonical item fields is a warning-only v2 fixture defect.
        spec = self.repo.plan_dir / "phases" / PHASE_ID / f"{ITEM_ID}.md"
        lines = spec.read_text().splitlines()
        intent = next(index for index, line in enumerate(lines) if line.startswith("**Intent:**"))
        why = next(index for index, line in enumerate(lines) if line.startswith("**Why:**"))
        lines[intent], lines[why] = lines[why], lines[intent]
        spec.write_text("\n".join(lines) + "\n")
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.ATTENTION)
        self.assertIn("lint-new-warning-only", result["signals_matched"])
        self.assertEqual(result["lint_class"], "new-warning-only")

    # --- RED ------------------------------------------------------------------

    def test_worker_timeout_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(outcome="timeout", result_text=None))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("outcome-not-ok", result["signals_matched"])

    def test_worker_transport_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(outcome="transport", result_text=None))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("outcome-not-ok", result["signals_matched"])

    def test_worker_quota_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(outcome="quota", result_text=None))
        self.assertEqual(result["verdict"], gate.RED)

    def test_new_error_is_red(self):
        self.repo.write_plan(done=0, phase_status="🟡 In progress")

        self.repo.write_phase(status="🟢 BROKEN")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("lint-new-error", result["signals_matched"])
        self.assertEqual(result["lint_class"], "new-error-suspected")

    def test_status_blocked_is_red(self):
        self.repo.write_plan(done=0, phase_status="🔴 Blocked")
        self.repo.write_phase(status="🔴 Blocked", escalation_needed="yes",
                              escalation_blockquote=True)
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("status-blocked", result["signals_matched"])

    def test_escalation_needed_yes_is_red(self):
        self.repo.write_plan(done=0, phase_status="🔴 Blocked")
        self.repo.write_phase(status="🔴 Blocked", escalation_needed="yes",
                              escalation_blockquote=True)
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict()
        self.assertIn("escalation-needed-yes", result["signals_matched"])

    def test_escalation_in_report_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = self._verdict(_ok_outcome(result_text="... ESCALATION-REQUIRED: P1.1 — conflict"))
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("escalation-in-report", result["signals_matched"])

    def test_no_commits_at_all_is_red(self):

        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("no-commits", result["signals_matched"])

    def test_closure_not_committed_at_all_is_red(self):
        """Internal documentation."""
        scope = self.repo.write_scope_file()
        self.repo.add(scope)
        self.repo.commit("item-commit: only Scope")

        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("closure-signature-incomplete", result["signals_matched"])

    def test_closure_partial_handoff_missing_is_red(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")

        self.repo.add(self.repo.plan_dir / "plan.md", self.repo.plan_dir / "phases" / PHASE_ID / f"{PHASE_ID}.md")
        self.repo.commit("bookkeeping without handoff.md")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("closure-signature-incomplete", result["signals_matched"])
        self.assertFalse(result["raw"]["closure"]["signature_complete"])

    def test_dirty_remainder_after_clean_close_is_red(self):
        """Internal documentation."""
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()

        plan_path = self.repo.plan_dir / "plan.md"
        plan_path.write_text(plan_path.read_text() + "\n<!-- uncommitted tail -->\n")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("dirty-remainder", result["signals_matched"])

    def test_preexisting_foreign_diff_does_not_cause_false_red(self):
        """Internal documentation."""
        foreign = self.repo.plan_dir / "foreign-owner-edit.md"
        foreign.write_text("owner rules in parallel\n")
        before = self.repo.snapshot()
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        result = gate.verdict(PLAN_ID, ITEM_ID, PHASE_ID, self.repo.plan_dir, before,
                              _ok_outcome(), monorepo_root=REPO_ROOT)
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertNotIn("dirty-remainder", result["signals_matched"])

    def test_no_op_status_not_terminal_is_red(self):
        self.repo.write_plan(done=0, phase_status="🟡 In progress")
        self.repo.write_phase(status="🟡 In progress")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping("no-op: there is a commit, the status has not changed")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.RED)
        self.assertIn("no-op", result["signals_matched"])

    def test_totality_default_is_red(self):
        """Internal documentation."""
        signals = {
            "outcome_class": "ok", "permission_denials": [], "result_text": "",
            "lint_clean": True, "lint_new_error_suspected": False, "lint_new_warning_only": False,
            "commit_count": 1, "signature_complete": True, "bundle": False,
            "dirty_remainder": [], "item_fields_available": True,
            "item_status": "⛔ Skipped by decision",
            "pending_work_nonempty": False, "known_deviations_nonempty": False,
            "escalation_needed_yes": False,
        }
        klass, matched = gate._classify(signals)
        self.assertEqual(klass, gate.RED)
        self.assertEqual(matched, ["no-signal-matched-default"])



    def test_commit_count_and_order_are_not_judged(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()

        scope1 = self.repo.write_scope_file("x = 1\n")
        self.repo.add(scope1)
        self.repo.commit("scope-commit 1/2")
        scope1.write_text("x = 2\n")
        self.repo.add(scope1)
        self.repo.commit("scope-commit 2/2 (item-commit)")
        self.repo.commit_bookkeeping("bookkeeping-commit")

        scope1.write_text("x = 3\n")
        self.repo.add(scope1)
        self.repo.commit("review-fix over topology")
        result = self._verdict()
        self.assertEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["raw"]["closure"]["commit_count"], 5)



    def test_degraded_baseline_is_not_green(self):
        self.repo.write_plan(done=1, phase_status="🟢 Done")
        self.repo.write_phase(status="🟢 Done", completion_notes="Done.")
        self.repo.write_handoff()
        self.repo.commit_bookkeeping()
        broken_before = dict(self.before, sha=self.repo.pre_plan_sha)
        result = gate.verdict(PLAN_ID, ITEM_ID, PHASE_ID, self.repo.plan_dir, broken_before,
                              _ok_outcome(), monorepo_root=REPO_ROOT)
        self.assertNotEqual(result["verdict"], gate.GREEN)
        self.assertEqual(result["lint_class"], "degraded")


class PreLaunchVerdictTest(unittest.TestCase):
    def test_not_drivable_is_red_without_spawning_worker(self):
        queue_item = {"item_id": ITEM_ID, "drivable": False,
                     "refusal": "EXEC-NOT-RUN", "refusal_detail": "Exec=plan-design"}
        result = gate.pre_launch_verdict(queue_item)
        self.assertEqual(result["verdict"], gate.RED)
        self.assertEqual(result["raw"]["refusal"], "EXEC-NOT-RUN")

    def test_drivable_item_raises(self):
        with self.assertRaises(ValueError):
            gate.pre_launch_verdict({"drivable": True})


if __name__ == "__main__":
    sys.exit(unittest.main())
