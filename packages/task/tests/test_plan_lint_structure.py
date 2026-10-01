"""Carrier structure, item state and handoff cases for plan-lint."""
import subprocess
import sys

try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *

from task import plan_bundle
from task.plan_lint_checks.engine import _next_runnable_item


class TestV2ItemSplit(TmpPlanTestCase):
    def _v2_plan(self):
        return write_valid_plan(self.root, layout="v2")

    def test_v2_item_spec_and_state_assemble_the_canonical_model(self):
        plan_dir = self._v2_plan()
        model, diag = _lint(plan_dir)
        self.assertFalse(diag.errors, diag.errors)
        fields = model["phases"]["P1"]["items"]["P1.1"]["fields"]
        self.assertEqual(list(fields), list(REQUIRED_ITEM_FIELDS))
        self.assertEqual(fields["Status"], "🟢 Done")

    def test_v2_rejects_outcome_field_in_item_spec(self):
        plan_dir = self._v2_plan()
        spec = plan_dir / "phases" / "P1" / "P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8") + "**Status:** 🟢 Done\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "origin field «Status» is prohibited"), diag.errors)

    def test_v2_rejects_spec_field_in_item_state(self):
        plan_dir = self._v2_plan()
        state = plan_dir / "phases" / "P1" / "P1.1.state.md"
        state.write_text(state.read_text(encoding="utf-8") + "**Intent:** extra source\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "TK field «Intent» not allowed"), diag.errors)

    def test_v2_requires_a_state_carrier_for_every_item(self):
        plan_dir = self._v2_plan()
        (plan_dir / "phases" / "P1" / "P1.1.state.md").unlink()
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "required state snapshot"), diag.errors)

    def test_v2_requires_a_fresh_bundle_for_the_next_runnable_item(self):
        plan_dir = self._v2_plan()
        state = plan_dir / "phases" / "P1" / "P1.1.state.md"
        state.write_text(
            state.read_text(encoding="utf-8").replace(
                "**Status:** 🟢 Done", "**Status:** ⬜ Not started"),
            encoding="utf-8",
        )
        plan_bundle.build(plan_dir, "P1.1")
        (plan_dir / "bundles" / "P1.1.json").unlink()

        _, diag = _lint(plan_dir)

        self.assertTrue(
            _errors_containing(diag, "required bundle next run item P1.1 missing"),
            diag.errors,
        )

    def test_v2_rejects_a_stale_bundle_for_the_next_runnable_item(self):
        plan_dir = self._v2_plan()
        state = plan_dir / "phases" / "P1" / "P1.1.state.md"
        state.write_text(
            state.read_text(encoding="utf-8").replace(
                "**Status:** 🟢 Done", "**Status:** ⬜ Not started"),
            encoding="utf-8",
        )
        target = plan_bundle.build(plan_dir, "P1.1")
        target.write_bytes(target.read_bytes() + b" ")

        _, diag = _lint(plan_dir)

        self.assertTrue(
            _errors_containing(diag, "required bundle next run item P1.1 is deprecated"),
            diag.errors,
        )

    def test_v2_rejects_an_item_file_with_another_phase_prefix(self):
        plan_dir = self._v2_plan()
        foreign = plan_dir / "phases" / "P1" / "P2.1.md"
        foreign.write_text((plan_dir / "phases" / "P1" / "P1.1.md").read_text(encoding="utf-8"),
                           encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "has the prefix P2"), diag.errors)


class TestNextRunnableBundle(unittest.TestCase):
    def test_next_runnable_item_uses_numeric_phase_order(self):
        phases = {
            "P1": {"items": {"P1.1": {}}},
            "P10": {"items": {"P10.1": {}}},
            "P2": {"items": {"P2.1": {}}},
        }
        all_items = {
            "P1.1": {"status": "🟢 Done"},
            "P2.1": {"status": "⬜ Not started"},
            "P10.1": {"status": "⬜ Not started"},
        }

        self.assertEqual(_next_runnable_item(phases, all_items), "P2.1")


