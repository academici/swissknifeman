"""unittest для task.plan_lint — по классу ошибок отдельный кейс (см. fixtures.py
для шаблонов plan.md/phases/Pn.md/handoff.md, байт-в-байт по snippets/*-template.md).
Запуск: cd packages/task && python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import (  # noqa: E402
    active_md, contracts_section, handoff_md, phase_md, plan_md, write_valid_plan,
)
from task.plan_lint import (  # noqa: E402
    Diagnostics, discover_plan_dirs, lint_plan, lint_plans_root, main,
)


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

    def test_missing_required_item_field_message_is_actionable(self):
        # ERROR скелет-item'а обязана называть путь починки (D11: ERROR не ослабляется,
        # меняется только текст) — /task:plan-design <ID> Pn.
        plan_dir = write_valid_plan(self.root)
        text = (plan_dir / "phases" / "P1.md").read_text(encoding="utf-8")
        text = text.replace("**Code Guidance:** ручная проверка dict-ключей.\n", "")
        (plan_dir / "phases" / "P1.md").write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "/task:plan-design <ID> P1"))

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
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт.")
        ho.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "«план закрыт», но не все items терминальны"))


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


class TestLint20Warnings(TmpPlanTestCase):
    """Проверки схемы 2.0 (ECOSYSTEM P5.2 блок 13) — ВСЕ warning-уровня:
    диагностика попадает в diag.warnings, diag.ok остаётся True."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def test_plan_sections_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        # меняем местами Decision Log (5) и Update Log (6) — номера не по возрастанию
        text = text.replace("## 5. Decision Log", "## X-TMP")
        text = text.replace("## 6. Update Log", "## 5. Decision Log… нет, Update Log")
        text = text.replace("## X-TMP", "## 6. Update Log")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "не по порядку"), diag.warnings)

    def test_plan_section_title_mismatch_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("## 3. Routing", "## 3. Маршрутизация")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "≠ канонической"), diag.warnings)

    def test_update_log_too_long_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        text = text.replace("| 2026-07-02 | issue-planner/opus | План создан |",
                            "| 2026-07-02 | issue-planner/opus | " + "х" * 301 + " |")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "Update Log"), diag.warnings)

    def test_decision_log_without_rag_markers_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        extra = ("| D2 | 2026-07-02 | ещё решение | так надо |\n"
                 "| D3 | 2026-07-02 | третье решение | и так надо |\n")
        text = text.replace("| D1 | 2026-07-02 | тест | тест |\n",
                            "| D1 | 2026-07-02 | тест | тест |\n" + extra)
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "RAG:✅"), diag.warnings)

    def test_decision_log_with_rag_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        extra = ("| D2 | 2026-07-02 | ещё решение | RAG:✅ 2026-07-02 запрос |\n"
                 "| D3 | 2026-07-02 | третье решение | [UNVERIFIED] |\n")
        text = text.replace("| D1 | 2026-07-02 | тест | тест |\n",
                            "| D1 | 2026-07-02 | тест | тест |\n" + extra)
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "RAG:✅»/«[UNVERIFIED]"), [])

    def test_decision_log_with_rag_dash_marker_no_warning(self):
        # третий маркер enum'а §7 (D29): `RAG:—` — repo-grounded факт, WARNING'а быть не должно
        plan_dir = write_valid_plan(self.root)
        plan = plan_dir / "plan.md"
        text = plan.read_text(encoding="utf-8")
        extra = ("| D2 | 2026-07-02 | ещё решение | RAG:— (repo-grounded: lib/pkg/config.py) |\n"
                 "| D3 | 2026-07-02 | третье решение | RAG:— |\n")
        text = text.replace("| D1 | 2026-07-02 | тест | тест |\n",
                            "| D1 | 2026-07-02 | тест | тест |\n" + extra)
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "Decision Log:"), [])

    def test_item_fields_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        # Intent и Why меняем местами — канонический порядок нарушен
        text = text.replace("**Intent:** Добавить проверку.\n**Why:** Диагностика дорогая.",
                            "**Why:** Диагностика дорогая.\n**Intent:** Добавить проверку.")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "не в каноническом порядке"), diag.warnings)

    def _make_hollow_item(self, plan_dir):
        """P1.1 с ⬜ и ≥50% пустых полей (скелетоподобный item)."""
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        for field, val in (("Intent", "Добавить проверку."), ("Why", "Диагностика дорогая."),
                           ("Scope Included", "load_config()."), ("Scope Excluded", "формат конфига."),
                           ("Inputs", "список ключей."), ("Files", "lib/pkg/config.py"),
                           ("Required Reads", "1) lib/pkg/config.py"),
                           ("Implementation Rules", "stdlib-only."),
                           ("Code Guidance", "ручная проверка dict-ключей.")):
            text = text.replace(f"**{field}:** {val}", f"**{field}:** —")
        text = text.replace("**Status:** 🟢 Done", "**Status:** ⬜ Not started")
        text = text.replace("| P1.1 | Валидация конфига | 🟢 Done |",
                            "| P1.1 | Валидация конфига | ⬜ Not started |")
        p1.write_text(text, encoding="utf-8")
        plan = plan_dir / "plan.md"
        ptext = plan.read_text(encoding="utf-8")
        ptext = ptext.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                              "| P1 | Фаза раз | 0/1 | ⬜ Not started |")
        ptext = ptext.replace("| Status | 🟢 Done |", "| Status | 🟡 In progress |")
        plan.write_text(ptext, encoding="utf-8")
        return p1

    def test_hollow_item_without_skeleton_marker_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._make_hollow_item(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "СКЕЛЕТ"), diag.warnings)

    def test_hollow_item_with_skeleton_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = self._make_hollow_item(plan_dir)
        text = p1.read_text(encoding="utf-8")
        text = text.replace(
            "Демо-фаза.",
            "Демо-фаза.\n\n> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design DEMO-1 P1")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "СКЕЛЕТ"), [], diag.warnings)

    def test_needs_clarification_in_active_phase_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = plan_dir / "phases" / "P1.md"
        text = p1.read_text(encoding="utf-8")
        text = text.replace("**Why:** Диагностика дорогая.",
                            "**Why:** Диагностика дорогая. [NEEDS CLARIFICATION: какой формат ошибок?]")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)  # фаза 🟢 Done — точно «ушла из дизайна»
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "NEEDS CLARIFICATION"), diag.warnings)

    def test_handoff_next_without_launch_block_warning(self):
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = handoff_md("DEMO-1")
        # выпиливаем launch-block целиком: остаётся голый Next без таблицы/code-block
        head, _, tail = text.partition("\n| Параметр | Значение |")
        _, _, after = tail.partition("````\n\n")
        ho.write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "launch-block"), diag.warnings)

    def test_handoff_plan_closed_launch_block_not_required(self):
        # план закрыт → запускать нечего, launch-block не требуется
        plan_dir = write_valid_plan(self.root)
        ho = plan_dir / "handoff.md"
        text = ho.read_text(encoding="utf-8")
        text = text.replace("/task:plan-exec DEMO-1 P1.1", "план закрыт — все фазы терминальны.")
        head, _, tail = text.partition("\n| Параметр | Значение |")
        _, _, after = tail.partition("````\n\n")
        ho.write_text(head + "\n" + after, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "launch-block"), [], diag.warnings)


