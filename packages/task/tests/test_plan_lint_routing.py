"""Next routing, discovery, root and CLI cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *


class TestNextFormsEnum(TmpPlanTestCase):
    """m8/B1/N1/N2 — enum 8 форм handoff.Next (SKILL §8): по кейсу на форму
    (принимается) + мусорная форма (ERROR) + plan-audit нетерминальной фазы (WARNING)."""

    def _next(self, plan_dir, new_next):
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", new_next)
        ho.write_text(text, encoding="utf-8")

    def test_plan_design_item_form_accepted(self):
        # item эскалирован/требует ре-дизайна — ссылка на существующий item Pn.m
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-design DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_design_item_form_nonexistent_item_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-design DEMO-1 P9.9")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» не существует ни в одной фазе"))

    def test_plan_audit_terminal_phase_accepted(self):
        # фаза P1 терминальна (🟢 Done в фикстуре) — plan-audit допустим без warning
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-audit DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual([w for w in diag.warnings if "не терминальна" in w], [])

    def test_plan_audit_nonterminal_phase_warns(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟡 In progress", completion_notes="—", handoff_text="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        self._next(plan_dir, "/task:plan-audit DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("не терминальна" in w for w in diag.warnings), diag.warnings)

    def test_plan_close_phase_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_item_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_item_form_nonexistent_item_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close DEMO-1 P9.9")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» не существует ни в одной фазе"))

    def test_plan_close_archive_form_accepted_when_closed(self):
        # план целиком терминален (единственный item 🟢 Done) — форма допустима
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "/task:plan-close archive DEMO-1")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_plan_close_archive_form_warns_when_not_closed(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟡 In progress", completion_notes="—", handoff_text="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        self._next(plan_dir, "/task:plan-close archive DEMO-1")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("план ещё не терминален целиком" in w for w in diag.warnings), diag.warnings)

    def test_manual_run_form_accepted(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "ЗАПУСК ВРУЧНУЮ: fable/high — item требует public-контракт решения")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_garbage_next_form_is_error(self):
        plan_dir = write_valid_plan(self.root)
        self._next(plan_dir, "сделай что-нибудь по вдохновению")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "не соответствует ни одной из допустимых форм"))


class TestRoutingItemsGrammar(TmpPlanTestCase):
    def _with_items(self, cell):
        plan_id = "DEMO-" + cell.replace(".", "").replace("–", "TO")
        plan_dir = write_valid_plan(self.root, plan_id=plan_id, layout="v2")
        path = plan_dir / "plan.md"
        table = ("## 3. Routing\n\n| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
                 "|:--|:--|:--|:--|:--|:--|\n"
                 f"| B1 | {cell} | implementation/high | manual | full | test |")
        path.write_text(path.read_text(encoding="utf-8").replace(
            "## 3. Routing", table), encoding="utf-8")
        return plan_dir

    def test_cross_phase_range_is_rejected_before_compiler(self):
        _model, diag = _lint(self._with_items("P1.1–P2.1"))
        self.assertTrue(_errors_containing(diag, "single-phase range"), diag.errors)

    def test_single_item_and_same_phase_range_are_accepted(self):
        for cell in ("P1.1", "P1.1–P1.3"):
            with self.subTest(cell=cell):
                _model, diag = _lint(self._with_items(cell))
                self.assertEqual(_errors_containing(diag, "закрытой грамматики"), [])


class TestNextDeclarationLine(TmpPlanTestCase):
    """D40 — форма `Next` объявляется ПЕРВОЙ строкой поля; проза launch-block'а (в т.ч.
    ячейка «Суть») законно ЦИТИРУЕТ другие формы enum'а и резолвер не перехватывает."""

    def _activate_item(self, plan_dir):
        """Делает единственный item 🟡 (план перестаёт быть терминальным целиком)."""
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        text = text.replace("**Status:** 🟢 Done", "**Status:** 🟡 In progress")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |",
                            "| P1.1 | Валидация конфига | 🟡 In progress |")
        p1.write_text(text, encoding="utf-8")
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                            "| P1 | Фаза раз | 0/1 | 🟡 In progress |")
        plan.write_text(text, encoding="utf-8")

    def _sut(self, plan_dir, next_decl, sut_cell):
        """Переписывает handoff: объявление формы + ячейка «Суть» launch-block'а."""
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("**Next:** /task:plan-exec DEMO-1 P1.1", f"**Next:** {next_decl}")
        text = text.replace("| Суть | закрыть следующий item |", f"| Суть | {sut_cell} |")
        ho.write_text(text, encoding="utf-8")

    def test_manual_declaration_beats_closed_literal_in_prose(self):
        # Дефект: греп «план закрыт» по ВСЕМУ полю ловил упоминание формы в «Сути»
        # и давал ложный ERROR «не все items терминальны», перебивая маркер manual.
        plan_dir = write_valid_plan(self.root)
        self._activate_item(plan_dir)
        self._sut(plan_dir, "«ЗАПУСК ВРУЧНУЮ: opus/high»",
                  "свести формы enum'а: «план закрыт» vs slash-команды")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_manual_declaration_beats_slash_form_in_prose(self):
        # Та же природа: slash-команда, ПРОЦИТИРОВАННАЯ в «Сути» manual-формы, не объявление —
        # резолв её ссылок дал бы ERROR по несуществующему item'у P9.9.
        plan_dir = write_valid_plan(self.root)
        self._sut(plan_dir, "«ЗАПУСК ВРУЧНУЮ: opus/high»",
                  "команды `/task:plan-design DEMO-1 P9.9` для этого item'а не существует")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_closed_literal_on_declaration_line_still_gated(self):
        # Анти-ослабление: объявленная первой строкой форма «план закрыт» гейтится как прежде.
        plan_dir = write_valid_plan(self.root)
        self._activate_item(plan_dir)
        self._sut(plan_dir, "«план закрыт»", "следующий шаг вне протокола")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«план закрыт», но не все items терминальны"))


