from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest

from orch import adhoc
from orch.cli import main
from orch.contracts import canonical_digest, validate

ROOT = Path(__file__).resolve().parents[1]


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as stop:  # argparse usage errors
            code = int(stop.code)
    return code, out.getvalue(), err.getvalue()


class AdhocTests(unittest.TestCase):
    def test_check_input_is_valid(self):
        doc = adhoc.build_adhoc_input("Fix typo", ["README.md"], checks=["V1=python3 -c 'print(1)'"])
        self.assertEqual([i for i in validate(doc, "execution-input") if i.level == "error"], [])
        check = doc["acceptance"]["checks"][0]
        self.assertEqual((check["cmd"], check["expect"], check["kind"]), ("python3 -c 'print(1)'", "exit 0", "acceptance"))
        self.assertEqual(doc["provenance"], {"kind": "adhoc", "request": "Fix typo", "created_by": "owner"})
        self.assertEqual(doc["route"]["minimum"], {"class": "implementation", "effort": "high"})
        self.assertIn("checks_run", doc["result_contract"]["report"])
        self.assertEqual(doc["result_contract"]["write_authority"], "code_scope")

    def test_identity_follows_digest(self):
        doc = adhoc.build_adhoc_input("Goal", ["a"], procedures=["V1=Looks right"])
        self.assertEqual(doc["digest"], canonical_digest(doc))
        self.assertEqual(doc["input_id"], "adhoc@" + doc["digest"][:12])
        self.assertEqual(doc, adhoc.build_adhoc_input("Goal", ["a"], procedures=["V1=Looks right"]))

    def test_expect_and_route_overrides(self):
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(ROOT)
        doc = adhoc.build_adhoc_input("Goal", ["a"], checks=["V1=true"], procedures=["V2=Looks right"],
                                      expect="exit 3", route={"effort": "low"}, why="Because", reads=["README.md", "nope.txt"])
        self.assertEqual([c["expect"] for c in doc["acceptance"]["checks"]], ["exit 3", "observed"])
        self.assertEqual(doc["route"]["minimum"], {"class": "implementation", "effort": "low"})
        self.assertEqual(doc["why"], "Because")
        self.assertEqual([r["exists"] for r in doc["reads"]], [True, False])

    def test_review_variant_is_read_only(self):
        doc = adhoc.build_adhoc_input(None, [], review="main..feature/x")
        self.assertEqual(doc["provenance"], {"kind": "review", "base": "main", "head": "feature/x",
                                             "target": "diff main..feature/x"})
        self.assertIs(doc["scope"]["read_only"], True)
        self.assertEqual(doc["result_contract"]["write_authority"], "none")
        self.assertEqual(doc["scope"]["include"], ["diff main..feature/x"])
        self.assertEqual(doc["acceptance"]["checks"][0]["procedure"], adhoc.REVIEW_PROCEDURE)
        self.assertEqual([i for i in validate(doc, "execution-input") if i.level == "error"], [])

    def test_acceptance_is_mandatory(self):
        with self.assertRaises(adhoc.AdhocError) as caught:
            adhoc.build_adhoc_input("Goal", ["a"])
        self.assertEqual(caught.exception.code, "USAGE")

    def test_usage_errors(self):
        for kwargs in (dict(goal="", include=["a"], procedures=["V1=x"]),
                       dict(goal="g", include=[], procedures=["V1=x"]),
                       dict(goal="g", include=["a"], procedures=["x"]),
                       dict(goal="g", include=["a"], checks=["V1="]),
                       dict(goal="g", include=["a"], checks=["V1=a", "V1=b"]),
                       dict(goal="g", include=["a"], procedures=["V1=x"], review="main")):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(adhoc.AdhocError) as caught:
                    adhoc.build_adhoc_input(**kwargs)
                self.assertEqual(caught.exception.code, "USAGE")

    def test_cli_prints_valid_json(self):
        code, out, _ = run("input", "adhoc", "--goal", "Fix typo", "--include", "README.md", "--procedure", "V1=Reads fine")
        self.assertEqual(code, 0)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "input.json"
            target.write_text(out, encoding="utf-8")
            self.assertEqual(run("validate", "execution-input", str(target), "--quiet")[0], 0)

    def test_cli_review_and_checks(self):
        code, out, _ = run("input", "adhoc", "--review", "a..b")
        self.assertEqual((code, json.loads(out)["provenance"]["kind"]), (0, "review"))
        code, out, _ = run("input", "adhoc", "--goal", "g", "--include", "x", "y", "--check", "V1=true", "--expect", "exit 0")
        self.assertEqual((code, json.loads(out)["scope"]["include"]), (0, ["x", "y"]))

    def test_cli_exit_codes(self):
        code, _, err = run("input", "adhoc", "--goal", "g", "--include", "x")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("USAGE: "))
        self.assertEqual(run("input", "adhoc", "--bogus")[0], 2)

    def test_cli_render_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "input.json"
            target.write_text(run("input", "adhoc", "--goal", "g", "--include", "x", "--procedure", "V1=ok")[1], encoding="utf-8")
            code, out, _ = run("render-prompt", "--input", str(target), "--role", "executor")
            self.assertEqual(code, 0)
            self.assertTrue(out.startswith("# Executor"))
            self.assertIn("\n---\n\n## Goal\n\ng\n", out)
            self.assertEqual(run("render-prompt", "--input", str(target), "--role", "nope")[0], 1)
            self.assertEqual(run("render-prompt", "--input", str(Path(tmp) / "missing.json"), "--role", "executor")[0], 1)


if __name__ == "__main__":
    unittest.main()
