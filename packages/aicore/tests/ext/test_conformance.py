"""aicore.ext.conformance: a good plugin passes, each broken fixture fails exactly the scenario it breaks.

The plugins are the folders of ``fixtures/plugins`` run in place. Scenarios that need Linux (``no-descendants``) are
checked there and may be a ``skip`` elsewhere.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import redirect_stderr
from io import StringIO

from aicore.ext import conformance
from aicore.ext.conformance import SCENARIOS, run_conformance

from tests.ext.support import FIXTURES, TempCase, run_cli

PLUGINS = FIXTURES / "plugins"
AICORE_ROOT = FIXTURES.parents[2]
SENTINEL = "s3cr3t-" + uuid.uuid4().hex
LINUX = sys.platform.startswith("linux")


class ConformanceCase(TempCase):
    def setUp(self):
        super().setUp()
        self.env["AICORE_ROOT"] = str(AICORE_ROOT)
        self.env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
        self.env["FIXTURE_SECRET"] = SENTINEL

    def run_plugin(self, name, **kwargs):
        results = run_conformance(PLUGINS / name / "extension.json", env=self.env, **kwargs)
        self.assertEqual([item["check_id"] for item in results], ["ext.conformance." + name for name in SCENARIOS])
        for item in results:
            self.assertEqual(conformance._problems(item, "check-result"), [], item)
            self.assertEqual(item["category"], "integration")
        found = {item["check_id"].rpartition(".")[2]: item for item in results}
        self.assertNotIn(SENTINEL, json.dumps(results))
        self.assertNotIn("conformance-sentinel-", json.dumps(results))
        return found

    def assertStatuses(self, found, **expected):
        self.assertEqual({name: found[name]["status"] for name in expected}, expected, found)


class TestGoodPlugins(ConformanceCase):
    def test_command_plugin_passes_every_scenario(self):
        found = self.run_plugin("echo")
        self.assertStatuses(found, manifest="ok", describe="ok", **{"protocol-unsupported": "ok"}, invoke="ok",
                            redelivery="skip", **{"stdout-discipline": "ok"}, deadline="ok", secrets="skip")
        self.assertIn(found["no-descendants"]["status"], ("ok", "skip") if not LINUX else ("ok",))

    def test_subscriber_plugin_passes_invoke_and_redelivery(self):
        found = self.run_plugin("sub")
        self.assertStatuses(found, manifest="ok", describe="ok", invoke="ok", redelivery="ok", secrets="skip")
        self.assertNotIn("fail", {item["status"] for item in found.values()})

    def test_secret_scenario_runs_trusted_with_a_made_up_value(self):
        found = self.run_plugin("probe")
        self.assertEqual(found["secrets"]["status"], "ok", found["secrets"])

    def test_input_document_replaces_the_example_input(self):
        results = run_conformance(PLUGINS / "echo" / "extension.json", env=self.env, input_doc={"y": 2})
        self.assertNotIn("fail", {item["status"] for item in results})

    def test_requests_follow_plugin_request_except_the_unsupported_protocol(self):
        manifest = conformance.load_manifest(PLUGINS / "echo" / "extension.json")
        runner = conformance._Runner(manifest, self.env, 20)
        good = runner.call("describe", {"op": "describe"})
        raw = runner.call("raw", {"op": "describe"}, protocol=conformance.UNSUPPORTED_PROTOCOL)
        self.assertEqual(conformance._problems(good.request, "plugin-request"), [])
        self.assertNotEqual(conformance._problems(raw.request, "plugin-request"), [])

    def test_the_callers_children_are_left_alone(self):
        """The orphan check reaps with waitpid(-1) in a process of its own, never in the caller."""
        bystander = subprocess.Popen([sys.executable, "-c", "pass"])
        time.sleep(0.5)  # it has exited and waits to be reaped by this process: a waitpid(-1) here would take it
        self.run_plugin("echo")
        self.assertEqual(os.waitpid(bystander.pid, 0)[0], bystander.pid)
        bystander.returncode = 0  # reaped above, the object must not wait again


class TestBrokenPlugins(ConformanceCase):
    def test_banner_before_json_breaks_stdout_discipline(self):
        found = self.run_plugin("banner-before-json")
        self.assertStatuses(found, manifest="ok", **{"stdout-discipline": "fail"}, describe="fail")
        self.assertIn("stdout", found["stdout-discipline"]["observed"])
        self.assertIn("remediation", found["stdout-discipline"])

    def test_a_plugin_that_ignores_the_protocol_number_fails(self):
        found = self.run_plugin("no-protocol-999")
        self.assertStatuses(found, describe="ok", invoke="ok", **{"protocol-unsupported": "fail"})

    def test_a_plugin_that_hangs_fails_the_deadline_and_the_rest_is_not_run(self):
        found = self.run_plugin("hangs")
        self.assertStatuses(found, deadline="fail", describe="fail", **{"protocol-unsupported": "skip"},
                            invoke="skip", **{"no-descendants": "skip"})
        self.assertIn("1 s", found["deadline"]["observed"])

    @unittest.skipUnless(LINUX, "needs PR_SET_CHILD_SUBREAPER")
    def test_a_process_in_its_own_session_is_found(self):
        found = self.run_plugin("setsid-grandchild")
        self.assertStatuses(found, describe="ok", invoke="ok", **{"no-descendants": "fail"})
        self.assertIn("outlived", found["no-descendants"]["observed"])

    def test_an_echoed_secret_fails_without_printing_it(self):
        found = self.run_plugin("echoes-secret")
        self.assertStatuses(found, secrets="fail", invoke="ok")
        self.assertNotIn("Traceback", found["secrets"]["observed"])

    def test_a_broken_manifest_fails_one_scenario_and_skips_the_others(self):
        found = self.run_plugin("bad-schema")
        self.assertEqual(found["manifest"]["status"], "fail")
        self.assertEqual({found[name]["status"] for name in SCENARIOS[1:]}, {"skip"})

    def test_a_missing_manifest_is_a_failed_scenario_not_an_exception(self):
        results = run_conformance(self.tmp / "nowhere" / "extension.json", env=self.env)
        self.assertEqual((results[0]["status"], len(results)), ("fail", len(SCENARIOS)))
        self.assertIn("PLUGIN_MANIFEST_INVALID", results[0]["observed"])


class TestCrash(ConformanceCase):
    """R13: a plugin that dies while it handles a call fails ``crash`` and the evidence names the exit or the signal."""

    def staged(self, name):
        """A copy of a fixture plugin in a fresh temporary directory, far from the repository."""
        root = tempfile.mkdtemp(prefix="aicore-foreign-plugin-")
        self.addCleanup(shutil.rmtree, root, True)
        target = os.path.join(root, name)
        shutil.copytree(PLUGINS / name, target, ignore=shutil.ignore_patterns("__pycache__", "marks"))
        return os.path.join(target, "extension.json")

    def test_good_plugins_do_not_crash(self):
        for name in ("echo", "sub"):
            with self.subTest(name):
                self.assertEqual(self.run_plugin(name)["crash"]["status"], "ok")

    def test_a_subscriber_that_exits_while_it_handles_an_event_fails_with_its_exit_code(self):
        found = self.run_plugin("crash")
        self.assertStatuses(found, manifest="ok", describe="ok", invoke="fail", crash="fail")
        self.assertEqual(found["crash"]["evidence"], ["call=event", "exit_code=3"])
        self.assertEqual(found["crash"]["remediation"],
                         "Answer with status error instead of exiting; the host redelivers after a crash.")

    @unittest.skipUnless(LINUX, "a signal death is reported as a negative exit status")
    def test_a_command_plugin_killed_by_a_signal_fails_with_the_signal(self):
        found = self.run_plugin("crash-signal")
        self.assertStatuses(found, describe="ok", crash="fail")
        self.assertEqual(found["crash"]["evidence"], ["call=invoke", "signal=SIGKILL"])

    def test_a_foreign_plugin_outside_the_repository_is_checked_by_its_path(self):
        path = self.staged("crash")
        self.assertFalse(path.startswith(str(AICORE_ROOT)))
        code, out, _err = run_cli("ext", "conformance", "--manifest", path, "--json", env=self.env)
        self.assertEqual(code, 1)
        results = {item["check_id"].rpartition(".")[2]: item for item in json.loads(out)}
        self.assertEqual(results["crash"]["status"], "fail")
        self.assertIn("exit_code=3", results["crash"]["evidence"])

    def test_a_foreign_good_plugin_passes_by_its_path(self):
        code, out, _err = run_cli("ext", "conformance", "--manifest", self.staged("sub"), "--json", env=self.env)
        self.assertEqual(code, 0, out)
        self.assertEqual({item["check_id"].rpartition(".")[2]: item["status"] for item in json.loads(out)}["crash"],
                         "ok")

    def test_the_manifest_is_given_once(self):
        path = self.staged("echo")
        code, _out, err = run_cli("ext", "conformance", path, "--manifest", path, env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("once", err)

    def test_a_crash_is_not_run_after_a_timeout(self):
        self.assertEqual(self.run_plugin("hangs")["crash"]["status"], "skip")


class TestCommandLine(ConformanceCase):
    def test_text_has_a_line_per_scenario_and_exit_0(self):
        code, out, err = run_cli("ext", "conformance", str(PLUGINS / "echo" / "extension.json"), env=self.env)
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(len(lines), len(SCENARIOS))
        self.assertTrue(lines[0].startswith("ok ext.conformance.manifest: "), lines[0])
        self.assertTrue(lines[4].startswith("skip ext.conformance.redelivery: "), lines[4])

    def test_json_is_a_list_of_check_results_and_a_failure_exits_1(self):
        code, out, _err = run_cli("ext", "conformance", str(PLUGINS / "no-protocol-999" / "extension.json"),
                                  "--json", env=self.env)
        self.assertEqual(code, 1)
        results = json.loads(out)
        self.assertEqual([item["check_id"].rpartition(".")[2] for item in results], list(SCENARIOS))
        for item in results:
            self.assertEqual(conformance._problems(item, "check-result"), [])
        self.assertIn("fail", {item["status"] for item in results})

    def test_a_relative_manifest_path_is_taken_from_the_working_directory(self):
        code, out, _err = run_cli("ext", "conformance", "echo/extension.json", "--json", env=self.env, cwd=PLUGINS)
        self.assertEqual(code, 0, out)

    def test_input_file(self):
        path = self.tmp / "input.json"
        path.write_text('{"y": 2}', encoding="utf-8")
        code, _out, _err = run_cli("ext", "conformance", str(PLUGINS / "echo" / "extension.json"),
                                   "--input-file", str(path), env=self.env)
        self.assertEqual(code, 0)
        path.write_text("[1]", encoding="utf-8")
        code, _out, err = run_cli("ext", "conformance", str(PLUGINS / "echo" / "extension.json"),
                                  "--input-file", str(path), env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("must be a JSON object", err)

    def test_usage_error_is_exit_2(self):
        self.assertEqual(run_cli("ext", "conformance", env=self.env)[0], 2)

    def test_the_supervisor_entry_refuses_other_arguments(self):
        with redirect_stderr(StringIO()) as err:
            self.assertEqual(conformance._supervisor_main([]), 2)
        self.assertIn("usage", err.getvalue())


if __name__ == "__main__":
    unittest.main()
