#!/usr/bin/env python3
"""scripts/affected-tests.py: the tests a change needs, the tools kept out of the core, the foundation touching all."""
import json
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "affected-tests.py"


def load_module():
    spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def partners(root):
    return {"PLANNER_ROOT": str(root / "packages/planner"), "PLANNER_PLAN_PY": str(root / "packages/planner/scripts/plan.py"),
            "SKM_ORCH_ROOT": str(root / "packages/orch"), "SKM_SKILLER_ROOT": str(root / "packages/skiller"),
            "SKM_HARNESS_ROOT": str(root / "packages/harness"), "AICORE_ROOT": str(root / "packages/aicore"),
            "SKM_GUI_ROOT": str(root / "packages/gui"), "SKM_WORKSPACE_MODULE_ROOT": str(root / "packages/workspace")}


def plan(*paths, tier="fast", extra=()):
    done = subprocess.run([sys.executable, str(SCRIPT), "--json", "--tier", tier, "--paths", *paths, *extra],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


class AffectedTestsTests(unittest.TestCase):
    def test_a_bridge_gets_its_partners_from_the_hub_layout(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = module.bridge_env()
        for name, expected in partners(module.ROOT).items():
            self.assertEqual(env[name], expected, name)

    def test_validate_runs_with_a_throwaway_home_so_the_dev_clone_guard_lets_it_pass(self):
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with module.command_env("packages/skiller", ["bash", "scripts/validate.sh"]) as env:
            self.assertNotEqual(os.path.realpath(env["HOME"]), os.path.realpath(os.path.expanduser("~")))
            self.assertTrue(Path(env["HOME"]).is_dir())
            self.assertEqual(env["GIT_CONFIG_GLOBAL"], str(Path(env["HOME"]) / ".gitconfig"))
        with module.command_env("packages/skiller", ["bash", "scripts/test.sh"]) as env:
            self.assertEqual(env["HOME"], os.environ["HOME"])

    def test_a_tool_is_tested_when_its_own_files_change(self):
        self.assertEqual(plan("packages/maind/lib/maind/x.py")["units"], ["packages/maind"])

    def test_a_module_brings_the_bridges_that_require_it_and_no_other_module(self):
        self.assertEqual(plan("packages/skiller/lib/skiller/cli.py")["units"], ["bridges/orch-skiller", "packages/skiller"])

    def test_the_foundation_affects_every_unit_except_the_tools(self):
        units = plan("packages/aicore/lib/aicore/util/io.py")["units"]
        self.assertIn("packages/harness", units)
        self.assertIn("bridges/planner-orch", units)
        self.assertNotIn("packages/maind", units)  # a tool joins only for its own changes, or with --with-tools
        self.assertIn("packages/maind", plan("packages/aicore/x.py", extra=("--with-tools",))["units"])

    def test_a_change_inside_a_unit_brings_the_golden_check_once(self):
        argv = [" ".join(item["argv"]) for item in plan("packages/orch/lib/orch/cli.py")["commands"]]
        self.assertEqual(argv.count("python3 scripts/golden.py check"), 1)
        both = [" ".join(item["argv"]) for item in plan("packages/orch/lib/orch/cli.py", "bootstrap/skills/x/SKILL.md")["commands"]]
        self.assertEqual(both.count("python3 scripts/golden.py check"), 1)

    def test_a_hub_path_runs_only_the_cheap_hub_checks(self):
        result = plan("docs/develop.md")
        self.assertEqual(result["units"], [])
        self.assertTrue(result["hub"])
        self.assertEqual({item["folder"] for item in result["commands"]}, {"hub"})

    def test_hub_paths_bring_their_own_checks(self):
        argv = [" ".join(item["argv"]) for item in plan("bootstrap/skills/x/SKILL.md", "scripts/docs-impact.py")["commands"]]
        self.assertIn("python3 scripts/golden.py check", argv)
        self.assertIn("python3 scripts/test-docs-impact.py", argv)
        self.assertNotIn("python3 scripts/golden.py check",
                         [" ".join(item["argv"]) for item in plan("docs/develop.md")["commands"]])

    def test_analyst_and_maind_are_tools(self):
        units = plan("packages/aicore/lib/aicore/util/io.py")["units"]
        self.assertNotIn("packages/analyst", units)
        self.assertEqual(plan("packages/analyst/lib/analyst/x.py")["units"], ["packages/analyst"])

    def test_planner_has_a_quick_test_command(self):
        commands = plan("packages/planner/lib/planner/plan/x.py")["commands"]
        self.assertIn(("packages/planner", ["bash", "scripts/test.sh"]),
                      [(item["folder"], item["argv"]) for item in commands])

    def test_the_cache_key_follows_the_content_of_the_unit_and_its_requirements(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        units = module.units()
        self.assertEqual(module.requirements(units, "bridges/planner-orch", "aicore"),
                         ["bridges/planner-orch", "packages/aicore", "packages/orch", "packages/planner"])
        key = module.content_key(["packages/brain"], ["bash", "scripts/test.sh"])
        self.assertEqual(key, module.content_key(["packages/brain"], ["bash", "scripts/test.sh"]))
        self.assertNotEqual(key, module.content_key(["packages/brain"], ["bash", "scripts/validate.sh"]))
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder, patch.object(module, "ROOT", Path(folder)):
            git = ["git", "-C", folder, "-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
            subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
            empty = module.content_key(["."], ["test"])
            keys = []
            source = Path(folder) / "source.py"
            for content, mode in (("one", 0o644), ("one", 0o755), ("two", 0o755), (None, None)):
                if content is None:
                    source.unlink()
                else:
                    source.write_text(content)
                    source.chmod(mode)
                expected = module.content_key(["."], ["test"])
                keys.append(expected)
                for args in (["add", "-A"], ["commit", "-qm", "snapshot"]):
                    subprocess.run(git + args, check=True, capture_output=True)
                    self.assertEqual(expected, module.content_key(["."], ["test"]))
            self.assertEqual(len(set(keys[:3])), 3)  # content and executable-mode changes invalidate green
            self.assertEqual(keys[-1], empty)

    def test_the_full_tier_adds_validate_and_all_is_every_core_unit(self):
        folders = [(item["folder"], item["argv"][-1]) for item in plan("packages/skiller/x.py", tier="full")["commands"]]
        self.assertIn(("packages/skiller", "scripts/validate.sh"), folders)
        everything = plan(tier="all")["units"]
        self.assertIn("packages/planner", everything)
        self.assertNotIn("packages/maind", everything)


class PartnerTests(unittest.TestCase):
    def test_command_env_overrides_live_checkout_partners_for_all_bridge_families(self):
        module = load_module()
        expected = partners(module.ROOT)
        with patch.dict(os.environ, {key: "/tmp/live-checkout/" + key for key in expected}):
            for bridge in ("gui-orch", "gui-workspace", "workspace-planner"):
                with module.command_env("bridges/" + bridge, ["bash", "scripts/test.sh"]) as env:
                    self.assertEqual({key: env[key] for key in expected}, expected)

    def test_bridge_shell_exports_current_checkout_without_running_real_bridges(self):
        # Copy just the wrapper to a fixture hub; its sole bridge prints the inherited exports.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            wrapper = root / "scripts/test-bridges.sh"
            wrapper.write_bytes(SCRIPT.with_name("test-bridges.sh").read_bytes())
            bridge = root / "bridges/probe"
            bridge.mkdir(parents=True)
            names = list(partners(root))
            probe = "import json,os; print(json.dumps({k:os.environ[k] for k in " + repr(names) + "}))"
            (bridge / "unit.json").write_text(json.dumps({"dev": {"test": [sys.executable, "-c", probe]}}))
            env = {**os.environ, **{name: "/tmp/live-checkout" for name in names}}
            done = subprocess.run(["bash", str(wrapper)], capture_output=True, text=True, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
            exported = next(json.loads(line) for line in done.stdout.splitlines() if line.startswith("{"))
            self.assertEqual(exported, partners(root))


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = load_module()
        self.module.ROOT = self.root
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / "configs").mkdir()
        (self.root / "configs/ecosystem-units.json").write_text("{}")
        self.log = self.root / "commands.log"
        self.env = patch.dict(os.environ, {"LOG": str(self.log), "SKM_CHECK_RUN": "", "SKM_TEST_JOBS": "2"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.module.HUB_CHECKS = [["bash", "-c", 'echo hub >> "$LOG"']]
        self.module.GOLDEN = ["bash", "-c", 'echo golden >> "$LOG"']
        for name in ("a", "b"):
            self.unit(name)

    def unit(self, name, test=True):
        folder = self.root / "packages" / name
        (folder / "scripts").mkdir(parents=True, exist_ok=True)
        dev = {"validate": ["bash", "scripts/validate.sh"]}
        if test:
            dev["test"] = ["bash", "scripts/test.sh"]
        (folder / "unit.json").write_text(json.dumps({"id": name, "dev": dev}))
        for kind in ("test", "validate"):
            (folder / "scripts" / (kind + ".sh")).write_text(
                'echo "' + name + ' ' + kind + ' SKIP=${SKM_VALIDATE_SKIP_TESTS:-unset} JOBS=$SKM_TEST_JOBS" >> "$LOG"\n')

    def run_runner(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.module.main(["--run", "--paths", "packages/a/x.py", "packages/b/x.py", *argv])
        return code, out.getvalue(), err.getvalue()

    def lines(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


class RunnerTests(RunnerFixture):
    def test_full_runs_test_before_validate_and_only_full_test_permits_skip(self):
        self.unit("c", test=False)
        with patch.dict(os.environ, {"SKM_VALIDATE_SKIP_TESTS": "1"}):
            code, _, err = self.run_runner("--tier", "all", "--no-cache")
        self.assertEqual(code, 0, err)
        lines = self.lines()
        for name in ("a", "b"):
            test = next(i for i, s in enumerate(lines) if s.startswith(name + " test SKIP=unset"))
            validate = next(i for i, s in enumerate(lines) if s.startswith(name + " validate SKIP=1"))
            self.assertLess(test, validate)
        self.assertTrue(any(s.startswith("c validate SKIP=unset") for s in lines))

    def test_hub_checks_finish_before_any_unit_with_parallel_workers(self):
        self.assertEqual(self.run_runner("--tier", "all", "--no-cache")[0], 0)
        self.assertEqual(self.lines()[:2], ["hub", "golden"])

    def test_a_green_child_prints_no_failed_output_path(self):
        code, out, err = self.run_runner("--tier", "fast", "--no-cache", "--paths", "packages/a/x.py")
        self.assertEqual(code, 0, err)
        self.assertNotIn("full output:", out + err)

    def test_a_failed_child_keeps_output_outside_the_excerpt(self):
        marker = "EARLY-FAILURE-MARKER"
        body = marker + "\n" + ("y" * 8000) + "\nTAIL\n"
        script = self.root / "packages/a/scripts/test.sh"
        script.write_text("python3 -c " + json.dumps(
            "import sys; sys.stdout.write(" + json.dumps(body) + "); sys.exit(1)") + "\n")
        code, out, err = self.run_runner("--tier", "fast", "--no-cache", "--paths", "packages/a/x.py")
        self.assertEqual(code, 1)
        self.assertNotIn(marker, err)
        self.assertIn("full output:", err)
        path = Path(err.split("full output:", 1)[1].split()[0])
        self.assertEqual(path.read_text(encoding="utf-8"), body)
        self.assertIn("TAIL", err)
        self.assertNotIn("full output:", out)

    def test_fail_fast_skips_unsubmitted_jobs_and_keeps_failed_test_outcome(self):
        script = self.root / "packages/a/scripts/test.sh"
        script.write_text(script.read_text() + "exit 1\n")
        code, out, _ = self.run_runner("--tier", "full", "--fail-fast", "-j", "1", "--no-cache")
        self.assertEqual(code, 1)
        self.assertIn("[skipped] packages/b:", out)
        self.assertFalse(any(s.startswith("b ") for s in self.lines()))
        self.assertTrue(any(s.startswith("a validate SKIP=1") for s in self.lines()))
        self.log.unlink()
        self.assertEqual(self.run_runner("--tier", "full", "-j", "1", "--no-cache")[0], 1)
        self.assertTrue(any(s.startswith("b test") for s in self.lines()))

    def test_hub_failure_fail_fast_never_launches_a_unit(self):
        self.module.HUB_CHECKS = [["bash", "-c", "exit 1"]]
        code, out, _ = self.run_runner("--tier", "all", "--fail-fast", "--no-cache")
        self.assertEqual(code, 1)
        self.assertIn("[skipped] packages/a:", out)
        self.assertEqual(self.lines(), [])

    def test_unlaunchable_test_does_not_grant_validate_a_test_skip(self):
        path = self.root / "packages/a/unit.json"
        doc = json.loads(path.read_text())
        doc["dev"]["test"] = ["/missing/test-runner"]
        path.write_text(json.dumps(doc))
        code, _, _ = self.run_runner("--tier", "full", "--no-cache")
        self.assertEqual(code, 1)
        self.assertTrue(any(s.startswith("a validate SKIP=unset") for s in self.lines()))

    def test_all_reuses_only_within_run_and_invalidates_changed_unit(self):
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "r1"}):
            self.assertEqual(self.run_runner("--tier", "all")[0], 0)
            self.assertTrue((self.root / ".git/affected-tests/run-r1.json").exists())
            self.log.unlink()
            code, out, _ = self.run_runner("--tier", "all")
            self.assertEqual(code, 0)
            self.assertIn("[cached] packages/a:", out)
            self.assertEqual(self.lines(), ["hub", "golden"])
            (self.root / "packages/a/change.py").write_text("changed")
            code, out, _ = self.run_runner("--tier", "all")
            self.assertEqual(code, 0)
            self.assertIn("[ok] packages/a:", out)
            self.assertIn("[cached] packages/b:", out)
            self.assertNotIn("[cached]", self.run_runner("--tier", "all", "--no-cache")[1])
        for run_id in ("", "../x"):
            with patch.dict(os.environ, {"SKM_CHECK_RUN": run_id}):
                self.assertNotIn("[cached]", self.run_runner("--tier", "all")[1])

    def test_corrupt_receipts_are_misses_and_replaced_and_old_runs_pruned(self):
        store = self.module.cache_file()
        for filename, tier in (("green.json", "fast"), ("run-r2.json", "all")):
            path = store.with_name(filename)
            path.write_text("{broken")
            old = store.with_name("run-old.json")
            old.write_text("{}")
            os.utime(old, (1, 1))
            with patch.dict(os.environ, {"SKM_CHECK_RUN": "r2"}):
                self.assertEqual(self.run_runner("--tier", tier)[0], 0)
            self.assertTrue(self.module.read_cache(path))
            if tier == "all":
                self.assertFalse(old.exists())
        store.write_text('{"not-a-receipt": true}')
        self.assertEqual(self.module.read_cache(store), {})

    def test_durations_schedule_known_heaviest_first_then_unknown(self):
        self.unit("c")
        path = self.module.cache_file().with_name("durations.json")
        self.module._write_json_atomic(path, {"packages/a bash scripts/test.sh": 1,
                                              "packages/b bash scripts/test.sh": 9})
        self.assertEqual(self.run_runner("--tier", "all", "-j", "1", "--no-cache")[0], 0)
        self.assertEqual([s.split()[0] for s in self.lines() if " test " in s], ["b", "a", "c"])
        self.assertIn("packages/c bash scripts/validate.sh", self.module.read_cache(path))

    def test_nested_jobs_share_parent_budget_and_json_explains_effective_jobs(self):
        with patch.dict(os.environ, {"SKM_TEST_JOBS": "5"}):
            code, _, _ = self.run_runner("--no-cache", "-j", "2")
            self.assertEqual(code, 0)
            self.assertTrue(all("JOBS=2" in s for s in self.lines() if " test " in s))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.module.main(["--paths", "packages/a/x.py", "--json", "-j", "20"])
            doc = json.loads(out.getvalue())
            self.assertEqual(doc["jobs"], {"requested": 20, "effective": 1, "budget": 5, "child": 5})

    def test_a_reuse_miss_names_the_changed_component_and_not_the_secret_value(self):
        secret = "super-secret-clash-value"
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "explain", "SKM_TEST_CLASH": "one"}):
            self.assertEqual(self.run_runner("--tier", "all")[0], 0)
            self.assertIn("[cached] packages/a:", self.run_runner("--tier", "all")[1])
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "explain", "SKM_TEST_CLASH": secret}):
            code, out, _ = self.run_runner("--tier", "all")
        self.assertEqual(code, 0)
        self.assertIn("[miss] packages/a:", out)
        self.assertIn("env:SKM_TEST_CLASH=", out)
        self.assertNotIn(secret, out)
        self.assertIn("[ok] packages/a:", out)

    def test_an_unknown_dependency_says_why_it_cannot_be_reused(self):
        path = self.root / "packages/a/unit.json"
        doc = json.loads(path.read_text())
        doc["requires"] = [{"unit": "not-a-unit"}]
        path.write_text(json.dumps(doc))
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "unknown"}):
            code, out, _ = self.run_runner("--tier", "fast", "--paths", "packages/a/x.py")
        self.assertEqual(code, 0)
        self.assertIn("unknown dependency; conservative run", out)
        self.assertNotIn("[cached] packages/a:", out)

    def test_env_runner_fixture_dependency_and_tool_changes_invalidate_reuse(self):
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "context"}):
            self.run_runner("--tier", "all")
            self.assertIn("[cached] packages/a:", self.run_runner("--tier", "all")[1])
            with patch.dict(os.environ, {"SKM_TEST_CLASH": "fail"}):
                self.assertNotIn("[cached]", self.run_runner("--tier", "all")[1])
            # Hub config/runner bytes are inputs even though they are outside the unit closure.
            (self.root / "scripts").mkdir()
            (self.root / "scripts/runner.py").write_text("new runner")
            self.assertNotIn("[cached]", self.run_runner("--tier", "all")[1])
            (self.root / "packages/a/fixtures").mkdir()
            (self.root / "packages/a/fixtures/input.json").write_text("{}")
            self.assertIn("[ok] packages/a:", self.run_runner("--tier", "all")[1])
            tool = self.root / "tools/bash"
            tool.parent.mkdir()
            tool.write_text('#!/bin/sh\nexec /bin/bash "$@"\n')
            tool.chmod(0o755)
            with patch.dict(os.environ, {"PATH": str(tool.parent) + os.pathsep + os.environ["PATH"]}):
                self.assertNotIn("[cached]", self.run_runner("--tier", "all")[1])

    def test_inputs_mutated_during_execution_do_not_publish_reusable_green(self):
        script = self.root / "packages/a/scripts/test.sh"
        script.write_text(script.read_text() + 'echo mutation >> changed.txt\n')
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "mutation"}):
            self.run_runner("--tier", "all")
            _, out, _ = self.run_runner("--tier", "all")
        self.assertIn("[ok] packages/a: bash scripts/test.sh", out)
        receipts = self.module.read_cache(self.module.cache_file().with_name("run-mutation.json"))
        self.assertFalse(any(d["folder"] == "packages/a" and d["command"] == ["bash", "scripts/test.sh"]
                             for d in receipts.values()))

    def test_dependency_and_foundation_changes_invalidate_consumers(self):
        self.unit("aicore")
        path = self.root / "packages/b/unit.json"
        doc = json.loads(path.read_text())
        doc["requires"] = [{"unit": "a"}]
        path.write_text(json.dumps(doc))
        with patch.dict(os.environ, {"SKM_CHECK_RUN": "dependencies"}):
            self.run_runner("--tier", "all")
            (self.root / "packages/a/shared.py").write_text("changed")
            out = self.run_runner("--tier", "all")[1]
            self.assertIn("[ok] packages/b:", out)
            (self.root / "packages/aicore/shared.py").write_text("changed foundation")
            out = self.run_runner("--tier", "all")[1]
            self.assertNotIn("[cached]", out)

    def test_python_symlink_target_and_in_place_executable_changes_invalidate_key(self):
        command = ["bash", "scripts/test.sh"]
        key = self.module.content_key(["packages/a"], command)
        with patch.object(sys, "version", "0.0.0 different interpreter"):
            self.assertNotEqual(key, self.module.content_key(["packages/a"], command))
        link = self.root / "packages/a/link"
        link.symlink_to("first")
        key = self.module.content_key(["packages/a"], command)
        link.unlink()
        link.symlink_to("second")
        self.assertNotEqual(key, self.module.content_key(["packages/a"], command))
        tool = self.root / "custom-tool"
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
        key = self.module.content_key(["packages/a"], [str(tool)])
        tool.write_text("#!/bin/sh\nexit 1\n")
        self.assertNotEqual(key, self.module.content_key(["packages/a"], [str(tool)]))


