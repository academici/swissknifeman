"""Canon conflicts and plan-2.0 warning cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *
import task.plan_lint_checks.conflicts as conflicts_module
from hashlib import sha256
import json


class TestConflictsFlagUnits(unittest.TestCase):
    """Units `--conflicts` on SYNTHETIC canon - fix
    FORM of reconciliation, regardless of the current live text `SKILL.md` (same principle as
    `test_canon_literals.py::TestT1CollectorVectors`). Live run vs real canon
    covered `TestConflictsFlagLiveRepo` below."""

    def _diag(self):
        return Diagnostics()

    # --- statuses -------------------------------------------------------------
    def test_statuses_consistent_is_silent(self):
        lines = [conflicts_module.CONFLICTS_ANCHOR_STATUSES, "```text",
                 *STATUSES, "```"]
        diag = self._diag()
        _conflicts_statuses(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_statuses_mismatch_is_error_with_both_sides(self):
        corrupted = STATUSES[:3] + ("🟠 Done with STRANGE deviations",) + STATUSES[4:]
        lines = [conflicts_module.CONFLICTS_ANCHOR_STATUSES, "```text",
                 *corrupted, "```"]
        diag = self._diag()
        _conflicts_statuses(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        [msg] = diag.errors
        self.assertIn("SKILL.md:", msg)
        self.assertIn("plan_lint.py:", msg)
        self.assertIn("STRANGE", msg)

    # --- 16 fields item'a -------------------------------------------------------
    def test_item_fields_consistent_is_silent(self):
        lines = ["- **Items.** Fields are strict lines",
                 f"  {conflicts_module.CONFLICTS_ANCHOR_ITEM_FIELDS}",
                 f"  `{', '.join(REQUIRED_ITEM_FIELDS)}`."]
        diag = self._diag()
        _conflicts_item_fields(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_item_fields_reordered_is_error(self):
        shuffled = REQUIRED_ITEM_FIELDS[1:] + REQUIRED_ITEM_FIELDS[:1]
        lines = ["- **Items.** Fields are strict lines",
                 f"  {conflicts_module.CONFLICTS_ANCHOR_ITEM_FIELDS}",
                 f"  `{', '.join(shuffled)}`."]
        diag = self._diag()
        _conflicts_item_fields(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "16-fields"), diag.errors)

    # --- forms Next ------------------------------------------------------------
    def _code_next_kinds(self):
        import re
        gm = re.search(r"\^\((.*?)\):", SEMANTIC_NEXT_RE.pattern)
        return gm.group(1).split("|")

    def test_next_forms_consistent_is_silent(self):
        lines = ["**Allowed `Next` forms**:", "```text", conflicts_module.CONFLICTS_ANCHOR_NEXT_FORMS,
                 "|:--|:--|"]
        lines += [f"| {kind}: example | explanation |" for kind in self._code_next_kinds()]
        lines += ["Other form = ERROR plan-lint.", "```"]
        diag = self._diag()
        _conflicts_next_forms(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_next_forms_missing_one_is_error(self):
        kinds = self._code_next_kinds()[:-1]  # without the last form (waiting)
        lines = ["**Allowed `Next` forms**:", "```text", conflicts_module.CONFLICTS_ANCHOR_NEXT_FORMS,
                 "|:--|:--|"]
        lines += [f"| {kind}: example | explanation |" for kind in kinds]
        lines += ["Other form = ERROR plan-lint.", "```"]
        diag = self._diag()
        _conflicts_next_forms(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "forms Next"), diag.errors)

    # --- three values Context ----------------------------------------------
    def test_context_values_consistent_is_silent(self):
        lines = [f"Context carries {conflicts_module.CONFLICTS_ANCHOR_CONTEXT}:"]
        lines += [f"- **`{v}`** — explanation." for v in CONTEXT_VALUES]
        diag = self._diag()
        _conflicts_context_values(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_context_values_mismatch_is_error(self):
        corrupted = ("continue-root", "isolated-child-return", "cold-start — WRONG")
        lines = [f"Context carries {conflicts_module.CONFLICTS_ANCHOR_CONTEXT}:"]
        lines += [f"- **`{v}`** — explanation." for v in corrupted]
        diag = self._diag()
        _conflicts_context_values(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Context"), diag.errors)

    # --- literals i18n-keep ------------------------------------------------
    def test_i18n_undeclared_literal_is_error(self):
        fake_literal = "test-undeclared-literal-P5-9"
        diag = self._diag()
        with unittest.mock.patch.object(
                plan_lint_module, "CANON_LITERALS", CANON_LITERALS + (fake_literal,)):
            _conflicts_i18n_literals("canon text without directives", ["canon text without directives"],
                                     Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, fake_literal), diag.errors)

    def test_i18n_all_declared_is_silent(self):
        skill_text = "".join(f"<!-- i18n-keep: {lit} -->\n" for lit in CANON_LITERALS)
        diag = self._diag()
        _conflicts_i18n_literals(skill_text, skill_text.splitlines(), Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    # --- regex form carriers launch-block'a -----------------------------
    def test_launch_table_regex_matches_canon_rows_is_silent(self):
        lines = ["| Parameter | Meaning |", "|:--|:--|", "| Model class | ... |",
                 "| Effort | ... |", "| Context | ... |", "| The bottom line | ... |", "",
                 "**Provider-native command:**", "", "```text", "/task:plan-run X P1.1", "```"]
        diag = self._diag()
        _conflicts_launch_table_regex(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_launch_table_missing_command_block_is_error(self):
        lines = ["| Parameter | Meaning |", "|:--|:--|", "| Model class | ... |",
                 "| Effort | ... |"]
        diag = self._diag()
        _conflicts_launch_table_regex(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "fenced command block"), diag.errors)

    def test_launch_table_command_row_is_rejected_by_canon_conflict(self):
        lines = ["| Parameter | Meaning |", "|:--|:--|", "| Model class | ... |",
                 "| Command | `...` |", "", "**Provider-native command:**", "",
                 "```text", "/task:plan-run X P1.1", "```"]
        diag = self._diag()
        _conflicts_launch_table_regex(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "reader-side compatibility"), diag.errors)

    # --- layout v2 carrier anchor ------------------------------------------
    def test_layout_v2_carriers_consistent_is_silent(self):
        lines = [conflicts_module.CONFLICTS_ANCHOR_LAYOUT_V2,
                 "phases/<Pn>/<Pn.m>.md", "phases/<Pn>/<Pn.m>.state.md",
                 "bundles/<Pn.m>.json", "phases/<Pn>/<Pn>.closed.md"]
        diag = self._diag()
        _conflicts_layout_v2(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_layout_v2_missing_carrier_is_error(self):
        lines = [conflicts_module.CONFLICTS_ANCHOR_LAYOUT_V2,
                 "phases/<Pn>/<Pn.m>.md", "phases/<Pn>/<Pn.m>.state.md",
                 "bundles/<Pn.m>.json"]
        diag = self._diag()
        _conflicts_layout_v2(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "<Pn>.closed.md"), diag.errors)


class TestConflictsFlagLiveRepo(unittest.TestCase):
    """`--conflicts` vs. REAL `SKILL.md` — Validation p.6 (first run on live
    tree). Standalone-layout (package `task` outside monorepo) — test is skipped, does not crash:
    same degradation class as `test_canon_literals.py`."""

    def setUp(self):
        if _find_skill() is None:
            self.skipTest("standalone-layout: SKILL.md not found from plan_lint.py up")

    def test_missing_canon_is_error_not_vacuous_pass(self):
        diag = Diagnostics()
        with unittest.mock.patch.object(conflicts_module, "_find_skill", return_value=None):
            run_conflicts_check(diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "canon plan-protocol"), diag.errors)

    def test_digest_locked_runtime_projection_is_accepted_standalone_and_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / conflicts_module.RUNTIME_SKILL_RELPATH
            provenance = root / conflicts_module.RUNTIME_PROVENANCE_RELPATH
            runtime.parent.mkdir(parents=True)
            source = _find_skill().read_bytes()
            runtime.write_bytes(source)
            provenance.write_text(json.dumps({
                "canonical_source": conflicts_module.SKILL_RELPATH.as_posix(),
                "canonical_sha256": "sha256:" + sha256(source).hexdigest(),
            }), encoding="utf-8")
            staged_module = root / "packages/task/lib/task/plan_lint_checks/conflicts.py"
            staged_module.parent.mkdir(parents=True)
            staged_module.write_text("# locator anchor\n", encoding="utf-8")
            with unittest.mock.patch.object(conflicts_module, "__file__", staged_module):
                self.assertEqual(conflicts_module._find_skill(), runtime)
                provenance.write_text("{}", encoding="utf-8")
                self.assertIsNone(conflicts_module._find_skill())

    def test_main_without_conflicts_or_path_errors(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(io.StringIO()):
                main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("path is required without --conflicts", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestLint20Warnings(TmpPlanTestCase):
    """Schema checks 2.0 (ECOSYSTEM P5.2 block 13) — ALL warning-level:
    diagnostics falls into diag.warnings, diag.ok remains True."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def test_plan_sections_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        # Changing the numbers of two v2-core sections, preserving the canonical title.
        text = text.replace("## 1. Context", "## X-TMP")
        text = text.replace("## 2. Execution Rules", "## 1. Context")
        text = text.replace("## X-TMP", "## 2. Execution Rules")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "out of order"), diag.warnings)

    def test_plan_section_title_mismatch_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("## 3. Routing", "## 3. Route selection")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "≠ canonical"), diag.warnings)

    def test_v2_update_projection_bounds_long_journal_note(self):
        plan_dir = write_valid_plan(self.root)
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["note"] = "x" * 301
        journal.write_text(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "Update Log"), [], diag.warnings)

    def test_decision_log_without_rag_markers_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._write_decisions(plan_dir, ("test", "that's how it should be", "and so it should be"))
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "RAG:✅"), diag.warnings)

    def test_decision_log_with_rag_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._write_decisions(plan_dir, ("test", "RAG:✅ 2026-07-02 request", "[UNVERIFIED]"))
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "RAG:✅»/«[UNVERIFIED]"), [])

    def test_decision_log_with_rag_dash_marker_no_warning(self):
        # third marker enum'a §7: `RAG:—` — repo-grounded fact, WARNING'but it shouldn't be
        plan_dir = write_valid_plan(self.root)
        self._write_decisions(plan_dir, ("test", "RAG:— (repo-grounded: lib/pkg/config.py)", "RAG:—"))
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "Decision Log:"), [])

    def _write_decisions(self, plan_dir, reasons):
        for number, reason in enumerate(reasons, 1):
            (plan_dir / "decisions" / f"D{number}-fixture.md").write_text(
                "---\n"
                f"id: D{number}\n"
                "date: 2026-07-02\nstatus: accepted\nitem: P1.1\n"
                "items: [P1.1]\nsupersedes: []\nsuperseded_by: null\n---\n"
                f"## Solution\n\nSolution {number}.\n\n## Why\n\n{reason}\n",
                encoding="utf-8")

    def test_item_fields_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = item_spec_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        # Intent and Why swap places - the canonical order is broken
        text = text.replace("**Intent:** Add check.\n**Why:** Diagnostics are expensive.",
                            "**Why:** Diagnostics are expensive.\n**Intent:** Add check.")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "not in canonical order"), diag.warnings)

    def _make_hollow_item(self, plan_dir):
        """P1.1 with ⬜ and ≥50% empty fields (skeletal item)."""
        p1 = item_spec_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        for field, val in (("Intent", "Add check."), ("Why", "Diagnostics are expensive."),
                           ("Scope Included", "load_config()."), ("Scope Excluded", "config format."),
                           ("Inputs", "list of keys."), ("Files", "lib/pkg/config.py"),
                           ("Required Reads", "1) lib/pkg/config.py"),
                           ("Implementation Rules", "stdlib-only."),
                           ("Code Guidance", "manual check dict-keys.")):
            text = text.replace(f"**{field}:** {val}", f"**{field}:** —")
        p1.write_text(text, encoding="utf-8")
        state = item_state_path(plan_dir)
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** ⬜ Not started"), encoding="utf-8")
        plan = plan_dir / "plan.md"
        ptext = plan.read_text(encoding="utf-8")
        ptext = ptext.replace("| P1 | Phase times | 1/1 | 🟢 Done |",
                              "| P1 | Phase times | 0/1 | ⬜ Not started |")
        ptext = ptext.replace("| Status | 🟢 Done |", "| Status | 🟡 In progress |")
        plan.write_text(ptext, encoding="utf-8")
        from task import plan_status
        plan_status.build_status(plan_dir)
        return p1

    def test_hollow_item_without_skeleton_marker_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._make_hollow_item(plan_dir)
        _, diag = _lint(plan_dir)
        bundle_errors = _errors_containing(diag, "required bundle next run item P1.1 is deprecated")
        self.assertTrue(bundle_errors, diag.errors)
        self.assertEqual(
            [error for error in diag.errors if error not in bundle_errors],
            [],
            diag.errors,
        )
        self.assertTrue(self._warnings_containing(diag, "SKELETON"), diag.warnings)

    def test_hollow_item_with_skeleton_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._make_hollow_item(plan_dir)
        p1 = phase_index_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        text = text.replace(
            "Demo phase.",
            "Demo phase.\n\n> SKELETON — not detailed, unfolds /task:plan-design DEMO-1 P1")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "SKELETON"), [], diag.warnings)

    def test_needs_clarification_in_active_phase_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = item_spec_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        text = text.replace("**Why:** Diagnostics are expensive.",
                            "**Why:** Diagnostics are expensive. [NEEDS CLARIFICATION: what is the error format?]")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)  # phase 🟢 Done — exactly «left design»
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "NEEDS CLARIFICATION"), diag.warnings)

    def test_handoff_next_without_launch_block_warning(self):
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = handoff_md("DEMO-1")
        # cut out launch-block entirely: remains naked Next without table/code-block
        head, _, tail = text.partition("\n| Parameter | Meaning |")
        _, _, after = tail.partition("````\n\n")
        ho.write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "launch-block"), diag.warnings)

    def test_handoff_plan_closed_launch_block_not_required(self):
        # plan closed → there is nothing to run, launch-block not required
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "plan closed — all phases are terminal.")
        head, _, tail = text.partition("\n| Parameter | Meaning |")
        _, _, after = tail.partition("````\n\n")
        ho.write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "launch-block"), [], diag.warnings)


