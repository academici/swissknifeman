"""Scout (D3): fake runner outcomes, filtering, the 40-line cut, the pack's section 13, start integration, config shape."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import command_catalog  # noqa: E402
from task.plan import cli, context, lifecycle, ops, scout, store  # noqa: E402
from task.plan.model import PlanError  # noqa: E402

OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
DETAIL = {
    "summary": "s", "why": "w", "scope": {"include": ["x"]}, "deliverables": ["d"],
    "task_files": [{"path": "lib/x.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}],
}
ANSWER = "Here is the map:\n- lib/x.py:load — entry point\nlib/y.py — helper\n```\nprint(1)\n```\nUnknowns:\n- where tests live\n"


def completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(["fake"], returncode, stdout, stderr)


class FakeRunner:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.error:
            raise self.error
        return self.result


class ScoutCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()
        self.plan = ops.new_plan("SCT", "Scout", plans_root=self.plans, repository="r", owner="o", authoring=OPUS,
                                 message="m", date="2026.10.07")
        self.root = self.plan.root
        ops.add_phase(self.plan, "One")
        ops.patch(self.plan, "P1", {"goal": "g"})
        ops.add_item(self.plan, "P1", "First")
        ops.patch(self.plan, "P1.1", copy.deepcopy(DETAIL))
        lifecycle.design_done(self.root, "P1", actor=OPUS)
        self.scout_file = self.root / "context" / "P1.1.scout.json"

    def events(self):
        return [e for _, e, _ in store.log_lines(self.root) if e and e.get("type") == "scout"]

    def run_scout(self, runner, provider="claude-code"):
        return scout.run(self.root, "P1.1", provider, runner=runner)


class RunTests(ScoutCase):
    def test_ok_keeps_entries_and_unknowns_and_logs_the_event(self):
        runner = FakeRunner(completed(ANSWER))
        result = self.run_scout(runner)
        self.assertEqual((result.outcome, result.lines, result.model), ("ok", 4, "haiku"))
        self.assertEqual(json.loads(self.scout_file.read_text())["entries"],
                         ["- lib/x.py:load — entry point", "lib/y.py — helper", "Unknowns:", "- where tests live"])
        (event,) = self.events()
        self.assertEqual({k: event["data"][k] for k in ("provider", "model", "outcome", "lines")},
                         {"provider": "claude-code", "model": "haiku", "outcome": "ok", "lines": 4})
        self.assertIn("seconds", event["data"])

    def test_the_prompt_goes_through_stdin_and_the_argv_is_substituted(self):
        runner = FakeRunner(completed(ANSWER))
        self.run_scout(runner)
        argv, kwargs = runner.calls[0]
        self.assertEqual(argv[:6], ["claude", "-p", "--model", "haiku", "--effort", "low"])
        self.assertNotIn("PLAN", " ".join(argv))
        self.assertIn("Never read plan Markdown or views/", kwargs["input"])
        self.assertIn("never edit code", kwargs["input"])
        self.assertIn('"ref": "PLAN1.P1.1"', kwargs["input"])
        self.assertEqual((kwargs["timeout"], kwargs["cwd"], kwargs["text"], kwargs["capture_output"]),
                         (300, self.plan.repo_root, True, True))

    def test_the_prompt_leaves_out_an_earlier_scout_map(self):
        self.scout_file.parent.mkdir()
        self.scout_file.write_text("- old/map.py — stale\n", encoding="utf-8")
        runner = FakeRunner(completed(ANSWER))
        self.run_scout(runner)
        self.assertNotIn("old/map.py", runner.calls[0][1]["input"])

    def test_timeout_is_a_failure_without_a_map(self):
        self.scout_file.parent.mkdir()
        self.scout_file.write_text("- old/map.py — stale\n", encoding="utf-8")
        result = self.run_scout(FakeRunner(error=subprocess.TimeoutExpired("claude", 300)))
        self.assertEqual(result.outcome, "failed")
        self.assertIn("timeout", result.reason)
        self.assertFalse(self.scout_file.exists())
        self.assertEqual(self.events()[0]["data"]["outcome"], "failed")

    def test_non_zero_exit_is_a_failure(self):
        result = self.run_scout(FakeRunner(completed("- a — b\n", returncode=3, stderr="boom\n")))
        self.assertEqual(result.outcome, "failed")
        self.assertIn("exit 3: boom", result.reason)
        self.assertFalse(self.scout_file.exists())

    def test_missing_executable_is_a_failure(self):
        result = self.run_scout(FakeRunner(error=FileNotFoundError("claude")))
        self.assertEqual(result.outcome, "failed")

    def test_empty_or_unusable_output_is_a_failure(self):
        for output in ("", "   \n", "I cannot help with that.\n"):
            with self.subTest(output=output):
                self.assertEqual(self.run_scout(FakeRunner(completed(output))).outcome, "failed")
        self.assertFalse(self.scout_file.exists())

    def test_the_answer_is_cut_to_40_lines(self):
        answer = "".join(f"- lib/f{n}.py — why {n}\n" for n in range(60))
        result = self.run_scout(FakeRunner(completed(answer)))
        self.assertEqual(result.lines, 60)
        self.assertEqual(len(json.loads(self.scout_file.read_text())["entries"]), 60)

    def test_a_provider_without_an_entry_is_skipped(self):
        runner = FakeRunner(completed(ANSWER))
        doc = json.loads(ConfigTests.ROUTING.read_text(encoding="utf-8"))
        doc["orchestration"]["scout"].pop("codex", None)
        routing = self.plans.parent / "routing.json"
        routing.write_text(json.dumps(doc), encoding="utf-8")
        result = scout.run(self.root, "P1.1", "codex", runner=runner, routing_path=routing)
        self.assertEqual(result.outcome, "skipped")
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.events()[0]["data"]["outcome"], "skipped")

    def test_codex_scout_uses_read_only_stdin_without_approvals(self):
        runner = FakeRunner(completed(ANSWER))
        result = self.run_scout(runner, provider="codex")
        self.assertEqual(result.outcome, "ok")
        argv, kwargs = runner.calls[0]
        self.assertEqual(argv[:4], ["codex", "-a", "never", "exec"])
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[argv.index("-c") + 1], 'model_reasoning_effort="low"')
        self.assertEqual(argv[-1], "-")
        self.assertIn("--ephemeral", argv)
        self.assertIn('"ref": "PLAN1.P1.1"', kwargs["input"])
        self.assertNotIn(kwargs["input"], argv)

    def test_an_unreadable_config_is_a_failure_not_an_exception(self):
        bad = Path(tempfile.mkdtemp()) / "routing.json"
        bad.write_text("{", encoding="utf-8")
        result = scout.run(self.root, "P1.1", "claude-code", runner=FakeRunner(completed(ANSWER)), routing_path=bad)
        self.assertEqual(result.outcome, "failed")

    def test_an_unknown_item_is_refused(self):
        with self.assertRaises(PlanError) as caught:
            scout.run(self.root, "P9.9", "claude-code", runner=FakeRunner())
        self.assertEqual(caught.exception.code, "REF_UNKNOWN")


class PackTests(ScoutCase):
    def test_section_13_appears_only_with_a_map(self):
        self.assertNotIn("scout", context.collect(store.load_plan(self.root), "P1.1"))
        self.run_scout(FakeRunner(completed(ANSWER)))
        self.assertIn("- lib/x.py:load — entry point", context.render(store.load_plan(self.root), "P1.1"))


class StartTests(ScoutCase):
    def start(self, **kwargs):
        runner = FakeRunner(completed(ANSWER))
        with mock.patch.object(scout.subprocess, "run", runner):
            return lifecycle.start(self.root, ["P1.1"], OPUS, **kwargs), runner

    def pack(self):
        return (self.root / "context" / "P1.1.json").read_text(encoding="utf-8")

    def test_scout_is_off_by_default(self):
        result, runner = self.start()
        self.assertEqual((runner.calls, result.scouts), ([], ()))
        self.assertNotIn("scout", json.loads(self.pack()))

    def test_the_flag_runs_the_scout_and_rebuilds_the_pack(self):
        result, runner = self.start(scout=True)
        self.assertEqual(len(runner.calls), 1)
        self.assertRegex(result.scouts[0], r"^scout P1\.1: ok \(4 lines, \d+s\)$")
        self.assertIn('"scout"', self.pack())
        self.assertIn(result.scouts[0], result.text("PLAN1"))

    def test_the_plan_setting_enables_it_and_the_flag_overrides_it(self):
        ops.set_plan(self.root, {"settings": {"scout": "auto"}})
        self.assertEqual(len(self.start()[1].calls), 1)
        self.assertEqual(self.start(scout=False)[1].calls, [])

    def test_a_scout_failure_does_not_block_the_start(self):
        with mock.patch.object(scout.subprocess, "run", FakeRunner(error=subprocess.TimeoutExpired("claude", 1))):
            result = lifecycle.start(self.root, ["P1.1"], OPUS, scout=True)
        self.assertIn("failed", result.scouts[0])
        self.assertEqual(store.load_plan(self.root).items["P1.1"]["status"], "in_progress")
        self.assertNotIn("scout", json.loads(self.pack()))

    def test_cli_flags_reach_start(self):
        parser = cli.build_parser()
        self.assertIs(parser.parse_args(["start", "PLAN1", "P1.1", "--actor", "a/b", "--scout"]).scout, True)
        self.assertIs(parser.parse_args(["start", "PLAN1", "P1.1", "--actor", "a/b", "--no-scout"]).scout, False)
        self.assertIsNone(parser.parse_args(["start", "PLAN1", "P1.1", "--actor", "a/b"]).scout)


class ConfigTests(unittest.TestCase):
    ROUTING = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"

    def load(self, change):
        doc = json.loads(self.ROUTING.read_text(encoding="utf-8"))
        change(doc)
        path = Path(tempfile.mkdtemp()) / "routing.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return command_catalog.load_routing_metadata(path)

    def refused(self, change):
        with self.assertRaises(command_catalog.CommandCatalogError) as caught:
            self.load(change)
        self.assertEqual(caught.exception.diagnostic.code, "CMD_ORCHESTRATION_INVALID")

    def test_the_shipped_config_is_valid_and_names_claude_code(self):
        entry = self.load(lambda d: None)["orchestration"]["scout"]["claude-code"]
        self.assertEqual((entry["model"], entry["effort"]), ("haiku", "low"))

    def test_the_section_is_optional(self):
        self.assertNotIn("orchestration", self.load(lambda d: d.pop("orchestration")))

    def test_unknown_keys_providers_and_placeholders_are_errors(self):
        self.refused(lambda d: d["orchestration"].update(extra={}))
        self.refused(lambda d: d["orchestration"]["scout"]["claude-code"].update(extra=1))
        self.refused(lambda d: d["orchestration"]["scout"].update(nobody=d["orchestration"]["scout"]["claude-code"]))
        self.refused(lambda d: d["orchestration"]["scout"]["claude-code"]["argv"].append("{prompt_file}"))

    def test_bad_values_are_errors(self):
        self.refused(lambda d: d["orchestration"]["scout"]["claude-code"].update(timeout_s=0))
        self.refused(lambda d: d["orchestration"]["scout"]["claude-code"].update(effort="max"))
        self.refused(lambda d: d["orchestration"]["scout"]["claude-code"].update(argv=[]))
        self.refused(lambda d: d["orchestration"]["scout"]["claude-code"].update(model=""))


class FilterTests(unittest.TestCase):
    def test_only_entries_and_the_unknowns_block_survive(self):
        self.assertEqual(scout.filter_answer("Sure!\n- a/b.py — x\npkg/m.py:f — y\nnot an entry\nUnknowns:\n- z\nfree text\n"),
                         ["- a/b.py — x", "pkg/m.py:f — y", "Unknowns:", "- z", "free text"])


if __name__ == "__main__":
    unittest.main()
