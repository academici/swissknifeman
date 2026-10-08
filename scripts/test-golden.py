#!/usr/bin/env python3
"""Tests of scripts/golden.py: normalization rules, fixture format, check/capture on a temporary tree.

The command runner is injected (a fake), so no sandbox is created; only the last class runs the real
tool on the real fixtures without executing a case (list).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "golden.py"

spec = importlib.util.spec_from_file_location("golden", SCRIPT)
golden = importlib.util.module_from_spec(spec)
sys.modules["golden"] = golden
spec.loader.exec_module(golden)

CASES_DOC = json.loads((ROOT / "tests" / "golden" / "cases.json").read_text(encoding="utf-8"))
RULES = {r["name"]: r for r in CASES_DOC["normalize"]}
CONTEXT = {"repo": "/work/repo", "sandbox": "/tmp/skm-sandbox-golden-42", "home": "/home/someone"}


def norm(name: str, text: str) -> str:
    return golden.normalize(text, [RULES[name]], CONTEXT)


class NormalizeTests(unittest.TestCase):
    def test_every_rule_has_a_reason_and_a_test(self):
        tested = {"repo-path", "sandbox-path", "home-path", "sha256", "git-sha-paren", "git-sha-after-version",
                  "iso-time"}
        self.assertEqual(set(RULES), tested)
        golden.validate_rules(CASES_DOC["normalize"])

    def test_rule_without_reason_is_refused(self):
        with self.assertRaises(golden.GoldenError):
            golden.validate_rules([{"name": "x", "type": "regex", "pattern": "a", "replace": "b"}])

    def test_paths(self):
        self.assertEqual(norm("repo-path", "see /work/repo/bin/x"), "see <REPO>/bin/x")
        self.assertEqual(norm("sandbox-path", "in /tmp/skm-sandbox-golden-42/home"), "in <SANDBOX>/home")
        self.assertEqual(norm("home-path", "at /home/someone/.cache"), "at <HOME>/.cache")

    def test_empty_context_value_changes_nothing(self):
        self.assertEqual(golden.normalize("abc", [RULES["sandbox-path"]], {"repo": "", "sandbox": "", "home": ""}),
                         "abc")

    def test_sha256(self):
        digest = "a" * 64
        self.assertEqual(norm("sha256", f"hash {digest}."), "hash <SHA256>.")
        self.assertEqual(norm("sha256", "b" * 63), "b" * 63)

    def test_git_sha(self):
        self.assertEqual(norm("git-sha-paren", "v1.2.3 (abc1234)"), "v1.2.3 (<SHA>)")
        self.assertEqual(norm("git-sha-paren", "(hello)"), "(hello)")
        self.assertEqual(norm("git-sha-after-version", "tool v1.2.3+deadbeef1234 ok"), "tool v1.2.3+<SHA> ok")
        self.assertEqual(norm("git-sha-after-version", "version 1.2.3 stays"), "version 1.2.3 stays")

    def test_timestamp(self):
        self.assertEqual(norm("iso-time", "at 2026-10-08T04:27:12Z and 2026-10-08T04:27:12.5"), "at <TS> and <TS>")

    def test_rule_order_matters_repo_before_home(self):
        rules = [RULES["repo-path"], RULES["home-path"]]
        ctx = {"repo": "/home/someone/repo", "sandbox": "", "home": "/home/someone"}
        self.assertEqual(golden.normalize("/home/someone/repo/x /home/someone/y", rules, ctx), "<REPO>/x <HOME>/y")

    def test_unknown_rule_type(self):
        with self.assertRaises(golden.GoldenError):
            golden.normalize("a", [{"type": "nope"}], CONTEXT)


class FormatTests(unittest.TestCase):
    def test_fixture_format(self):
        self.assertEqual(golden.render_fixture(2, "out", "err"), "exit: 2\n--- stdout ---\nout\n--- stderr ---\nerr\n")

    def test_expand(self):
        self.assertEqual(golden.expand("{SANDBOX}/plans {REPO}", CONTEXT), "/tmp/skm-sandbox-golden-42/plans /work/repo")

    def test_glob(self):
        match = lambda pat, path: bool(golden.glob_regex(pat).match(path))
        self.assertTrue(match("a/*/x.json", "a/b/x.json"))
        self.assertFalse(match("a/*/x.json", "a/b/c/x.json"))
        self.assertTrue(match("a/**", "a/b/c/x.json"))
        self.assertTrue(match("**/x.json", "x.json"))
        self.assertTrue(match("**/x.json", "p/q/x.json"))
        self.assertFalse(match("a/x.json", "a/xjson"))

    def test_real_fixtures_are_clean_and_enough(self):
        ids = [c["id"] for c in CASES_DOC["cases"]]
        self.assertGreaterEqual(len(ids), 18)
        self.assertEqual(len(ids), len(set(ids)))
        for case_id in ids:
            text = (ROOT / "tests" / "golden" / "cli" / f"{case_id}.txt").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("exit: "), case_id)
            self.assertIn("\n--- stdout ---\n", text)
            self.assertIn("\n--- stderr ---\n", text)
            self.assertNotIn("/home/", text, case_id)
            self.assertNotIn("skm-sandbox", text, case_id)


class FakeRunner:
    def __init__(self, outputs=None, rc_by_argv=None):
        self.outputs = outputs or {}
        self.calls = []
        self.rc_by_argv = rc_by_argv or {}

    def run(self, argv, stdin=None, timeout=0, cwd=None, env=None):
        self.calls.append((list(argv), cwd, env))
        out = self.outputs.get(argv[0], "")
        if callable(out):
            out = out()
        return self.rc_by_argv.get(argv[0], 0), out, ""


def make_tree(tmp: Path) -> Path:
    root = tmp / "repo"
    (root / "tests" / "golden" / "cli").mkdir(parents=True)
    (root / "gen").mkdir()
    (root / "gen" / "out.txt").write_text("generated\n", encoding="utf-8")
    cases = {"schema": "golden-cases/v1", "captured_from": "", "reason": "", "setup": [],
             "normalize": [{"name": "repo-path", "type": "repo", "token": "<REPO>", "reason": "test"}],
             "cases": [{"id": "one", "argv": ["tool-one"]}, {"id": "two", "argv": ["tool-two"]}]}
    generation = {"schema": "golden-generation/v1", "captured_from": "", "reason": "", "digests": {},
                  "generators": [{"id": "gen", "check_argv": ["gen-check"], "outputs": ["gen/*.txt"]}]}
    (root / "tests" / "golden" / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    (root / "tests" / "golden" / "generation.json").write_text(json.dumps(generation), encoding="utf-8")
    run = lambda *a: subprocess.run(a, cwd=root, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "add", "-A")
    run("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return root


class CommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_tree(Path(self._tmp.name))
        self.runner = FakeRunner({"tool-one": "one output", "tool-two": "two output"})

    def factory(self, runner=None):
        @contextmanager
        def make(root, setup):
            yield (runner or self.runner), "/tmp/skm-sandbox-golden-1"
        return make

    def capture(self, reason="test capture", only="", runner=None):
        return golden.cmd_capture(self.root, Namespace(only=only, reason=reason), self.factory(runner))

    def check(self, only="", runner=None):
        return golden.cmd_check(self.root, Namespace(only=only), self.factory(runner))

    def test_capture_writes_fixtures_reason_and_sha(self):
        self.assertEqual(self.capture(), 0)
        cases = json.loads((self.root / "tests/golden/cases.json").read_text())
        generation = json.loads((self.root / "tests/golden/generation.json").read_text())
        self.assertEqual(cases["reason"], "test capture")
        self.assertRegex(cases["captured_from"], r"^[0-9a-f]{12}$")
        self.assertEqual(generation["reason"], "test capture")
        self.assertEqual(list(generation["digests"]), ["gen/out.txt"])
        self.assertEqual((self.root / "tests/golden/cli/one.txt").read_text(),
                         "exit: 0\n--- stdout ---\none output\n--- stderr ---\n\n")

    def test_capture_without_reason_is_usage_error(self):
        with self.assertRaises(golden.GoldenError):
            self.capture(reason=" ")

    def test_check_matches_after_capture(self):
        self.capture()
        # capture rewrote tracked json files: commit them so the tree is the same before and after the check
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"], cwd=self.root,
                       check=True, capture_output=True)
        self.assertEqual(self.check(), 0)

    def test_check_reports_changed_output_with_diff_and_exit_1(self):
        self.capture()
        runner = FakeRunner({"tool-one": "changed", "tool-two": "two output"})
        import io
        from contextlib import redirect_stderr
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            code = self.check(runner=runner)
        self.assertEqual(code, 1)
        self.assertIn("one: output differs", buffer.getvalue())
        self.assertIn("-one output", buffer.getvalue())
        self.assertIn("+changed", buffer.getvalue())
        self.assertNotIn("two:", buffer.getvalue())

    def test_check_only_limits_cases(self):
        self.capture()
        runner = FakeRunner({"tool-one": "one output", "tool-two": "CHANGED"})
        self.assertEqual(self.check(only="one", runner=runner), 0)
        self.assertEqual(self.check(only="two", runner=runner), 1)

    def test_unknown_only_id(self):
        with self.assertRaises(golden.GoldenError):
            self.check(only="nope")

    def test_missing_fixture_is_a_mismatch(self):
        self.capture()
        (self.root / "tests/golden/cli/one.txt").unlink()
        self.assertEqual(self.check(), 1)

    def test_capture_refuses_unstable_case_and_writes_nothing(self):
        counter = iter(range(100))
        runner = FakeRunner({"tool-one": lambda: f"run {next(counter)}", "tool-two": "stable"})
        self.assertEqual(self.capture(runner=runner), 1)
        self.assertFalse((self.root / "tests/golden/cli/two.txt").exists())
        self.assertFalse((self.root / "tests/golden/cli/one.txt").exists())

    def test_generator_part_catches_a_changed_byte(self):
        self.capture()
        (self.root / "gen/out.txt").write_text("generateD\n", encoding="utf-8")
        self.assertEqual(self.check(only="gen"), 1)

    def test_generator_part_catches_new_and_vanished_file(self):
        self.capture()
        (self.root / "gen/new.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "gen/new.txt"], cwd=self.root, check=True)
        self.assertEqual(self.check(only="gen"), 1)
        subprocess.run(["git", "rm", "-qf", "gen/new.txt", "gen/out.txt"], cwd=self.root, check=True)
        self.assertEqual(self.check(only="gen"), 1)

    def test_generator_check_failure_is_a_mismatch_and_blocks_capture(self):
        failing = FakeRunner({"tool-one": "a", "tool-two": "b"}, rc_by_argv={"gen-check": 3})
        self.assertEqual(self.capture(runner=failing), 1)
        self.assertEqual(json.loads((self.root / "tests/golden/generation.json").read_text())["digests"], {})
        self.capture()
        self.assertEqual(self.check(only="gen", runner=failing), 1)

    def test_case_that_dirties_the_repository_is_an_environment_error(self):
        self.capture()
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"], cwd=self.root,
                       check=True, capture_output=True)
        root = self.root

        def dirty():
            (root / "stray.txt").write_text("x", encoding="utf-8")
            return "one output"
        with self.assertRaises(golden.GoldenError):
            self.check(runner=FakeRunner({"tool-one": dirty, "tool-two": "two output"}))


class CliTests(unittest.TestCase):
    def test_list_names_cases_and_generators(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "list"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("case\tskiller-help", proc.stdout)
        self.assertIn("generator\tskiller-registry", proc.stdout)

    def test_capture_requires_reason(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "capture"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--reason", proc.stderr)

    def test_no_command_is_usage_error(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