class TestValidPlan(TmpPlanTestCase):
    def test_valid_plan_ok(self):
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_json_model_shape(self):
        plan_dir = write_valid_plan(self.root)
        model, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)
        self.assertEqual(model["id"], "DEMO-1")
        self.assertEqual(model["meta"]["Plan ID"], "DEMO-1")
        self.assertIn("P1", model["phases"])
        self.assertIn("P1.1", model["phases"]["P1"]["items"])
        self.assertEqual(model["phases"]["P1"]["items"]["P1.1"]["fields"]["Status"], "🟢 Done")
        # model should be serialized to JSON lossless (--json dumps exactly this)
        json.dumps(model, ensure_ascii=False)


class TestShortPlanIdentity(TmpPlanTestCase):
    def _short_plan(self, plan_id="DEMO-1", short_id="PLAN1"):
        plan_dir = write_valid_plan(self.root, plan_id)
        plan_md = plan_dir / "plan.md"
        text = plan_md.read_text(encoding="utf-8")
        text = text.replace(f"| Plan ID | {plan_id} |",
                            f"| Plan ID | {plan_id} |\n| Short ID | {short_id} |")
        plan_md.write_text(text, encoding="utf-8")
        return plan_dir

    def test_valid_short_id_and_legacy_absence(self):
        for plan_dir in (self._short_plan(), write_valid_plan(self.root, "OLD-1")):
            _, diag = _lint(plan_dir)
            self.assertFalse(_errors_containing(diag, "Short ID"), diag.errors)

    def test_invalid_short_ids(self):
        for index, short_id in enumerate(("PLAN0", "PLAN01", "TASK1", "#PLAN1", "P1", "")):
            with self.subTest(short_id=short_id):
                _, diag = _lint(self._short_plan(plan_id=f"INVALID-{index}", short_id=short_id))
                self.assertTrue(_errors_containing(diag, "Short ID"), diag.errors)

    def test_duplicate_short_id_in_live_or_archive(self):
        current = self._short_plan()
        other = self._short_plan("OTHER-1")
        _, diag = _lint(current)
        self.assertTrue(_errors_containing(diag, "Short ID PLAN1 duplicate"), diag.errors)
        archive = self.root / "plans" / "archive"
        archive.mkdir()
        shutil.move(str(other), str(archive / other.name))
        _, diag = _lint(current)
        self.assertTrue(_errors_containing(diag, "Short ID PLAN1 duplicate"), diag.errors)

    def test_same_plan_live_archive_copy_is_not_a_collision(self):
        current = self._short_plan()
        shutil.copytree(current, self.root / "plans" / "archive" / current.name)
        _, diag = _lint(current)
        self.assertFalse(_errors_containing(diag, "Short ID"), diag.errors)