class TestPlanIdentity43Warnings(TmpPlanTestCase):
    """P4.3 (D24/D27/D28) — три WARNING-проверки идентичности плана: регулярка PLAN-ID,
    место/имя workflow-скрипта, supersedes-преемственность. ВСЕ warning: diag.ok=True."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _add_js(self, plan_dir, rel, with_marker=True):
        p = plan_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        body = "export const meta = {\n  name: 'x',\n}\n" if with_marker else "// не workflow\n"
        p.write_text(body, encoding="utf-8")
        return p

    # --- (1) регулярка PLAN-ID (D24) -----------------------------------------
    def test_legacy_id_no_warning(self):
        plan_dir = write_valid_plan(self.root, "OLD-STYLE")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "канону PLAN-ID"), [], diag.warnings)

    def test_dated_id_no_warning(self):
        plan_dir = write_valid_plan(self.root, "2026.07.10-DEMO")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "канону PLAN-ID"), [], diag.warnings)

    def test_noncanonical_id_warning(self):
        # строчные буквы → не матчит ни старый `[A-Z]…`, ни датовый паттерн
        plan_dir = write_valid_plan(self.root, "demo-lower")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "канону PLAN-ID"), diag.warnings)

    # --- (2) место/имя workflow-скрипта (D28) --------------------------------
    def test_canonical_workflow_script_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # codename = demo-1
        self._add_js(plan_dir, "workflows/wf-demo-1-drive.js")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-скрипт"), [], diag.warnings)

    def test_workflow_script_outside_workflows_dir_warns_place(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "wf-demo-1-drive.js")  # каноничное имя, но не под workflows/
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        w = self._warnings_containing(diag, "workflow-скрипт")
        self.assertTrue(any("вне" in x for x in w), diag.warnings)
        self.assertFalse(any("неканоничным именем" in x for x in w), diag.warnings)

    def test_workflow_script_noncanonical_name_warns_name(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "workflows/wf-bad.js")  # под workflows/, но имя неканонично
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        w = self._warnings_containing(diag, "workflow-скрипт")
        self.assertTrue(any("неканоничным именем" in x for x in w), diag.warnings)
        self.assertFalse(any("вне" in x for x in w), diag.warnings)

    def test_js_without_marker_ignored(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "helpers/util.js", with_marker=False)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "workflow-скрипт"), [], diag.warnings)

    # --- (3) supersedes-преемственность (D27) --------------------------------
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
            "| Status | 🟢 Done |", "| Status | 🟢 Done |\n| supersedes | DEMO-OLD |")
        plan.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "supersedes"), [], diag.warnings)

    def test_no_archive_dir_no_warning(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # plans/archive/ отсутствует
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "supersedes"), [], diag.warnings)


class TestWorkflowDoRWarning46(TmpPlanTestCase):
    """P4.6 (D29) — workflow-как-DoR: фаза со статусом 🟡+, ЗАЯВЛЯЮЩАЯ оркестрацию
    (грепаемый признак multi-agent/fan-out), но без workflow-скрипта в
    `plans/<ID>/workflows/` = WARNING. Условность: без признака / при статусе ⬜ /
    при наличии скрипта — тишина. Всё warning-only: diag.ok=True."""

    _NEEDLE = "заявляет оркестрацию"

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _inject_orchestration(self, plan_dir, phase="P1"):
        """Добавляет грепаемый признак оркестрации в Phase Context фазы."""
        p = plan_dir / "phases" / f"{phase}.md"
        text = p.read_text(encoding="utf-8").replace(
            "Демо-фаза.", "Демо-фаза. Оркестрация fan-out субагентов, launch-block по scriptPath.")
        p.write_text(text, encoding="utf-8")

    def _add_workflow(self, plan_dir, name="wf-demo-1-drive.js"):
        wf = plan_dir / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / name).write_text("export const meta = {\n  phases: [],\n}\n", encoding="utf-8")

    # --- позитив: фаза заявляет оркестрацию, статус 🟢, скрипта нет → warning -----
    def test_orchestration_phase_without_script_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._inject_orchestration(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)  # warning-only, не error
        self.assertTrue(self._warnings_containing(diag, self._NEEDLE), diag.warnings)

    # --- негатив: признак есть, но скрипт в workflows/ лежит → тишина -------------
    def test_orchestration_phase_with_script_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._inject_orchestration(plan_dir)
        self._add_workflow(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: признака оркестрации в фазе нет → тишина (ручное исполнение) ----
    def test_phase_without_orchestration_marker_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # green-path, без маркера
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: бумерное `fan-out` в прозе (не декларация) → тишина ------------
    # регрессия на ложный warning SKM-MASTER-002/P3 (fan-out в Known Deviations про
    # токен-учёт): консервативный набор маркеров намеренно НЕ ловит одиночное слово.
    def test_bare_fanout_in_prose_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p = plan_dir / "phases" / "P1.md"
        text = p.read_text(encoding="utf-8").replace(
            "Демо-фаза.", "Демо-фаза. Искажение метрики при fan-out субагентов — допущено.")
        p.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: фаза заявляет оркестрацию, но статус ⬜ → тишина (не в exec) -----
    def test_orchestration_phase_not_started_silent(self):
        plan_dir = Path(self.root) / "plans" / "DEMO-1"
        (plan_dir / "phases").mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text(
            plan_md("DEMO-1", items_cell="0/1", phase_status="⬜ Not started"), encoding="utf-8")
        (plan_dir / "phases" / "P1.md").write_text(
            phase_md(item_status="⬜ Not started", completion_notes="—",
                     handoff_text="—"), encoding="utf-8")
        (plan_dir / "handoff.md").write_text(handoff_md("DEMO-1"), encoding="utf-8")
        self._inject_orchestration(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)


class TestContractsSection(TmpPlanTestCase):
    """m7/D10 — опциональная секция `## 7. Contracts` + cross-plan сверка версий (§11)."""

    CONTRACT = "root/contracts/module-manifest.md"

    def _write_pair(self, donor_version, pinned):
        """Донор DONOR (Exported) + потребитель CONSUMER (Consumed) в одном корне plans/."""
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
        self.assertEqual([w for w in diag.warnings if "уведомление не разнесено" in w], [])
        self.assertEqual(models["DONOR"]["contracts"]["exported"][0]["Версия"], "v2.0.2")

    def test_version_drift_warns_once(self):
        _, diag = self._lint_root(self._write_pair("v2.0.2", "v2.0.0"))
        hits = [w for w in diag.warnings if "уведомление не разнесено" in w]
        self.assertEqual(len(hits), 1, diag.warnings)
        self.assertIn("потребитель CONSUMER запинен на v2.0.0", hits[0])
        self.assertEqual(diag.errors, [])  # только WARNING — механизм молод (D10)

    def test_no_section_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        model, diag = _lint(plan_dir)
        self.assertEqual(diag.errors, [])
        self.assertEqual(diag.warnings, [])
        self.assertEqual(model["contracts"], {"exported": [], "consumed": []})

    def test_donor_outside_root_silent(self):
        # Донор в другом репо (в этом корне его нет) — линтер честно молчит (граница §11).
        consumer = write_valid_plan(self.root, "CONSUMER")
        (consumer / "plan.md").write_text(
            plan_md("CONSUMER") + contracts_section(
                consumed=[(f"REGHUB/{self.CONTRACT}", "REGHUB", "v2.0.0")]),
            encoding="utf-8")
        (self.root / "plans" / "ACTIVE.md").write_text(active_md("CONSUMER"), encoding="utf-8")
        _, diag = self._lint_root(self.root / "plans")
        self.assertEqual(diag.errors, [])
        self.assertEqual([w for w in diag.warnings if "уведомление не разнесено" in w], [])

    def test_wrong_columns_warn_not_error(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        broken = contracts_section(
            exported=[(self.CONTRACT, "v1.0.0", "—")]).replace("| Статус |", "| State |")
        (plan_dir / "plan.md").write_text(plan_md("DEMO-1") + broken, encoding="utf-8")
        model, diag = _lint(plan_dir)
        self.assertEqual(diag.errors, [])
        self.assertTrue(any("колонки" in w for w in diag.warnings), diag.warnings)
        self.assertEqual(model["contracts"]["exported"], [])  # кривая таблица не парсится


class TestBaselineGate(TmpPlanTestCase):
    """P1.2/B1/D5/D6 — `--baseline`/`--gate`: детерминированный счёт новых ошибок K."""

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

    @unittest.skipUnless(shutil.which("git"), "git недоступен")
    def test_baseline_no_new_errors_on_clean_tree(self):
        plan_dir = self._init_repo_with_valid_plan()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("новых от рабочего дерева: 0", out.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git недоступен")
    def test_baseline_counts_new_error_and_gate_new_fails(self):
        plan_dir = self._init_repo_with_valid_plan()
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
        text = text.replace("| Plan ID | DEMO-1 |\n", "")
        (plan_dir / "plan.md").write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline", "HEAD", "--gate", "new"])
        self.assertEqual(code, 1)
        self.assertIn("новых от рабочего дерева: 1", out.getvalue())

    @unittest.skipUnless(shutil.which("git"), "git недоступен")
    def test_baseline_default_gate_stays_all_even_when_k_zero(self):
        # --gate=all (дефолт, back-compat CI) — exit по N, даже если сам baseline-дифф
        # чист (K==0), а план несёт остаточную ошибку вне диффа этого коммита.
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
        self.assertIn("новых от рабочего дерева: 0", out.getvalue())

    def test_baseline_unavailable_without_git_repo(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")  # НЕТ git init
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(plan_dir), "--baseline"])
        self.assertEqual(code, 0, err.getvalue())  # exit по N (план валиден), не по K
        self.assertIn("baseline", err.getvalue())
        self.assertIn("недоступен", err.getvalue())
        self.assertNotIn("новых от рабочего дерева", out.getvalue())
