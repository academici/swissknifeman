"""Carrier structure, item state and handoff cases for plan-lint."""
import subprocess
import sys

try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *


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
        self.assertTrue(_errors_containing(diag, "поле исхода «Status» запрещено"), diag.errors)

    def test_v2_rejects_spec_field_in_item_state(self):
        plan_dir = self._v2_plan()
        state = plan_dir / "phases" / "P1" / "P1.1.state.md"
        state.write_text(state.read_text(encoding="utf-8") + "**Intent:** лишний источник\n", encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "поле ТЗ «Intent» запрещено"), diag.errors)

    def test_v2_requires_a_state_carrier_for_every_item(self):
        plan_dir = self._v2_plan()
        (plan_dir / "phases" / "P1" / "P1.1.state.md").unlink()
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "обязательный слепок состояния"), diag.errors)

    def test_v2_rejects_an_item_file_with_another_phase_prefix(self):
        plan_dir = self._v2_plan()
        foreign = plan_dir / "phases" / "P1" / "P2.1.md"
        foreign.write_text((plan_dir / "phases" / "P1" / "P1.1.md").read_text(encoding="utf-8"),
                           encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "имеет префикс P2"), diag.errors)


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
        # модель должна сериализоваться в JSON без потерь (--json дампит именно её)
        json.dumps(model, ensure_ascii=False)


class TestNumberedPlanIdentity(TmpPlanTestCase):
    def _numbered(self, plan_id="2026.08.12-№1-DEMO", title="План №1 — Демо"):
        plan_dir = write_valid_plan(self.root, plan_id)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8").replace("| Title | Демо-план |", f"| Title | {title} |")
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
        self.assertTrue(_errors_containing(diag, "требует порядковый номер"), diag.errors)

    def test_numbered_plan_rejects_zero_ordinal(self):
        plan_dir = self._numbered("2026.08.12-№0-DEMO", "План №0 — Демо")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "положительным"), diag.errors)

    def test_numbered_plan_title_must_match_ordinal(self):
        plan_dir = self._numbered(title="План №2 — Демо")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Title должен начинаться"), diag.errors)

    def test_same_day_ordinal_must_be_unique_across_active_and_archive(self):
        plan_dir = self._numbered()
        archived = self.root / "plans" / "archive" / "2026.08.12-№1-OLD"
        shutil.copytree(plan_dir, archived)
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "дублирует порядковый номер"), diag.errors)

    def test_numbered_plan_codename_excludes_ordinal(self):
        from task.plan_lint import _plan_codename
        self.assertEqual(_plan_codename("2026.08.12-№12-TASK-RESILIENCE"), "task-resilience")

    def test_numbered_plan_id_round_trips_through_unicode_cli(self):
        plan_dir = self._numbered()
        plan = plan_dir / "plan.md"
        plan.write_text(plan.read_text(encoding="utf-8").replace(
            "## 3. Routing\n",
            "## 3. Routing\n\n"
            "| Batch | Items | Model class/effort | Exec | Review | Почему |\n"
            "|:--|:--|:--|:--|:--|:--|\n"
            "| solo | P1.1 | implementation/medium | plan-exec | full | fixture |\n",
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
        self.assertTrue(_errors_containing(diag, "plan.md отсутствует"))

    def test_meta_missing_required_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет обязательного поля «Plan ID»"))

    def test_status_board_section_missing(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("## 4. Phase Index & Status Board", "## 4. Что-то другое")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет доски фаз"))

    def test_status_board_invalid_status(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                             "| P1 | Фаза раз | 1/1 | Готово |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "все items 🟢 Done, но статус фазы «Готово»"))

    def test_status_board_malformed_phase_token(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз |", "| Phase1 | Фаза раз |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "фаза P1 есть как"))


class TestPhaseBoardCorrespondence(TmpPlanTestCase):
    def test_phase_in_board_without_file(self):
        plan_dir = write_valid_plan(self.root)
        shutil.rmtree(plan_dir / "phases" / "P1")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "дерево не состоит из phases/Pn/Pn.md"))

    def test_phase_file_without_board_row(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, phase_id="P2", item_id="P2.1", refresh_views=False)
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "фаза P2 есть как"))


