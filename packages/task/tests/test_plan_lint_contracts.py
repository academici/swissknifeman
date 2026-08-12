"""Contracts, baseline and late protocol gate cases for plan-lint."""
try:
    from .test_plan_lint_support import *
except ImportError:
    from test_plan_lint_support import *


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

    def test_read_budget_observations_do_not_rekey_same_baseline_failure(self):
        before, after = Diagnostics(), Diagnostics()
        path = self.root / "plans" / "DEMO-1" / "plan.md"
        before.error(path, None,
                     "read-budget-v1: пункт P1.1: вес 100001 > порога 100000 "
                     "оценочных токенов (calibration)")
        after.error(path, None,
                    "read-budget-v1: пункт P1.1: вес 100777 > порога 100000 "
                    "оценочных токенов (calibration)")
        self.assertEqual(before.normalized_keys(self.root), after.normalized_keys(self.root))

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


class TestAuditBlockOutsidePhaseGates(TmpPlanTestCase):
    """P3.8/A4/D52 — append-only блок `## Audit Pn` ВНЕ региона грепов по фазе.
    Аудитор обязан назвать маркер, о проверке которого отчитывается («маркеров X — 0»);
    греп по всему файлу фазы ронял гейт на его собственной строке. Регион кончается на
    первом `## Audit`; тот же маркер в ТЕЛЕ item'а по-прежнему даёт WARNING."""

    def _warnings_containing(self, diag, needle):
        return [w for w in diag.warnings if needle in w]

    def _append_audit_block(self, plan_dir, body, phase="P1"):
        p = phase_index_path(plan_dir, phase)
        p.write_text(p.read_text(encoding="utf-8")
                     + f"\n## Audit {phase} — 2026-07-15\n\n**Вердикт:** 🟢 GREEN\n\n{body}\n",
                     encoding="utf-8")

    # --- A4: DoR-маркер ТОЛЬКО в блоке аудита → гейт молчит -----------------------
    def test_clarification_marker_inside_audit_block_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._append_audit_block(
            plan_dir, "- Проверено: маркеров `[NEEDS CLARIFICATION: …]` в фазе — 0.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "NEEDS CLARIFICATION"), [], diag.warnings)

    # --- контроль: тот же маркер в ТЕЛЕ item'а → WARNING (гейт не ослаблен) -------
    def test_clarification_marker_in_item_body_still_warns(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        p1 = item_spec_path(plan_dir)
        p1.write_text(p1.read_text(encoding="utf-8").replace(
            "**Why:** Диагностика дорогая.",
            "**Why:** Диагностика дорогая. [NEEDS CLARIFICATION: какой формат?]"),
            encoding="utf-8")
        self._append_audit_block(plan_dir, "- Проверено: маркеров уточнения — 0.")
        _, diag = _lint(plan_dir)
        self.assertTrue(self._warnings_containing(diag, "NEEDS CLARIFICATION"), diag.warnings)

    # --- тот же регион у второго грепа по фазе: признак оркестрации в блоке аудита -
    def test_orchestration_marker_inside_audit_block_silent(self):
        plan_dir = write_valid_plan(self.root, "DEMO-1")
        self._append_audit_block(
            plan_dir, "- Оркестрация фазой не заявлена: `scriptPath` в launch-block отсутствует.")
        _, diag = _lint(plan_dir)
        self.assertTrue(diag.ok, diag.errors)
        self.assertEqual(self._warnings_containing(diag, "заявляет оркестрацию"), [], diag.warnings)


class TestCheckpointedGate83(TmpPlanTestCase):
    """P8.3/D44: item со статусом `🔴 Blocked` обязан нести в Pending Work строку
    `Возобновление: <команда>`; `⛔ Skipped by decision` — РОВНО `Возобновление: —` И
    ссылку `D<номер>`. Активация — opt-in Meta `Closure Protocol | v1` (без даты-канона:
    на дату детализации живых 🔴/⛔ items с включённым протоколом на флоте нет). Каждый
    различающий кейс проверен КРАСНЫМ на коде до этого item'а: `git show
    HEAD:packages/task/lib/task/plan_lint.py` не нёс ни `_lint_checkpointed_83`, ни
    вызова из `lint_plan` — старый код молчал на ВСЕХ кейсах."""

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
        """(a) 🔴 + `Возобновление: <команда>` → диагностик гейта нет."""
        plan_dir = self._write(pending_work="Возобновление: /task:plan-design DEMO-1 P1.1")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Возобновление"), [])

    def test_b_blocked_without_resume_line_is_error_with_id(self):
        """(б) 🔴 без строки `Возобновление:` → ERROR, текст несёт id item'а."""
        plan_dir = self._write(pending_work="—")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "Возобновление")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in e for e in hits), hits)

    def test_b2_blocked_with_bare_dash_resume_is_error(self):
        """(б, вариант) 🔴 + `Возобновление: —` (голый прочерк, без внешнего блокера и
        без команды) → ERROR: непустая команда обязательна, «—» ей не считается."""
        plan_dir = self._write(pending_work="Возобновление: —")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Возобновление"), diag.errors)

    def test_b3_blocked_with_external_blocker_form_passes(self):
        """(б, вариант) 🔴 + `Возобновление: — (внешний блокер: …)` — легальная форма
        для блокера без локального шага (Code Guidance P8.3) → диагностик нет."""
        plan_dir = self._write(
            pending_work="Возобновление: — (внешний блокер: решение владельца по OQ-4)")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Возобновление"), [])

    def test_c_skipped_without_resume_and_d_ref_is_error(self):
        """(в) ⛔ без `Возобновление: —`/без `D<номер>` → ERROR с id item'а."""
        plan_dir = self._write(item_status="⛔ Skipped by decision", pending_work="—")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "Возобновление")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P1.1" in e for e in hits), hits)

    def test_c2_skipped_with_resume_dash_but_no_d_ref_is_error(self):
        """(в, вариант) ⛔ + `Возобновление: —`, но БЕЗ ссылки `D<номер>` → ERROR:
        решение о пропуске обязано быть предъявлено записью, не молчанием."""
        plan_dir = self._write(item_status="⛔ Skipped by decision",
                               pending_work="Возобновление: —")
        _, diag = _lint(plan_dir)
        self.assertTrue(_errors_containing(diag, "Возобновление"), diag.errors)

    def test_c3_skipped_with_resume_dash_and_d_ref_passes(self):
        """(в, обратный) ⛔ + РОВНО `Возобновление: —` И `D40` в том же поле (другой
        строкой) → диагностик нет."""
        plan_dir = self._write(
            item_status="⛔ Skipped by decision",
            pending_work="Возобновление: —\nМоот, решение — D40.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Возобновление"), [])

    def test_d_done_status_has_no_new_requirement(self):
        """(г) 🟢 Done без строки `Возобновление:` — гейт молчит (требование только у
        🔴/⛔)."""
        plan_dir = self._write(item_status="🟢 Done", pending_work="—")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Возобновление"), [])

    def test_e_additivity_plan_without_meta_field_gets_no_new_diagnostics(self):
        """(д) АДДИТИВНОСТЬ: тот же 🔴-план БЕЗ Meta `Closure Protocol` не даёт ни
        одной диагностики гейта, даже без строки `Возобновление:`."""
        plan_dir = self._write(closure_protocol=None, pending_work="—")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "Возобновление"), [])


