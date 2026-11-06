"""Caller context reaches a blocked retry without rewriting its input, session task or spent budgets."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from orch.conductor import prompts, records
from orch.conductor.infrastructure import operator_context
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import safe
from tests.test_conductor import GREEN
from tests.test_conductor_input import EXECUTOR, InputCase


BLOCKED = {"result": {"status": "blocked", "summary": "network setup needs owner repair", "changed_paths": [],
    "checks_run": [], "evidence": [], "open_issues": [{"kind": "escalation", "escalation_class": "environment",
    "text": "Docker address pools exhausted", "impact": "checks cannot start", "next": "owner repairs tooling"}]}}
NOTE = "Tooling repaired in commit bfa3d3bee. Verify tools/bin/suite; use its normal command.\n"


class OperatorContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "operator.md"
        self.source.write_text(NOTE)
        self.state = {}
        self.owner = SimpleNamespace(directory=self.directory, progress=SimpleNamespace(emit=lambda *a, **k: None))
        self.item = Item("W1", "workrun", self.state, self.directory / "W1", {})

    def record(self):
        operator_context.record(self.owner, "W1", self.state, "executor.1", operator_context.read_note(self.source))

    def test_snapshot_has_typed_provenance_and_does_not_follow_later_source_edits(self):
        self.record()
        self.source.write_text("later operator text")
        context = operator_context.current(self.owner, self.item, "executor.1")
        self.assertEqual(context["text"], NOTE)
        self.assertEqual(context["sha256"], sha256(NOTE.encode()).hexdigest())
        self.assertEqual(context["source"], str(self.source.resolve()))
        self.assertEqual(context["file"], "W1/operator-context/1.md")
        self.assertIsNone(operator_context.current(self.owner, self.item, "executor.2"))
        records.write(self.directory / "state.json", {"status": "stopped", "items": {"W1": self.state}}, "state")

    def test_note_changes_no_task_block_or_digest_in_full_or_resumed_prompt(self):
        self.record()
        context = operator_context.current(self.owner, self.item, "executor.1")
        base = [prompts.Block("input", "input.json", "canonical task\n\n"),
                prompts.Block("result_contract", "conductor", "unchanged result\n")]
        augmented = prompts.with_operator_context(base, context)
        self.assertEqual(prompts.task_digest(base), prompts.task_digest(augmented))
        self.assertEqual([b for b in augmented if b.kind != "operator_context"], base)
        resumed = prompts.with_operator_context(prompts.executor_resumed(item="W1", step="executor.1"), context)
        for blocks in (augmented, resumed):
            text = prompts.render(blocks)
            self.assertIn(NOTE.strip(), text)
            self.assertIn("Verify its claims", text)
            self.assertIn("only new checks", text)
            block = next(b for b in blocks if b.kind == "operator_context")
            self.assertEqual(block.origin, "invocation:resume --note-file:" + str(self.source.resolve()))

    def test_invalid_notes_fail_before_snapshotting(self):
        for raw in (b"", b" \n", b"bad\0text", b"\xff", b"a" * 65537):
            with self.subTest(raw=raw[:12]):
                self.source.write_bytes(raw)
                with self.assertRaises(Stop):
                    operator_context.read_note(self.source)
                self.assertEqual(self.state, {})

    def test_changed_snapshot_is_refused(self):
        self.record()
        (self.directory / "W1/operator-context/1.md").write_text("tampered")
        with self.assertRaises(Stop) as caught:
            operator_context.current(self.owner, self.item, "executor.1")
        self.assertEqual(caught.exception.code, "OPERATOR_CONTEXT_CHANGED")

    def test_repeated_identical_context_is_idempotent(self):
        self.record()
        before = json.dumps(self.state, sort_keys=True)
        self.record()
        self.assertEqual(json.dumps(self.state, sort_keys=True), before)

    def test_escaping_snapshot_directory_is_refused(self):
        self.item.directory.mkdir()
        (self.item.directory / "operator-context").symlink_to(self.directory)
        with self.assertRaises(Stop):
            self.record()
        self.assertFalse((self.directory / "1.md").exists())


class OperatorContextLifecycleTests(InputCase):
    def blocked(self, *, lost=False, again=False):
        path = self.write_input()
        self.options_path = self.project.parent / "options.json"
        self.options_path.write_text(json.dumps({"session": {"executor": "handoff"}, "limits": {"retries": 2}}))
        # Spend one real automatic retry before blocking; the explicit retry must not refill it.
        answers = [{"exit": 3}, BLOCKED]
        if lost:
            answers.append({"exit": 3})
        answers.append(BLOCKED if again else EXECUTOR)
        self.script({"executor": answers, "reviewer": [GREEN]})
        code, _, error = self.run_input(path, "--options", self.options_path)
        self.assertEqual((code, self.outcome(error)), (1, ("stopped", "ITEM_BLOCKED")), error)
        self.directory = self.run_dir(error)
        self.ref = self.input_doc["input_id"]
        self.piece = self.directory / safe(self.ref)
        self.note = self.project.parent / "operator.md"
        self.note.write_text(NOTE)
        return path, error

    def retry(self):
        return self.conduct("resume", "--run", self.directory.name, "--retry", self.ref,
                            "--note-file", self.note, "--json-lines")

    def test_same_run_retry_preserves_input_history_budget_and_resumes_session_with_context(self):
        path, error = self.blocked()
        before = self.state(error)
        original_input = path.read_bytes()
        input_snapshot = (self.piece / "input.json").read_bytes()
        option_snapshot = (self.piece / "options.json").read_bytes()
        old_report = (self.piece / "reports/executor.1.json").read_bytes()
        old_requests = {p: p.read_bytes() for p in self.piece.glob("agents/*/request.json")}
        code, _, error = self.retry()
        self.assertEqual((code, self.outcome(error)), (0, ("finished", None)), error)
        after = self.state(error)
        item = after["items"][self.ref]
        self.assertEqual(item["retries_used"], before["items"][self.ref]["retries_used"])
        self.assertEqual(item["retries_used"], 1)
        self.assertEqual(item["retries_by_stage"], before["items"][self.ref]["retries_by_stage"])
        self.assertEqual(path.read_bytes(), original_input)
        self.assertEqual((self.piece / "input.json").read_bytes(), input_snapshot)
        self.assertEqual((self.piece / "options.json").read_bytes(), option_snapshot)
        self.assertEqual((self.piece / "attempts/1/reports/executor.1.json").read_bytes(), old_report)
        for request, raw in old_requests.items():
            self.assertEqual(request.read_bytes(), raw)
        argv = json.loads((self.fake / "executor-3.argv").read_text())
        self.assertIn("--resume", argv)
        self.assertIn(NOTE.strip(), self.prompt("executor", 3))
        self.assertIn("## Continuation", self.prompt("executor", 3))
        manifest = json.loads((self.piece / "prompts/executor.1.manifest.json").read_text())
        self.assertTrue(manifest["resumed_session"])
        self.assertTrue(any(b["kind"] == "operator_context" and b["origin"].startswith("invocation:") for b in manifest["blocks"]))
        self.assertTrue(any(k.startswith("checks.") for k in item["steps"]))
        self.assertEqual(len(item["operator_context"]), 1)
        self.assertEqual(after["resumes"], 1)
        self.assertGreater(after["tokens"]["input"], before["tokens"]["input"])

    def test_lost_provider_session_gets_same_context_in_full_fallback_without_budget_reset(self):
        path, error = self.blocked(lost=True)
        before = path.read_bytes()
        code, _, error = self.retry()
        self.assertEqual((code, self.outcome(error)), (0, ("finished", None)), error)
        self.assertEqual(self.calls("executor"), 4)
        self.assertIn("SESSION_RESUME_FAILED", error)
        self.assertIn("--resume", json.loads((self.fake / "executor-3.argv").read_text()))
        self.assertNotIn("--resume", json.loads((self.fake / "executor-4.argv").read_text()))
        for number in (3, 4):
            self.assertIn(NOTE.strip(), self.prompt("executor", number))
        self.assertIn("# Executor", self.prompt("executor", 4))
        self.assertEqual(path.read_bytes(), before)
        self.assertGreaterEqual(self.state(error)["items"][self.ref]["retries_used"], 1)

    def test_invalid_cli_context_leaves_state_input_and_launch_count_unchanged(self):
        path, error = self.blocked()
        before = (self.directory / "state.json").read_bytes(), path.read_bytes(), self.calls("executor")
        for raw in (b"", b"\xff", b"a" * 65537):
            self.note.write_bytes(raw)
            code, _, error = self.retry()
            self.assertEqual(code, 1, error)
            self.assertIn("OPERATOR_CONTEXT_INVALID", error)
            self.assertEqual(((self.directory / "state.json").read_bytes(), path.read_bytes(), self.calls("executor")), before)
        self.note.write_text(NOTE)
        code, _, error = self.conduct("resume", "--run", self.directory.name, "--note-file", self.note)
        self.assertEqual(code, 1, error)
        self.assertIn("requires exactly one --retry", error)
        self.assertEqual((self.directory / "state.json").read_bytes(), before[0])
        code, _, error = self.conduct("resume", "--run", self.directory.name, "--retry", self.ref,
                                      "--note-file", self.note, "--raise-limit", "tokens_hard_max=0")
        self.assertEqual(code, 1, error)
        self.assertIn("OPTIONS_INVALID", error)
        self.assertEqual((self.directory / "state.json").read_bytes(), before[0])

    def test_tampered_snapshot_stops_next_retry_before_executor_launch(self):
        _, error = self.blocked(again=True)
        code, _, error = self.retry()
        self.assertEqual(code, 1, error)
        note = self.state(error)["items"][self.ref]["operator_context"][0]
        (self.directory / note["file"]).write_text("tampered")
        count = self.calls("executor")
        code, _, error = self.conduct("resume", "--run", self.directory.name, "--retry", self.ref, "--json-lines")
        self.assertEqual(code, 1, error)
        self.assertIn("OPERATOR_CONTEXT_CHANGED", error)
        self.assertEqual(self.calls("executor"), count)