class TestNumberedPlanIdentity(TmpPlanTestCase):
    def _numbered(self, plan_id="2026.08.12-№1-DEMO", title="Plan №1 — Demo"):
        plan_dir = write_valid_plan(self.root, plan_id)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8").replace("| Title | Demo plan |", f"| Title | {title} |")
        plan.write_text(text, encoding="utf-8")
        return plan_dir

    def test_numbered_plan_id_and_matching_title_are_valid(self):
        plan_dir = self._numbered()
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "PLAN-ID"), diag.errors)
        self.assertFalse([w for w in diag.warnings if "PLAN-ID" in w], diag.warnings)

    def test_new_legacy_dated_id_requires_number(self):
        plan_dir = write_valid_plan(self.root, "2026.08.12-DEMO")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "requires a sequence number"), diag.errors)

    def test_numbered_plan_rejects_zero_ordinal(self):
        plan_dir = self._numbered("2026.08.12-№0-DEMO", "Plan №0 — Demo")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "positive"), diag.errors)

    def test_numbered_plan_title_must_match_ordinal(self):
        plan_dir = self._numbered(title="Plan №2 — Demo")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Title must start"), diag.errors)

    def test_same_day_ordinal_must_be_unique_across_active_and_archive(self):
        plan_dir = self._numbered()
        archived = self.root / "plans" / "archive" / "2026.08.12-№1-DEMO-OLD"
        shutil.copytree(plan_dir, archived)
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "duplicates the sequence number"), diag.errors)

    def test_active_reactivation_and_archived_copy_share_one_plan_identity(self):
        plan_dir = self._numbered()
        archived = self.root / "plans" / "archive" / plan_dir.name
        shutil.copytree(plan_dir, archived)
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "duplicates the sequence number"), diag.errors)
        self.assertFalse(
            [warning for warning in diag.warnings if "repeats codename" in warning],
            diag.warnings,
        )

    def test_numbered_plan_codename_excludes_ordinal(self):
        from task.plan_lint import _plan_codename
        self.assertEqual(_plan_codename("2026.08.12-№12-DEMO-PLAN"), "demo-plan")

    def test_numbered_plan_id_round_trips_through_unicode_cli(self):
        plan_dir = self._numbered()
        plan = plan_dir / "plan.md"
        plan.write_text(plan.read_text(encoding="utf-8").replace(
            "## 3. Routing\n",
            "## 3. Routing\n\n"
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | run | full | fixture |\n",
        ), encoding="utf-8")
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Model | sonnet |", "| Batch | solo |\n| Model | sonnet |",
        ), encoding="utf-8")
        script = Path(__file__).parents[1] / "scripts" / "plan-lint.py"
        result = subprocess.run(
            [sys.executable, str(script), str(plan_dir)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("plan-lint: OK", result.stdout)


class TestPlanMdStructure(TmpPlanTestCase):
    def test_missing_plan_md(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "phases" / "P1.md").write_text(legacy_phase_md(), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "plan.md missing"))

    def test_meta_missing_required_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no required field «Plan ID»"))

    def test_status_board_section_missing(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("## 4. Phase Index & Status Board", "## 4. Something else")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no phase board"))

    def test_status_board_invalid_status(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Phase times | 1/1 | 🟢 Done |",
                             "| P1 | Phase times | 1/1 | Done |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "all items 🟢 Done, but phase status «Done»"))

    def test_status_board_malformed_phase_token(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Phase times |", "| Phase1 | Phase times |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "phase P1 is like"))


class TestPhaseBoardCorrespondence(TmpPlanTestCase):
    def test_phase_in_board_without_file(self):
        plan_dir = write_valid_plan(self.root)
        shutil.rmtree(plan_dir / "phases" / "P1")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "tree does not consist of phases/Pn/Pn.md"))

    def test_phase_file_without_board_row(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, phase_id="P2", item_id="P2.1", refresh_views=False)
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "phase P2 is like"))


class TestItemHeaderAndFields(TmpPlanTestCase):
    def test_malformed_item_header(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("### P1.1 — Config validation", "### P1.1 Config validation")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "exactly one header expected"))

    def test_missing_required_item_field(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** manual check dict-keys.\n", "")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no TK field «Code Guidance»"))

    def test_missing_required_item_field_message_is_actionable(self):
        # ERROR skeleton-item'and must name the repair path (D11: ERROR is not weakened,
        # only the text changes) — /task:plan-design <ID> Pn.
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** manual check dict-keys.\n", "")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no TK field «Code Guidance»"))

    def test_invalid_item_status(self):
        plan_dir = write_valid_plan(self.root)
        state = item_state_path(plan_dir)
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** Done"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item P1.1: invalid status «Done»"))

    def test_item_prefix_mismatch(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("P1.1", "P2.1")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "exactly one header expected"))


class TestCompletionAndDeviations(TmpPlanTestCase):
    def test_done_without_completion_notes(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟢 Done", completion_notes="—"))
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "requires non-empty Completion Notes"))

    def test_deviations_without_known_deviations(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(
                item_status="🟠 Done with deviations",
                completion_notes="made with reservation", known_deviations="—"))
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "requires non-empty Known Deviations"))