class TestHandoffBoardGate113(TmpPlanTestCase):
    """P11.3/D129: каждое вхождение `Pn a/b` в handoff.md обязано совпадать со значением
    колонки `Items 🟢/всего` строки `Pn` доски «## 4. Phase Index & Status Board»; фаза,
    отсутствующая в доске, — «висячая ссылка». Forward-only по ДАТЕ ЗАГОЛОВКА handoff'а
    (HANDOFF_BOARD_CANON_DATE); severity внутри скоупа — как у launch-block-гейта (датовый
    `plan_id` от BRIEF_CANON_DATE → ERROR, легаси → WARNING). Каждый различающий кейс
    проверен КРАСНЫМ на коде до этого item'а: `git show HEAD:packages/task/lib/task/
    plan_lint.py` не нёс ни `_lint_handoff_board_113`, ни `HANDOFF_BOARD_REF_RE`, ни вызова
    из `lint_plan` — старый код молчал на ВСЕХ кейсах ниже."""

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
            text = text.replace("**Done:** P1.1 закрыт.",
                                 f"**Done:** P1.1 закрыт. {handoff_extra}")
        (plan_dir / "handoff.md").write_text(text, encoding="utf-8")
        return plan_dir

    def test_a_f8_mismatch_on_dated_plan_is_error_naming_both_sides(self):
        """(a) фикстура F8: handoff говорит `P1 4/4`, доска несёт `1/1` (дефолт) на
        датовом `plan_id` (≥ BRIEF_CANON_DATE) → ERROR, текст называет ОБЕ стороны."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO",
                               handoff_extra="Доска: P1 4/4 согласно прозе.")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "P1 4/4")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("1/1" in e for e in hits), hits)

    def test_b_matching_numbers_is_silent(self):
        """(б) handoff `P1 1/1` совпадает с доской `1/1` → диагностик гейта нет."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO",
                               handoff_extra="Доска: P1 1/1 согласно прозе.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "P1 1/1") +
                         [w for w in diag.warnings if "P1 1/1" in w], [])

    def test_c_handoff_older_than_canon_date_is_silent(self):
        """(в) forward-only: handoff датирован < HANDOFF_BOARD_CANON_DATE — даже
        заведомое расхождение `P1 4/4` vs доска `1/1` НЕ диагностируется (И10)."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO", handoff_date="2026-07-27",
                               handoff_extra="Доска: P1 4/4 (заведомо неверно).")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "P1 4/4") +
                         [w for w in diag.warnings if "P1 4/4" in w], [])

    def test_d_phase_missing_from_board_is_dangling_reference(self):
        """(г) `Pn`, отсутствующая в доске (план несёт только `P1`), → диагностика
        «висячая ссылка»."""
        plan_dir = self._write(plan_id="2026.07.28-DEMO",
                               handoff_extra="См. P9 3/5 — фаза не существует в этом плане.")
        _, diag = _lint(plan_dir)
        hits = _errors_containing(diag, "висячая ссылка")
        self.assertTrue(hits, diag.errors)
        self.assertTrue(any("P9" in e for e in hits), hits)

    def test_e_legacy_plan_id_mismatch_is_warning_not_error(self):
        """(д) severity-развилка, как у brief/launch-block-гейта: легаси `plan_id`
        (не датовый) с расхождением → WARNING, а не ERROR."""
        plan_dir = self._write(plan_id="DEMO-1",
                               handoff_extra="Доска: P1 4/4 согласно прозе.")
        _, diag = _lint(plan_dir)
        self.assertEqual(_errors_containing(diag, "P1 4/4"), [])
        self.assertTrue([w for w in diag.warnings if "P1 4/4" in w], diag.warnings)

    def test_f_additivity_plan_without_pattern_gets_no_new_diagnostics(self):
        """(е) АДДИТИВНОСТЬ: датовый план с ГЕЙТОМ АКТИВНЫМ (handoff ≥ канон-даты), но БЕЗ
        шаблона `Pn a/b` в handoff'е, даёт РОВНО тот же набор диагностик, что тот же план с
        гейтом молчащим (handoff < канон-даты) — сравнение МНОЖЕСТВ (D129, план без
        handoff-числа не получает НИ ОДНОЙ новой диагностики)."""
        baseline_dir = self._write(plan_id="2026.07.28-BASE", handoff_date="2026-07-27")
        _, baseline_diag = _lint(baseline_dir)
        baseline = set(baseline_diag.normalized_keys(baseline_dir))

        plan_dir = self._write(plan_id="2026.07.28-DEMO", handoff_date="2026-07-28")
        _, diag = _lint(plan_dir)
        self.assertEqual(set(diag.normalized_keys(plan_dir)), baseline,
                         (diag.errors, diag.warnings))