class TestWaitingForm(TmpPlanTestCase):
    """P2.1/D8 — 9-я форма Next «ОЖИДАНИЕ» (waiting): резолв ДО exec, требует
    launch-block; C2-WARNING на прозаическую gate-оговорку в runnable-форме."""

    def _waiting_handoff(self, plan_id="DEMO-1", *, cond="≥2026-07-16",
                         target="/task:plan-exec DEMO-1 P1.1", guard=True):
        guard_line = f"# НЕ раньше: {cond}\n" if guard else ""
        return f"""# HANDOFF — 2026-07-02 — after P1.1

**Next:** ОЖИДАНИЕ: {cond} → {target}

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | закрыть целевой item по снятии гейта |

````
{guard_line}{target}
````

**Done:** P1.1 закрыт.
**Remaining:** целевой шаг ждёт гейта.
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
        # целевой /task:plan-exec … P9.9 в ОБЪЯВЛЕНИИ не должен резолвиться как exec и ловить
        # ERROR по несуществующему item'у — форма waiting перехватывает резолвер раньше (D8).
        plan_dir = write_valid_plan(self.root)
        ho = self._waiting_handoff(target="/task:plan-exec DEMO-1 P9.9")
        (plan_dir / "handoff.md").write_text(ho, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual([e for e in diag.errors if "P9.9" in e], [], diag.errors)

    def test_waiting_guard_line_no_c2_warning(self):
        # guard-строка `# НЕ раньше:` в code-block'е НЕ триггерит C2: сканируется только
        # строка-объявление, а она резолвится в waiting (не в runnable-форму).
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").write_text(self._waiting_handoff(guard=True), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual([w for w in diag.warnings if "прозу-оговорку" in w], [], diag.warnings)

    def test_waiting_without_launch_block_warns(self):
        # waiting несёт launch-block как прочие runnable-формы — не exempt (в отличие от «план закрыт»)
        plan_dir = write_valid_plan(self.root)
        text = self._waiting_handoff()
        head, _, tail = text.partition("\n| Параметр | Значение |")
        _, _, after = tail.partition("````\n\n")
        (plan_dir / "handoff.md").write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("launch-block" in w for w in diag.warnings), diag.warnings)

    def test_c2_prose_oговорка_in_runnable_form_warns(self):
        # runnable-форма (exec) + прозаический стем в объявлении = C2-WARNING (не ERROR)
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace(
            "**Next:** /task:plan-exec DEMO-1 P1.1",
            "**Next:** /task:plan-exec DEMO-1 P1.1 — НО не раньше ~2026-07-16 (тайм-гейт)")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("прозу-оговорку" in w for w in diag.warnings), diag.warnings)

    def test_clean_runnable_form_no_c2_warning(self):
        # чистый exec без стемов — C2 молчит
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertEqual([w for w in diag.warnings if "прозу-оговорку" in w], [], diag.warnings)


class TestArchivePlansNotPhantomPlan(TmpPlanTestCase):
    """N3/D14 — `plans/archive/` сама планом не является (не должна требовать
    plan.md/handoff.md), а `plans/archive/<ID>` линтуется как обычный план."""

    def _write_archived_plan(self, plan_id="DEMO-OLD"):
        plan_dir = self.root / "plans" / "archive" / plan_id
        (plan_dir / "phases").mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text(plan_md(plan_id), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md(plan_id), encoding="utf-8")
        return plan_dir

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
        self.assertIn("нет обязательного поля «Plan ID»", err.getvalue())

    def test_discover_plan_dirs_excludes_archive_container_includes_children(self):
        write_valid_plan(self.root, "DEMO-1")
        self._write_archived_plan("DEMO-OLD")
        found = discover_plan_dirs(self.root / "plans")
        names = sorted(p.name for p in found)
        self.assertEqual(names, ["DEMO-1", "DEMO-OLD"])


class TestGlobalUniqueness(TmpPlanTestCase):
    def test_duplicate_item_id_across_phases(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        text = plan_md("DEMO-1").replace(
            "| P1 | Фаза раз | 1/1 | 🟢 Done |",
            "| P1 | Фаза раз | 1/1 | 🟢 Done |\n| P2 | Фаза два | 1/1 | 🟢 Done |",
        )
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md("P1", item_id="P1.1"), encoding="utf-8")
        # умышленный баг: во второй фазе снова P1.1 (должно быть P2.1)
        (plan_dir / "phases" / "P2.md").write_text(phase_md("P2", item_id="P1.1"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "переиспользован в фазах"))

    def test_duplicate_item_id_within_one_file(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        block = text.split("### P1.1", 1)[1]
        text = text + "\n### P1.1" + block
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "повторяется в файле"))


class TestWarnings(TmpPlanTestCase):
    def test_duplicate_title_warning(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        text = plan_md("DEMO-1").replace(
            "| P1 | Фаза раз | 1/1 | 🟢 Done |",
            "| P1 | Фаза раз | 2/2 | 🟢 Done |",
        )
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")

        # второй item с ТЕМ ЖЕ Title, что и P1.1 ("Валидация конфига") — добавляем
        # его строку в Phase Status и сам item-блок перед `## Phase Handoff`.
        second_item_block = """### P1.2 — Валидация конфига