class TestPlanIdentity43Warnings(TmpPlanTestCase):
    """P4.3 — three WARNING-plan identity checks: regular PLAN-ID,
    place/name workflow-script, supersedes-continuity. EVERYTHING warning: diag.ok=True."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _add_js(self, plan_dir, rel, with_marker=True):
        p = plan_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        body = "export const meta = {\n  name: 'x',\n}\n" if with_marker else "// not workflow\n"
        p.write_text(body, encoding="utf-8")
        return p

    # --- (1) regular PLAN-ID -----------------------------------------
    def test_legacy_id_no_warning(self):
        plan_dir = write_valid_plan(self.root, "OLD-STYLE")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "to canon PLAN-ID"), [], diag.warnings)

    def test_dated_id_no_warning(self):
        plan_dir = write_valid_plan(self.root, "2026.07.10-DEMO")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "to canon PLAN-ID"), [], diag.warnings)

    def test_noncanonical_id_warning(self):
        # lowercase letters → does not match the old one `[A-Z]…`, nor date pattern
        plan_dir = write_valid_plan(self.root, "demo-lower")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "not canon PLAN-ID"), diag.warnings)

    # --- (2) place/name workflow-script --------------------------------
    def test_canonical_workflow_script_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # codename = demo-1
        self._add_js(plan_dir, "workflows/wf-demo-1-drive.js")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-script"), [], diag.warnings)

    def test_workflow_script_outside_workflows_dir_warns_place(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "wf-demo-1-drive.js")  # canonical name, but not under workflows/
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        w = self._warnings_containing(diag, "workflow-script")
        self.assertTrue(any("out" in x for x in w), diag.warnings)
        self.assertFalse(any("non-canonical name" in x for x in w), diag.warnings)

    def test_workflow_script_noncanonical_name_warns_name(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "workflows/wf-bad.js")  # under workflows/, but the name is non-canonical
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        w = self._warnings_containing(diag, "workflow-script")
        self.assertTrue(any("non-canonical name" in x for x in w), diag.warnings)
        self.assertFalse(any("out" in x for x in w), diag.warnings)

    def test_js_without_marker_ignored(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "helpers/util.js", with_marker=False)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-script"), [], diag.warnings)

    # --- (2b) dev-loop.js — resident agent-pack class, exempt (P3.3/findings A4) ---
    def test_dev_loop_js_exempt_by_name(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "dev-loop.js")  # out workflows/, non-canonical name - both triggers
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-script"), [], diag.warnings)

    # --- (3) supersedes-continuity --------------------------------
    def test_supersedes_missing_with_archived_codename_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        (self.root / "plans" / "archive" / "DEMO-1").mkdir(parents=True)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "supersedes"), diag.warnings)

    def test_supersedes_present_silences(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        (self.root / "plans" / "archive" / "DEMO-1").mkdir(parents=True)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8").replace(
            "| Layout | v2 |", "| Layout | v2 |\n| supersedes | DEMO-OLD |")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "supersedes"), [], diag.warnings)

    def test_no_archive_dir_no_warning(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # plans/archive/ missing
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "supersedes"), [], diag.warnings)


class TestWorkflowDoRWarning46(TmpPlanTestCase):
    """P4.6 — workflow-like-DoR: phase with status 🟡+, DECLARING orchestration
    (grabable sign multi-agent/fan-out), but without workflow-script in
    `plans/<ID>/workflows/` = WARNING. Convention: no attribute / at status ⬜ /
    if there is a script - silence. Everything warning-only: diag.ok=True."""

    _NEEDLE = "states orchestration"

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _inject_orchestration(self, plan_dir, phase="P1"):
        """Adds a grappable orchestration flag to Phase Context phases."""
        p = phase_index_path(plan_dir, phase)
        text = p.read_text(encoding="utf-8").replace(
            "Demo phase.", "Demo phase. Orchestration fan-out subagents, launch-block by scriptPath.")
        p.write_text(text, encoding="utf-8")

    def _add_workflow(self, plan_dir, name="wf-demo-1-drive.js"):
        wf = plan_dir / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / name).write_text("export const meta = {\n  phases: [],\n}\n", encoding="utf-8")

    # --- positive: phase states orchestration, status 🟢, no script → warning -----
    def test_orchestration_phase_without_script_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._inject_orchestration(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)  # warning-only, not error
        self.assertTrue(self._warnings_containing(diag, self._NEEDLE), diag.warnings)

    # --- negative: the sign is there, but the script is in workflows/ lies → silence -------------
    def test_orchestration_phase_with_script_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._inject_orchestration(plan_dir)
        self._add_workflow(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- negative: there is no sign of orchestration in the phase → silence (manual execution) ----
    def test_phase_without_orchestration_marker_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # green-path, without marker
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    def test_orchestration_only_in_phase_handoff_is_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = phase_index_path(plan_dir)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "Phase completed: everything is green.",
            "The next phase introduces multi-agent orchestration."), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    def test_orchestration_in_phase_context_still_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = phase_index_path(plan_dir)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "Demo phase.", "Multi-agent orchestration is announced for this phase."),
            encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, self._NEEDLE), diag.warnings)

    def test_p6_shaped_explicit_negation_is_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = phase_index_path(plan_dir)
        text = p.read_text(encoding="utf-8").replace(
            "Demo phase.",
            "## Sequence and orchestration\n\n"
            "Orchestration not declared and workflow not required; the chain is strictly sequential.")
        p.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    def test_script_path_and_multi_agent_declarations_still_warn(self):
        for plan_id, declaration in (
                ("DEMO-1", "launch-block uses scriptPath for orchestration."),
                ("DEMO-2", "Multi-agent orchestration is claimed for the phase.")):
            with self.subTest(declaration=declaration):
                plan_dir = write_valid_plan(self.root, plan_id)
                p = phase_index_path(plan_dir)
                p.write_text(p.read_text(encoding="utf-8").replace(
                    "Demo phase.", declaration), encoding="utf-8")
                _, diag = _lint(plan_dir)
                self.assertTrue(diag.ok, diag.errors)
                self.assertTrue(self._warnings_containing(diag, self._NEEDLE), diag.warnings)

    def test_positive_line_after_negation_still_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = phase_index_path(plan_dir)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "Demo phase.",
            "Orchestration not declared and workflow is not required.\n"
            "Multi-agent orchestration claimed for retry flow."), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, self._NEEDLE), diag.warnings)

    # --- negative: boomer `fan-out` in prose (not a declaration) → silence ------------
    # regression to false warning SKM-MASTER-002/P3 (fan-out in Known Deviations about
    # token-accounting): conservative set of tokens intentionally does NOT catch a single word.
    def test_bare_fanout_in_prose_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = phase_index_path(plan_dir)
        text = p.read_text(encoding="utf-8").replace(
            "Demo phase.", "Demo phase. Metric distortion when fan-out subagents - allowed.")
        p.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- negative: phase states orchestration, but status ⬜ → silence (not in exec) -----
    def test_orchestration_phase_not_started_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        state = item_state_path(plan_dir)
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** ⬜ Not started"), encoding="utf-8")
        from task import plan_status
        plan_status.build_status(plan_dir)
        self._inject_orchestration(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)
