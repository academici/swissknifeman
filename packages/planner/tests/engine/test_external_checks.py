"""External plan checks: the ``planner:check`` extension point, the ``check-plugin/v1`` contract and ``plan.py check``."""
import json
import os
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_AICORE_LIB = Path(__file__).resolve().parents[3] / "aicore" / "lib"
if (_AICORE_LIB / "aicore" / "__init__.py").is_file() and str(_AICORE_LIB) not in sys.path:
    sys.path.insert(1, str(_AICORE_LIB))

from planner import integration  # noqa: E402
from planner.integration import plugins  # noqa: E402
from planner.plan import schema, settings, store  # noqa: E402

try:
    from . import test_settings
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_settings

PLANNER = Path(__file__).resolve().parents[2]
PLUGIN = PLANNER / "tests" / "fixtures" / "plugins" / "check-demo"
run = test_settings.run
needs_aicore = unittest.skipUnless(integration.available(), "needs the aicore foundation")


class ContractTests(unittest.TestCase):
    def test_unit_declares_the_point_and_the_contract(self):
        unit = json.loads((PLANNER / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual([point["id"] for point in unit["provides"]["extension_points"]], ["check"])
        contract = next(row for row in unit["provides"]["contracts"]
                        if row["id"] == "urn:swissknifeman:planner:check-plugin")
        self.assertEqual((contract["path"], contract["version"]), ("schemas/check-plugin/v1", "v1"))
        for name in ("input", "output"):
            document = json.loads((PLANNER / contract["path"] / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertEqual(document["$id"], f"urn:swissknifeman:planner:check-plugin:{name}:v1")

    def test_the_schemas_stay_inside_the_closed_profile(self):
        registry = schema.load_registry(plugins.SCHEMA_DIR)
        self.assertEqual(len(registry._schemas), 2)

    def test_output_problems(self):
        good = {"issues": [{"severity": "error", "code": "A_B1", "message": "m", "ref": "P1.1", "path": "plan.json"},
                           {"severity": "warning", "code": "C", "message": "m"}]}
        self.assertEqual(plugins.output_problems(good), [])
        self.assertEqual(plugins.output_problems({"issues": []}), [])
        for bad in ({}, {"issues": "x"}, {"issues": [{"severity": "fatal", "code": "A", "message": "m"}]},
                    {"issues": [{"severity": "error", "code": "a", "message": "m"}]},
                    {"issues": [{"severity": "error", "code": "A", "message": ""}]},
                    {"issues": [{"severity": "error", "code": "A", "message": "m", "extra": 1}]},
                    {"issues": [{"severity": "error", "code": "A"}]}, {"issues": [], "more": 1}, []):
            with self.subTest(bad=bad):
                self.assertTrue(plugins.output_problems(bad))

    def test_at_most_five_hundred_issues(self):
        row = {"severity": "warning", "code": "A", "message": "m"}
        self.assertEqual(plugins.output_problems({"issues": [row] * 500}), [])
        self.assertTrue(plugins.output_problems({"issues": [row] * 501}))

    def test_the_input_follows_its_schema(self):
        document = plugins.build_input(plan_id="2026.10.07-№1-X", short_id="PLAN1", plan_dir=Path("/tmp/p/plans/x"),
                                       plans_root=Path("/tmp/p/plans"), project_root=None)
        registry = schema.load_registry(plugins.SCHEMA_DIR)
        node, base = registry.resolve("urn:swissknifeman:planner:check-plugin:input:v1", "")
        self.assertEqual(schema.validate_node(registry, node, base, document), [])
        self.assertEqual(document["schema_urn_prefix"], "urn:swissknifeman:task:plan:")
        self.assertIsNone(document["project_root"])
        broken = dict(document, schema_urn_prefix="other:")
        self.assertTrue(schema.validate_node(registry, node, base, broken))


@needs_aicore
class ExternalCheckCase(test_settings.ConfigCase):
    """Plan LIFE in a temporary project; the demo plugin is registered in the machine configuration."""

    def setUp(self):
        super().setUp()
        self.marks = self.home / "marks"
        os.environ["AICORE_ROOT"] = integration.status()["root"]
        os.environ["CHECK_DEMO_MARKS"] = str(self.marks)
        self.config = ""

    def machine(self, text):
        self.config += text
        self.write(self.machine_file(), self.config)

    def register(self, mode=None, extra=""):
        if mode is not None:
            os.environ["CHECK_DEMO_MODE"] = mode
        self.config = ""
        self.machine(f'[aicore.plugins.check-demo]\nmanifest = "{PLUGIN / "extension.json"}"\ntrusted = true\n{extra}')

    def calls(self):
        path = self.marks / "calls.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def check(self, *flags):
        return run("check", self.root, *flags)

    def builtin_warnings(self):
        """Warnings the plan has on its own (the plugins are not called)."""
        return json.loads(self.check("--no-external", "--json")[1])["warnings"]


@needs_aicore
class RegisteredPluginTests(ExternalCheckCase):
    def test_the_findings_fail_the_check_and_carry_the_plugin_prefix(self):
        self.register()
        code, out, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("DEMO_ERROR: P1.1: [check-demo] the demo check rejects", err)
        self.assertIn("warning DEMO_WARNING: plan.json: [check-demo] the demo check has a remark", out)
        self.assertIn(f"1 error(s), {self.builtin_warnings() + 1} warning(s)", out)

    def test_the_builtin_checks_are_unchanged_without_a_plugin(self):
        code, out, err = self.check()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.calls(), [])
        self.assertIn("0 error(s)", out)
        self.assertNotIn("EXTERNAL", out)

    def test_json_lists_the_findings_beside_the_builtin_ones(self):
        self.register()
        code, out, _ = self.check("--json")
        data = json.loads(out)
        self.assertEqual((code, data["ok"], data["errors"]), (1, False, 1))
        self.assertEqual(sorted(issue["code"] for issue in data["issues"] if "[check-demo]" in issue["message"]),
                         ["DEMO_ERROR", "DEMO_WARNING"])

    def test_no_external_skips_the_plugins(self):
        self.register()
        code, out, err = self.check("--no-external")
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("DEMO", out)
        self.assertEqual(self.calls(), [])

    def test_the_plugin_receives_the_plan_in_the_contract_shape(self):
        self.register("clean")
        self.assertEqual(self.check()[0], 0)
        invoke = [call for call in self.calls() if call["op"] == "invoke"]
        self.assertEqual(len(invoke), 1)
        self.assertEqual(invoke[0]["point"], "planner:check")
        self.assertEqual(invoke[0]["plan_id"], store.load_plan(self.root).plan["id"])
        self.assertEqual(invoke[0]["keys"], sorted(["plan_id", "short_id", "plan_dir", "plans_root", "project_root",
                                                     "planner_version", "schema_urn_prefix"]))

    def test_a_clean_plugin_and_a_skipping_plugin_add_nothing(self):
        for mode in ("clean", "skipped"):
            with self.subTest(mode):
                self.register(mode)
                code, out, err = self.check()
                self.assertEqual((code, err), (0, ""))
                self.assertIn(f"0 error(s), {self.builtin_warnings()} warning(s)", out)

    def test_a_disabled_plugin_is_not_called(self):
        self.register(extra="enabled = false\n")
        self.assertEqual(self.check()[0], 0)
        self.assertEqual(self.calls(), [])


@needs_aicore
class FailureTests(ExternalCheckCase):
    def test_a_failing_plugin_is_a_warning_and_does_not_fail_the_check(self):
        self.register("error")
        code, out, err = self.check()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("warning EXTERNAL_CHECK_FAILED: check-demo: DEMO_CRASH", out)

    def test_a_plugin_that_exits_non_zero_is_reported_by_its_reason(self):
        self.register("exit")
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("warning EXTERNAL_CHECK_FAILED: check-demo: PROCESS_EXIT", out)

    def test_a_timeout_is_reported_too(self):
        self.register("issues", "timeout_seconds = 1\n")
        sleeper = self.home / "slow"
        sleeper.mkdir()
        (sleeper / "extension.json").write_text((PLUGIN / "extension.json").read_text(encoding="utf-8"),
                                                encoding="utf-8")
        (sleeper / "plugin.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        self.config = ""
        self.machine(f'[aicore.plugins.check-demo]\nmanifest = "{sleeper / "extension.json"}"\ntrusted = true\n'
                     'timeout_seconds = 1\n')
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("warning EXTERNAL_CHECK_FAILED: check-demo: PROCESS_TIMEOUT", out)

    def test_an_output_outside_the_contract_is_one_failure(self):
        for mode in ("invalid", "many"):
            with self.subTest(mode):
                self.register(mode)
                code, out, _ = self.check()
                self.assertEqual(code, 0)
                self.assertEqual(out.count("EXTERNAL_CHECK_FAILED"), 1)
                self.assertIn("INVALID_OUTPUT", out)

    def test_external_failure_error_makes_a_failing_plugin_an_error(self):
        self.register("error")
        self.machine('[planner.checks]\nexternal_failure = "error"\n')
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn("EXTERNAL_CHECK_FAILED: check-demo: DEMO_CRASH", err)

    def test_the_failure_of_one_plugin_does_not_hide_another(self):
        self.register("error")
        other = self.home / "other"
        other.mkdir()
        manifest = json.loads((PLUGIN / "extension.json").read_text(encoding="utf-8"))
        manifest["id"] = "check-other"
        (other / "extension.json").write_text(json.dumps(manifest), encoding="utf-8")
        body = (PLUGIN / "plugin.py").read_text(encoding="utf-8")
        (other / "plugin.py").write_text(body.replace('os.environ.get("CHECK_DEMO_MODE", "issues")', '"issues"'),
                                         encoding="utf-8")
        self.machine(f'[aicore.plugins.check-other]\nmanifest = "{other / "extension.json"}"\ntrusted = true\n')
        _, out, err = self.check()
        self.assertIn("EXTERNAL_CHECK_FAILED: check-demo", out)
        self.assertIn("[check-other] the demo check rejects", err)


@needs_aicore
class SwitchTests(ExternalCheckCase):
    def test_checks_external_false_calls_nothing(self):
        self.register()
        self.machine("[planner.checks]\nexternal = false\n")
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertNotIn("DEMO", out)
        self.assertEqual(self.calls(), [])

    def test_a_mutation_never_runs_a_plugin(self):
        self.register()
        run("set", self.root, "P1.1", "--json", '{"summary": "changed"}')
        run("log", self.root, "P1.1", "--type", "note", "--summary", "n")
        run("design-done", self.root, "P1")
        run("render", self.root)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.check()[0], 1)
        self.assertEqual(len([c for c in self.calls() if c["op"] == "invoke"]), 1)

    def test_without_aicore_the_plugins_are_skipped_silently(self):
        self.register()
        with test_settings.without_aicore():
            code, out, err = self.check()
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("DEMO", out)
        self.assertEqual(self.calls(), [])

    def test_the_planner_registers_nothing_itself(self):
        self.assertEqual(self.check()[0], 0)
        self.assertFalse(self.machine_file().exists())
        self.assertEqual(settings.for_plan(store.load_plan(self.root)).get("checks.external"), True)


if __name__ == "__main__":
    unittest.main()
