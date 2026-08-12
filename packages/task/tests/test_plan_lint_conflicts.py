"""Canon conflicts and plan-2.0 warning cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *
import task.plan_lint_checks.conflicts as conflicts_module
from hashlib import sha256
import json


class TestConflictsFlagUnits(unittest.TestCase):
    """Юниты `--conflicts` (2026.07.31-SKM-LEAN P5.9) на СИНТЕТИЧЕСКОМ каноне — фиксируют
    ФОРМУ сверки, независимо от текущего текста живого `SKILL.md` (тот же принцип, что
    `test_canon_literals.py::TestT1CollectorVectors`). Живой прогон против реального канона
    покрыт `TestConflictsFlagLiveRepo` ниже."""

    def _diag(self):
        return Diagnostics()

    # --- статусы -------------------------------------------------------------
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

    # --- 16 полей item'а -------------------------------------------------------
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
        self.assertTrue(_errors_containing(diag, "16-полей"), diag.errors)

    # --- формы Next ------------------------------------------------------------
    def _code_next_kinds(self):
        import re
        gm = re.search(r"\^\((.*?)\):", SEMANTIC_NEXT_RE.pattern)
        return gm.group(1).split("|")

    def test_next_forms_consistent_is_silent(self):
        lines = ["**Allowed `Next` forms**:", "```text", conflicts_module.CONFLICTS_ANCHOR_NEXT_FORMS,
                 "|:--|:--|"]
        lines += [f"| {kind}: пример | пояснение |" for kind in self._code_next_kinds()]
        lines += ["Иная форма = ERROR plan-lint.", "```"]
        diag = self._diag()
        _conflicts_next_forms(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_next_forms_missing_one_is_error(self):
        kinds = self._code_next_kinds()[:-1]  # без последней формы (waiting)
        lines = ["**Allowed `Next` forms**:", "```text", conflicts_module.CONFLICTS_ANCHOR_NEXT_FORMS,
                 "|:--|:--|"]
        lines += [f"| {kind}: пример | пояснение |" for kind in kinds]
        lines += ["Иная форма = ERROR plan-lint.", "```"]
        diag = self._diag()
        _conflicts_next_forms(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "формы Next"), diag.errors)

    # --- три значения Context ----------------------------------------------
    def test_context_values_consistent_is_silent(self):
        lines = [f"Context carries {conflicts_module.CONFLICTS_ANCHOR_CONTEXT}:"]
        lines += [f"- **`{v}`** — пояснение." for v in CONTEXT_VALUES]
        diag = self._diag()
        _conflicts_context_values(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_context_values_mismatch_is_error(self):
        corrupted = ("continue-root", "isolated-child-return", "cold-start — WRONG")
        lines = [f"Context carries {conflicts_module.CONFLICTS_ANCHOR_CONTEXT}:"]
        lines += [f"- **`{v}`** — пояснение." for v in corrupted]
        diag = self._diag()
        _conflicts_context_values(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "Context"), diag.errors)

    # --- литералы i18n-keep ------------------------------------------------
    def test_i18n_undeclared_literal_is_error(self):
        fake_literal = "тестовый-небъявленный-литерал-P5-9"
        diag = self._diag()
        with unittest.mock.patch.object(
                plan_lint_module, "CANON_LITERALS", CANON_LITERALS + (fake_literal,)):
            _conflicts_i18n_literals("текст канона без директив", ["текст канона без директив"],
                                     Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, fake_literal), diag.errors)

    def test_i18n_all_declared_is_silent(self):
        skill_text = "".join(f"<!-- i18n-keep: {lit} -->\n" for lit in CANON_LITERALS)
        diag = self._diag()
        _conflicts_i18n_literals(skill_text, skill_text.splitlines(), Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    # --- регекс-носители формы launch-block'а -------------------------------
    def test_launch_table_regex_matches_canon_rows_is_silent(self):
        lines = ["| Параметр | Значение |", "|:--|:--|", "| Model class | ... |",
                 "| Effort | ... |", "| Context | ... |", "| Суть | ... |",
                 "| Команда | `...` |"]
        diag = self._diag()
        _conflicts_launch_table_regex(lines, Path("SKILL.md"), diag)
        self.assertTrue(diag.ok, diag.errors)

    def test_launch_table_missing_command_row_is_error(self):
        lines = ["| Параметр | Значение |", "|:--|:--|", "| Model class | ... |",
                 "| Effort | ... |"]
        diag = self._diag()
        _conflicts_launch_table_regex(lines, Path("SKILL.md"), diag)
        self.assertFalse(diag.ok)
        self.assertTrue(_errors_containing(diag, "LAUNCH_COMMAND_ROW_RE"), diag.errors)

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
    """`--conflicts` против РЕАЛЬНОГО `SKILL.md` — Validation п.6 (первый прогон на живом
    дереве). Standalone-раскладка (пакет `task` вне монорепо) — тест пропускается, не падает:
    тот же класс деградации, что `test_canon_literals.py`."""

    def setUp(self):
        if _find_skill() is None:
            self.skipTest("standalone-раскладка: SKILL.md не найден от plan_lint.py вверх")

    def test_conflicts_green_on_live_canon(self):
        diag = Diagnostics()
        run_conflicts_check(diag)
        self.assertTrue(diag.ok, diag.errors)

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

    def test_main_conflicts_flag_exit_0(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--conflicts"])
        self.assertEqual(code, 0)
        self.assertIn("OK", out.getvalue())

    def test_main_path_optional_with_conflicts(self):
        """Implementation Rule 5: `path` необязателен при `--conflicts` (back-compat
        позиционного `path` без флага сохраняется — см. `test_main_without_conflicts_or_path_errors`)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--conflicts"])
        self.assertEqual(code, 0)

    def test_main_without_conflicts_or_path_errors(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(io.StringIO()):
                main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("path обязателен без --conflicts", err.getvalue())


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
        # Меняем номера двух v2-core секций, сохраняя канонические title.
        text = text.replace("## 1. Context", "## X-TMP")
        text = text.replace("## 2. Execution Rules", "## 1. Context")
        text = text.replace("## X-TMP", "## 2. Execution Rules")
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

    def test_v2_update_projection_bounds_long_journal_note(self):
        plan_dir = write_valid_plan(self.root)
        journal = plan_dir / "journal.jsonl"
        entry = json.loads(journal.read_text(encoding="utf-8"))
        entry["note"] = "х" * 301
        journal.write_text(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "Update Log"), [], diag.warnings)

    def test_decision_log_without_rag_markers_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._write_decisions(plan_dir, ("тест", "так надо", "и так надо"))
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "RAG:✅"), diag.warnings)

    def test_decision_log_with_rag_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._write_decisions(plan_dir, ("тест", "RAG:✅ 2026-07-02 запрос", "[UNVERIFIED]"))
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "RAG:✅»/«[UNVERIFIED]"), [])

    def test_decision_log_with_rag_dash_marker_no_warning(self):
        # третий маркер enum'а §7 (D29): `RAG:—` — repo-grounded факт, WARNING'а быть не должно
        plan_dir = write_valid_plan(self.root)
        self._write_decisions(plan_dir, ("тест", "RAG:— (repo-grounded: lib/pkg/config.py)", "RAG:—"))
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
                f"## Решение\n\nРешение {number}.\n\n## Почему\n\n{reason}\n",
                encoding="utf-8")

    def test_item_fields_out_of_order_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = item_spec_path(plan_dir)
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
        p1 = item_spec_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        for field, val in (("Intent", "Добавить проверку."), ("Why", "Диагностика дорогая."),
                           ("Scope Included", "load_config()."), ("Scope Excluded", "формат конфига."),
                           ("Inputs", "список ключей."), ("Files", "lib/pkg/config.py"),
                           ("Required Reads", "1) lib/pkg/config.py"),
                           ("Implementation Rules", "stdlib-only."),
                           ("Code Guidance", "ручная проверка dict-ключей.")):
            text = text.replace(f"**{field}:** {val}", f"**{field}:** —")
        p1.write_text(text, encoding="utf-8")
        state = item_state_path(plan_dir)
        state.write_text(state.read_text(encoding="utf-8").replace(
            "**Status:** 🟢 Done", "**Status:** ⬜ Not started"), encoding="utf-8")
        plan = plan_dir / "plan.md"
        ptext = plan.read_text(encoding="utf-8")
        ptext = ptext.replace("| P1 | Фаза раз | 1/1 | 🟢 Done |",
                              "| P1 | Фаза раз | 0/1 | ⬜ Not started |")
        ptext = ptext.replace("| Status | 🟢 Done |", "| Status | 🟡 In progress |")
        plan.write_text(ptext, encoding="utf-8")
        from task import plan_status
        plan_status.build_status(plan_dir)
        return p1

    def test_hollow_item_without_skeleton_marker_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._make_hollow_item(plan_dir)
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertTrue(self._warnings_containing(diag, "СКЕЛЕТ"), diag.warnings)

    def test_hollow_item_with_skeleton_marker_no_warning(self):
        plan_dir = write_valid_plan(self.root)
        self._make_hollow_item(plan_dir)
        p1 = phase_index_path(plan_dir)
        text = p1.read_text(encoding="utf-8")
        text = text.replace(
            "Демо-фаза.",
            "Демо-фаза.\n\n> СКЕЛЕТ — не детализирован, разворачивается /task:plan-design DEMO-1 P1")
        p1.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertEqual(self._warnings_containing(diag, "СКЕЛЕТ"), [], diag.warnings)

    def test_needs_clarification_in_active_phase_warning(self):
        plan_dir = write_valid_plan(self.root)
        p1 = item_spec_path(plan_dir)
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

    # --- (2b) dev-loop.js — резидентный agent-pack класс, exempt (P3.3/findings A4) ---
    def test_dev_loop_js_exempt_by_name(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._add_js(plan_dir, "dev-loop.js")  # вне workflows/, неканоничное имя — оба триггера
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
            "| Layout | v2 |", "| Layout | v2 |\n| supersedes | DEMO-OLD |")
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
        p = phase_index_path(plan_dir, phase)
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
        p = phase_index_path(plan_dir)
        text = p.read_text(encoding="utf-8").replace(
            "Демо-фаза.", "Демо-фаза. Искажение метрики при fan-out субагентов — допущено.")
        p.write_text(text, encoding="utf-8")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, self._NEEDLE), [], diag.warnings)

    # --- негатив: фаза заявляет оркестрацию, но статус ⬜ → тишина (не в exec) -----
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