class TestItemHeaderAndFields(TmpPlanTestCase):
    def test_malformed_item_header(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("### P1.1 — Валидация конфига", "### P1.1 Валидация конфига")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается ровно один заголовок"))

    def test_missing_required_item_field(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** ручная проверка dict-ключей.\n", "")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет поля ТЗ «Code Guidance»"))

    def test_missing_required_item_field_message_is_actionable(self):
        # ERROR скелет-item'а обязана называть путь починки (D11: ERROR не ослабляется,
        # меняется только текст) — /task:plan-design <ID> Pn.
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** ручная проверка dict-ключей.\n", "")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет поля ТЗ «Code Guidance»"))

    def test_invalid_item_status(self):
        plan_dir = write_valid_plan(self.root)
        state = item_state_path(plan_dir)
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** Готово"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item P1.1: недопустимый статус «Готово»"))

    def test_item_prefix_mismatch(self):
        plan_dir = write_valid_plan(self.root)
        path = item_spec_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("P1.1", "P2.1")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается ровно один заголовок"))


class TestCompletionAndDeviations(TmpPlanTestCase):
    def test_done_without_completion_notes(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟢 Done", completion_notes="—"))
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "требует непустых Completion Notes"))

    def test_deviations_without_known_deviations(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(
                item_status="🟠 Done with deviations",
                completion_notes="сделано с оговоркой", known_deviations="—"))
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "требует непустых Known Deviations"))


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
        self.assertTrue(_errors_containing(diag, "рассогласованы"))

    def test_escalation_flag_yes_without_blocked_status(self):
        plan_dir = self._write("🟢 Done", "yes", completion_notes="сделано")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "рассогласованы"))

    def test_escalation_needed_invalid_value(self):
        plan_dir = self._write("⬜ Not started", "maybe")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается yes/no/—"))

    def test_blocked_with_full_escalation_triple_passes(self):
        plan_dir = self._write(
            "🔴 Blocked", "yes",
            extra_blockquote="> 🔴 ESCALATION P1.1: неясная архитектура | trigger: неясная "
                              "архитектура | нужен: plan-design",
        )
        _, diag = _lint(plan_dir)
        self.assertFalse(_errors_containing(diag, "рассогласованы"))


class TestPhaseStatusConsistency(TmpPlanTestCase):
    def test_generated_item_row_is_not_a_second_execution_source(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace(
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |",
            "| P1.1 | Валидация конфига | 🟡 In progress | 2026-07-02 |",
        )
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)