class TestEscalationConsistency(TmpPlanTestCase):
    def _write(self, item_status, escalation_needed, extra_blockquote=None,
               completion_notes="—", known_deviations="—"):
        plan_dir = write_valid_plan(self.root)
        spec = item_spec_md()
        if extra_blockquote:
            spec = spec.rstrip() + f"\n\n{extra_blockquote}\n"
        write_v2_carriers(
            plan_dir, item_spec=spec,
            item_state=item_state_md(
                item_status=item_status, escalation_needed=escalation_needed,
                completion_notes=completion_notes, known_deviations=known_deviations))
        return plan_dir

    def test_blocked_without_escalation_block_or_flag(self):
        plan_dir = self._write("🔴 Blocked", "—")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "mismatched"))

    def test_escalation_flag_yes_without_blocked_status(self):
        plan_dir = self._write("🟢 Done", "yes", completion_notes="done")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "mismatched"))

    def test_escalation_needed_invalid_value(self):
        plan_dir = self._write("⬜ Not started", "maybe")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "pending yes/no/—"))

    def test_blocked_with_full_escalation_triple_passes(self):
        plan_dir = self._write(
            "🔴 Blocked", "yes",
            extra_blockquote="> 🔴 ESCALATION P1.1: unclear architecture | trigger: unclear "
                              "architecture | needed: plan-design",
        )
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "mismatched"))

    def test_escalation_in_generated_state_does_not_require_spec_mutation(self):
        plan_dir = self._write("🔴 Blocked", "yes")
        state = item_state_path(plan_dir)
        state.write_text(state.read_text(encoding="utf-8")
                         + "\n> 🔴 ESCALATION P1.1: owner decision pending\n", encoding="utf-8")
        from task.plan_lint_checks import parsing
        parsed = parsing._parse_v2_item_file(item_spec_path(plan_dir), "P1.1", Diagnostics())
        self.assertTrue(parsed["has_escalation"])
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "mismatched"))


class TestPhaseStatusConsistency(TmpPlanTestCase):
    def test_generated_item_row_is_not_a_second_execution_source(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace(
            "| P1.1 | Config validation | 🟢 Done | 2026-07-02 |",
            "| P1.1 | Config validation | 🟡 In progress | 2026-07-02 |",
        )
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)


class TestStatusBoardConsistency(TmpPlanTestCase):
    def test_items_cell_wrong_count(self):
        plan_dir = write_valid_plan(self.root, )
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Phase times | 1/1 | 🟢 Done |", "| P1 | Phase times | 0/1 | 🟢 Done |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "≠ actual 1/1"))

    def test_items_cell_bad_format(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Phase times | 1/1 | 🟢 Done |", "| P1 | Phase times | one | 🟢 Done |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "expected format N/M"))

    def test_all_done_may_remain_in_progress_as_pre_close_audit_candidate(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Phase times | 1/1 | 🟢 Done |", "| P1 | Phase times | 1/1 | 🟡 In progress |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_all_done_rejects_non_candidate_board_status(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Phase times | 1/1 | 🟢 Done |", "| P1 | Phase times | 1/1 | ⬜ Not started |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "all items 🟢 Done, but phase status"))

    def test_blocked_item_but_board_status_not_blocked(self):
        plan_dir = write_valid_plan(self.root)
        spec = item_spec_md().rstrip() + (
            "\n\n> 🔴 ESCALATION P1.1: reason | trigger: unclear architecture | "
            "needed: plan-design\n")
        write_v2_carriers(
            plan_dir, item_spec=spec,
            item_state=item_state_md(
                item_status="🔴 Blocked", escalation_needed="yes", completion_notes="—"))
        status = plan_dir / "status.md"
        status.write_text(status.read_text(encoding="utf-8").replace(
            "| P1 | Phase times | 0/1 | 🔴 Blocked |",
            "| P1 | Phase times | 0/1 | 🟢 Done |"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "yes 🔴 Blocked item, but phase status"))


