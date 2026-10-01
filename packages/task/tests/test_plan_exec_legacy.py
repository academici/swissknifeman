"""`task:plan-run` is the single execution command; `plan-exec` is a legacy spelling.

Readers keep accepting the legacy spelling (journals, handoffs, Routing `Exec`, CLI flags);
writers (carriers, templates, generated projections) emit only `plan-run`.
"""
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_LIB = _TESTS.parents[0] / "lib"
for _path in (str(_LIB), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import fixtures  # noqa: E402,F401
from fixtures import write_valid_plan  # noqa: E402
from task import (command_catalog, command_render, journal, plan_lint,  # noqa: E402
                  plan_work, review_policy, task_contract, terminal_admission)
from task.plan_lint_checks.parsing import _resolve_next_form  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPO_ROOT / "packages/task"
LEGACY = "plan-exec"


class LegacyJournalTests(unittest.TestCase):
    def test_legacy_command_is_a_valid_journal_command(self):
        self.assertIn(LEGACY, journal.COMMANDS)
        entry = journal.new_entry(
            plan_id="P", item_id="P1.1", command=LEGACY,
            actor="implementation/medium", result="in-progress")
        journal.validate_entry(entry)
        self.assertEqual(journal.canonical_command(LEGACY), "plan-run")
        self.assertEqual(journal.canonical_command("plan-run"), "plan-run")
        self.assertEqual(journal.canonical_command("plan-close"), "plan-close")

    def test_legacy_journal_file_is_read_authoritatively(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "2026.07.18-DEMO-LEGACY", layout="v2")
            (plan / "journal.jsonl").write_text("", encoding="utf-8")
            journal.append(plan, journal.new_entry(
                plan_id=plan.name, item_id="P1.1", command=LEGACY,
                actor="implementation/medium", result="in-progress",
                session_id="s1", run_id="r1"))
            rows = journal.read_authoritative_entries(plan)
            self.assertEqual([row["command"] for row in rows], [LEGACY])

    def test_legacy_plan_fixture_lints_clean(self):
        source = _TESTS / "data" / "plan-v2"
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "plan-v2"
            shutil.copytree(source, plan_dir)
            text = (plan_dir / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn(f'"command": "{LEGACY}"', text)
            self.assertIn(f"/task:{LEGACY} plan-v2 P1.1",
                          (plan_dir / "handoff.md").read_text(encoding="utf-8"))
            diag = plan_lint.Diagnostics()
            plan_lint.lint_plan(plan_dir, diag)
            # The pinned generated bundle of this fixture is stale by design; no other error.
            self.assertEqual([error for error in diag.errors if "bundle" not in error], [])


class LegacyNextFormTests(unittest.TestCase):
    def test_lint_resolver_reads_legacy_slash_and_semantic_forms_as_run(self):
        for text in (f"/task:{LEGACY} DEMO-1 P1.1",
                     f"exec-items: task:{LEGACY} DEMO-1 P1.1",
                     f"exec-items: task:plan-run DEMO-1 P1.1",
                     f"run-items: task:{LEGACY} DEMO-1 P1.1-P1.2",
                     "run-items: task:plan-run DEMO-1 P1.1"):
            with self.subTest(text=text):
                self.assertEqual(_resolve_next_form(text)[0], "run")

    def test_lint_resolver_still_rejects_a_foreign_command_for_run_kinds(self):
        self.assertEqual(_resolve_next_form("run-items: task:plan-audit DEMO-1 P1")[0],
                         "invalid-semantic")

    def test_next_carrier_parser_normalizes_the_legacy_command(self):
        carrier = command_render.parse_next_carrier(f"exec-items: task:{LEGACY} PLAN P4.5")
        self.assertEqual(carrier.command_id, "task:plan-run")
        self.assertEqual(carrier.kind, "exec-items")
        waiting = command_render.parse_next_carrier(
            f"waiting: gate D1 → exec-items: task:{LEGACY} PLAN P4.4",
            context_kind="continue-root")
        self.assertEqual(waiting.kind, "waiting")

    def test_phase_audit_continuation_regex_accepts_legacy_spelling(self):
        for continuation in (f"exec-items: task:{LEGACY} P P1.1",
                             "run-items: task:plan-run P P1.1"):
            with self.subTest(continuation=continuation):
                entry = journal.new_entry(
                    plan_id="P", item_id="P1", command="plan-audit", actor="m/high",
                    result="audit-attention",
                    decision={"signal_class": "product", "scope_class": "P1.1",
                              "action": "return-owning-continuation", "recovered": False,
                              "terminal": False, "reason_code": "FINDING",
                              "evidence_ids": ["e1"], "continuation": continuation})
                policy = review_policy.phase_audit_terminal_policy(entry)
                self.assertEqual(policy["continuation"], continuation)


class LegacyExecModeTests(unittest.TestCase):
    def test_every_spelling_resolves_to_one_mode(self):
        for value in ("run", "plan-run", LEGACY, "manual"):
            with self.subTest(value=value):
                self.assertEqual(task_contract.resolve_exec(value), "run")
        self.assertEqual(task_contract.resolve_exec("plan-design"), "plan-design")
        for bad in ("plan-rnu", "", "exec"):
            with self.subTest(bad=bad), self.assertRaises(task_contract.TaskContractBuildError):
                task_contract.resolve_exec(bad)

    def test_harness_reader_mirrors_the_spellings(self):
        sys.path.insert(0, str(REPO_ROOT / "packages/harness/lib"))
        try:
            from harness.run import plan_reader
        finally:
            sys.path.pop(0)
        self.assertEqual(
            plan_reader.EXEC_RUN_SPELLINGS,
            {"run", "plan-run", LEGACY, "manual"})


class LegacyCliTests(unittest.TestCase):
    def _run(self, module, argv):
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            try:
                return module.main(argv)
            except SystemExit as exit_:
                return exit_.code

    def test_plan_work_prepare_accepts_the_legacy_command_flag(self):
        accepted = self._run(plan_work, [
            "prepare", "--plan-dir", "/nonexistent-plan", "--item", "P1.1",
            "--command", LEGACY, "--actor", "a"])
        self.assertNotEqual(accepted, 2)  # argparse rejection is exit code 2
        self.assertEqual(self._run(plan_work, [
            "prepare", "--plan-dir", "/nonexistent-plan", "--item", "P1.1",
            "--command", "plan-bogus", "--actor", "a"]), 2)

    def test_plan_work_prepare_records_the_canonical_command(self):
        from task import plan_item_state, plan_status, route_evidence
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "WORK")
            (plan / "journal.jsonl").write_text("")
            plan_item_state.build_states(plan, item_id="P1.1")
            plan_status.build_status(plan)
            core = plan / "plan.md"
            core.write_text(core.read_text().replace("## 3. Routing", (
                "## 3. Routing\n\n"
                "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
                "|:--|:--|:--|:--|:--|:--|\n"
                f"| solo | P1.1 | implementation/medium | {LEGACY} | light | recommended: legacy |\n")))
            actual = route_evidence.capture_actual(
                "implementation", "medium", source="provider-thread-state", model="test")
            actual.update(thread_id="test-session", source_version="test", cwd=tmp,
                          invocation="task:plan-run WORK P1.1")
            plan_work.prepare(plan, "P1.1", command=LEGACY, actor="test/medium",
                              session_id="test-session", actual_route=actual)
            commands = {row["command"] for row in journal.read_authoritative_entries(plan)}
            self.assertEqual(commands, {"plan-run"})

    def test_terminal_admission_accepts_the_legacy_command_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["check", "--state-dir", tmp, "--plan", "P", "--subject", "P1.1",
                    "--command", LEGACY, "--run-id", "r", "--task-session", "s",
                    "--provider", "codex", "--provider-session", "ps", "--turn-id", "t",
                    "--continuity-json", "{}"]
            self.assertNotEqual(self._run(terminal_admission, argv), 2)


class WritersNeverEmitLegacyTests(unittest.TestCase):
    def test_catalog_has_no_legacy_command(self):
        catalog = command_catalog.build_command_catalog(
            PACKAGE / "commands", PACKAGE / "configs/command-routing.json")
        ids = [record.command_id for record in catalog.records]
        self.assertIn("task:plan-run", ids)
        self.assertNotIn(f"task:{LEGACY}", ids)
        self.assertFalse((PACKAGE / "commands" / f"{LEGACY}.md").exists())
        record = catalog.by_id()["task:plan-run"]
        self.assertEqual(record.routing.mode, "inherited-plan")

    def test_generated_provider_projections_never_name_the_legacy_command(self):
        catalog = command_catalog.build_command_catalog(
            PACKAGE / "commands", PACKAGE / "configs/command-routing.json")
        plans = (
            command_render.plan_claude_command_render(
                catalog, command_render.mapping_from_catalog(catalog, "claude-code"),
                plugin_bytes=(PACKAGE / ".claude-plugin/plugin.json").read_bytes()),
            command_render.plan_codex_command_render(
                catalog, command_render.mapping_from_catalog(catalog, "codex")),
            command_render.plan_cursor_command_render(
                catalog, command_render.mapping_from_catalog(catalog, "cursor")),
        )
        for plan in plans:
            self.assertTrue(plan.ok, plan.diagnostics)
            for artifact in plan.artifacts:
                with self.subTest(path=artifact.path):
                    self.assertNotIn(LEGACY, artifact.path)
                    self.assertNotIn(LEGACY.encode(), artifact.managed_bytes)

    def test_committed_adapters_and_runtime_copies_have_no_legacy_command_dirs(self):
        for provider in ("codex", "cursor"):
            legacy_dir = PACKAGE / "adapters" / provider / "skills" / f"task-{LEGACY}"
            self.assertFalse((legacy_dir / "SKILL.md").exists())
            self.assertFalse((legacy_dir / "command.md").exists())
        for source in (REPO_ROOT / "packages/skiller/skills/general/plan-protocol/snippets",
                       PACKAGE / "runtime/plan-protocol/snippets"):
            for path in sorted(source.glob("*.md")):
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if f"task:{LEGACY}" in line:
                        # Only an explicit "legacy ... readable" note may name it.
                        self.assertIn("legacy", line, f"{path.name}:{number}")

    def test_exec_items_kind_renders_the_canonical_command(self):
        catalog = command_catalog.build_command_catalog(
            PACKAGE / "commands", PACKAGE / "configs/command-routing.json")
        mapping = command_render.mapping_from_catalog(catalog, "claude-code")
        carrier = command_render.parse_next_carrier(f"exec-items: task:{LEGACY} PLAN P1.1")
        result = command_render.plan_provider_invocation(
            catalog, carrier, mapping, observed_class="implementation",
            observed_effort="high", inherited_minimum=("implementation", "medium"))
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.invocation, "/task:plan-run PLAN P1.1")

    def test_built_task_contract_carries_only_the_canonical_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "2026.07.18-DEMO-WRITER", layout="v2")
            core = plan / "plan.md"
            core.write_text(core.read_text().replace("## 3. Routing", (
                "## 3. Routing\n\n"
                "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
                "|:--|:--|:--|:--|:--|:--|\n"
                "| solo | P1.1 | implementation/medium | run | light | recommended: demo |\n")))
            contract = task_contract.build(plan, "P1.1")
            payload = json.dumps(contract, ensure_ascii=False)
            self.assertNotIn(LEGACY, payload)
            self.assertEqual(contract["portability"]["semantic_carrier"], "task:plan-run")
            self.assertEqual(contract["next"]["carrier"], f"task:plan-run {plan.name} P1.1")
            self.assertTrue(re.fullmatch(
                rf"/task:plan-run {re.escape(plan.name)} P1\.1",
                contract["portability"]["provider_renderers"]["claude"]))

    def test_execution_sheet_row_uses_the_canonical_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp), "2026.07.18-DEMO-SHEET", layout="v2")
            core = plan / "plan.md"
            core.write_text(core.read_text().replace("## 3. Routing", (
                "## 3. Routing\n\n"
                "| Batch | Items | Model class/effort | Exec | Review | Why |\n"
                "|:--|:--|:--|:--|:--|:--|\n"
                f"| solo | P1.1 | implementation/medium | {LEGACY} | light | legacy cell |\n")))
            routing = task_contract.compile_batch_routing(plan)
            sheet = plan_work._execution_sheet(plan, routing, strict=False)
            self.assertTrue(sheet["rows"])
            for row in sheet["rows"]:
                self.assertEqual(row["command"], f"task:plan-run {plan.name} P1.1")


if __name__ == "__main__":
    unittest.main()
