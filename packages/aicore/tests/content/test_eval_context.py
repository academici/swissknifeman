"""aicore.content.eval: the eval-context/v1 result context, observed values only, on a fake `claude`."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from aicore.content import eval as ev
from aicore.content.skill import skill_digest
from aicore.util import schema
from aicore.util.digest import digest_json

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "eval-context" / "v1"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_fake_claude(directory, *, models=("claude-sonnet-5-5",), version="9.9.9 (Claude Code)"):
    """Executable stub: `--version` prints `version`; any other call prints the JSON of `claude -p`."""
    usage = {name: {"inputTokens": 1} for name in models} if models is not None else None
    payload = {"result": "ok output", "usage": {"input_tokens": 10, "output_tokens": 5}}
    if usage is not None:
        payload["modelUsage"] = usage
    script = Path(directory) / "fake_claude.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "if '--version' in sys.argv:\n"
        f"    print({version!r})\n"
        "else:\n"
        f"    print(json.dumps({payload!r}))\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


def make_skill(root, body="Body of the skill.\n"):
    directory = Path(root) / "skills" / "quality" / "demo"
    write(directory / "SKILL.md", f"---\nname: demo\ndescription: A demo skill.\n---\n{body}")
    write(directory / "evals" / "evals.json", json.dumps({"skill": "demo", "cases": [
        {"id": 1, "prompt": "say ok", "assertions": [{"type": "contains", "value": "ok"}]}]}))
    return directory


def valid_context():
    return {
        "schema": "eval-context/v1",
        "skill": {"id": "x/y", "digest": "sha256:" + "0" * 64},
        "fixtures": {"id": "evals", "version": None, "digest": "sha256:" + "1" * 64},
        "grader": {"id": "skill-eval", "version": "1"},
        "runner": {"provider": "claude-code", "cli_version": None, "models": []},
    }


def validate(doc):
    registry, kind = schema.load_contract(CONTRACT)
    return schema.validate(doc, kind, registry)


class SkillContextCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.skill_dir = make_skill(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def observe(self, claude):
        """Run the case through the fake binary; → the runner block built from what it reported."""
        runs = ev.run_suite(self.skill_dir, [{"id": 1, "prompt": "say ok"}], with_skill=True, claude=claude)
        return ev.runner_context(claude, [m for run in runs for m in run["models"]])

    def test_context_names_the_skill_the_models_and_the_cli(self):
        claude = write_fake_claude(self.tmp)
        context = ev.skill_eval_context(self.skill_dir, "quality/demo", self.observe(claude))
        self.assertEqual(validate(context), [])
        self.assertEqual(context["skill"], {"id": "quality/demo", "digest": skill_digest(self.skill_dir)})
        self.assertEqual(context["runner"], {"provider": "claude-code", "cli_version": "9.9.9",
                                             "models": ["claude-sonnet-5-5"]})
        self.assertEqual(context["grader"], {"id": "skill-eval", "version": ev.GRADER_VERSION})
        fixtures = {"evals": json.loads((self.skill_dir / "evals" / "evals.json").read_text()),
                    "pressure": None}
        self.assertEqual(context["fixtures"], {"id": "evals", "version": None, "digest": digest_json(fixtures)})

    def test_changed_skill_is_named_by_the_comparison(self):
        claude = write_fake_claude(self.tmp)
        runner = self.observe(claude)
        before = ev.skill_eval_context(self.skill_dir, "quality/demo", runner)
        write(self.skill_dir / "SKILL.md", "---\nname: demo\ndescription: A demo skill.\n---\nChanged body.\n")
        after = ev.skill_eval_context(self.skill_dir, "quality/demo", runner)
        self.assertEqual(ev.compare_eval_context(before, before), [])
        self.assertEqual(ev.compare_eval_context(before, after), ["skill.digest"])

    def test_changed_fixtures_are_named_by_the_comparison(self):
        runner = self.observe(write_fake_claude(self.tmp))
        before = ev.skill_eval_context(self.skill_dir, "quality/demo", runner)
        write(self.skill_dir / "evals" / "pressure.json", json.dumps({"skill": "demo", "scenarios": []}))
        after = ev.skill_eval_context(self.skill_dir, "quality/demo", runner)
        self.assertEqual(ev.compare_eval_context(before, after), ["fixtures.digest"])

    def test_models_are_the_union_of_the_runs(self):
        runner = ev.runner_context(None, ["b-model", "a-model", "b-model"])
        self.assertEqual(runner["models"], ["a-model", "b-model"])

    def test_nothing_is_invented_when_the_binary_reports_nothing(self):
        claude = write_fake_claude(self.tmp, models=None, version="not a version")
        runner = self.observe(claude)
        self.assertEqual(runner, {"provider": "claude-code", "cli_version": None, "models": []})
        self.assertEqual(validate(ev.skill_eval_context(self.skill_dir, "quality/demo", runner)), [])

    def test_missing_binary_and_failing_probe_give_null(self):
        self.assertIsNone(ev.runner_context(None, [])["cli_version"])
        failing = Path(self.tmp) / "failing.sh"
        write(failing, "#!/bin/sh\necho 1.2.3\nexit 3\n")
        failing.chmod(0o755)
        self.assertIsNone(ev.runner_context(str(failing), [])["cli_version"])
        self.assertIsNone(ev.runner_context(str(self.tmp / "absent"), [])["cli_version"])

    def test_version_probe_takes_the_first_word_of_the_first_line(self):
        claude = write_fake_claude(self.tmp, version="2.1.294 (Claude Code)")
        self.assertEqual(ev.runner_context(claude, [])["cli_version"], "2.1.294")

    def test_run_records_the_models_it_observed(self):
        claude = write_fake_claude(self.tmp, models=("m-1", "m-2"))
        run = ev.run_case(self.skill_dir, {"id": 1, "prompt": "p"}, with_skill=False,
                          workspace=self.tmp / "ws", claude=claude)
        self.assertEqual(run["models"], ["m-1", "m-2"])
        self.assertEqual(ev._parse_claude_json("not json"), ("not json", None, []))

    def test_claude_bin_reads_the_override(self):
        claude = write_fake_claude(self.tmp)
        old = os.environ.get(ev.CLAUDE_BIN_ENV)
        os.environ[ev.CLAUDE_BIN_ENV] = claude
        try:
            self.assertEqual(ev.claude_bin(), claude)
            os.environ[ev.CLAUDE_BIN_ENV] = str(self.tmp / "absent")
            self.assertIsNone(ev.claude_bin())
        finally:
            if old is None:
                os.environ.pop(ev.CLAUDE_BIN_ENV, None)
            else:
                os.environ[ev.CLAUDE_BIN_ENV] = old


class SystemBankContextCase(unittest.TestCase):
    def setUp(self):
        self.cases_doc = json.loads((FIXTURES / "system-reliability-bank-v1.json").read_text())
        self.graders_doc = json.loads((FIXTURES / "system-reliability-graders-v1.json").read_text())

    def build(self, **kwargs):
        return ev.build_system_benchmark(self.cases_doc, self.graders_doc,
                                         generated_at="2026-01-01T00:00:00Z", **kwargs)

    def test_bank_context_carries_the_versions_and_the_digest(self):
        bench = self.build()
        self.assertEqual(bench["schema_version"], "system-bank-benchmark/v2")
        self.assertEqual(bench["bank_version"], "test-1.0.0")
        self.assertEqual(bench["grader_version"], "test-1.0.0")
        context = bench["context"]
        self.assertEqual(validate(context), [])
        self.assertIsNone(context["skill"])
        self.assertEqual(context["fixtures"], {"id": "system-bank", "version": "test-1.0.0",
                                               "digest": digest_json(self.cases_doc)})
        self.assertEqual(context["grader"], {"id": "system-bank", "version": "test-1.0.0"})
        self.assertEqual(context["runner"], {"provider": "claude-code", "cli_version": None, "models": []})

    def test_a_given_runner_is_recorded(self):
        runner = {"provider": "claude-code", "cli_version": "9.9.9", "models": ["m"]}
        self.assertEqual(self.build(runner=runner)["context"]["runner"], runner)

    def test_changed_bank_is_named_by_the_comparison(self):
        first = self.build()["context"]
        self.cases_doc["bank_version"] = "test-2.0.0"
        second = self.build()["context"]
        self.assertEqual(ev.compare_eval_context(first, second), ["fixtures.digest", "fixtures.version"])

    def test_only_the_context_and_version_differ_from_v1_keys(self):
        self.assertEqual(sorted(self.build()), sorted([
            "schema_version", "generated_at", "context", "bank_version", "grader_version", "counts",
            "baseline", "candidate", "pair", "sample", "provider_capability"]))


class EvalContextShapeCase(unittest.TestCase):
    def parts(self):
        context = valid_context()
        return {name: context[name] for name in ("skill", "fixtures", "grader", "runner")}

    def test_valid_parts_build_a_valid_context(self):
        context = ev.eval_context(**self.parts())
        self.assertEqual(context, valid_context())
        self.assertEqual(validate(context), [])

    def test_the_arguments_are_copied(self):
        parts = self.parts()
        context = ev.eval_context(**parts)
        parts["runner"]["models"].append("late")
        parts["skill"]["id"] = "changed/id"
        self.assertEqual(context, valid_context())

    def test_a_skill_is_optional(self):
        parts = self.parts()
        del parts["skill"]
        self.assertIsNone(ev.eval_context(**parts)["skill"])

    def test_malformed_parts_are_refused_with_every_problem(self):
        cases = {
            "skill.digest": lambda p: p["skill"].update(digest="abc"),
            "skill.id": lambda p: p["skill"].update(id="no-bucket"),
            "fixtures.digest": lambda p: p["fixtures"].update(digest="sha256:zz"),
            "fixtures.version": lambda p: p["fixtures"].update(version=1),
            "grader.version": lambda p: p["grader"].update(version=1),
            "runner.cli_version": lambda p: p["runner"].update(cli_version=2),
            "runner.models": lambda p: p["runner"].update(models="m"),
            "runner must be": lambda p: p.update(runner={"provider": "claude-code"}),
        }
        for needle, mutate in cases.items():
            with self.subTest(needle=needle):
                parts = self.parts()
                mutate(parts)
                with self.assertRaises(ValueError) as caught:
                    ev.eval_context(**parts)
                self.assertIn(needle, str(caught.exception))

    def test_compare_reports_sorted_paths_and_whole_sections(self):
        a, b = valid_context(), copy.deepcopy(valid_context())
        b["runner"]["models"] = ["m"]
        b["runner"]["cli_version"] = "1.0.0"
        b["grader"]["version"] = "2"
        self.assertEqual(ev.compare_eval_context(a, b), ["grader.version", "runner.cli_version", "runner.models"])
        b = copy.deepcopy(a)
        b["skill"] = None
        self.assertEqual(ev.compare_eval_context(a, b), ["skill"])
        self.assertEqual(ev.compare_eval_context(b, b), [])


class ReportLineCase(unittest.TestCase):
    def test_context_line_in_the_report(self):
        context = valid_context()
        context["runner"] = {"provider": "claude-code", "cli_version": "9.9.9", "models": ["m-1", "m-2"]}
        bench = {"skill": "demo", "context": context, "with_skill": {}}
        self.assertIn("Context: skill sha256:000000000000…, models m-1, m-2, claude 9.9.9",
                      ev.render_markdown(bench))

    def test_unobserved_values_are_said_so_and_old_results_have_no_line(self):
        bench = {"skill": "demo", "context": valid_context(), "with_skill": {}}
        self.assertIn("models unobserved, claude unknown", ev.render_markdown(bench))
        self.assertNotIn("Context:", ev.render_markdown({"skill": "demo", "with_skill": {}}))
        bank = valid_context()
        bank["skill"] = None
        self.assertIn("Context: skill none,", ev.render_markdown({"skill": "bank", "context": bank}))


if __name__ == "__main__":
    unittest.main()