class AtomicCacheTests(unittest.TestCase):
    def test_eight_writers_never_expose_partial_json(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atomic.json"
            module._write_json_atomic(path, {})

            def writer(index):
                for iteration in range(100):
                    module._write_json_atomic(path, {"writer": index, "iteration": iteration})
                    self.assertIsInstance(json.loads(path.read_text()), dict)
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(writer, range(8)))
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_concurrent_merges_preserve_each_writers_receipts(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "durations.json"
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda n: module.merge_cache(path, {str(n): n}), range(100)))
            self.assertEqual(module.read_cache(path), {str(n): n for n in range(100)})


class PlannerRunnerTests(unittest.TestCase):
    def test_wrapper_has_one_discovery_forwards_pattern_and_rejects_missing_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "python3"
            fake.write_text('''#!/bin/bash
if [[ "$*" == *"import aicore.util.par_unittest"* ]]; then exit 0; fi
printf '%s\\n' "$*" >> "$DISCOVERY_LOG"
echo 'stub discovery complete'
''')
            fake.chmod(0o755)
            log = root / "discovery.log"
            hub = SCRIPT.parents[1]
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                   "AICORE_ROOT": str(hub / "packages/aicore"), "DISCOVERY_LOG": str(log)}
            wrapper = hub / "packages/planner/scripts/test.sh"
            for args, pattern in (([], "test_*.py"), (["-p", "test_check.py"], "test_check.py")):
                done = subprocess.run(["bash", str(wrapper), *args], capture_output=True, text=True, env=env)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.count("== tests"), 1)
                self.assertEqual(log.read_text().splitlines(),
                                 ["-m aicore.util.par_unittest discover -s tests -p " + pattern])
                log.unlink()
            for args in (["-p"], ["-p", ""], ["-p", "-x"], ["unknown"]):
                done = subprocess.run(["bash", str(wrapper), *args], capture_output=True, text=True, env=env)
                self.assertEqual(done.returncode, 2)
                self.assertIn("usage:", done.stderr)
                self.assertFalse(log.exists())


