"""Contracts, baseline and late protocol gate cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *


class TestContractsSection(TmpPlanTestCase):
    """m7/D10 — optional section `## 7. Contracts` + cross-plan version reconciliation (§11)."""

    CONTRACT = "root/contracts/module-manifest.md"

    def _write_pair(self, donor_version, pinned):
        """Donor DONOR (Exported) + consumer CONSUMER (Consumed) in one root plans/."""
        donor = write_valid_plan(self.root, "DONOR")
        consumer = write_valid_plan(self.root, "CONSUMER")
        (donor / "plan.md").write_text(
            plan_md("DONOR") + contracts_section(
                exported=[(self.CONTRACT, donor_version, "CONSUMER (P1.1)")]),
            encoding="utf-8")
        (consumer / "plan.md").write_text(
            plan_md("CONSUMER") + contracts_section(
                consumed=[(f"DONOR/{self.CONTRACT}", "DONOR", pinned)]),
            encoding="utf-8")
        (self.root / "plans" / "ACTIVE.md").write_text(active_md("DONOR"), encoding="utf-8")
        return self.root / "plans"

    def _lint_root(self, plans_root):
        diag = Diagnostics()
        models = {d.name: lint_plan(d, diag) for d in discover_plan_dirs(plans_root)}
        lint_plans_root(plans_root, models, diag)
        return models, diag

    def test_versions_in_sync_no_warning(self):
        models, diag = self._lint_root(self._write_pair("v2.0.2", "v2.0.2"))
        self.assertEqual(diag.errors, [])
        self.assertEqual([w for w in diag.warnings if "notification not posted" in w], [])
        self.assertEqual(models["DONOR"]["contracts"]["exported"][0]["Version"], "v2.0.2")

    def test_version_drift_warns_once(self):
        _, diag = self._lint_root(self._write_pair("v2.0.2", "v2.0.0"))
        hits = [w for w in diag.warnings if "notification not posted" in w]
        self.assertEqual(len(hits), 1, diag.warnings)
        self.assertIn("consumer CONSUMER pinned to v2.0.0", hits[0])
        self.assertEqual(diag.errors, []) # only WARNING — mechanism is young

    def test_no_section_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        model, diag = _lint(plan_dir)
        self.assertEqual(diag.errors, [])
        self.assertEqual(diag.warnings, [])
        self.assertEqual(model["contracts"], {"exported": [], "consumed": []})

    def test_donor_outside_root_silent(self):
        # Donor in another repo (it is not in this root) — linter is honestly silent (border §11).
        consumer = write_valid_plan(self.root, "CONSUMER")
        (consumer / "plan.md").write_text(
            plan_md("CONSUMER") + contracts_section(
                consumed=[(f"REGHUB/{self.CONTRACT}", "REGHUB", "v2.0.0")]),
            encoding="utf-8")
        (self.root / "plans" / "ACTIVE.md").write_text(active_md("CONSUMER"), encoding="utf-8")
        _, diag = self._lint_root(self.root / "plans")
        self.assertEqual(diag.errors, [])
        self.assertEqual([w for w in diag.warnings if "notification not posted" in w], [])

    def test_wrong_columns_warn_not_error(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        broken = contracts_section(
            exported=[(self.CONTRACT, "v1.0.0", "—")]).replace("| Status |", "| State |")
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1") + broken, encoding="utf-8")
        model, diag = _lint(plan_dir)
        self.assertEqual(diag.errors, [])
        self.assertTrue(any("columns" in w for w in diag.warnings), diag.warnings)
        self.assertEqual(model["contracts"]["exported"], [])  # crooked table is not parsed


class TestBaselineGate(TmpPlanTestCase):
    """P1.2/B1/D5/D6 — `--baseline`/`--gate`: deterministic count of new errors K."""

    def _git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.root), check=True, capture_output=True)

    def _init_repo_with_valid_plan(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        return plan_dir

    def test_read_budget_observations_do_not_rekey_same_baseline_failure(self):
        before, after = Diagnostics(), Diagnostics()
        path = self.root / "plans" / "DEMO-1" / "plan.md"
        before.error(path, None,
                     "read-budget-v1: item P1.1: weight 100001 > threshold 100000 "
                     "evaluation tokens (calibration)")
        after.error(path, None,
                    "read-budget-v1: item P1.1: weight 100777 > threshold 100000 "
                    "evaluation tokens (calibration)")
        self.assertEqual(before.normalized_keys(self.root), after.normalized_keys(self.root))

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_baseline_no_new_errors_on_clean_tree(self):
        plan_dir = self._init_repo_with_valid_plan()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("new from working tree: 0", out.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_baseline_counts_new_error_and_gate_new_fails(self):
        plan_dir = self._init_repo_with_valid_plan()
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline", "HEAD", "--gate", "new"])
        self.assertEqual(code, 1)
        self.assertIn("new from working tree: 1", out.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_baseline_default_gate_stays_all_even_when_k_zero(self):
        # --gate=all (default, back-compat CI) — exit by N, even if baseline-diff
        # clean (K==0), and the plan carries a residual error outside the diff of this commit.
        plan_dir = self._init_repo_with_valid_plan()
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "broken baseline too")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 1)
        self.assertIn("new from working tree: 0", out.getvalue())

    def test_baseline_unavailable_without_git_repo(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # NO git init
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 0, err.getvalue())  # exit by N (plan is valid), not by K
        self.assertIn("baseline", err.getvalue())
        self.assertIn("not available", err.getvalue())
        self.assertNotIn("new from working tree", out.getvalue())


class TestAuditBlockOutsidePhaseGates(TmpPlanTestCase):
    """P3.8/A4/D52 — append-only block `## Audit Pn` OUTSIDE the phase grep region.
    The auditor is required to name the marker on which he is reporting («markers X — 0»);
    grep throughout the phase file was dropping a gate on its own line. Region ends with
    first `## Audit`; same marker in BODY item'but still gives WARNING."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _append_audit_block(self, plan_dir, body, phase="P1"):
        p = phase_index_path(plan_dir, phase)
        p.write_text(p.read_text(encoding="utf-8")
                     + f"\n## Audit {phase} — 2026-07-15\n\n**Verdict:** 🟢 GREEN\n\n{body}\n",
                     encoding="utf-8")

    # --- A4: DoR-marker ONLY in the audit block → gate is silent -----------------------
    def test_clarification_marker_inside_audit_block_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._append_audit_block(
            plan_dir, "- Checked: markers `[NEEDS CLARIFICATION: …]` in phase - 0.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "NEEDS CLARIFICATION"), [], diag.warnings)

    # --- control: same marker in BODY item'a → WARNING (gate is not weakened) -------
    def test_clarification_marker_in_item_body_still_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p1 = item_spec_path(plan_dir)
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "**Why:** Diagnostics are expensive.",
            "**Why:** Diagnostics are expensive. [NEEDS CLARIFICATION: what format?]"),
            encoding="utf-8")
        self._append_audit_block(plan_dir, "- Checked: 0 qualification markers.")
        _, diag = _lint(plan_dir)
        self.assertTrue(self._warnings_containing(diag, "NEEDS CLARIFICATION"), diag.warnings)

    # --- same region for the second grep in phase: orchestration sign in the audit block -
    def test_orchestration_marker_inside_audit_block_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._append_audit_block(
            plan_dir, "- Orchestration by phase is not declared: `scriptPath` in launch-block is missing.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "states orchestration"), [], diag.warnings)


class TestCheckpointedGate83(TmpPlanTestCase):
    """P8.3/D44: item with status `🔴 Blocked` is required to bear Pending Work line
    `Resume: <command>`; `⛔ Skipped by decision` — EXACTLY `Resume: —` AND
    link `D<number>`. Activation - opt-in Meta `Closure Protocol | v1` (without canon date:
    on the date of details of living 🔴/⛔ items with protocol enabled not available in fleet). Everyone
    distinguishing case checked RED on the code before item'a: `git show
    HEAD:packages/task/lib/task/plan_lint.py` did not carry any `_lint_checkpointed_83`, neither
    call from `lint_plan` — the old code was silent on ALL cases."""

    def _write(self, *, closure_protocol="v1", item_status="🔴 Blocked", pending_work="—"):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "plan.md").write_text(
            plan_md(plan_dir.name, closure_protocol=closure_protocol),
            encoding="utf-8")
        write_v2_carriers(
            plan_dir, item_state=item_state_md(
                item_status=item_status, pending_work=pending_work))
        return plan_dir

    def test_a_blocked_with_resume_command_passes(self):
        """(a) 🔴 + `Resume: <command>` → there are no gate diagnostics."""
        plan_dir = self._write(pending_work="Resume: /task:plan-design DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Resume"), [])

    def test_b_blocked_without_resume_line_is_error_with_id(self):
        """(b) 🔴 without line `Resume:` → ERROR, text carries id item'a."""
        plan_dir = self._write(pending_work="—")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "Resume")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in e for e in hits), hits)

    def test_b2_blocked_with_bare_dash_resume_is_error(self):
        """(b, option) 🔴 + `Resume: —` (bare dash, without external blocker and
        without command) → ERROR: non-empty command is required, «—» doesn't count for her."""
        plan_dir = self._write(pending_work="Resume: —")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Resume"), diag.errors)

    def test_b3_blocked_with_external_blocker_form_passes(self):
        """(b, option) 🔴 + `Resume: — (external blocker: …)` — legal form
        for blocker without local step (Code Guidance P8.3) → no diagnostics."""
        plan_dir = self._write(
            pending_work="Resume: — (external blocker: owner's decision on OQ-4)")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Resume"), [])

    def test_c_skipped_without_resume_and_d_ref_is_error(self):
        """(in) ⛔ without `Resume: —`/without `D<number>` → ERROR with id item'a."""
        plan_dir = self._write(item_status="⛔ Skipped by decision", pending_work="—")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "Resume")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in e for e in hits), hits)

    def test_c2_skipped_with_resume_dash_but_no_d_ref_is_error(self):
        """(in, option) ⛔ + `Resume: —`, but WITHOUT link `D<number>` → ERROR:
        the decision to pass must be presented in writing, not in silence."""
        plan_dir = self._write(item_status="⛔ Skipped by decision",
                               pending_work="Resume: —")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Resume"), diag.errors)

    def test_c3_skipped_with_resume_dash_and_d_ref_passes(self):
        """(in, reverse) ⛔ + EXACTLY `Resume: —` AND `D40` in the same field (other
        line) → no diagnostics."""
        plan_dir = self._write(
            item_status="⛔ Skipped by decision",
            pending_work="Resume: —\nMoot, decision — D40.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Resume"), [])

    def test_d_done_status_has_no_new_requirement(self):
        """(g) 🟢 Done without line `Resume:` — gate is silent (requirement only for
        🔴/⛔)."""
        plan_dir = self._write(item_status="🟢 Done", pending_work="—")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Resume"), [])

    def test_e_additivity_plan_without_meta_field_gets_no_new_diagnostics(self):
        """(d) ADDITIVITY: same 🔴-plan WITHOUT Meta `Closure Protocol` does not give any
        one gate diagnostic, even without a line `Resume:`."""
        plan_dir = self._write(closure_protocol=None, pending_work="—")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Resume"), [])