**Status:** 🟢 Done
**Intent:** —
**Why:** —
**Scope Included:** —
**Scope Excluded:** —
**Inputs:** —
**Files:** —
**Required Reads:** —
**Implementation Rules:** —
**Code Guidance:** —
**Validation:** —
**Deliverables:** —
**Completion Notes:** сделано
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

## Phase Handoff"""
        phase_text = phase_md("P1", item_id="P1.1")
        phase_text = phase_text.replace(
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |",
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |\n"
            "| P1.2 | Валидация конфига | 🟢 Done | 2026-07-02 |",
        )
        phase_text = phase_text.replace("## Phase Handoff", second_item_block)
        (plan_dir / "phases" / "P1.md").write_text(phase_text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("дубль Title" in w for w in diag.warnings))

    def test_phase_first_warning(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        text = plan_md("DEMO-1", items_cell="0/1", phase_status="🟡 In progress")
        text = text.replace(
            "| P1 | Фаза раз | 0/1 | 🟡 In progress |",
            "| P1 | Фаза раз | 0/1 | 🟡 In progress |\n| P2 | Фаза два | 0/1 | 🟡 In progress |",
        )
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md("P1", item_id="P1.1", item_status="⬜ Not started",
                      completion_notes="—", known_deviations="—"),
            encoding="utf-8")
        (plan_dir / "phases" / "P2.md").write_text(
            phase_md("P2", item_id="P2.1", item_status="🟡 In progress",
                      completion_notes="—", known_deviations="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1", item_id="P2.1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("phase-first" in w for w in diag.warnings), diag.warnings)

    def test_empty_required_reads_warning_for_active_item(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("**Status:** 🟢 Done", "**Status:** 🟡 In progress")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |", "| P1.1 | Валидация конфига | 🟡 In progress |")
        text = text.replace("**Required Reads:** 1) lib/pkg/config.py", "**Required Reads:** —")
        text = text.replace("**Completion Notes:** сделано, тест зелёный", "**Completion Notes:** —")
        board = (plan_dir / "plan.md").read_text(encoding="utf-8")
        board = board.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 0/1 | 🟡 In progress |")
        (plan_dir / "plan.md").write_text(board, encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(any("пустые Required Reads" in w for w in diag.warnings))


class TestSemanticNextCarrier(TmpPlanTestCase):
    """P4.4: neutral Next is canonical; frozen slash syntax remains compatible."""

    def test_semantic_audit_phase_resolves_the_same_plan_and_phase(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "/task:plan-exec DEMO-1 P1.1",
            "audit-phase: task:plan-audit DEMO-1 P1")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertFalse(any("Next не соответствует" in item for item in diag.errors))

    def test_audit_phase_accepts_terminal_items_before_formal_phase_close(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        plan.write_text(plan.read_text(encoding="utf-8").replace(
            "| P1 | Фаза раз | 1/1 | 🟢 Done |",
            "| P1 | Фаза раз | 1/1 | 🟡 In progress |",
        ), encoding="utf-8")
        handoff = plan_dir / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace(
            "/task:plan-exec DEMO-1 P1.1",
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
        self.assertFalse(any("Next не соответствует" in item for item in diag.errors))

    def test_semantic_kind_command_mismatch_is_rejected(self):
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8").replace(
            "/task:plan-exec DEMO-1 P1.1",
            "audit-phase: task:plan-exec DEMO-1 P1.1")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(any("Next не соответствует" in item for item in diag.errors),
                        diag.errors)

    def test_design_finish_and_roadmap_forms_are_accepted(self):
        for declaration in ("design-finish: task:plan-design DEMO-1 finish",
                            "design-roadmap: task:plan-design DEMO-1 roadmap"):
            with self.subTest(declaration=declaration):
                plan_dir = write_valid_plan(self.root, plan_id="DEMO-1")
                handoff = plan_dir / "handoff.md"
                text = handoff.read_text(encoding="utf-8").replace(
                    "/task:plan-exec DEMO-1 P1.1", declaration)
                handoff.write_text(text, encoding="utf-8")
                _, diag = _lint(plan_dir)
                self.assertTrue(diag.ok, diag.errors)

    def test_all_closed_semantic_kinds_resolve_before_provider_rendering(self):
        fixture = Path(__file__).with_name("fixtures_data") / "provider-plan-cases.json"
        declarations = json.loads(fixture.read_text(encoding="utf-8"))["next_declarations"]
        expected = {
            "exec-items": "exec", "run-items": "run", "audit-design": "audit-design",
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
    """Root-level проверки (path = plans/ целиком): ACTIVE.md + черновики (P1.5)."""

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
        self.assertIn("не указывает на существующий план", err.getvalue())

    def test_active_md_without_active_field_is_error(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "ACTIVE.md").write_text("# ACTIVE\n\nничего полезного\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 1)
        self.assertIn("нет поля «**Active:**»", err.getvalue())

    def test_two_in_progress_plans_without_active_warns(self):
        write_valid_plan(self.root, "DEMO-1")
        write_valid_plan(self.root, "DEMO-2")
        # дефолт фикстуры — Meta Status «🟢 Done»; переводим оба плана в «🟡 In progress»
        # (только Meta-строку — консистентность items/board эта проверка не трогает).
        for pid in ("DEMO-1", "DEMO-2"):
            p = self._plans_root() / pid / "plan.md"
            text = p.read_text(encoding="utf-8").replace(
                "| Status | 🟢 Done |", "| Status | 🟡 In progress |")
            p.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())  # WARNING, не ERROR
        self.assertIn("активный план неоднозначен", err.getvalue())

    def test_single_in_progress_plan_without_active_is_clean(self):
        write_valid_plan(self.root, "DEMO-1")  # дефолт Meta Status «🟢 Done» — не 🟡
        diag = Diagnostics()
        model = lint_plan(self._plans_root() / "DEMO-1", diag)
        lint_plans_root(self._plans_root(), {"DEMO-1": model}, diag)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(diag.warnings, [])

    def test_draft_flat_md_warns_with_from_draft_hint(self):
        write_valid_plan(self.root, "DEMO-1")
        (self._plans_root() / "sketch.md").write_text("# черновик\n", encoding="utf-8")
        (self._plans_root() / "ACTIVE.md").write_text(active_md("DEMO-1"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(self._plans_root())])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("черновики plan mode", err.getvalue())
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
        # plan-lint.py plans/<ID> (одиночный режим) не видит ACTIVE.md вовсе — даже
        # битый (указывающий на несуществующий план) не должен на него влиять.
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
        self.assertIn("ПРОВАЛ", out.getvalue())
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
    """D90 (2026.07.31-SKM-LEAN P5.9) — `**Поле:**`-строка внутри свободной прозы другого
    поля (напр. Completion Notes) молча подменяла приёмочное значение: и `plan_lint`, и
    `task_contract` берут ПОСЛЕДНЕЕ вхождение ключа. Воспроизведено на P2.2 2026-07-31
    (`research/10-validation-acceptance-form-2026-07-31.md`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_duplicate_validation_field_in_completion_notes_is_error(self):
        plan_dir = write_valid_plan(self.root)
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        needle = "**Completion Notes:** сделано, тест зелёный"
        self.assertIn(needle, text)
        injected = (needle + "\n**Validation:** переприёмка на item-коммите abc123 — зелёная "
                   "(инлайн-заметка, НЕ настоящее поле)")
        p1.write_text(text.replace(needle, injected, 1), encoding="utf-8")
        diag = Diagnostics()
        lint_plan(plan_dir, diag)
        hits = _errors_containing(diag, "поле «Validation» встречается повторно")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in h for h in hits), hits)

    def test_no_duplicate_is_silent(self):
        plan_dir = write_valid_plan(self.root)
        diag = Diagnostics()
        lint_plan(plan_dir, diag)
        self.assertEqual(_errors_containing(diag, "встречается повторно"), [])
