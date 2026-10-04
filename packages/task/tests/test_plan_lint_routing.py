"""Next routing, discovery, root and CLI cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *


class TestNextFormsEnum(TmpPlanTestCase):
    """m8/B1/N1/N2 — enum 8 forms handoff.Next (SKILL §8): per case per form
    (accepted) + junk form (ERROR) + plan-audit non-terminal phase (WARNING)."""

    def _next(self, plan_dir, new_next):
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-run DEMO-1 P1.1", new_next)
        ho.write_text(text, encoding="utf-8")

    def test_plan_design_item_form_accepted(self):
        # item escalated/requires re-design - link to existing item Pn.m
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-design DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_design_item_form_nonexistent_item_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-design DEMO-1 P9.9")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» does not exist in any phase"))

    def test_plan_audit_terminal_phase_accepted(self):
        # phase P1 terminal (🟢 Done in fixture) — plan-audit acceptable without warning
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-audit DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual([w for w in diag.warnings if "is not terminal" in w], [])

    def test_plan_audit_nonterminal_phase_warns(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, phase_index=phase_index_md(handoff_text="—"),
            item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        self._next(plan_dir, "/task:plan-audit DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("is not terminal" in w for w in diag.warnings), diag.warnings)

    def test_plan_close_phase_form_rejected(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)

    def test_plan_close_item_form_rejected(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)

    def test_plan_close_item_form_nonexistent_item_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P9.9")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Next does not match any of the valid forms"))

    def test_plan_close_archive_form_accepted_when_closed(self):
        # plan is entirely terminal (the only one item 🟢 Done) — form is valid
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close archive DEMO-1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_archive_form_warns_when_not_closed(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, phase_index=phase_index_md(handoff_text="—"),
            item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        self._next(plan_dir, "/task:plan-close archive DEMO-1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("the plan is not yet completely terminal" in w for w in diag.warnings), diag.warnings)

    def test_manual_run_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "MANUAL START: fable/high — item requires public-solution contract")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_garbage_next_form_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "do something inspired")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "does not match any of the valid forms"))

    def test_typed_waiting_owner_handoff_passes_continuity_gate(self):
        import json
        from task import plan_continuity
        plan_dir = write_valid_plan(self.root, "2026.09.27-DEMO-OWNER-WAIT")
        handoff = plan_dir / "handoff.md"
        decision = plan_continuity.evaluate(
            route_attested=True, context_attested=True, batch_receipt_valid=True,
            waiting_owner=True)
        handoff.write_text(
            "# HANDOFF — 2026-09-27 — after P1.1\n\n"
            "**Next:** manual: owner decision required before continuing\n\n"
            "| Parameter | Meaning |\n|:--|:--|\n| Context | waiting-owner |\n\n"
            "```session-continuity-decision/v1\n"
            + json.dumps(decision.as_dict()) + "\n```\n\n**Done:** checkpoint\n",
            encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "CONTINUITY_CONTEXT_INVALID"))
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Context | waiting-owner |", "| Context | continue-root |"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "CONTINUITY_CONTEXT_INVALID"))


class TestRoutingItemsGrammar(TmpPlanTestCase):
    def _with_items(self, cell):
        plan_id = "DEMO-" + cell.replace(".", "").replace("–", "TO")
        plan_dir = write_valid_plan(self.root, plan_id=plan_id, layout="v2")
        path = plan_dir / "plan.md"
        table = ("## 3. Routing\n\n| Batch | Items | Model class/effort | Exec | Review | Why |\n"
                 "|:--|:--|:--|:--|:--|:--|\n"
                 f"| B1 | {cell} | implementation/high | run | full | test |")
        path.write_text(path.read_text(encoding="utf-8").replace(
            "## 3. Routing", table), encoding="utf-8")
        return plan_dir

    def test_cross_phase_range_is_rejected_before_compiler(self):
        _model, diag = _lint(self._with_items("P1.1–P2.1"))
        self.assertTrue(_errors_containing(diag, "single-phase range"), diag.errors)

    def test_comma_list_and_descending_range_remain_rejected(self):
        for cell in ("P1.1, P1.2", "P1.3–P1.1"):
            with self.subTest(cell=cell):
                _model, diag = _lint(self._with_items(cell))
                self.assertTrue(_errors_containing(diag, "closed grammar"), diag.errors)

    def test_single_item_and_same_phase_range_are_accepted(self):
        for cell in ("P1.1", "P1.1–P1.3"):
            with self.subTest(cell=cell):
                _model, diag = _lint(self._with_items(cell))
                self.assertEqual(_errors_containing(diag, "closed grammar"), [])


class TestRoutingBatchSchema(TmpPlanTestCase):
    """New layout-v2 plans cannot lose batch/solo between design and handoff."""

    PLAN_ID = "2026.08.12-№1-DEMO"

    def _plan(self, routing=None, *, batch_in_handoff=True):
        from task import plan_bundle, plan_status

        plan_dir = write_valid_plan(self.root, self.PLAN_ID, layout="v2")
        plan_path = plan_dir / "plan.md"
        text = plan_path.read_text(encoding="utf-8").replace(
            "| Title | Demo plan |", "| Title | Plan №1 — Demo plan |")
        if routing is not None:
            text = text.replace("## 3. Routing", "## 3. Routing\n\n" + routing)
        plan_path.write_text(text, encoding="utf-8")
        if batch_in_handoff:
            handoff = plan_dir / "handoff.md"
            handoff.write_text(
                handoff.read_text(encoding="utf-8").replace(
                    "| Model | sonnet |", "| Batch | solo |\n| Model | sonnet |"),
                encoding="utf-8",
            )
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, "P1.1")
        return plan_dir

    def test_missing_routing_table_is_error(self):
        _, diag = _lint(self._plan())
        self.assertTrue(_errors_containing(diag, "Routing schema"), diag.errors)

    def test_legacy_four_column_routing_is_error(self):
        routing = (
            "| Items | Model class/effort | Exec | Why |\n"
            "|:--|:--|:--|:--|\n"
            "| P1.1 | implementation/medium | run | test |"
        )
        _, diag = _lint(self._plan(routing))
        self.assertTrue(_errors_containing(diag, "Routing schema"), diag.errors)

    def test_canonical_solo_row_is_accepted(self):
        routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | run | full | test |"
        )
        _, diag = _lint(self._plan(routing))
        self.assertEqual(_errors_containing(diag, "Routing schema"), [], diag.errors)
        self.assertEqual(_errors_containing(diag, "Routing Batch"), [], diag.errors)

    def test_executable_handoff_requires_batch_row(self):
        routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | run | full | test |"
        )
        _, diag = _lint(self._plan(routing, batch_in_handoff=False))
        self.assertTrue(_errors_containing(diag, "handoff.Next: no line `| Batch |"),
                        diag.errors)

    def test_handoff_batch_must_match_routing(self):
        routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | run | full | test |"
        )
        plan_dir = self._plan(routing)
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Batch | solo |", "| Batch | B-wrong |"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "≠ Routing «solo»"), diag.errors)

    def test_legacy_exec_spellings_share_one_lint_execution_mode(self):
        from task import task_contract
        routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| B1 | P1.1 | implementation/high | plan-exec | full | shared reads |\n"
            "| B1 | P1.2 | implementation/high | manual | light | same lifecycle |"
        )
        plan_dir = self._plan(routing)
        from fixtures import write_v2_carriers
        write_v2_carriers(plan_dir, item_id="P1.2", refresh_views=False)
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "invalid Exec"), diag.errors)
        self.assertFalse(_errors_containing(diag, "incompatible Exec"), diag.errors)
        self.assertEqual(task_contract.compile_batch_routing(plan_dir)["batches"]["B1"]["exec"], "run")

    def test_handoff_cannot_collapse_batch_to_one_item(self):
        from task import plan_bundle, plan_item_state, plan_status

        routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| B1 | P1.1 | implementation/high | run | full | shared reads |\n"
            "| B1 | P1.2 | implementation/high | run | light | producer chain |"
        )
        plan_dir = self._plan(routing)
        phase = plan_dir / "phases" / "P1"
        second = (phase / "P1.1.md").read_text(encoding="utf-8").replace(
            "P1.1", "P1.2").replace("Config validation", "Second validation")
        (phase / "P1.2.md").write_text(second, encoding="utf-8")
        (plan_dir / "journal.jsonl").write_text("", encoding="utf-8")
        plan_item_state.build_states(plan_dir, item_id="P1.1")
        plan_item_state.build_states(plan_dir, item_id="P1.2")
        plan_bundle.build(plan_dir, "P1.2")
        plan_status.build_status(plan_dir)
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Batch | solo |", "| Batch | B1 |"), encoding="utf-8")

        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "all remaining adjacent-suffix"), diag.errors)

        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            f"/task:plan-run {self.PLAN_ID} P1.1",
            f"/task:plan-run {self.PLAN_ID} P1.1-P1.2"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "all remaining adjacent-suffix"), [],
                         diag.errors)

        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "P1.1-P1.2", "P1.1 P1.2"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "all remaining adjacent-suffix"), [],
                         diag.errors)


class TestExecutableRoutingTableBoundary(TmpPlanTestCase):
    def _plan(self, suffix):
        plan_dir = write_valid_plan(self.root, "2026.09.10-№1-DEMO-ROUTING", layout="v2")
        routing = (
            "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | run | full | test |\n")
        plan = plan_dir / "plan.md"
        plan.write_text(plan.read_text(encoding="utf-8").replace(
            "## 3. Routing\n\n", "## 3. Routing\n\n" + routing + suffix),
            encoding="utf-8")
        return plan_dir

    def test_adjacent_provider_mapping_is_not_a_second_routing_table(self):
        _model, diag = _lint(self._plan(
            "\n| Provider | Model | Selector |\n"
            "|:--|:--|:--|\n"
            "| Codex | gpt-5.6-terra | implementation |\n"))
        self.assertEqual(_errors_containing(diag, "Routing schema"), [], diag.errors)

    def test_second_executable_header_is_a_named_routing_error(self):
        duplicate = (
            "\n| Batch | Items | Model class/effort | Exec | Review | Why |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | run | full | duplicate |\n")
        _model, diag = _lint(self._plan(duplicate))
        self.assertTrue(_errors_containing(diag, "duplicate executable Routing tables"),
                        diag.errors)


class TestContinuityHandoffGate(TmpPlanTestCase):
    PLAN_ID = "2026.09.09-№1-DEMO-CONTINUITY"

    def _plan(self, context, suffix="BASE"):
        from task import plan_bundle, plan_status

        plan_dir = write_valid_plan(
            self.root, f"{self.PLAN_ID}-{suffix}", layout="v2")
        plan_path = plan_dir / "plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8")
            .replace("| Title | Demo plan |", "| Title | Plan №1 — Continuity |")
            .replace(
                "## 3. Routing",
                "## 3. Routing\n\n"
                "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
                "|:--|:--|:--|:--|:--|:--|\n"
                "| solo | P1.1 | implementation/medium | run | full | test |",
            ),
            encoding="utf-8",
        )
        handoff = plan_dir / "handoff.md"
        handoff.write_text(
            handoff.read_text(encoding="utf-8")
            .replace("| Model | sonnet |", "| Batch | solo |\n| Model | sonnet |")
            .replace("| Context | fresh session |", f"| Context | {context} |"),
            encoding="utf-8",
        )
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, "P1.1")
        return plan_dir

    def test_canonical_context_is_live_linted(self):
        _, diag = _lint(self._plan("continue-root"))
        self.assertEqual(_errors_containing(diag, "CONTINUITY_CONTEXT_INVALID"), [],
                         diag.errors)

    def test_cold_start_requires_one_canonical_reason(self):
        for index, context in enumerate(
                ("cold-start-root", "cold-start-root: made-up", "fresh session")):
            with self.subTest(context=context):
                _, diag = _lint(self._plan(context, str(index)))
                self.assertTrue(
                    _errors_containing(diag, "CONTINUITY_CONTEXT_INVALID"), diag.errors)

    def test_context_row_is_required_exactly_once(self):
        plan_dir = self._plan("continue-root")
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "| Context | continue-root |", ""), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "exactly one line `| Context |"),
                        diag.errors)


class TestNextDeclarationLine(TmpPlanTestCase):
    """D40 — form `Next` is declared as the FIRST line of the field; prose launch-block'a (incl.
    cell «The bottom line») legitimately QUOTES other forms enum'and the resolver does not intercept."""

    def _activate_item(self, plan_dir):
        """Makes the only one item 🟡 (the plan ceases to be entirely terminal)."""
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))

    def _sut(self, plan_dir, next_decl, sut_cell):
        """Rewrites handoff: form declaration + cell «The bottom line» launch-block'a."""
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("**Next:** /task:plan-run DEMO-1 P1.1", f"**Next:** {next_decl}")
        text = text.replace("| The bottom line | close next item |", f"| The bottom line | {sut_cell} |")
        ho.write_text(text, encoding="utf-8")

    def test_manual_declaration_beats_closed_literal_in_prose(self):
        # Defect: grep «plan closed» across the ENTIRE field I caught a mention of the form in «Essences»
        # and gave false ERROR «not all items terminal», interrupting the marker manual.
        plan_dir = write_valid_plan(self.root)
        self._activate_item(plan_dir)
        self._sut(plan_dir, "«MANUAL START: opus/high»",
                  "flatten forms enum'a: «plan closed» vs slash-commands")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_manual_declaration_beats_slash_form_in_prose(self):
        # Same nature: slash-command QUOTED in «Essences» manual-forms, not declaration -
        # resolving her links would give ERROR for non-existent item'y P9.9.
        plan_dir = write_valid_plan(self.root)
        self._sut(plan_dir, "«MANUAL START: opus/high»",
                  "commands `/task:plan-design DEMO-1 P9.9` for this item'does not exist")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_closed_literal_on_declaration_line_still_gated(self):
        # Anti-weakening: form declared by first line «plan closed» is gated as before.
        plan_dir = write_valid_plan(self.root)
        self._activate_item(plan_dir)
        self._sut(plan_dir, "«plan closed»", "next step outside the protocol")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«plan closed», but not all items terminal"))