class TestPhaseHandoffGating(TmpPlanTestCase):
    def test_fresh_v2_closure_supplies_terminal_handoff_without_design_edits(self):
        from task import plan_closure
        plan_dir = write_valid_plan(self.root)
        text = phase_index_md(handoff_text="—").replace(
            "Demo phase.", "> **Phase contract.** Demo phase.")
        write_v2_carriers(plan_dir, phase_index=text)
        target = plan_closure.build_closure(plan_dir, "P1")
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "Phase Handoff» empty"))
        target.write_text(target.read_text(encoding="utf-8") + "stale\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Phase Handoff» empty"))

    def test_done_phase_with_empty_phase_handoff(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(plan_dir, phase_index=phase_index_md(handoff_text="—"))
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Phase Handoff» empty"))

    def test_missing_phase_handoff_section(self):
        plan_dir = write_valid_plan(self.root)
        path = phase_index_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("## Phase Handoff", "## Something else")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no section «## Phase Handoff»"))


class TestStalePhaseHandoff(TmpPlanTestCase):
    """P2.15/D34 (H2): reopen disables `## Phase Handoff` marker; block that survived
    reopens and approves the closure of the phase, - WARNING. Gate NARROW: blank/the skeleton is silent."""

    STALE_TEXT = ("Phase P1 closed: **1/1 terminal**.\n\n"
                  "**Submitted:** config validation.\n\n**Next:** `/task:plan-audit DEMO-1 P1`.")

    def _write_reopened_phase(self, handoff_text):
        """Phase 🟡 (reopenene: item back in action) with the given `## Phase Handoff`."""
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, phase_index=phase_index_md(handoff_text=handoff_text),
            item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        return plan_dir

    def _stale_warnings(self, diag):
        return [w for w in diag.warnings if "Phase Handoff rotten" in w]

    def test_nonterminal_phase_with_closure_claim_warns(self):
        plan_dir = self._write_reopened_phase(self.STALE_TEXT)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors) # exactly WARNING, not ERROR
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)
        self.assertIn("> DEPRECATED — phase reopened <D#>", self._stale_warnings(diag)[0])

    def test_stale_marker_silences_the_gate(self):
        plan_dir = self._write_reopened_phase(
            "> **DEPRECATED — phase reopened (D9, 2026-07-14).** The block below is written plan-close\n"
            "> to rheopen; fact: 0/1, phase 🟡.\n\n" + self.STALE_TEXT)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._stale_warnings(diag), [])

    def test_placeholder_handoff_of_unfinished_phase_is_silent(self):
        # anti-regression: skeletons/fleet blanks (naive formulation of the 104 phase beat)
        for text in ("—", "Filled in when a phase is closed."):
            with self.subTest(handoff=text):
                plan_dir = self._write_reopened_phase(text)
                _, diag = _lint(plan_dir)
                self.assertEqual(self._stale_warnings(diag), [])
                shutil.rmtree(plan_dir.parent)

    # --- P3.7/D50 (J1): gate judges by the SUBJECT of the statement, and not by the word it encounters.
    # Both fixtures are LITERAL forms of the fleet,
    # not «comfortable» synthetic lines: exactly on them the gate diverged from the truth.

    def test_honest_interim_handoff_is_silent(self):
        """themeon//P5: first line DENIES phase closure, and the word
        «Terminal» refers to ITEMS → false positive WARNING (J1, Blocker)."""
        plan_dir = self._write_reopened_phase(
            "**Phase P5 is NOT closed.** Terminal only P5.1 and P5.2 (2/10); P5.3–P5.10 (8/10) — "
            "🟠⬜ `Not started`\n(dterema: breakpoints/runtime-switch; vintera: all pilot).\n\n"
            "**What's passed (dterema, thread `themeon-migration/P5`, NOT merged):** 3 commit.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._stale_warnings(diag), [], diag.warnings)

    def test_delivery_claim_of_nonterminal_phase_still_warns(self):
        """vaulter/VLT-REMED/P5: first line APPROVES the completion of the phase with a non-terminal
        status → true positive WARNING must be preserved (anti-predicate fitting)."""
        plan_dir = self._write_reopened_phase(
            "**Submitted:** Phase P5 (end-to-end adversarial code review all changes VLT-REMED) — "
            "**terminal (3/3)**:\nP5.1 (🔴 Blocked) → P5.2 (🟠 Done with deviations) → "
            "**P5.3 (🟢 Done)**.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)

    def test_negation_below_first_line_does_not_silence_the_gate(self):
        """Negation is judged by the SAME first line: «phase closed … but P1.2 is not closed»
        below does not suppress true triggering (Implementation Rules P3.7)."""
        plan_dir = self._write_reopened_phase(
            "**Submitted:** phase closed, 1/1.\n\nRemainder: P1.2 not closed - moved to P2.")
        _, diag = _lint(plan_dir)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)


class TestHandoffMd(TmpPlanTestCase):
    def test_missing_handoff_file(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").unlink()
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "handoff.md missing"))

    def test_handoff_missing_title(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("# HANDOFF — 2026-07-02 — after P1.1\n", "")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no header «# HANDOFF"))

    def test_handoff_title_after_item_valid(self):
        # form `after Pn.m` (closed item) — basic, remains valid
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_after_phase_valid(self):
        # second form `after Pn` (closed/audited PHASE) — D30/G10
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_after_nonexistent_phase(self):
        # anti-fitting: `after Pn` must RESOLUTE, not just match regex'ohm
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P9\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "title: phase «P9» does not exist in the plan"))

    def test_handoff_title_item_form_nonexistent_phase(self):
        # D37/H10: item-form `after Pn.m` no longer bypasses the resolution gate - PHASE must be
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P9.1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "title: phase «P9» does not exist in the plan"))

    def test_handoff_title_bootstrap_item_form_allowed(self):
        # D37: whitelist — EXACTLY `P0.0` (starting handoff, phases P0 does not happen in the plan) → quiet
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P0.0\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_prose_form_rejected(self):
        # `after phase 2` — outside both forms enum'a
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after phase 1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "header does not match either of the two forms"))

    def test_handoff_missing_required_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("**Remaining:** nothing.\n", "")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "no required field «Remaining»"))

    def test_handoff_next_missing_reference(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "do something")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "does not match any of the valid forms"))

    def test_handoff_next_wrong_plan_id(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "/task:plan-run OTHER-ID P1.1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "PLAN-ID «OTHER-ID» ≠ actual «DEMO-1»"))

    def test_handoff_next_nonexistent_item(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "/task:plan-run DEMO-1 P9.9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» does not exist in any phase"))

    def test_handoff_next_plan_closed_allowed(self):
        # all items terminal → Next «plan closed» without link plan-run — is valid
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "plan closed — all phases are terminal.")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)

    def test_handoff_next_plan_design_phase_allowed(self):
        # skeleton phase ahead → Next «/task:plan-design <ID> Pn» (phase reference, not item) — is valid
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "/task:plan-design DEMO-1 P1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)

    def test_handoff_next_plan_design_backlog_only_skeleton_allowed(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run DEMO-1 P1.1", "/task:plan-design DEMO-1 P2"), encoding="utf-8")
        backlog = plan_dir / "backlog"
        backlog.mkdir()
        target = backlog / "P2.md"
        target.write_text("# P2\n\n> SKELETON — not detailed\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        target.write_text("# P2\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "phase «P2» does not exist in the plan"))

    def test_handoff_next_plan_design_wrong_plan_id(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "/task:plan-design OTHER-ID P1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "PLAN-ID «OTHER-ID» ≠ actual «DEMO-1»"))

    def test_handoff_next_plan_design_nonexistent_phase(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "/task:plan-design DEMO-1 P9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "phase «P9» does not exist in the plan"))

    def test_handoff_next_plan_design_rolling_backlog_phase(self):
        # D24-style rolling backlog: skeleton lives in backlog/<Pn>.md until plan-design moves it
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "backlog").mkdir()
        (plan_dir / "backlog" / "P9.md").write_text("# P9 — skeleton\n", encoding="utf-8")
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "/task:plan-design DEMO-1 P9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "phase «P9» does not exist in the plan"), [])

    def test_handoff_next_plan_closed_rejected_when_items_active(self):
        # «plan closed» alive 🟡 item — is not an excuse, ERROR remains
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", "plan closed.")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«plan closed», but not all items terminal"))
