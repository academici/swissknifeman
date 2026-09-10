"""D2/P3 gate tests for the sole executable layout."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import journal, plan_bundle, plan_gates, plan_item_state, plan_lint, plan_status, plan_weight


DATA = Path(__file__).resolve().parent / "data"


def lint(plan_dir):
    diag = plan_lint.Diagnostics()
    plan_lint.lint_plan(plan_dir, diag)
    return diag


class TestReadBudgetGate(unittest.TestCase):
    def copied_fixture(self, name):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / name
        shutil.copytree(DATA / name, target)
        return target

    def test_retired_layout_is_rejected_before_execution_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = write_valid_plan(Path(tmp), layout=None)
            diag = lint(plan_dir)
        self.assertTrue(any("PLAN_LAYOUT_V1_RETIRED" in row for row in diag.errors), diag.errors)

    def test_v2_phase_candidate_fingerprint_tracks_plan_and_repo_relative_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            plan_dir = write_valid_plan(root, layout="v2")
            spec = plan_dir / "phases" / "P1" / "P1.1.md"
            spec.write_text(
                spec.read_text(encoding="utf-8").replace(
                    "**Files:** lib/pkg/config.py",
                    "**Files:** `artifacts/result.txt` · `packages/task/result.txt`",
                ),
                encoding="utf-8",
            )
            plan_product = plan_dir / "artifacts" / "result.txt"
            repo_product = root / "packages" / "task" / "result.txt"
            plan_product.parent.mkdir(parents=True)
            repo_product.parent.mkdir(parents=True)
            plan_product.write_text("plan-v1\n", encoding="utf-8")
            repo_product.write_text("repo-v1\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "plans/DEMO-1/artifacts/result.txt", "packages/task/result.txt"],
                cwd=root, check=True,
            )

            before = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            rows = {row["declared"]: row for row in before["snapshot"]["product_files"]}
            self.assertEqual(rows["artifacts/result.txt"]["state"], "file")
            self.assertEqual(
                rows["artifacts/result.txt"]["path"],
                "plans/DEMO-1/artifacts/result.txt",
            )
            self.assertEqual(rows["packages/task/result.txt"]["state"], "file")
            self.assertEqual(rows["packages/task/result.txt"]["path"], "packages/task/result.txt")

            plan_product.write_text("plan-v2\n", encoding="utf-8")
            after_plan_change = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            self.assertNotEqual(after_plan_change["fingerprint"], before["fingerprint"])

            repo_product.write_text("repo-v2\n", encoding="utf-8")
            after_repo_change = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            self.assertNotEqual(after_repo_change["fingerprint"], after_plan_change["fingerprint"])

    def test_product_tree_uses_tracked_exact_directory_glob_and_brace_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            plan_dir = root / "plans" / "DEMO-1"
            plan_dir.mkdir(parents=True)
            tracked = {
                "products/exact.txt": "exact-v1\n",
                "products/tree/root.txt": "root-v1\n",
                "products/tree/nested/leaf.txt": "leaf-v1\n",
                "products/brace/left.txt": "left-v1\n",
                "products/brace/right.txt": "right-v1\n",
                "plans/DEMO-1/artifacts/result.txt": "plan-v1\n",
            }
            for relative, content in tracked.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (root / "products" / "link.txt").symlink_to("exact.txt")
            subprocess.run(["git", "add", "products", "plans/DEMO-1/artifacts/result.txt"],
                           cwd=root, check=True)

            declared = {
                "products/exact.txt",
                "products/tree",
                "products/tree/**",
                "products/brace/{left,right}.txt",
                "products/link.txt",
                "artifacts/result.txt",
            }
            before_digest, before_rows = plan_gates._product_tree(plan_dir, declared)
            rows = {row["declared"]: row for row in before_rows}
            self.assertEqual(rows["products/exact.txt"]["state"], "file")
            self.assertEqual(rows["products/link.txt"]["state"], "symlink")
            self.assertEqual(rows["artifacts/result.txt"]["path"],
                             "plans/DEMO-1/artifacts/result.txt")
            directory_members = rows["products/tree"]["members"]
            self.assertEqual(directory_members, rows["products/tree/**"]["members"])
            self.assertEqual(
                [member["path"] for member in rows["products/brace/{left,right}.txt"]["members"]],
                ["products/brace/left.txt", "products/brace/right.txt"],
            )

            ignored = root / "products" / "tree" / "__pycache__" / "cache.pyc"
            ignored.parent.mkdir(parents=True)
            ignored.write_bytes(b"ignored")
            (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
            (root / "products" / "tree" / "untracked.txt").write_text(
                "untracked\n", encoding="utf-8")
            stable_digest, _rows = plan_gates._product_tree(plan_dir, declared)
            self.assertEqual(stable_digest, before_digest)

            (root / "products" / "tree" / "root.txt").write_text("root-v2\n", encoding="utf-8")
            edited_digest, _rows = plan_gates._product_tree(plan_dir, declared)
            self.assertNotEqual(edited_digest, before_digest)

            (root / "products" / "exact.txt").unlink()
            deleted_digest, deleted_rows = plan_gates._product_tree(plan_dir, declared)
            self.assertNotEqual(deleted_digest, edited_digest)
            deleted = {row["declared"]: row for row in deleted_rows}["products/exact.txt"]
            self.assertEqual(deleted["state"], "deleted")

    def test_product_tree_rejects_escaping_and_invalid_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            plan_dir = root / "plans" / "DEMO-1"
            plan_dir.mkdir(parents=True)
            invalid = (
                "../escape.txt", "/absolute.txt", "~/home.txt", "bad\\path.txt",
                "bad/{left,right.txt", "bad/{left,{middle,right}}.txt", "bad/[abc.txt",
                "bad/{" + ",".join(str(number) for number in range(65)) + "}.txt",
            )
            for declared in invalid:
                with self.subTest(declared=declared):
                    with self.assertRaises(ValueError):
                        plan_gates._product_tree(plan_dir, {declared})

    def test_audit_fixer_rebind_distinguishes_product_change_from_bookkeeping(self):
        before = {
            "fingerprint": "",
            "snapshot": {"phase_id": "P1", "scope": [], "terminal_item_heads": [],
                         "material_risks": [], "declared_files": [], "product_tree_sha256": "a" * 64},
        }
        before["fingerprint"] = plan_gates._candidate_snapshot_fingerprint(before["snapshot"])
        bookkeeping = {"fingerprint": before["fingerprint"], "snapshot": copy.deepcopy(before["snapshot"])}
        self.assertEqual(plan_gates.audit_fixer_rebind(before, bookkeeping)["reason"], "audit-bookkeeping-only")
        repaired = {"fingerprint": "", "snapshot": copy.deepcopy(before["snapshot"])}
        repaired["snapshot"]["product_tree_sha256"] = "b" * 64
        repaired["fingerprint"] = plan_gates._candidate_snapshot_fingerprint(repaired["snapshot"])
        rebound = plan_gates.audit_fixer_rebind(before, repaired)
        self.assertTrue(rebound["rebound"])
        self.assertEqual(rebound["reason"], "product-or-terminal-evidence-changed")

    def test_phase_candidate_ignores_generated_state_bookkeeping_but_tracks_terminal_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            plan_dir = write_valid_plan(root, layout="v2")
            before = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            state = plan_dir / "phases" / "P1" / "P1.1.state.md"
            state.write_text(state.read_text(encoding="utf-8") + "\nbookkeeping\n", encoding="utf-8")
            after_bookkeeping = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            self.assertEqual(after_bookkeeping["fingerprint"], before["fingerprint"])

            journal_path = plan_dir / "journal.jsonl"
            event = json.loads(journal_path.read_text(encoding="utf-8"))
            event["note"] = "material deviation changed"
            journal_path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
            after_material = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            self.assertNotEqual(after_material["fingerprint"], before["fingerprint"])

    def test_overweight_v2_item_names_item_weight_threshold_and_unit(self):
        diag = lint(self.copied_fixture("plan-v2-overweight"))
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(rows, diag.errors)
        self.assertTrue(any("P1.1" in row and "порога 100" in row
                            and "gpt-5.6-terra" in row for row in rows), rows)

    def test_rebuilt_item_passes_with_frozen_production_threshold(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_dir = write_valid_plan(Path(tmp.name), layout="v2")
        journal.append(plan_dir, journal.new_entry(
            plan_id=plan_dir.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="in-progress",
        ))
        plan_item_state.build_states(plan_dir)
        plan_status.build_status(plan_dir)
        contract = plan_dir / "root" / "contracts" / "read-budget-v1.md"
        contract.write_text(contract.read_text(encoding="utf-8").replace(
            "<= 100000", "<= 100"), encoding="utf-8")
        self.assertTrue(any(plan_gates.GATE_ID in row for row in lint(plan_dir).errors))
        contract.write_text(contract.read_text(encoding="utf-8").replace(
            "<= 100", "<= 100000"), encoding="utf-8")
        diag = lint(plan_dir)
        self.assertFalse(any(plan_gates.GATE_ID in row for row in diag.errors), diag.errors)

    def test_oversized_file_names_file_and_both_limits(self):
        plan_dir = self.copied_fixture("plan-v2")
        large = plan_dir / "brief" / "00-brief.md"
        large.write_text("x" * 300000, encoding="utf-8")
        plan_bundle.build(plan_dir, "P1.1")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(any("brief/00-brief.md" in row and "262144 байт" in row
                            and "25000 токенов" in row for row in rows), rows)

    def test_missing_contract_fails_closed(self):
        plan_dir = self.copied_fixture("plan-v2")
        (plan_dir / "root" / "contracts" / "read-budget-v1.md").unlink()
        diag = lint(plan_dir)
        self.assertTrue(any("контракт порога" in row for row in diag.errors), diag.errors)

    def test_archived_plan_skips_execution_only_read_budget_gate(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_dir = Path(tmp.name) / "plans" / "archive" / "plan-v2"
        plan_dir.parent.mkdir(parents=True)
        shutil.copytree(DATA / "plan-v2", plan_dir)
        (plan_dir / "root" / "contracts" / "read-budget-v1.md").unlink()
        diag = lint(plan_dir)
        self.assertFalse(any(plan_gates.GATE_ID in row for row in diag.errors), diag.errors)

    def test_archived_plan_skips_execution_only_return_loop_gates(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_dir = Path(tmp.name) / "plans" / "archive" / "plan-v2"
        plan_dir.parent.mkdir(parents=True)
        shutil.copytree(DATA / "plan-v2", plan_dir)
        diag = lint(plan_dir)
        with unittest.mock.patch.object(plan_gates, "_lint_return_escalation_qualification") as qualification, \
                unittest.mock.patch.object(plan_gates, "_lint_return_owner_authorization") as authorization, \
                unittest.mock.patch.object(plan_gates, "_lint_terminal_phase_unresolved_decisions") as unresolved:
            plan_gates.lint_return_loop(plan_dir, "v2", diag)
        qualification.assert_not_called()
        authorization.assert_not_called()
        unresolved.assert_not_called()

    def test_missing_calibration_and_limit_are_errors(self):
        plan_dir = self.copied_fixture("plan-v2")
        for message in ("артефакт калибровки не читается", "артефакт лимита чтения не читается"):
            with self.subTest(message=message), unittest.mock.patch.object(
                    plan_gates.plan_weight, "Measurer",
                    side_effect=plan_weight.PlanWeightError(message)):
                diag = lint(plan_dir)
            self.assertTrue(any(message in row for row in diag.errors), diag.errors)

    def test_clean_v2_bundle_and_views_are_fresh(self):
        diag = lint(self.copied_fixture("plan-v2"))
        self.assertFalse(any(plan_gates.BUNDLE_GATE_ID in row for row in diag.errors), diag.errors)

    def test_unresolvable_next_bundle_requires_local_repair_not_design(self):
        plan_dir = self.copied_fixture("plan-v2")
        spec = plan_dir / "phases" / "P1" / "P1.1.md"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("brief/00-brief.md", "missing.md"),
            encoding="utf-8",
        )

        diag = lint(plan_dir)

        message = next(row for row in diag.errors if "unresolvable_entry" in row)
        self.assertIn("локальный обратимый носитель", message)
        self.assertNotIn("исправь ТЗ через task:plan-design", message)

    def test_terminal_bundle_keeps_schema_checks_without_live_source_resolution(self):
        plan_dir = self.copied_fixture("plan-v2")
        target = plan_dir / "bundles" / "P0.1.json"
        bundle = json.loads(target.read_text(encoding="utf-8"))
        bundle["entries"][0]["path"] = "retired/source.md"
        target.write_text(plan_bundle.canonical_json(bundle), encoding="utf-8")

        diag = lint(plan_dir)
        self.assertFalse(any("P0.1" in row and "unresolvable_entry" in row
                             for row in diag.errors), diag.errors)

        bundle["unexpected"] = True
        target.write_text(plan_bundle.canonical_json(bundle), encoding="utf-8")
        diag = lint(plan_dir)
        self.assertTrue(any("P0.1" in row and "terminal evidence schema invalid" in row
                            for row in diag.errors), diag.errors)

    def test_missing_bundle_for_pending_producer_is_not_required(self):
        plan_dir = self.copied_fixture("plan-v2")
        producer = plan_dir / "phases" / "P1" / "P1.1.md"
        producer.write_text(producer.read_text(encoding="utf-8").replace(
            "**Deliverables:** валидация + тест.",
            "**Deliverables:** `artifacts/future.json`."), encoding="utf-8")
        (plan_dir / "phases" / "P1" / "P1.2.md").write_text(
            "### P1.2 — Потребить будущий артефакт\n\n"
            "**Intent:** Проверить admission до материализации bundle.\n"
            "**Why:** Будущий producer output ещё не существует.\n"
            "**Scope Included:** stage-aware admission.\n"
            "**Scope Excluded:** создание артефакта.\n"
            "**Inputs:** `brief/00-brief.md`\n"
            "**Files:** packages/task/lib/task/plan_weight.py\n"
            "**Required Reads:** 1) `artifacts/future.json` (producer: P1.1)\n"
            "**Implementation Rules:** Не ослаблять ready-гейт.\n"
            "**Code Guidance:** Использовать declared producer edge.\n"
            "**Validation:** admission_state == pending-producer.\n"
            "**Deliverables:** проверенный consumer.\n",
            encoding="utf-8",
        )
        plan_item_state.build_states(plan_dir)
        plan_status.build_status(plan_dir)

        measured = plan_weight.measure_plan(plan_dir, plan_weight.Measurer(), only_item="P1.2")
        consumer = measured["items"][0]
        self.assertEqual(consumer["admission_state"], "pending-producer")
        self.assertEqual(consumer["producer_item"], "P1.1")

        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.BUNDLE_GATE_ID in row]
        self.assertFalse(any("P1.2" in row for row in rows), rows)

    def test_missing_bundle_with_unannotated_missing_read_stays_fail_closed(self):
        plan_dir = self.copied_fixture("plan-v2")
        (plan_dir / "phases" / "P1" / "P1.2.md").write_text(
            "### P1.2 — Потребить отсутствующий вход\n\n"
            "**Intent:** Проверить fail-closed admission.\n"
            "**Why:** Неаннотированный вход не является producer edge.\n"
            "**Scope Included:** stage-aware admission.\n"
            "**Scope Excluded:** создание входа.\n"
            "**Inputs:** `brief/00-brief.md`\n"
            "**Files:** packages/task/lib/task/plan_weight.py\n"
            "**Required Reads:** 1) `artifacts/missing.json`\n"
            "**Implementation Rules:** Не выводить pending без producer.\n"
            "**Code Guidance:** Сохранить fail-closed поведение.\n"
            "**Validation:** admission_state == ready, admission_pass == false.\n"
            "**Deliverables:** проверенный consumer.\n",
            encoding="utf-8",
        )
        plan_item_state.build_states(plan_dir)
        plan_status.build_status(plan_dir)

        measured = plan_weight.measure_plan(plan_dir, plan_weight.Measurer(), only_item="P1.2")
        consumer = measured["items"][0]
        self.assertEqual(consumer["admission_state"], "ready")
        self.assertFalse(consumer["admission_pass"])

        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.GATE_ID in row]
        self.assertTrue(any("P1.2" in row and "D2(b)" in row for row in rows), rows)

    def test_future_phase_is_outside_bundle_materialization_scope(self):
        plan_dir = self.copied_fixture("plan-v2")
        (plan_dir / "bundles" / "P1.1.json").unlink()
        status = plan_dir / "status.md"
        status.write_text(status.read_text(encoding="utf-8").replace(
            "| P1 | Фаза раз | 0/1 | 🟡 In progress |",
            "| P1 | Фаза раз | 0/1 | ⬜ Not started |"), encoding="utf-8")
        diag = lint(plan_dir)
        self.assertFalse(any("P1.1: missing_entry" in row for row in diag.errors), diag.errors)

    def test_stale_fixture_checks_only_the_next_runnable_bundle(self):
        diag = lint(self.copied_fixture("plan-v2-stale"))
        messages = "\n".join((*diag.errors, *diag.warnings))
        self.assertIn("следующего запускаемого item P1.1 устарел", messages)
        self.assertNotIn("P1.5: extraneous_entry", messages)

    def test_unilateral_decision_link_does_not_reopen_future_bundle_scope(self):
        plan_dir = self.copied_fixture("plan-v2")
        old = plan_dir / "decisions" / "D1-fixture.md"
        old.write_text(old.read_text(encoding="utf-8").replace(
            "status: accepted\n", "status: superseded\n").replace(
            "superseded_by: null\n", "superseded_by: D2\n"), encoding="utf-8")
        (plan_dir / "decisions" / "D2-fixture.md").write_text(
            "---\nid: D2\ndate: 2026-07-03\nstatus: accepted\nitem: P1.1\n"
            "items: [P1.1]\nsupersedes: []\nsuperseded_by: null\n---\n"
            "## Решение\n\nFixture.\n\n## Почему\n\nFixture.\n", encoding="utf-8")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.BUNDLE_GATE_ID in row]
        self.assertFalse(any("D1" in row and "D2" in row for row in rows), rows)

    def test_path_order_and_history_boundary_use_declared_registry(self):
        plan_dir = self.copied_fixture("plan-v2")
        spec = copy.deepcopy(plan_gates.plan_layout.read_path_spec())
        registry = copy.deepcopy(plan_gates.plan_layout.registry())
        executor = spec["paths"]["executor"]["slots"]
        executor[0]["carrier_id"] = "item-state"
        executor[-1]["carrier_id"] = "plan-core"
        executor[2]["carrier_id"] = "history-view"
        with unittest.mock.patch.object(plan_gates.plan_layout, "read_path_spec", return_value=spec), \
                unittest.mock.patch.object(plan_gates.plan_layout, "registry", return_value=registry):
            diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.PATH_GATE_ID in row]
        self.assertTrue(any("монотонный предикат порядка" in row for row in rows), rows)
        self.assertTrue(any("history" in row and "executor" in row for row in rows), rows)

    def test_terminal_item_input_is_rejected_but_sibling_is_not_a_rule(self):
        plan_dir = self.copied_fixture("plan-v2")
        spec = plan_dir / "phases" / "P1" / "P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "`brief/00-brief.md`", "`phases/P0/P0.1.md`", 1), encoding="utf-8")
        diag = lint(plan_dir)
        rows = [row for row in diag.errors if plan_gates.PATH_GATE_ID in row]
        self.assertTrue(any("терминальной фазы" in row and "P1.1" in row for row in rows), rows)


if __name__ == "__main__":
    unittest.main()