class TestHandoffBoardGate113(TmpPlanTestCase):
    """P11.3/D129: every occurrence `Pn a/b` in handoff.md must match the value
    columns `Items 🟢/total` lines `Pn` boards «## 4. Phase Index & Status Board»; phase,
    missing from the board, - «dangling link». Forward-only by TITLE DATE handoff'a
    (HANDOFF_BOARD_CANON_DATE); severity inside the scope - like launch-block-gate (dated
    `plan_id` from BRIEF_CANON_DATE → ERROR, legacy → WARNING). Each distinguishing case
    checked RED on the code before item'a: `git show HEAD:packages/task/lib/task/
    plan_lint.py` did not carry any `_lint_handoff_board_113`, neither `HANDOFF_BOARD_REF_RE`, no call
    from `lint_plan` — the old code was silent in ALL cases below."""

    def _write(self, *, plan_id="DEMO-1", handoff_date="2026-07-28", handoff_extra="",
               items_cell="1/1"):
        plan_dir = write_valid_plan(self.root, plan_id=plan_id)
        if items_cell != "1/1":
            (plan_dir / "plan.md").write_text(
                plan_md(plan_dir.name, items_cell=items_cell), encoding="utf-8")
        text = handoff_md(plan_dir.name).replace(
            "# HANDOFF — 2026-07-02 — after P1.1",
            f"# HANDOFF — {handoff_date} — after P1.1")
        if handoff_extra:
            text = text.replace("**Done:** P1.1 is closed.",
                                 f"**Done:** P1.1 is closed. {handoff_extra}")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        return plan_dir

    def test_a_f8_mismatch_on_dated_plan_is_error_naming_both_sides(self):
        """(a) fixture F8: handoff says `P1 4/4`, board carries `1/1` (default) on
        date `plan_id` (≥ BRIEF_CANON_DATE) → ERROR, text names BOTH sides."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO",
                               handoff_extra="Board: P1 4/4 according to the prose.")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "P1 4/4")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("1/1" in e for e in hits), hits)

    def test_b_matching_numbers_is_silent(self):
        """(b) handoff `P1 1/1` matches the board `1/1` → there are no gate diagnostics."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO",
                               handoff_extra="Board: P1 1/1 according to the prose.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "P1 1/1") +
                         [w for w in diag.warnings if "P1 1/1" in w], [])

    def test_c_handoff_older_than_canon_date_is_silent(self):
        """(in) forward-only: handoff dated < HANDOFF_BOARD_CANON_DATE — even
        deliberate discrepancy `P1 4/4` vs board `1/1` is not diagnosed."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO", handoff_date="2026-07-27",
                               handoff_extra="Board: P1 4/4 (obviously incorrect).")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "P1 4/4") +
                         [w for w in diag.warnings if "P1 4/4" in w], [])

    def test_d_phase_missing_from_board_is_dangling_reference(self):
        """(g) `Pn`, missing from the board (plan carries only `P1`), → diagnostics
        «dangling link»."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO",
                               handoff_extra="See The P9 3/5 — phase does not exist in this plane.")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "dangling link")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P9" in e for e in hits), hits)

    def test_e_legacy_plan_id_mismatch_is_warning_not_error(self):
        """(d) severity-fork, like brief/launch-block-gate: legacy `plan_id`
        (not dated) with discrepancy → WARNING, and not ERROR."""
        plan_dir = self._write(plan_id="DEMO-1",
                               handoff_extra="Board: P1 4/4 according to the prose.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "P1 4/4"), [])
        self.assertTrue([w for w in diag.warnings if "P1 4/4" in w], diag.warnings)

    def test_f_additivity_plan_without_pattern_gets_no_new_diagnostics(self):
        """(e) ADDITIVITY: date plan with GATE ACTIVE (handoff ≥ canon-dates), but WITHOUT
        template `Pn a/b` in handoff'e, gives EXACTLY the same set of diagnostics as the same plan with
        silent gate (handoff < canon-dates) — SET comparison (D129, plan without
        handoff-numbers does not receive ANY new diagnostics)."""
        baseline_dir = self._write(plan_id="2026.07.28-DEMO-PLAN", handoff_date="2026-07-27")
        _, baseline_diag = _lint(baseline_dir)
        baseline = set(baseline_diag.normalized_keys(baseline_dir))

        plan_dir = self._write(plan_id="2026.07.28-DEMO", handoff_date="2026-07-28")
        _, diag = _lint(plan_dir)
        self.assertEqual(set(diag.normalized_keys(plan_dir)), baseline,
                         (diag.errors, diag.warnings))
