#!/usr/bin/env python3
"""Tests of the aicore locator fragment copied into module wrappers and runners.

Real CLIs are never run here: the locator behaviour is checked on a synthetic script.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "packages/aicore/scripts/aicore-locator.sh"
START = "# --- aicore locator ---"
END = "# --- end aicore locator ---"
CARRIERS = [
    "packages/analyst/bin/analyst",
    "packages/brain/bin/brain",
    "packages/harness/bin/harness",
    "packages/maind/bin/maind",
    "packages/skiller/bin/skiller",
    "packages/analyst/scripts/test.sh",
    "packages/brain/scripts/test.sh",
    "packages/harness/scripts/test.sh",
    "packages/maind/scripts/test.sh",
    "packages/skiller/scripts/test.sh",
    "packages/harness/scripts/sync-usage.sh",
    "packages/harness/scripts/validate.sh",
    "packages/skiller/scripts/validate.sh",
    "packages/brain/scripts/e2e-plan-note.sh",
    "packages/skiller/scripts/generate-hub.sh",
    "packages/skiller/install.sh",
    "packages/planner/scripts/validate.sh",
    "packages/orch/scripts/test.sh",
    "packages/orch/scripts/validate.sh",
]
PY_CANONICAL = ROOT / "packages/aicore/scripts/aicore_locator.py"
PY_START = "# --- aicore locator (python) ---"
PY_END = "# --- end aicore locator (python) ---"
PY_CARRIERS = [
    "packages/planner/scripts/plan.py",
    "packages/planner/scripts/render-provider-commands.py",
    "packages/orch/scripts/orch.py",
]


def blocks(text: str, start: str = START, end: str = END) -> list[str]:
    return re.findall(re.escape(start) + r".*?" + re.escape(end), text, re.S)


class CarrierTests(unittest.TestCase):
    def test_canonical_file_is_one_block(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        self.assertEqual(blocks(text), [text.rstrip("\n")])

    def test_each_carrier_has_exactly_one_identical_block(self) -> None:
        canonical = blocks(CANONICAL.read_text(encoding="utf-8"))[0]
        for name in CARRIERS:
            found = blocks((ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(len(found), 1, f"{name}: expected exactly one locator block")
            self.assertEqual(found[0], canonical, f"{name}: locator block differs from the canonical copy")

    def test_carriers_put_aicore_lib_on_pythonpath(self) -> None:
        for name in CARRIERS[:8]:
            self.assertIn("$AICORE_LIB", re.sub(r"(?s)" + re.escape(START) + ".*?" + re.escape(END), "",
                                                 (ROOT / name).read_text(encoding="utf-8")), name)


class PythonCarrierTests(unittest.TestCase):
    def test_canonical_file_is_one_block(self) -> None:
        text = PY_CANONICAL.read_text(encoding="utf-8")
        self.assertEqual(blocks(text, PY_START, PY_END), [text.rstrip("\n")])

    def test_each_carrier_has_exactly_one_identical_block(self) -> None:
        canonical = blocks(PY_CANONICAL.read_text(encoding="utf-8"), PY_START, PY_END)[0]
        for name in PY_CARRIERS:
            found = blocks((ROOT / name).read_text(encoding="utf-8"), PY_START, PY_END)
            self.assertEqual(len(found), 1, f"{name}: expected exactly one locator block")
            self.assertEqual(found[0], canonical, f"{name}: locator block differs from the canonical copy")


class PythonLocatorBehaviourTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skm-locator-py-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mods = self.tmp / "mods"
        self.module = self.mods / "m"
        self.module.mkdir(parents=True)
        self.block = blocks(PY_CANONICAL.read_text(encoding="utf-8"), PY_START, PY_END)[0]

    def make_aicore(self, path: Path, unit_id: str = "aicore") -> Path:
        path.mkdir(parents=True)
        (path / "unit.json").write_text('{"id": "%s"}\n' % unit_id, encoding="utf-8")
        return path

    def run_locator(self, **env: str) -> subprocess.CompletedProcess:
        script = f'{self.block}\nprint(_aicore_lib("{self.module}"))\n'
        base = {k: v for k, v in os.environ.items() if k != "AICORE_ROOT"}
        return subprocess.run([sys.executable, "-I", "-c", script], env={**base, **env},
                              capture_output=True, text=True, check=False)

    def test_valid_env_root_wins(self) -> None:
        explicit = self.make_aicore(self.tmp / "elsewhere")
        self.make_aicore(self.module / "_vendor" / "aicore")
        result = self.run_locator(AICORE_ROOT=str(explicit))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{explicit}/lib")

    def test_invalid_env_root_fails(self) -> None:
        self.make_aicore(self.mods / "aicore")
        result = self.run_locator(AICORE_ROOT=str(self.tmp / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AICORE_NOT_FOUND", result.stderr)

    def test_vendor_beats_sibling(self) -> None:
        vendor = self.make_aicore(self.module / "_vendor" / "aicore")
        self.make_aicore(self.mods / "aicore")
        result = self.run_locator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{vendor}/lib")

    def test_sibling_is_absolute(self) -> None:
        sibling = self.make_aicore(self.mods / "aicore")
        result = self.run_locator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{sibling}/lib")
        self.assertNotIn("..", result.stdout)

    def test_nothing_found_is_none(self) -> None:
        result = self.run_locator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "None")

    def test_other_unit_id_does_not_match(self) -> None:
        self.make_aicore(self.mods / "aicore", unit_id="skiller")
        result = self.run_locator()
        self.assertEqual(result.stdout.strip(), "None")

    def test_malformed_unit_json_does_not_match(self) -> None:
        sibling = self.make_aicore(self.mods / "aicore")
        (sibling / "unit.json").write_text("{not json", encoding="utf-8")
        result = self.run_locator()
        self.assertEqual(result.stdout.strip(), "None")


class LocatorBehaviourTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skm-locator-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mods = self.tmp / "mods"
        self.module = self.mods / "m"
        self.module.mkdir(parents=True)
        self.block = blocks(CANONICAL.read_text(encoding="utf-8"))[0]

    def make_aicore(self, path: Path, unit_id: str = "aicore") -> Path:
        path.mkdir(parents=True)
        (path / "unit.json").write_text('{"id": "%s"}\n' % unit_id, encoding="utf-8")
        return path

    def run_locator(self, **env: str) -> subprocess.CompletedProcess:
        script = f'set -euo pipefail\nREPO_ROOT="{self.module}"\n{self.block}\necho "$AICORE_ROOT|$AICORE_LIB"\n'
        base = {k: v for k, v in os.environ.items() if k != "AICORE_ROOT"}
        return subprocess.run(["bash", "-c", script], env={**base, **env}, capture_output=True,
                              text=True, check=False)

    def test_valid_env_root_wins(self) -> None:
        explicit = self.make_aicore(self.tmp / "elsewhere")
        self.make_aicore(self.module / "_vendor" / "aicore")
        result = self.run_locator(AICORE_ROOT=str(explicit))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{explicit}|{explicit}/lib")

    def test_invalid_env_root_fails(self) -> None:
        self.make_aicore(self.mods / "aicore")
        result = self.run_locator(AICORE_ROOT=str(self.tmp / "missing"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("AICORE_NOT_FOUND", result.stderr)

    def test_vendor_beats_sibling(self) -> None:
        vendor = self.make_aicore(self.module / "_vendor" / "aicore")
        self.make_aicore(self.mods / "aicore")
        result = self.run_locator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{vendor}|{vendor}/lib")

    def test_sibling_is_absolute(self) -> None:
        sibling = self.make_aicore(self.mods / "aicore")
        result = self.run_locator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{sibling}|{sibling}/lib")
        self.assertNotIn("..", result.stdout)

    def test_nothing_found_fails(self) -> None:
        result = self.run_locator()
        self.assertEqual(result.returncode, 2)
        self.assertIn("AICORE_NOT_FOUND", result.stderr)

    def test_other_unit_id_does_not_match(self) -> None:
        self.make_aicore(self.mods / "aicore", unit_id="skiller")
        result = self.run_locator()
        self.assertEqual(result.returncode, 2)
        self.assertIn("AICORE_NOT_FOUND", result.stderr)


if __name__ == "__main__":
    unittest.main()