class DispatchTests(RunnerFixture):
    def test_mixed_profiles_preserve_owner_and_declared_consumer_closure(self):
        docs = {"packages/planner": {"id": "planner", "dev": {"test": ["bash", "scripts/test.sh"]}},
                "packages/a": {"id": "a"}, "bridges/a-planner": {"id": "a-planner", "requires": [{"unit": "planner"}]}}
        test = self.root / "packages/planner/tests/test_one.py"
        test.parent.mkdir(parents=True)
        test.write_text("")
        paths = ["packages/planner/tests/test_one.py", "packages/a/lib/a/x.py"]
        folders, _ = self.module.select(docs, "aicore", set(), paths, "fast", False)
        subsets, explain = self.module.obligations(docs, folders, paths, "aicore", "fast")
        self.assertEqual(set(folders), set(docs))
        self.assertEqual(subsets, {})
        self.assertTrue(all(e["reason"] and e["inputs"] and e["context"] for e in explain))
        self.assertEqual(self.module.obligations(docs, folders, paths, "aicore", "full")[0], {})
        paths.append("packages/planner/tests/shared_fixture.py")
        self.assertEqual(self.module.obligations(docs, folders, paths, "aicore", "fast")[0], {})
        test.unlink()  # deleted test cannot justify an empty subset
        self.assertEqual(self.module.obligations(docs, folders, paths[:2], "aicore", "fast")[0], {})

    def test_broad_mixed_diffs_never_narrow_mapped_leaf_consumers(self):
        docs = {"packages/aicore": {"id": "aicore"},
                "packages/runtime": {"id": "runtime"},
                **{f"packages/{name}": {"id": name, "requires": [{"unit": "runtime"}],
                     "dev": {"test": ["bash", "scripts/test.sh"]}} for name in ("planner", "orch")}}
        for name in ("planner", "orch"):
            leaf = f"packages/{name}/tests/test_one.py"
            test = self.root / leaf
            test.parent.mkdir(parents=True)
            test.write_text("")
            for other, reason in (("packages/aicore/lib/aicore/util/foo.py", "foundation"),
                                  ("packages/runtime/lib/runtime/foo.py", "mixed"),
                                  ("mystery/file.txt", "unknown hub"),
                                  ("scripts/schema-types.py", "unknown hub")):
                with self.subTest(name=name, other=other):
                    paths = [other, leaf]
                    folders, hub = self.module.select(docs, "aicore", set(), paths, "fast", False)
                    subsets, explain = self.module.obligations(docs, folders, paths, "aicore", "fast")
                    self.assertEqual(subsets, {})
                    selected = next(e for e in explain if e["folder"] == f"packages/{name}")
                    self.assertEqual(selected["obligation"], "full-suite")
                    self.assertIn(reason, selected["reason"])
                    commands = self.module.commands(docs, folders, hub, "fast", paths, subsets)
                    self.assertEqual(next(argv for f, argv in commands if f == f"packages/{name}"),
                                     [["bash", "scripts/test.sh"]])

    def test_pure_mapped_leaf_diff_keeps_subsets_and_full_consumer_contracts(self):
        for name in ("planner", "orch"):
            with self.subTest(name=name):
                folder = f"packages/{name}"
                paths = [folder + "/tests/test_one.py", folder + "/tests/test_two.py"]
                for path in paths:
                    test = self.root / path
                    test.parent.mkdir(parents=True, exist_ok=True)
                    test.write_text("")
                docs = {folder: {"id": name, "dev": {"test": ["bash", "scripts/test.sh"]}},
                        "bridges/consumer": {"id": "consumer", "requires": [{"unit": name}],
                                             "dev": {"test": ["bash", "scripts/test.sh"]}}}
                folders, hub = self.module.select(docs, "aicore", set(), paths, "fast", False)
                subsets, explain = self.module.obligations(docs, folders, paths, "aicore", "fast")
                self.assertEqual(subsets, {folder: [["bash", "scripts/test.sh", "-p", Path(p).name] for p in paths]})
                self.assertEqual({e["folder"]: e["obligation"] for e in explain},
                                 {folder: "explicit-subset", "bridges/consumer": "full-suite"})
                self.assertIn("known test-file subset", next(e for e in explain if e["folder"] == folder)["reason"])
                commands = self.module.commands(docs, folders, hub, "fast", paths, subsets)
                self.assertEqual(next(argv for f, argv in commands if f == "bridges/consumer"),
                                 [["bash", "scripts/test.sh"]])

    def test_imported_test_file_is_a_shared_fixture_and_requires_full_suite(self):
        folder = self.root / "packages/planner"
        (folder / "tests").mkdir(parents=True)
        (folder / "tests/test_fixture.py").write_text("class Helper: pass\n")
        (folder / "tests/test_consumer.py").write_text("from .test_fixture import Helper\n")
        docs = {"packages/planner": {"id": "planner", "dev": {"test": ["bash", "scripts/test.sh"]}}}
        subsets, _ = self.module.obligations(docs, list(docs), ["packages/planner/tests/test_fixture.py"], "aicore", "fast")
        self.assertEqual(subsets, {})
        (folder / "tests/test_consumer.py").write_text("")
        docs["bridges/consumer"] = {"requires": [{"unit": "planner"}, {"unit": "unknown-partner"}]}
        subsets, _ = self.module.obligations(docs, list(docs), ["packages/planner/tests/test_fixture.py"], "aicore", "fast")
        self.assertEqual(subsets, {})

    def test_foundation_bridge_generator_unknown_and_product_inputs_fall_back_safely(self):
        docs = self.module.units()
        docs["packages/a"]["id"] = "aicore"
        docs["bridges/a-b"] = {"requires": [{"unit": "b"}]}
        for path in ("packages/a/lib/x.py", "scripts/schema-types.py", "mystery/file.txt", "bootstrap/x.md"):
            self.assertEqual(set(self.module.select(docs, "aicore", set(), [path], "fast", False)[0]), set(docs))
        self.assertEqual(self.module.select(docs, "aicore", set(), ["bridges/a-b/x.py"], "fast", False)[0], ["bridges/a-b"])
        for path in ("packages/b/skills/readme.md", "packages/b/templates/page.md", "packages/b/tests/helper.py"):
            self.assertEqual(self.module.profile(docs, "aicore", path), "unknown")

    def test_base_and_status_include_both_rename_owners_deletions_and_untracked(self):
        git = ["git", "-C", str(self.root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
        source = self.root / "packages/a/old.py"
        source.write_text("rename candidate\n" * 30)
        deleted = self.root / "packages/b/deleted.py"
        deleted.write_text("deleted")
        subprocess.run(git + ["add", "."], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "initial"], check=True, capture_output=True)
        subprocess.run(git + ["mv", "packages/a/old.py", "packages/b/new.py"], check=True, capture_output=True)
        deleted.unlink()
        (self.root / "packages/a/untracked.py").write_text("new")
        import argparse
        expected = {"packages/a/old.py", "packages/b/new.py", "packages/b/deleted.py", "packages/a/untracked.py"}
        for base in (None, "HEAD"):
            paths = self.module.changed_paths(argparse.Namespace(paths=None, base=base))
            self.assertEqual(set(paths), expected)


if __name__ == "__main__":
    unittest.main()
