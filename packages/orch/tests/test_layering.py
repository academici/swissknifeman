"""The standalone AST ratchet: gate totals, informative moves and item targets."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/layering.py"
SPEC = importlib.util.spec_from_file_location("layering", SCRIPT)
layering = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(layering)


class LayeringTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "conductor"
        self.baseline = Path(tmp.name) / "baseline.json"
        self.write("engine.py", "from orch.conductor.policies import p\n"
                   "from orch.conductor.stages import s\n"
                   "class Conductor:\n    _a = p.a\n    _b = s.b\n")
        self.write("policies/p.py", "def a(self):\n    return self._b()\n")
        self.write("stages/s.py", "def b(self):\n    return 1\n")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root),
                               "--baseline", str(self.baseline), *args], cwd=self.root.parent,
                              text=True, capture_output=True, check=False)

    def capture(self):
        result = self.run_script("--update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(self.baseline.read_text(encoding="utf-8"))

    def test_current_tree_matches_baseline(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=self.root.parent,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "layering: OK\n")

    def test_upward_call_owner_sites_and_cycle(self):
        measured = json.loads(self.run_script("--json").stdout)
        self.assertEqual(measured["upward_self_calls"], {"policies->stages": 1})
        self.assertEqual(measured["upward_sites"], {"policies->stages": ["policies.p:2 self._b -> stages.s"]})
        self.assertEqual(measured["largest_self_scc"], 0)
        self.write("stages/s.py", "def b(self):\n    return self._a()\n")
        self.assertEqual(json.loads(self.run_script("--json").stdout)["largest_self_scc"], 2)

    def test_upward_growth_is_a_regression(self):
        self.write("policies/p.py", "def a(self):\n    return 1\n")
        self.capture()
        self.write("policies/p.py", "def a(self):\n    return self._b()\n")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines()[0],
                         "LAYERING_REGRESSION: upward_total total: 1 > 0; sites: policies.p:2 self._b -> stages.s")

    def test_reduction_requires_baseline_update(self):
        self.capture()
        self.write("policies/p.py", "def a(self):\n    return 1\n")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("LAYERING_BASELINE_STALE: upward_total total: 0 < 1; run layering.py --update", result.stdout)

    def test_module_owned_class_methods_are_not_facade_functions(self):
        self.write("engine.py", "from orch.conductor.application import service as app\n"
                   "class Conductor:\n    release = app.release\n")
        self.write("infrastructure/lease.py", "class RunLease:\n    def release(self):\n        self.release()\n")
        self.write("application/service.py", "def release(self):\n    return None\n")
        self.write("policies/p.py", "")
        measured = json.loads(self.run_script("--json").stdout)
        self.assertEqual(measured["self_functions"]["infrastructure"], 0)
        self.assertEqual(measured["upward_total"], 0)

    def test_update_refuses_gate_growth_without_writing(self):
        self.write("policies/p.py", "")
        self.capture()
        before = self.baseline.read_bytes()
        self.write("policies/p.py", "def a(self):\n    return self._b()\n")
        result = self.run_script("--update")
        self.assertEqual(result.returncode, 1)
        self.assertIn("LAYERING_REGRESSION", result.stdout)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_redistribution_and_informative_growth_are_allowed(self):
        self.write("engine.py", "from orch.conductor.infrastructure import i\n"
                   "from orch.conductor.policies import p\nfrom orch.conductor.application import a\n"
                   "class Conductor:\n    _i = i.i\n    _p = p.p\n    _a = a.a\n")
        self.write("infrastructure/i.py", "def i(self):\n    return self._p()\n")
        self.write("policies/p.py", "def p():\n    return 1\n")
        self.write("stages/s.py", "")
        self.write("application/a.py", "def a(self):\n    return 1\n")
        before = self.capture()
        self.write("infrastructure/i.py", "def i(self):\n    return self._a()\n")
        self.write("application/a.py", "def a(self):\n    return 1\ndef extra(self):\n    return 2\n")
        with (self.root / "engine.py").open("a", encoding="utf-8") as stream:
            stream.write("    _extra = staticmethod(a.extra)\n")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in ("bindings", "staticmethod_bindings", "self_functions application", "upward_self_calls infrastructure->application"):
            self.assertIn(f"layering: info {name}", result.stdout)
        self.capture()
        after = json.loads(self.baseline.read_text())
        self.assertEqual(layering.gates(before), layering.gates(after))
        self.assertEqual(before["targets"], after["targets"])
        self.assertEqual(self.run_script("--check").stdout, "layering: OK\n")

    def test_policy_wrapper_move_reduces_gates_and_update_accepts_it(self):
        self.capture()
        self.write("engine.py", "from orch.conductor.application import wrapper\n"
                   "from orch.conductor.stages import s\n"
                   "class Conductor:\n    _a = wrapper.a\n    _b = s.b\n")
        self.write("policies/p.py", "def a():\n    return 1\n")
        self.write("application/wrapper.py", "def a(self):\n    return self._b()\n")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("LAYERING_BASELINE_STALE: upward_total", result.stdout)
        self.assertIn("LAYERING_BASELINE_STALE: self_functions policies", result.stdout)
        self.assertIn("layering: info self_functions application", result.stdout)
        self.capture()
        self.assertEqual(self.run_script("--check").stdout, "layering: OK\n")

    def test_prompts_target_rejects_oversized_module(self):
        self.write("prompts.py", "# prompt\n" * 601)
        self.capture()
        result = self.run_script("--check", "--target", "P5.4")
        self.assertEqual(result.returncode, 1)
        self.assertIn("LAYERING_TARGET: P5.4 oversized_modules.prompts.py: 601 (want absent)", result.stdout)
        for folder in ("context", "prompts"):
            self.write("prompts.py", "")
            self.write(f"{folder}/blocks.py", "# block\n" * 601)
            # A fresh baseline isolates the target from the growth gate.
            self.baseline.unlink()
            self.capture()
            self.assertIn(f"LAYERING_TARGET: P5.4 oversized_modules.{folder}/*", self.run_script("--check", "--target", "P5.4").stdout)

    def test_ports_are_data_not_upward_facade_calls(self):
        self.write("infrastructure/i.py", "def i(self):\n    return self.role_ports.unmetered(item)\n")
        self.write("stages/s.py", "def b(self):\n    return self.stage_ports.budget(item)\n")
        self.write("policies/p.py", "")
        measured = json.loads(self.run_script("--json").stdout)
        self.assertEqual(measured["upward_total"], 0)
        self.assertEqual(measured["port_calls"], {"infrastructure.role_ports.unmetered": 1, "stages.stage_ports.budget": 1})

    def test_aliases_facade_calls_and_private_access(self):
        self.write("engine.py", "from orch.conductor.application.service import helper as h\n"
                   "from orch.conductor.stages import s as stage\n"
                   "class Conductor:\n    _a = h.a\n    _b = staticmethod(stage.b)\n"
                   "    def _save(self):\n        pass\n")
        self.write("policies/p.py", "def a(self):\n    self._save()\n    return self._a()\n")
        self.write("cli.py", "eng._a()\nself._a()\neng.public()\n")
        measured = json.loads(self.run_script("--json").stdout)
        self.assertEqual((measured["bindings"], measured["staticmethod_bindings"]), (2, 1))
        self.assertEqual(measured["facade_calls"], {"policies": 1})
        self.assertEqual(measured["private_facade_access"], {"cli.py": 1})
        self.assertEqual(measured["upward_self_calls"], {"policies->application": 1})

    def test_every_other_gate_rejects_growth(self):
        baseline = self.capture()
        for path, content, gate in (("domain/d.py", "def d(self): pass\n", "self_functions domain"),
                                    ("cli.py", "eng._a()\n", "private_facade_access_total"),
                                    ("stages/s.py", "def b(self): return self._a()\n", "largest_self_scc"),
                                    ("prompts.py", "# line\n" * 601, "oversized_modules"),
                                    ("helper.py", "def h(self): pass\n", "unlayered_self_functions")):
            with self.subTest(gate=gate):
                target = self.root / path
                before = target.read_text() if target.exists() else None
                self.write(path, content)
                result = self.run_script("--check")
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"LAYERING_REGRESSION: {gate}", result.stdout)
                if before is None:
                    target.unlink()
                else:
                    target.write_text(before)
                self.assertEqual(json.loads(self.baseline.read_text()), baseline)

    def test_policy_and_roles_targets(self):
        self.capture()
        self.assertIn("LAYERING_TARGET: P5.2 self_functions.policies", self.run_script("--check", "--target", "P5.2").stdout)
        self.write("infrastructure/roles.py", "# line\n" * 301)
        result = self.run_script("--check", "--target", "P5.3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("LAYERING_TARGET: P5.3 infrastructure/roles.py: 301 (want <= 300 lines)", result.stdout)
        self.assertNotIn("P5.5", json.loads(self.baseline.read_text())["targets"])

    def test_scc_handles_deep_graph_without_python_recursion(self):
        graph = {str(n): {str(n + 1)} for n in range(2000)}
        self.assertEqual(layering.largest_scc(graph), 0)
        graph["2000"] = {"0"}
        self.assertEqual(layering.largest_scc(graph), 2001)

    def test_baseline_schema_is_validated_before_check_and_write(self):
        baseline = self.capture()
        for broken in ({**baseline, "bindings": True}, {**baseline, "unknown": 1},
                       {**baseline, "targets": {**baseline["targets"], "P5.5": {}}}):
            with self.subTest(broken=broken):
                self.baseline.write_text(json.dumps(broken), encoding="utf-8")
                before = self.baseline.read_bytes()
                for mode in ("--check", "--update"):
                    result = self.run_script(mode)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("invalid layering baseline", result.stderr)
                    self.assertEqual(self.baseline.read_bytes(), before)

    def test_initial_baseline_cannot_waive_zero_self_invariants(self):
        for name in ("domain/d.py", "helper.py"):
            with self.subTest(module=name):
                self.write(name, "def invalid(self): pass\n")
                result = self.run_script("--update")
                self.assertEqual(result.returncode, 1)
                self.assertIn("LAYERING_REGRESSION", result.stdout)
                self.assertFalse(self.baseline.exists())
                (self.root / name).unlink()


if __name__ == "__main__":
    unittest.main()
