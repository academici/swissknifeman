"""``doctor.py``: the doctor row of the bridge says whether the planner and orch are found the way the bridge finds them."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import partners

BRIDGE = Path(partners.__file__).resolve().parent


def probe(env: dict) -> tuple:
    full = {key: value for key, value in os.environ.items()
            if key not in ("PLANNER_ROOT", "PLANNER_PLAN_PY", "SKM_ORCH_ROOT")}
    full["PATH"] = tempfile.gettempdir()  # no `planner` or `orch` command to fall back to
    full.update(env)
    done = subprocess.run([sys.executable, str(BRIDGE / "doctor.py")], capture_output=True, text=True, env=full,
                          cwd=tempfile.gettempdir(), check=False)
    return done.returncode, json.loads(done.stdout)[0]


class DoctorProbe(unittest.TestCase):
    @unittest.skipUnless(partners._hub_partner("planner", "scripts/plan.py") and
                         partners._hub_partner("orch", "scripts/orch.py"), "bridge has no hub partners")
    def test_bridge_uses_its_hub_without_path_or_root_variables(self):
        code, row = probe({})
        self.assertEqual((code, row["status"]), (0, "ok"))

    def test_missing_partners_are_a_fail_that_names_the_variables(self):
        code, row = probe({"PLANNER_ROOT": "/missing-planner", "SKM_ORCH_ROOT": "/missing-orch"})
        self.assertEqual((code, row["check_id"], row["status"]), (0, "planner-orch.partners", "fail"))
        self.assertIn("PLANNER_ROOT", row["observed"])
        self.assertIn("SKM_ORCH_ROOT", row["observed"])

    @unittest.skipUnless(partners.planner_root() and partners.find_orch_root(), "partners not found")
    def test_found_partners_are_ok(self):
        code, row = probe({"PLANNER_ROOT": str(partners.planner_root()), "SKM_ORCH_ROOT": str(partners.find_orch_root())})
        self.assertEqual((code, row["status"]), (0, "ok"))


if __name__ == "__main__":
    unittest.main()
