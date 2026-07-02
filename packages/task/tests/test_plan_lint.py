"""unittest для task.plan_lint — по классу ошибок отдельный кейс (см. fixtures.py
для шаблонов plan.md/phases/Pn.md/handoff.md, байт-в-байт по snippets/*-template.md).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import handoff_md, phase_md, plan_md, write_valid_plan  # noqa: E402
from task.plan_lint import Diagnostics, discover_plan_dirs, lint_plan, main  # noqa: E402


def _lint(plan_dir):
    """lint_plan напрямую (без CLI/subprocess) — возвращает (model, diag)."""
    diag = Diagnostics()
    model = lint_plan(plan_dir, diag)
    return model, diag


def _errors_containing(diag, needle):
    return [e for e in diag.errors if needle in e]


class TmpPlanTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


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


class TestPlanMdStructure(TmpPlanTestCase):
    def test_missing_plan_md(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
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
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("## 4. Phase Index & Status Board", "## 4. Что-то другое")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет секции «## 4. Phase Index & Status Board»"))

    def test_status_board_invalid_status(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                             "| P1 | Фаза раз | 1/1 | Готово |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Status Board: недопустимый статус «Готово»"))

    def test_status_board_malformed_phase_token(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз |", "| Phase1 | Фаза раз |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "не похож на Pn"))


class TestPhaseBoardCorrespondence(TmpPlanTestCase):
    def test_phase_in_board_without_file(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        # phases/P1.md сознательно не создан
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть в Status Board, но нет phases/P1.md"))

    def test_phase_file_without_board_row(self):
        plan_dir = write_valid_plan(self.root)
        (plan_dir / "phases" / "P2.md").write_text(phase_md("P2", item_id="P2.1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть как phases/P2.md, но нет в Status Board"))


class TestItemHeaderAndFields(TmpPlanTestCase):
    def test_malformed_item_header(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("### P1.1 — Валидация конфига", "### P1.1 Валидация конфига")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "заголовок item не соответствует regex"))

    def test_missing_required_item_field(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** ручная проверка dict-ключей.\n", "")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет обязательного поля «Code Guidance»"))

    def test_invalid_item_status(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        text = phase_md().replace("**Status:** 🟢 Done", "**Status:** Готово")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "item P1.1: недопустимый статус «Готово»"))

    def test_item_prefix_mismatch(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        # переименовываем item P1.1 -> P2.1, но он остаётся физически в файле phases/P1.md
        text = text.replace("P1.1", "P2.1")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "префикс «P2» не совпадает с файлом фазы «P1»"))


class TestCompletionAndDeviations(TmpPlanTestCase):
    def test_done_without_completion_notes(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟢 Done", completion_notes="—"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "требует непустых Completion Notes"))

    def test_deviations_without_known_deviations(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", phase_status="🟠 Done with deviations"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="🟠 Done with deviations",
                      completion_notes="сделано с оговоркой", known_deviations="—"),
            encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "требует непустых Known Deviations"))


class TestEscalationConsistency(TmpPlanTestCase):
    def _write(self, item_status, escalation_needed, extra_blockquote=None,
               completion_notes="—", known_deviations="—"):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", phase_status=item_status if item_status != "🟢 Done" else "🟢 Done"),
            encoding="utf-8")
        text = phase_md(item_status=item_status, escalation_needed=escalation_needed,
                         completion_notes=completion_notes, known_deviations=known_deviations)
        if extra_blockquote:
            text = text.replace("## Phase Handoff", f"{extra_blockquote}\n\n## Phase Handoff")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
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
    def test_phase_status_table_vs_item_status_mismatch(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        # таблица говорит Done, а сам item ниже — In progress
        text = text.replace(
            "| P1.1 | Валидация конфига | 🟢 Done | 2026-07-02 |",
            "| P1.1 | Валидация конфига | 🟡 In progress | 2026-07-02 |",
        )
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "статус в Phase Status «🟡 In progress» ≠ статусу item «🟢 Done»"))


class TestStatusBoardConsistency(TmpPlanTestCase):
    def test_items_cell_wrong_count(self):
        plan_dir = write_valid_plan(self.root, )
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 0/1 | 🟢 Done |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "≠ фактическому 1/1"))

    def test_items_cell_bad_format(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | one | 🟢 Done |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "ожидается формат N/M"))

    def test_all_done_but_board_status_not_done(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |", "| P1 | Фаза раз | 1/1 | 🟡 In progress |")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "все items 🟢 Done, но статус фазы"))

    def test_blocked_item_but_board_status_not_blocked(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="🟢 Done"), encoding="utf-8")
        text = phase_md(item_status="🔴 Blocked", escalation_needed="yes",
                         completion_notes="—", known_deviations="—")
        text = text.replace(
            "## Phase Handoff",
            "> 🔴 ESCALATION P1.1: причина | trigger: неясная архитектура | "
            "нужен: plan-design\n\n## Phase Handoff",
        )
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "есть 🔴 Blocked item, но статус фазы"))


class TestPhaseHandoffGating(TmpPlanTestCase):
    def test_done_phase_with_empty_phase_handoff(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md(handoff_text="—"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Phase Handoff» пуст"))

    def test_missing_phase_handoff_section(self):
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("## Phase Handoff", "## Что-то другое")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "нет секции «## Phase Handoff»"))


class TestHandoffMd(TmpPlanTestCase):
    def test_missing_handoff_file(self):
        plan_dir = self.root / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True)
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
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
        text = text.replace("**Next:** /task:plan-exec DEMO-1 P1.1\n", "**Next:** сделай что-нибудь\n")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Next не содержит «/task:plan-exec"))

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


if __name__ == "__main__":
    unittest.main()