class TestWaitingForm(TmpPlanTestCase):
    """P2.1/D8 — 9-I form Next «WAITING» (waiting): resolve BEFORE exec, requires
    launch-block; C2-WARNING to prosaic gate-disclaimer in runnable-form."""

    def _waiting_handoff(self, plan_id="DEMO-1", *, cond="≥2026-07-16",
                         target="/task:plan-run DEMO-1 P1.1", guard=True):
        guard_line = f"# NOT before: {cond}\n" if guard else ""
        return f"""# HANDOFF — 2026-07-02 — after P1.1

**Next:** WAITING: {cond} → {target}

| Parameter | Meaning |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | continue (/clear) — manual item |
| The bottom line | close target item upon removing the gate |

````
{guard_line}{target}
````

**Done:** P1.1 is closed.
**Remaining:** target step is waiting for a gate.
**Sources of truth:** plans/{plan_id}/plan.md · plans/{plan_id}/phases/P1.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""

    def test_waiting_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").write_text(self._waiting_handoff(), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_waiting_resolves_before_exec_no_item_ref_error(self):
        # target /task:plan-run … P9.9 in ANNOUNCEMENT should not resolve as run and catch
        # ERROR for non-existent item'y - form waiting intercepts the resolver early.
        plan_dir = write_valid_plan(self.root)
        ho = self._waiting_handoff(target="/task:plan-run DEMO-1 P9.9")
        (plan_dir / "handoff.md").write_text(ho, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual([e for e in diag.errors if "P9.9" in e], [], diag.errors)

    def test_waiting_guard_line_no_c2_warning(self):
        # guard-string `# NOT before:` in code-block'does NOT trigger C2: is scanned only
        # declaration line, and it resolves to waiting (not in runnable-form).
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").write_text(self._waiting_handoff(guard=True), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual([w for w in diag.warnings if "prose clause" in w], [], diag.warnings)

    def test_waiting_without_launch_block_warns(self):
        # waiting carries launch-block like others runnable-forms - not exempt (unlike «plan closed»)
        plan_dir = write_valid_plan(self.root)
        text = self._waiting_handoff()
        head, _, tail = text.partition("\n| Parameter | Meaning |")
        _, _, after = tail.partition("````\n\n")
        (plan_dir / "handoff.md").write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("launch-block" in w for w in diag.warnings), diag.warnings)

    def test_c2_prose_osaying_in_runnable_form_warns(self):
        # runnable-form (exec) + prose theme in the ad = C2-WARNING (not ERROR)
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace(
            "**Next:** /task:plan-run DEMO-1 P1.1",
            "**Next:** /task:plan-run DEMO-1 P1.1 — BUT not before ~2026-07-16 (time gate)")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("prose clause" in w for w in diag.warnings), diag.warnings)

    def test_clean_runnable_form_no_c2_warning(self):
        # clean exec without stems - C2 is silent
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertEqual([w for w in diag.warnings if "prose clause" in w], [], diag.warnings)


class TestArchivePlansNotPhantomPlan(TmpPlanTestCase):
    """N3/D14 — `plans/archive/` is not a plan itself (should not require
    plan.md/handoff.md), a `plans/archive/<ID>` is linted like a regular plan."""

    def _write_archived_plan(self, plan_id="DEMO-OLD"):
        source = write_valid_plan(self.root, plan_id)
        archive = self.root / "plans" / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        target = archive / plan_id
        source.rename(target)
        return target

    def test_archive_container_produces_no_phantom_errors(self):
        write_valid_plan(self.root, "DEMO-1")
        self._write_archived_plan("DEMO-OLD")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans")])
        self.assertEqual(code, 0, err.getvalue())
        self.assertNotIn("archive/plan.md", err.getvalue())
        self.assertNotIn("archive/handoff.md", err.getvalue())

    def test_archived_plan_still_linted(self):
        write_valid_plan(self.root, "DEMO-1")
        archived_dir = self._write_archived_plan("DEMO-OLD")
        text = (archived_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-OLD |\n", "")
        (archived_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans")])
        self.assertEqual(code, 1)
        self.assertIn("no required field «Plan ID»", err.getvalue())

    def test_discover_plan_dirs_excludes_archive_container_includes_children(self):
        write_valid_plan(self.root, "DEMO-1")
        self._write_archived_plan("DEMO-OLD")
        found = discover_plan_dirs(self.root / "plans")
        names = sorted(p.name for p in found)
        self.assertEqual(names, ["DEMO-1", "DEMO-OLD"])

    def test_historical_v1_archive_is_inert(self):
        write_valid_plan(self.root, "DEMO-1")
        archived_dir = self._write_archived_plan("DEMO-V1")
        text = (archived_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Layout | v2 |", "| Layout | v1 |")
        (archived_dir / "plan.md").write_text(text, encoding="utf-8")

        found = discover_plan_dirs(self.root / "plans")

        self.assertEqual([path.name for path in found], ["DEMO-1"])

    def test_pre_cutover_v2_archive_is_inert_for_root_wide_validation(self):
        write_valid_plan(self.root, "DEMO-1")
        archived_dir = self._write_archived_plan("2026.08.02-DEMO-OLD")
        text = (archived_dir / "plan.md").read_text(encoding="utf-8")
        (archived_dir / "plan.md").write_text(
            text.replace("| Plan ID | 2026.08.02-DEMO-OLD |\n", ""), encoding="utf-8")

        found = discover_plan_dirs(self.root / "plans")

        self.assertEqual([path.name for path in found], ["DEMO-1"])


class TestGlobalUniqueness(TmpPlanTestCase):
    def test_duplicate_item_id_across_phases(self):
        plan_dir = write_valid_plan(self.root)
        phase = plan_dir / "phases" / "P1"
        foreign = phase / "P2.1.md"
        foreign.write_text(item_spec_path(plan_dir).read_text(encoding="utf-8"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "has the prefix P2"))

    def test_duplicate_item_id_within_one_file(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        block = text.split("### P1.1", 1)[1]
        text = text + "\n### P1.1" + block
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "exactly one header expected"))


class TestWarnings(TmpPlanTestCase):
    def test_duplicate_title_warning(self):
        from task import plan_bundle, plan_decisions, plan_item_state, plan_status
        plan_dir = write_valid_plan(self.root)
        phase = plan_dir / "phases" / "P1"
        (phase / "P1.2.md").write_text(
            item_spec_path(plan_dir).read_text(encoding="utf-8").replace("P1.1", "P1.2"),
            encoding="utf-8")
        journal = plan_dir / "journal.jsonl"
        event = json.loads(journal.read_text(encoding="utf-8"))
        event["item_id"] = "P1.2"
        journal.write_text(journal.read_text(encoding="utf-8")
                           + json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        plan_item_state.build_states(plan_dir, item_id="P1.2")
        plan_decisions.build_views(plan_dir)
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, "P1.2")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("take Title" in w for w in diag.warnings))

    def test_phase_first_warning(self):
        from task import plan_bundle, plan_decisions, plan_item_state, plan_status
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(
                item_status="⬜ Not started", completion_notes="—"), refresh_views=False)
        write_v2_carriers(
            plan_dir, phase_id="P2", item_id="P2.1",
            item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"),
            refresh_views=False)
        journal = plan_dir / "journal.jsonl"
        event = json.loads(journal.read_text(encoding="utf-8"))
        event.update({"item_id": "P2.1", "result": "in-progress", "note": None})
        journal.write_text(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        plan_item_state.build_states(plan_dir, item_id="P1.1")
        plan_item_state.build_states(plan_dir, item_id="P2.1")
        plan_decisions.build_views(plan_dir)
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, "P1.1")
        plan_bundle.build(plan_dir, "P2.1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("phase-first" in w for w in diag.warnings), diag.warnings)

    def test_empty_required_reads_warning_for_active_item(self):
        plan_dir = write_valid_plan(self.root)
        spec = item_spec_md().replace(
            "**Required Reads:** 1) lib/pkg/config.py", "**Required Reads:** —")
        write_v2_carriers(
            plan_dir, item_spec=spec,
            item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("empty Required Reads" in w for w in diag.warnings))


class TestSemanticNextCarrier(TmpPlanTestCase):
    """P4.4: neutral Next is canonical; frozen slash syntax remains compatible."""

    def test_semantic_audit_phase_resolves_the_same_plan_and_phase(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run DEMO-1 P1.1",
            "audit-phase: task:plan-audit DEMO-1 P1")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertFalse(any("Next does not match" in item for item in diag.errors))

    def test_audit_phase_accepts_terminal_items_before_formal_phase_close(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        plan.write_text(plan.read_text(encoding="utf-8").replace(
            "| P1 | Phase times | 1/1 | 🟢 Done |",
            "| P1 | Phase times | 1/1 | 🟡 In progress |",
        ), encoding="utf-8")
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run DEMO-1 P1.1",
            "audit-phase: task:plan-audit DEMO-1 P1",
        ), encoding="utf-8")

        _, diag = _lint(plan_dir)

        self.assertTrue(diag.ok, diag.errors)
        self.assertFalse(any("terminal phase candidate" in item for item in diag.warnings),
                         diag.warnings)

    def test_historical_slash_next_remains_accepted(self):
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertFalse(any("Next does not match" in item for item in diag.errors))

    def test_semantic_kind_command_mismatch_is_rejected(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "/task:plan-run DEMO-1 P1.1",
            "audit-phase: task:plan-run DEMO-1 P1.1")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("Next does not match" in item for item in diag.errors),
                        diag.errors)

    def test_design_finish_and_roadmap_forms_are_accepted(self):
        for declaration in ("design-finish: task:plan-design DEMO-1 finish",
            "design-roadmap: task:plan-design DEMO-1 roadmap"):
            with self.subTest(declaration=declaration):
                shutil.rmtree(self.root / "plans" / "DEMO-1", ignore_errors=True)
                plan_dir = write_valid_plan(self.root, plan_id="DEMO-1")
                handoff = plan_dir / "handoff.md"
                text = handoff.read_text(encoding="utf-8").replace(
                    "/task:plan-run DEMO-1 P1.1", declaration)
                handoff.write_text(text, encoding="utf-8")
                _, diag = _lint(plan_dir)
                self.assertTrue(diag.ok, diag.errors)

    def test_all_closed_semantic_kinds_resolve_before_provider_rendering(self):
        fixture = Path(__file__).with_name("fixtures_data") / "provider-plan-cases.json"
        declarations = json.loads(fixture.read_text(encoding="utf-8"))["next_declarations"]
        expected = {
            "exec-items": "run", "run-items": "run", "audit-design": "audit-design",
            "design-phase": "design-phase", "design-item": "design-item",
            "design-finish": "design-finish", "design-roadmap": "design-roadmap",
            "audit-phase": "audit", "close": "close", "archive": "close-archive",
            "terminal": "closed", "manual": "manual", "waiting": "waiting",
        }
        self.assertEqual(
            {kind: _resolve_next_form(value)[0] for kind, value in declarations.items()},
            expected,
        )


class TestPlansRoot(TmpPlanTestCase):
    """Root-level checks (path = plans/ in full): ACTIVE.md + drafts."""

    def _plans_root(self):
        return self.root / "plans"

    def test_valid_active_pointing_to_existing_plan_ok(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_active_dash_means_no_active_plan_ok(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("—"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())

    def test_active_pointing_to_nonexistent_plan_is_error(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("NO-SUCH-PLAN"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 1)
        self.assertIn("does not point to an existing plan", err.getvalue())

    def test_active_md_without_active_field_is_error(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text("# ACTIVE\n\nnothing useful\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 1)
        self.assertIn("no field «**Active:**»", err.getvalue())

    def test_two_in_progress_plans_without_active_warns(self):
        write_valid_plan(self.root, "DEMO-1")
        write_valid_plan(self.root, "DEMO-2")
        # fixture default - Meta Status «🟢 Done»; convert both plans to «🟡 In progress»
        # (only Meta-line - consistency items/board this check does not affect).
        for pid in ("DEMO-1", "DEMO-2"):
            write_v2_carriers(
                self._plans_root() / pid,
                item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())  # WARNING, not ERROR
        self.assertIn("active plan is ambiguous", err.getvalue())

    def test_single_in_progress_plan_without_active_is_clean(self):
        write_valid_plan(self.root, "DEMO-1")  # default Meta Status «🟢 Done» — not 🟡
        diag = Diagnostics()
        model = lint_plan(self._plans_root() / "DEMO-1", diag)
        lint_plans_root(self._plans_root(), {"DEMO-1": model}, diag)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_draft_flat_md_warns_with_from_draft_hint(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "sketch.md").write_text("# draft\n", encoding="utf-8")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("drafts plan mode", err.getvalue())
        self.assertIn("sketch.md", err.getvalue())
        self.assertIn("/task:plan-design from-draft", err.getvalue())

    def test_readme_and_active_are_not_drafts(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "README.md").write_text("# readme\n", encoding="utf-8")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_single_plan_mode_ignores_sibling_active_md(self):
        # plan-lint.py plans/<ID> (single mode) doesn't see ACTIVE.md at all - even
        # broken (pointing to a non-existent plan) should not affect it.
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("NO-SUCH-PLAN"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir)])
        self.assertEqual(code, 0, err.getvalue())


class TestDiscoveryAndCli(TmpPlanTestCase):
    def test_discover_single_plan_dir(self):
        plan_dir = write_valid_plan(self.root)
        found = discover_plan_dirs(plan_dir)
        self.assertEqual(found, [plan_dir])

    def test_discover_plans_root_multiple(self):
        write_valid_plan(self.root, "DEMO-1")
        write_valid_plan(self.root, "DEMO-2")
        found = discover_plan_dirs(self.root / "plans")
        self.assertEqual(sorted(p.name for p in found), ["DEMO-1", "DEMO-2"])

    def test_discover_nonexistent_path(self):
        self.assertIsNone(discover_plan_dirs(self.root / "no-such-dir"))

    def test_discover_empty_plans_root_is_not_error(self):
        (self.root / "plans").mkdir()
        self.assertEqual(discover_plan_dirs(self.root / "plans"), [])

    def test_discover_ignores_tooling_directories(self):
        plans = self.root / "plans"
        plans.mkdir()
        (plans / ".claude").mkdir()
        (plans / "__pycache__").mkdir()
        self.assertEqual(discover_plan_dirs(plans), [])

    def test_main_exit_code_ok(self):
        write_valid_plan(self.root, "DEMO-1")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans" / "DEMO-1")])
        self.assertEqual(code, 0)
        self.assertIn("OK", out.getvalue())

    def test_main_exit_code_fail(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir)])
        self.assertEqual(code, 1)
        self.assertIn("FAILURE", out.getvalue())
        self.assertIn("ERROR:", err.getvalue())

    def test_main_json_flag_emits_parseable_json(self):
        write_valid_plan(self.root, "DEMO-1")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "plans" / "DEMO-1"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("DEMO-1", payload["plans"])

    def test_main_nonexistent_path_exit_1(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self.root / "no-such-plans")])
        self.assertEqual(code, 1)
        self.assertIn("ERROR:", err.getvalue())


class TestDuplicateItemFieldGate(unittest.TestCase):
    """D90 — `**Field:**`-line inside the free prose of another
    fields (e.g. Completion Notes) silently replaced the acceptance value: and `plan_lint`, and
    `task_contract` take the LAST occurrence of the key. Reproduced on P2.2 2026-07-31
    (`research/10-validation-acceptance-form-2026-07-31.md`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_duplicate_validation_field_in_completion_notes_is_error(self):
        plan_dir = write_valid_plan(self.root)
        p1 = item_state_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        needle = "**Completion Notes:** test"
        self.assertIn(needle, text)
        injected = (needle + "\n**Validation:** re-acceptance to item-commit abc123 — green "
                   "(inline note, NOT real field)")
        p1.write_text(text.replace(needle, injected, 1), encoding="utf-8")
        diag = Diagnostics()
        lint_plan(plan_dir, diag)
        hits = _errors_containing(diag, "TK field «Validation» not allowed")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in h for h in hits), hits)

    def test_no_duplicate_is_silent(self):
        plan_dir = write_valid_plan(self.root)
        diag = Diagnostics()
        lint_plan(plan_dir, diag)
        self.assertEqual(_errors_containing(diag, "occurs repeatedly"), [])
