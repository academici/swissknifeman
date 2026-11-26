#!/usr/bin/env python3
"""Tests of scripts/typecheck.sh: the pin, the per-package baseline and the strict paths, on a fixture hub whose
`pyright` is a stand-in that prints a recorded JSON report (pyright itself never runs here)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
SCRIPT = HUB / "scripts/typecheck.sh"
PIN = "1.1.414"
STRICT_FILE = "packages/alpha/lib/alpha/typed.py"

CONFIG = {
    "include": ["packages/alpha/lib", "packages/beta/lib", "packages/clean/lib"],
    "strict": [STRICT_FILE, "packages/beta/lib/beta/_types"],
    "typeCheckingMode": "basic",
}

# a pyright stand-in: --version answers its version, anything else prints the recorded report; the arguments are logged
STUB = """#!/bin/bash
echo "$@" >> "$STUB_LOG"
if [ "${1:-}" = "--version" ]; then echo "pyright @VERSION@"; exit 0; fi
if [ "@FORWARD@" = "1" ]; then shift; fi   # uvx pyright==V ... / pipx run pyright==V ...
if [ "${1:-}" = "run" ]; then shift; fi
shift
cat "$STUB_REPORT"
exit 1
"""


def diagnostic(root: Path, path: str, line: int, message: str, severity: str = "error") -> dict:
    return {"file": str(root / path), "severity": severity, "message": message,
            "range": {"start": {"line": line - 1, "character": 0}, "end": {"line": line - 1, "character": 1}},
            "rule": "reportArgumentType"}


class Fixture:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "hub"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "configs").mkdir()
        shutil.copy(SCRIPT, self.root / "scripts/typecheck.sh")
        self.write_json("pyrightconfig.json", CONFIG)
        self.bin = Path(self._tmp.name) / "bin"
        self.bin.mkdir()
        self.log = Path(self._tmp.name) / "calls.log"
        self.report = Path(self._tmp.name) / "report.json"
        for tool in ("python3", "dirname", "grep", "head", "mktemp", "rm", "cat"):  # what the script itself needs
            os.symlink(shutil.which(tool) or tool, self.bin / tool)
        self.set_report([])

    def close(self) -> None:
        self._tmp.cleanup()

    def write_json(self, rel: str, doc: object) -> None:
        (self.root / rel).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def baseline(self, errors: dict, pyright: str = PIN) -> None:
        self.write_json("configs/typecheck-baseline.json", {"pyright": pyright, "mode": "basic", "errors": errors})

    def baseline_doc(self) -> dict:
        return json.loads((self.root / "configs/typecheck-baseline.json").read_text(encoding="utf-8"))

    def set_report(self, diagnostics: list) -> None:
        self.report.write_text(json.dumps({"version": PIN, "generalDiagnostics": diagnostics}), encoding="utf-8")

    def tool(self, name: str, version: str = PIN, forward: bool = False) -> None:
        """Put an executable `name` on PATH that behaves like pyright (``forward``: like uvx / pipx run)."""
        path = self.bin / name
        path.write_text(STUB.replace("@VERSION@", version).replace("@FORWARD@", "1" if forward else "0"), encoding="utf-8")
        path.chmod(0o755)

    def run(self, *args: str) -> subprocess.CompletedProcess:
        env = {"PATH": str(self.bin), "HOME": str(self.root), "TMPDIR": self._tmp.name, "STUB_LOG": str(self.log),
               "STUB_REPORT": str(self.report)}
        return subprocess.run([shutil.which("bash") or "bash", str(self.root / "scripts/typecheck.sh"), *args], cwd=str(self.root), env=env,
                              capture_output=True, text=True, timeout=60)

    def calls(self) -> list:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


class TypecheckGateTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)
        self.fx.tool("pyright")
        root = self.fx.root
        # alpha: two errors and a warning; beta: one error; clean: none; the strict file is clean unless a test adds to it
        self.base = [
            diagnostic(root, "packages/alpha/lib/alpha/a.py", 3, "Argument of type \"int\"\n  detail line"),
            diagnostic(root, "packages/alpha/lib/alpha/b.py", 9, "\"x\" is possibly unbound"),
            diagnostic(root, "packages/alpha/lib/alpha/b.py", 12, "Expression value is unused", severity="warning"),
            diagnostic(root, "packages/beta/lib/beta/c.py", 1, "Import \"nope\" could not be resolved"),
        ]
        self.fx.set_report(self.base)

    # -- counting and comparing
    def test_counts_errors_per_package_and_ignores_warnings(self):
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("typecheck: ok (alpha 2, beta 1, clean 0)", out.stdout)
        self.assertIn("--outputjson", self.fx.calls()[-1])  # the report is JSON of the config in the hub root

    def test_growth_of_one_package_is_a_regression_with_both_numbers(self):
        self.fx.baseline({"alpha": 1, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_REGRESSION: alpha 1 -> 2", out.stderr)
        self.assertNotIn("beta", out.stderr)

    def test_a_package_missing_from_the_baseline_counts_from_zero(self):
        self.fx.baseline({"alpha": 2, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_REGRESSION: beta 0 -> 1", out.stderr)

    def test_a_smaller_count_is_an_improvement_not_a_failure(self):
        self.fx.baseline({"alpha": 5, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("TYPECHECK_IMPROVED: alpha 5 -> 2", out.stdout)

    def test_an_improvement_does_not_hide_a_regression_elsewhere(self):
        self.fx.baseline({"alpha": 5, "beta": 0, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_IMPROVED: alpha 5 -> 2", out.stdout)
        self.assertIn("TYPECHECK_REGRESSION: beta 0 -> 1", out.stderr)

    # -- strict paths
    def test_an_error_in_a_strict_file_fails_with_its_position_and_is_not_counted_in_the_package(self):
        self.fx.set_report(self.base + [diagnostic(self.fx.root, STRICT_FILE, 7, "Type of \"x\" is unknown\n  more")])
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn(f"TYPECHECK_STRICT: {STRICT_FILE}:7: Type of \"x\" is unknown", out.stderr)
        self.assertNotIn("TYPECHECK_REGRESSION", out.stderr)

    def test_a_strict_directory_covers_the_files_below_it(self):
        self.fx.set_report(self.base + [diagnostic(self.fx.root, "packages/beta/lib/beta/_types/x.py", 2, "bad")])
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_STRICT: packages/beta/lib/beta/_types/x.py:2: bad", out.stderr)

    def test_a_file_next_to_a_strict_directory_name_is_not_strict(self):
        self.fx.set_report(self.base + [diagnostic(self.fx.root, "packages/beta/lib/beta/_types_old.py", 2, "bad")])
        self.fx.baseline({"alpha": 2, "beta": 2, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 0, out.stderr)

    # -- the baseline file
    def test_a_missing_baseline_fails_in_baseline_mode(self):
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_BASELINE_MISSING", out.stderr)

    def test_a_baseline_of_another_pyright_version_is_not_comparable(self):
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0}, pyright="1.1.400")
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_BASELINE_VERSION", out.stderr)
        self.assertIn("1.1.400", out.stderr)

    def test_a_broken_baseline_file_is_reported(self):
        (self.fx.root / "configs/typecheck-baseline.json").write_text("{not json", encoding="utf-8")
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_BASELINE_INVALID", out.stderr)

    def test_no_json_report_is_a_failure_not_a_green_run(self):
        self.fx.report.write_text("Traceback: pyright crashed", encoding="utf-8")
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_NO_REPORT", out.stderr)

    # -- --update-baseline
    def test_update_writes_only_smaller_numbers(self):
        self.fx.baseline({"alpha": 5, "beta": 1, "clean": 0})
        out = self.fx.run("--update-baseline")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.fx.baseline_doc(), {"pyright": PIN, "mode": "basic",
                                                  "errors": {"alpha": 2, "beta": 1, "clean": 0}})
        self.assertIn("TYPECHECK_BASELINE: alpha 5 -> 2", out.stdout)

    def test_update_refuses_growth_and_leaves_the_file_alone(self):
        self.fx.baseline({"alpha": 1, "beta": 1, "clean": 0})
        before = (self.fx.root / "configs/typecheck-baseline.json").read_bytes()
        out = self.fx.run("--update-baseline")
        self.assertEqual(out.returncode, 1)
        self.assertIn("TYPECHECK_REGRESSION: alpha 1 -> 2", out.stderr)
        self.assertEqual((self.fx.root / "configs/typecheck-baseline.json").read_bytes(), before)

    def test_update_takes_growth_with_a_reason_and_prints_it(self):
        self.fx.baseline({"alpha": 1, "beta": 4, "clean": 0})
        out = self.fx.run("--update-baseline", "--allow-growth", "new module alpha")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.fx.baseline_doc()["errors"], {"alpha": 2, "beta": 1, "clean": 0})
        self.assertIn("TYPECHECK_BASELINE_REASON: new module alpha", out.stdout)

    def test_the_first_baseline_needs_a_reason(self):
        out = self.fx.run("--update-baseline")
        self.assertEqual(out.returncode, 1)
        self.assertFalse((self.fx.root / "configs/typecheck-baseline.json").exists())
        out = self.fx.run("--update-baseline", "--allow-growth", "initial baseline")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.fx.baseline_doc()["errors"], {"alpha": 2, "beta": 1, "clean": 0})

    def test_update_does_not_write_while_a_strict_path_has_errors(self):
        self.fx.set_report(self.base + [diagnostic(self.fx.root, STRICT_FILE, 7, "bad")])
        self.fx.baseline({"alpha": 9, "beta": 9, "clean": 0})
        out = self.fx.run("--update-baseline", "--allow-growth", "r")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(self.fx.baseline_doc()["errors"]["alpha"], 9)

    def test_usage_errors_exit_two(self):
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        for argv in (["--allow-growth"], ["--allow-growth", ""], ["--allow-growth", "why"],
                     ["--baseline", "--allow-growth", "why"], ["--baseline", "src"]):
            out = self.fx.run(*argv)
            self.assertEqual(out.returncode, 2, (argv, out.stderr))
            self.assertIn("TYPECHECK_USAGE", out.stderr)

    # -- the pin
    def test_without_a_gate_flag_pyright_runs_as_before_with_the_given_arguments(self):
        out = self.fx.run("--version")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.fx.calls()[-1], "--version")

    def test_a_pyright_of_another_version_on_path_is_not_used(self):
        self.fx.tool("pyright", version="1.1.500")
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 2)
        self.assertIn("TYPECHECK_TOOL_MISSING", out.stderr)
        self.assertNotIn("--outputjson", " ".join(self.fx.calls()))  # only the version probe ran

    def test_uvx_is_asked_for_the_pinned_version_when_path_has_another_one(self):
        self.fx.tool("pyright", version="1.1.500")
        self.fx.tool("uvx", forward=True)
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 0, out.stderr)
        calls = self.fx.calls()
        self.assertTrue(any(c.startswith(f"pyright=={PIN} ") or c == f"pyright=={PIN}" for c in calls), calls)

    def test_pipx_run_is_the_last_resort(self):
        (self.fx.bin / "pyright").unlink()
        self.fx.tool("pipx", forward=True)
        self.fx.baseline({"alpha": 2, "beta": 1, "clean": 0})
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(any(c.startswith(f"run pyright=={PIN}") for c in self.fx.calls()), self.fx.calls())

    def test_no_tool_at_all_is_exit_two(self):
        (self.fx.bin / "pyright").unlink()
        out = self.fx.run("--baseline")
        self.assertEqual(out.returncode, 2)
        self.assertIn("TYPECHECK_TOOL_MISSING", out.stderr)


class RealHubTests(unittest.TestCase):
    """The committed config and baseline of this hub (no pyright run)."""

    STRICT = ["packages/orch/lib/orch/_types", "packages/planner/lib/planner/plan/_types.py",
              *(f"packages/aicore/lib/aicore/util/{name}.py" for name in ("lock", "timefmt", "docio", "schemacodegen", "schemacli"))]

    def config(self) -> dict:
        return json.loads((HUB / "pyrightconfig.json").read_text(encoding="utf-8"))

    def libs(self) -> list:
        return sorted(p.parent.name for p in (HUB / "packages").glob("*/lib") if p.is_dir())

    def test_the_pin_is_one_version_in_the_script_and_the_baseline(self):
        baseline = json.loads((HUB / "configs/typecheck-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["pyright"], PIN)
        self.assertEqual(baseline["mode"], "basic")
        self.assertIn(f'PYRIGHT_VERSION="{PIN}"', SCRIPT.read_text(encoding="utf-8"))

    def test_every_lib_of_the_hub_is_checked(self):
        config = self.config()
        self.assertEqual(sorted(config["include"]), [f"packages/{name}/lib" for name in self.libs()])
        self.assertEqual(config["typeCheckingMode"], "basic")

    def test_the_baseline_counts_exactly_the_checked_packages(self):
        baseline = json.loads((HUB / "configs/typecheck-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(baseline["errors"]), self.libs())
        self.assertTrue(all(isinstance(n, int) and n >= 0 for n in baseline["errors"].values()))

    def test_the_strict_list_is_the_generated_types_and_the_new_aicore_modules(self):
        self.assertEqual(sorted(self.config().get("strict", [])), sorted(self.STRICT))
        for path in self.STRICT:
            self.assertTrue((HUB / path).exists(), path)


if __name__ == "__main__":
    unittest.main()