class TestStatusBoardConsistency(TmpPlanTestCase):
    def test_items_cell_wrong_count(self):
        plan_dir = write_valid_plan(self.root, )
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 0/1 | 🟢 Done |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "≠ фактическому 1/1"))

    def test_items_cell_bad_format(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | one | 🟢 Done |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается формат N/M"))

    def test_all_done_may_remain_in_progress_as_pre_close_audit_candidate(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 1/1 | 🟡 In progress |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_all_done_rejects_non_candidate_board_status(self):
        plan_dir = write_valid_plan(self.root)
        status = plan_dir / "status.md"
        text = status.read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 1/1 | ⬜ Not started |")
        status.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "все items 🟢 Done, но статус фазы"))

    def test_blocked_item_but_board_status_not_blocked(self):
        plan_dir = write_valid_plan(self.root)
        spec = item_spec_md().rstrip() + (
            "\n\n> 🔴 ESCALATION P1.1: причина | trigger: неясная архитектура | "
            "нужен: plan-design\n")
        write_v2_carriers(
            plan_dir, item_spec=spec,
            item_state=item_state_md(
                item_status="🔴 Blocked", escalation_needed="yes", completion_notes="—"))
        status = plan_dir / "status.md"
        status.write_text(status.read_text(encoding="utf-8").replace(
            "| P1 | Фаза раз | 0/1 | 🔴 Blocked |",
            "| P1 | Фаза раз | 0/1 | 🟢 Done |"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть 🔴 Blocked item, но статус фазы"))


class TestPhaseHandoffGating(TmpPlanTestCase):
    def test_done_phase_with_empty_phase_handoff(self):
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(plan_dir, phase_index=phase_index_md(handoff_text="—"))
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Phase Handoff» пуст"))

    def test_missing_phase_handoff_section(self):
        plan_dir = write_valid_plan(self.root)
        path = phase_index_path(plan_dir)
        text = path.read_text(encoding="utf-8")
        text = text.replace("## Phase Handoff", "## Что-то другое")
        path.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет секции «## Phase Handoff»"))


class TestStalePhaseHandoff(TmpPlanTestCase):
    """P2.15/D34 (H2): реопен инвалидирует `## Phase Handoff` маркером; блок, переживший
    реопен и утверждающий закрытие фазы, — WARNING. Гейт УЗКИЙ: заготовка/скелет молчит."""

    STALE_TEXT = ("Фаза P1 закрыта: **1/1 терминальны**.\n\n"
                  "**Сдано:** валидация конфига.\n\n**Дальше:** `/task:plan-audit DEMO-1 P1`.")

    def _write_reopened_phase(self, handoff_text):
        """Фаза 🟡 (реопенена: item снова в работе) с заданным `## Phase Handoff`."""
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, phase_index=phase_index_md(handoff_text=handoff_text),
            item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        return plan_dir

    def _stale_warnings(self, diag):
        return [w for w in diag.warnings if "Phase Handoff протух" in w]

    def test_nonterminal_phase_with_closure_claim_warns(self):
        plan_dir = self._write_reopened_phase(self.STALE_TEXT)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)  # именно WARNING, не ERROR (D34)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)
        self.assertIn("> УСТАРЕЛ — фаза реопенена <D#>", self._stale_warnings(diag)[0])

    def test_stale_marker_silences_the_gate(self):
        plan_dir = self._write_reopened_phase(
            "> **УСТАРЕЛ — фаза реопенена (D9, 2026-07-14).** Блок ниже записан plan-close\n"
            "> до реопена; факт: 0/1, фаза 🟡.\n\n" + self.STALE_TEXT)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._stale_warnings(diag), [])

    def test_placeholder_handoff_of_unfinished_phase_is_silent(self):
        # анти-регресс: скелеты/заготовки флота (наивная формулировка била 104 фазы)
        for text in ("—", "Заполняется при закрытии фазы."):
            with self.subTest(handoff=text):
                plan_dir = self._write_reopened_phase(text)
                _, diag = _lint(plan_dir)
                self.assertEqual(self._stale_warnings(diag), [])
                shutil.rmtree(plan_dir.parent)

    # --- P3.7/D50 (J1): гейт судит по СУБЪЕКТУ утверждения, а не по встреченному слову.
    # Обе фикстуры — ДОСЛОВНЫЕ формы флота (findings/P3-reopen-gates-and-fleet.md §1),
    # не «удобные» синтетические строки: ровно на них гейт разошёлся с истиной.

    def test_honest_interim_handoff_is_silent(self):
        """themeon/2026.07.12-BASE/P5: первая строка ОТРИЦАЕТ закрытие фазы, а слово
        «Терминальны» относится к ITEMS → ложно-положительный WARNING (J1, Blocker)."""
        plan_dir = self._write_reopened_phase(
            "**Фаза P5 НЕ закрыта.** Терминальны только P5.1 и P5.2 (2/10); P5.3–P5.10 (8/10) — "
            "🟠⬜ `Not started`\n(dterema: breakpoints/runtime-switch; vintera: весь пилот).\n\n"
            "**Что сдано (dterema, ветка `themeon-migration/P5`, НЕ смержена):** 3 коммита.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._stale_warnings(diag), [], diag.warnings)

    def test_delivery_claim_of_nonterminal_phase_still_warns(self):
        """vaulter/VLT-REMED/P5: первая строка УТВЕРЖДАЕТ сдачу фазы при нетерминальном
        статусе → истинно-положительный WARNING обязан сохраниться (анти-подгонка предиката)."""
        plan_dir = self._write_reopened_phase(
            "**Сдано:** Фаза P5 (сквозной adversarial code review всех изменений VLT-REMED) — "
            "**терминальна (3/3)**:\nP5.1 (🔴 Blocked) → P5.2 (🟠 Done with deviations) → "
            "**P5.3 (🟢 Done)**.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)

    def test_negation_below_first_line_does_not_silence_the_gate(self):
        """Отрицание судится по ТОЙ ЖЕ первой строке: «фаза закрыта … но P1.2 не закрыта»
        ниже по тексту не гасит истинное срабатывание (Implementation Rules P3.7)."""
        plan_dir = self._write_reopened_phase(
            "**Сдано:** фаза закрыта, 1/1.\n\nОстаток: P1.2 не закрыта — переносится в P2.")
        _, diag = _lint(plan_dir)
        self.assertEqual(len(self._stale_warnings(diag)), 1, diag.warnings)


class TestHandoffMd(TmpPlanTestCase):
    def test_missing_handoff_file(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "handoff.md").unlink()
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "handoff.md отсутствует"))

    def test_handoff_missing_title(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("# HANDOFF — 2026-07-02 — after P1.1\n", "")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет заголовка «# HANDOFF"))

    def test_handoff_title_after_item_valid(self):
        # форма `after Pn.m` (закрыт item) — базовая, остаётся валидной (D30)
        plan_dir = write_valid_plan(self.root)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_after_phase_valid(self):
        # вторая форма `after Pn` (закрыта/проаудирована ФАЗА) — D30/G10
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_after_nonexistent_phase(self):
        # анти-подгонка: `after Pn` обязан РЕЗОЛВИТЬСЯ, а не просто матчиться regex'ом
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P9\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок: фаза «P9» не существует в плане"))

    def test_handoff_title_item_form_nonexistent_phase(self):
        # D37/H10: item-форма `after Pn.m` больше не обходит гейт резолва — ФАЗА обязана быть
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P9.1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок: фаза «P9» не существует в плане"))

    def test_handoff_title_bootstrap_item_form_allowed(self):
        # D37: whitelist — РОВНО `P0.0` (стартовый handoff, фазы P0 в плане не бывает) → тихо
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after P0.0\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)

    def test_handoff_title_prose_form_rejected(self):
        # `after phase 2` — вне обеих форм enum'а
        plan_dir = write_valid_plan(self.root)
        handoff = plan_dir / "handoff.md"
        text = handoff.read_text(encoding="utf-8")
        text = text.replace("— after P1.1\n", "— after phase 1\n")
        handoff.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок не соответствует ни одной из двух форм"))

    def test_handoff_missing_required_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("**Remaining:** ничего.\n", "")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет обязательного поля «Remaining»"))

    def test_handoff_next_missing_reference(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "сделай что-нибудь")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "не соответствует ни одной из допустимых форм"))

    def test_handoff_next_wrong_plan_id(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-exec OTHER-ID P1.1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "PLAN-ID «OTHER-ID» ≠ фактическому «DEMO-1»"))

    def test_handoff_next_nonexistent_item(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-exec DEMO-1 P9.9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item «P9.9» не существует ни в одной фазе"))

    def test_handoff_next_plan_closed_allowed(self):
        # все items терминальны → Next «план закрыт» без ссылки plan-exec — валиден
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт — все фазы терминальны.")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)

    def test_handoff_next_plan_design_phase_allowed(self):
        # фаза-скелет впереди → Next «/task:plan-design <ID> Pn» (ссылка на фазу, не item) — валиден
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-design DEMO-1 P1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok)

    def test_handoff_next_plan_design_wrong_plan_id(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-design OTHER-ID P1")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "PLAN-ID «OTHER-ID» ≠ фактическому «DEMO-1»"))

    def test_handoff_next_plan_design_nonexistent_phase(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "handoff.md").read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "/task:plan-design DEMO-1 P9")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "фаза «P9» не существует в плане"))

    def test_handoff_next_plan_closed_rejected_when_items_active(self):
        # «план закрыт» при живом 🟡 item — не оправдание, ERROR остаётся
        plan_dir = write_valid_plan(self.root)
        write_v2_carriers(
            plan_dir, item_state=item_state_md(item_status="🟡 In progress", completion_notes="—"))
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт.")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«план закрыт», но не все items терминальны"))
