#!/usr/bin/env python3
"""Tests of scripts/ci-matrix.py on a fixture hub: list, steps, run with fake dev commands, --check."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
SCRIPT = HUB / "scripts/ci-matrix.py"

GOOD_WORKFLOW = """name: Modules
jobs:
  matrix:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.list.outputs.matrix }}
    steps:
      - id: list
        run: echo "matrix=$(python3 scripts/ci-matrix.py list --json)" >> "$GITHUB_OUTPUT"
  unit:
    needs: matrix
    strategy:
      matrix: ${{ fromJSON(needs.matrix.outputs.matrix) }}
    steps:
      - run: python3 scripts/ci-matrix.py run --unit ${{ matrix.unit }}
"""


def unit_doc(unit_id: str, kind: str = "capability", test=None, validate=None) -> dict:
    dev = {}
    if test is not None:
        dev["test"] = test
    if validate is not None:
        dev["validate"] = validate
    return {"id": unit_id, "kind": kind, "version": "0.1.0", "dev": dev, "provides": {}}


def eu_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_matrix_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def close(self):
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def unit(self, folder: str, doc: dict) -> None:
        self.write(f"{folder}/unit.json", json.dumps(doc))

    def workflow(self, text: str) -> None:
        self.write(".github/workflows/modules.yml", text)

    def legacy(self, commands: list) -> str:
        self.write("legacy.json", json.dumps(commands))
        return str(self.root / "legacy.json")

    def run(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args],
                              capture_output=True, text=True, timeout=120, env=env)


class CiMatrixTests(unittest.TestCase):
    def test_partner_env_pins_all_roots_to_current_hub_and_overrides_live_paths(self):
        from unittest.mock import patch
        module = eu_module()
        root = HUB
        expected = {"PLANNER_ROOT": str(root / "packages/planner"),
                    "PLANNER_PLAN_PY": str(root / "packages/planner/scripts/plan.py"),
                    "SKM_ORCH_ROOT": str(root / "packages/orch"), "SKM_SKILLER_ROOT": str(root / "packages/skiller"),
                    "SKM_HARNESS_ROOT": str(root / "packages/harness"), "AICORE_ROOT": str(root / "packages/aicore"),
                    "SKM_GUI_ROOT": str(root / "packages/gui"), "SKM_WORKSPACE_MODULE_ROOT": str(root / "packages/workspace")}
        with patch.dict(os.environ, {name: "/tmp/live-checkout" for name in expected}):
            env = {**os.environ, **module.partner_env(root)}
            self.assertEqual({name: env[name] for name in expected}, expected)
            for name in ("gui-orch", "gui-workspace", "workspace-planner"):
                unit = module.discover(root)[name]
                test = next(s for s in module.build_steps(root, unit) if s["id"] == "test")
                self.assertEqual({k: test["env"][k] for k in expected}, expected)

    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)
        self.fx.write("configs/ecosystem-units.json", json.dumps({"standalone": {"tools": ["tooly"]}}))
        self.fx.unit("packages/alpha", unit_doc("alpha", test=["bash", "scripts/test.sh"], validate=["bash", "scripts/validate.sh"]))
        self.fx.unit("packages/tooly", unit_doc("tooly", test=["bash", "-c", "exit 0"]))
        self.fx.unit("bridges/link", unit_doc("link", "bridge", test=["bash", "-c", "exit 0"]))

    def test_list_reads_modules_and_bridges_and_marks_tools(self):
        out = self.fx.run("list", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        include = {e["unit"]: e for e in json.loads(out.stdout)["include"]}
        self.assertEqual(sorted(include), ["alpha", "link", "tooly"])
        self.assertEqual(include["link"]["kind"], "bridge")
        self.assertTrue(include["tooly"]["tool"])
        self.assertFalse(include["alpha"]["tool"])

    def test_list_python_and_step_filter(self):
        self.fx.unit("packages/mute", unit_doc("mute"))
        out = json.loads(self.fx.run("list", "--json", "--step", "test", "--python", "3.11,3.13").stdout)
        pairs = sorted((e["unit"], e["python"]) for e in out["include"])
        self.assertEqual(pairs, sorted((u, v) for u in ("alpha", "link", "tooly") for v in ("3.11", "3.13")))

    def test_list_python_defaults_to_the_floor_matrix(self):
        out = json.loads(self.fx.run("list", "--json", "--step", "test", "--python").stdout)
        versions = sorted({e["python"] for e in out["include"]})
        self.assertEqual(versions, ["3.11", "3.13", "3.14"])
        bare = json.loads(self.fx.run("list", "--json", "--step", "test").stdout)
        self.assertTrue(all("python" not in e for e in bare["include"]))

    def test_steps_of_a_module_and_a_bridge(self):
        module = [row.split("\t")[0] for row in self.fx.run("steps", "alpha").stdout.splitlines()]
        self.assertEqual(module, ["test", "validate", "standalone", "contracts", "secrets"])
        bridge = [row.split("\t")[0] for row in self.fx.run("steps", "link").stdout.splitlines()]
        self.assertEqual(bridge, ["test", "contracts"])
        self.assertEqual(self.fx.run("steps", "nope").returncode, 2)

    def test_bridge_with_lib_and_cli_still_has_only_test_and_contracts(self):
        doc = unit_doc("wired", "bridge", test=["bash", "-c", "exit 0"])
        doc["provides"] = {"cli": ["tool.py"]}
        self.fx.unit("bridges/wired", doc)
        self.fx.write("bridges/wired/lib/x.py", "")
        self.fx.write("bridges/wired/tests/t.py", "")
        self.fx.write("bridges/wired/tool.py", "import sys\nsys.stdin.read()\n")
        steps = [row.split("\t")[0] for row in self.fx.run("steps", "wired").stdout.splitlines()]
        self.assertEqual(steps, ["test", "contracts"])

    def test_cli_smoke_does_not_block_on_open_stdin(self):
        doc = unit_doc("reader")
        doc["provides"] = {"cli": ["tool.py"]}
        self.fx.unit("packages/reader", doc)
        self.fx.write("packages/reader/tool.py", "import sys\nsys.stdin.read()\n")
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.fx.root), "run", "--unit", "reader",
                              "--step", "cli-smoke"], stdin=subprocess.PIPE, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_run_reports_ok_fail_and_exit_code(self):
        self.fx.unit("packages/broken", unit_doc("broken", test=["bash", "-c", "exit 3"]))
        ok = self.fx.run("run", "--unit", "tooly", "--step", "test")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertRegex(ok.stdout, r"^ok tooly test \d+\.\d\n$")
        bad = self.fx.run("run", "--unit", "broken", "--step", "test")
        self.assertEqual(bad.returncode, 1)
        self.assertRegex(bad.stdout, r"^fail broken test \d+\.\d\n$")

    def test_validate_skips_the_tests_after_a_green_test_step(self):
        log = self.fx.root / "validate-env"
        probe = f'echo "${{SKM_VALIDATE_SKIP_TESTS:-unset}}" >> {log}'
        self.fx.unit("packages/dedup", unit_doc("dedup", test=["bash", "-c", "exit 0"], validate=["bash", "-c", probe]))
        self.fx.unit("packages/redtest", unit_doc("redtest", test=["bash", "-c", "exit 1"], validate=["bash", "-c", probe]))
        self.assertEqual(self.fx.run("run", "--unit", "dedup", "--step", "test", "--step", "validate").returncode, 0)
        self.assertEqual(self.fx.run("run", "--unit", "dedup", "--step", "validate").returncode, 0)  # tests not run here
        self.fx.run("run", "--unit", "redtest", "--step", "test", "--step", "validate")  # a red test step: no skip
        self.assertEqual(self.fx.run("run", "--unit", "dedup", "--repeat-tests", "--step", "test", "--step", "validate").returncode, 0)
        self.assertEqual(log.read_text(encoding="utf-8").split(), ["1", "unset", "unset", "unset"])

    def test_units_run_side_by_side_with_jobs_and_the_steps_of_a_unit_stay_in_order(self):
        mark = self.fx.root / "marks"
        script = lambda name: ["python3", "-c", f"import time; open({str(mark)!r}, 'a').write('{name}+ '); time.sleep(1.0); open({str(mark)!r}, 'a').write('{name}- ')"]
        for name in ("p1", "p2", "p3"):
            self.fx.unit(f"packages/{name}", unit_doc(name, test=script(name)))
        started = __import__("time").monotonic()
        out = self.fx.run("run", "--unit", "p1", "--unit", "p2", "--unit", "p3", "--step", "test", "--jobs", "3")
        took = __import__("time").monotonic() - started
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertLess(took, 2.8)  # three one-second tests side by side, not one after the other
        marks = mark.read_text().split()
        self.assertEqual(sorted(marks[:3]), ["p1+", "p2+", "p3+"])  # all started before any ended
        self.assertEqual(len(out.stdout.splitlines()), 3)

    def test_the_independent_steps_of_one_unit_overlap_and_validate_still_follows_the_test(self):
        mark = self.fx.root / "overlap"
        log = lambda name: ["python3", "-c", f"import time; open({str(mark)!r}, 'a').write('{name}+ '); time.sleep(1.0); open({str(mark)!r}, 'a').write('{name}- ')"]
        doc = unit_doc("two", test=log("test"), validate=log("validate"))
        doc["dev"]["standalone_setup"] = []
        self.fx.unit("packages/two", doc)
        out = self.fx.run("run", "--unit", "two", "--step", "test", "--step", "validate", "--step", "contracts", "--jobs", "3")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        marks = mark.read_text().split()
        self.assertEqual(marks, ["test+", "test-", "validate+", "validate-"])  # validate after the test of its unit
        self.assertEqual(sorted(line.split()[2] for line in out.stdout.splitlines()), ["contracts", "test", "validate"])

    def test_chains_pair_test_and_validate_and_leave_the_other_steps_alone(self):
        steps = [{"id": name} for name in ("lint", "test", "validate", "standalone", "secrets")]
        self.assertEqual([[s["id"] for s in chain] for chain in eu_module().chains(steps)],
                         [["lint"], ["test", "validate"], ["standalone"], ["secrets"]])
        self.assertEqual([[s["id"] for s in chain] for chain in eu_module().chains(steps[2:3])], [["validate"]])

    def test_jobs_one_is_the_old_order_and_a_red_unit_still_fails_the_run(self):
        self.fx.unit("packages/broken", unit_doc("broken", test=["bash", "-c", "exit 3"]))
        out = self.fx.run("run", "--unit", "tooly", "--unit", "broken", "--step", "test", "--jobs", "1")
        self.assertEqual(out.returncode, 1)
        self.assertEqual([line.split()[:3] for line in out.stdout.splitlines()], [["ok", "tooly", "test"], ["fail", "broken", "test"]])
        out = self.fx.run("run", "--unit", "tooly", "--unit", "broken", "--step", "test", "--jobs", "2")
        self.assertEqual(out.returncode, 1)

    def test_run_skip_and_unknown(self):
        out = self.fx.run("run", "--unit", "link", "--skip", "test")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn(" link test ", out.stdout)
        self.assertIn("ok link contracts", out.stdout)
        self.assertEqual(self.fx.run("run", "--unit", "ghost").returncode, 2)
        self.assertEqual(self.fx.run("run", "--unit", "alpha", "--step", "nope").returncode, 2)

    def test_run_uses_a_throwaway_home(self):
        marker = self.fx.root / "home-seen"
        self.fx.unit("packages/homey", unit_doc("homey", test=["bash", "-c", f'echo "$HOME" > {marker}']))
        self.assertEqual(self.fx.run("run", "--unit", "homey", "--step", "test").returncode, 0)
        self.assertNotEqual(marker.read_text().strip(), str(Path.home()))

    def typecheck_script(self, code: int, marker: str = "") -> None:
        """A stand-in for scripts/typecheck.sh: records its arguments and the HOME it saw, exits with ``code``."""
        self.fx.write("scripts/typecheck.sh", f'echo "$HOME $@" > {self.fx.root / "typecheck-seen"}\nexit {code}\n')

    def test_the_hub_has_the_typecheck_step_only_when_the_script_exists_and_is_not_in_the_matrix(self):
        self.assertEqual(self.fx.run("steps", "hub").stdout, "")  # no script: no step
        self.assertEqual(self.fx.run("run", "--unit", "hub", "--step", "typecheck").returncode, 2)
        self.typecheck_script(0)
        steps = self.fx.run("steps", "hub")
        self.assertEqual(steps.stdout.strip(), "typecheck\tbash scripts/typecheck.sh --baseline")
        listed = [e["unit"] for e in json.loads(self.fx.run("list", "--json").stdout)["include"]]
        self.assertNotIn("hub", listed)  # the matrix holds the units of unit.json only

    def test_run_hub_typecheck_reports_ok_and_fail_and_keeps_the_real_home(self):
        self.typecheck_script(0)
        ok = self.fx.run("run", "--unit", "hub", "--step", "typecheck")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertRegex(ok.stdout, r"^ok hub typecheck \d+\.\d\n$")
        seen = (self.fx.root / "typecheck-seen").read_text(encoding="utf-8").split()
        self.assertEqual(seen, [os.environ.get("HOME", str(Path.home())), "--baseline"])  # the pinned tool lives in the real cache
        self.typecheck_script(1)
        bad = self.fx.run("run", "--unit", "hub", "--step", "typecheck")
        self.assertEqual(bad.returncode, 1)
        self.assertRegex(bad.stdout, r"^fail hub typecheck \d+\.\d\n$")

    def test_a_missing_typecheck_tool_is_a_skip_off_ci_and_a_failure_on_ci(self):
        self.typecheck_script(2)
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        local = self.fx.run("run", "--unit", "hub", "--step", "typecheck", env=env)
        self.assertEqual(local.returncode, 0, local.stderr)
        self.assertRegex(local.stdout, r"^skip hub typecheck ")
        on_ci = self.fx.run("run", "--unit", "hub", "--step", "typecheck", env={**env, "CI": "true"})
        self.assertEqual(on_ci.returncode, 1)
        self.assertRegex(on_ci.stdout, r"^fail hub typecheck ")

    def test_run_all_includes_the_hub_typecheck_when_the_script_exists(self):
        before = self.fx.run("run", "--all", "--skip", "contracts", "--skip", "secrets", "--skip", "standalone")
        self.assertNotIn(" hub ", before.stdout)
        self.typecheck_script(0)
        after = self.fx.run("run", "--all", "--skip", "contracts", "--skip", "secrets", "--skip", "standalone")
        self.assertRegex(after.stdout, r"(?m)^ok hub typecheck ")

    def test_check_demands_the_hub_typecheck_job_once_the_script_exists(self):
        self.fx.workflow(GOOD_WORKFLOW)
        legacy = self.fx.legacy(["bash packages/alpha/scripts/test.sh -v", "bash packages/alpha/scripts/validate.sh"])
        self.typecheck_script(0)
        out = self.fx.run("--check", "--legacy", legacy)
        self.assertEqual(out.returncode, 1)
        self.assertIn("ci-matrix.py run --unit hub --step typecheck", out.stderr)
        self.fx.workflow(GOOD_WORKFLOW + "  hub:\n    steps:\n      - run: python3 scripts/ci-matrix.py run --unit hub --step typecheck\n")
        self.assertEqual(self.fx.run("--check", "--legacy", legacy).returncode, 0)

    def test_check_passes_on_a_covered_hub(self):
        self.fx.workflow(GOOD_WORKFLOW)
        legacy = self.fx.legacy(["bash packages/alpha/scripts/test.sh -v", "bash packages/alpha/scripts/validate.sh"])
        out = self.fx.run("--check", "--legacy", legacy)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_check_catches_a_literal_matrix(self):
        self.fx.workflow(GOOD_WORKFLOW.replace("${{ fromJSON(needs.matrix.outputs.matrix) }}",
                                               "\n        include:\n          - unit: alpha").replace(
            "matrix: \n", "matrix:\n"))
        out = self.fx.run("--check", "--legacy", self.fx.legacy([]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("literal", out.stderr)

    def test_check_catches_an_inline_unit_list(self):
        self.fx.workflow(GOOD_WORKFLOW.replace("${{ fromJSON(needs.matrix.outputs.matrix) }}", "{unit: [alpha, link]}"))
        out = self.fx.run("--check", "--legacy", self.fx.legacy([]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("literal matrix", out.stderr)

    def test_check_catches_an_uncovered_legacy_command(self):
        self.fx.workflow(GOOD_WORKFLOW)
        out = self.fx.run("--check", "--legacy", self.fx.legacy(["bash packages/ghost/scripts/test.sh -v"]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("legacy command not covered", out.stderr)
        out = self.fx.run("--check", "--legacy", self.fx.legacy(["bash packages/tooly/scripts/validate.sh"]))
        self.assertEqual(out.returncode, 1)

    def test_check_catches_a_workflow_that_does_not_use_the_list(self):
        self.fx.workflow(GOOD_WORKFLOW.replace("ci-matrix.py list --json", "echo none"))
        out = self.fx.run("--check", "--legacy", self.fx.legacy([]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("list --json", out.stderr)

    def test_check_catches_a_duplicated_step_command(self):
        self.fx.workflow(GOOD_WORKFLOW + "      - run: bash packages/alpha/scripts/test.sh\n")
        out = self.fx.run("--check", "--legacy", self.fx.legacy([]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("duplicates", out.stderr)

    def test_check_catches_an_unknown_command_of_an_old_workflow(self):
        self.fx.workflow(GOOD_WORKFLOW)
        self.fx.write(".github/workflows/test.yml", "jobs:\n  t:\n    steps:\n      - run: make mystery\n")
        out = self.fx.run("--check", "--legacy", self.fx.legacy([]))
        self.assertEqual(out.returncode, 1)
        self.assertIn("make mystery", out.stderr)


class StepTests(unittest.TestCase):
    """The contracts and schema-compat steps on a fixture module."""

    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)
        self.fx.write("configs/ecosystem-units.json", "{}")

    def module(self, contracts: list) -> None:
        doc = unit_doc("mod", test=["bash", "-c", "exit 0"])
        doc["provides"] = {"contracts": contracts}
        self.fx.unit("packages/mod", doc)

    def link_foundation(self) -> None:
        (self.fx.root / "packages").mkdir(exist_ok=True)
        if not (self.fx.root / "packages/aicore").exists():
            (self.fx.root / "packages/aicore").symlink_to(HUB / "packages/aicore")

    def fake_compat(self, code: int, message: str) -> None:
        self.fx.write("packages/aicore/bin/aicore", f"#!/bin/bash\necho '{message}' >&2\nexit {code}\n")
        self.module([])
        self.fx.write("packages/mod/schemas/x/v1/x.schema.json", "{}")

    def schema(self, name: str, body: dict) -> None:
        self.fx.write(f"packages/mod/schemas/{name}/v1/{name}.schema.json", json.dumps(body))

    def contract(self) -> subprocess.CompletedProcess:
        self.module([{"id": "urn:mod", "path": "schemas/thing/v1", "version": "v1", "stability": "alpha"}])
        self.link_foundation()
        return self.fx.run("run", "--unit", "mod", "--step", "contracts")

    def good(self, extra=None) -> dict:
        body = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:swissknifeman:aicore:thing:v1",
                "type": "object"}
        body.update(extra or {})
        return body

    def test_contracts_pass_on_a_clean_schema(self):
        self.schema("thing", self.good())
        self.assertEqual(self.contract().returncode, 0)

    def test_contracts_fail_on_an_unresolved_ref_that_keeps_the_id(self):
        self.schema("thing", self.good({"properties": {"a": {"$ref": "urn:nowhere:other:v1"}}}))
        out = self.contract()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)

    def test_contracts_fail_on_a_profile_violation_that_keeps_the_id(self):
        self.schema("thing", self.good({"allOf": [{"type": "string"}]}))
        out = self.contract()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)

    def test_contracts_fail_on_a_broken_legacy_folder(self):
        self.module([{"id": "urn:mod", "path": "schema", "version": "v1", "stability": "alpha"}])
        self.link_foundation()
        self.fx.write("packages/mod/schema/a.schema.json", json.dumps(
            {"$schema": "http://json-schema.org/draft-07/schema#", "properties": {"a": {"$ref": "#/definitions/none"}}}))
        self.assertEqual(self.fx.run("run", "--unit", "mod", "--step", "contracts").returncode, 1)
        self.fx.write("packages/mod/schema/a.schema.json", json.dumps(
            {"$schema": "http://json-schema.org/draft-07/schema#", "definitions": {"d": {"type": "string"}},
             "properties": {"a": {"$ref": "#/definitions/d"}}}))
        self.assertEqual(self.fx.run("run", "--unit", "mod", "--step", "contracts").returncode, 0)

    def slot_set(self, extra: dict) -> subprocess.CompletedProcess:
        """A contract set of two documents; ``main`` leaves the extension slot ``options`` open, as plan/v1 does."""
        self.module([{"id": "urn:swissknifeman:mod:set", "path": "schemas/set/v1", "version": "v1", "stability": "alpha"}])
        self.link_foundation()
        prefix = "urn:swissknifeman:mod:set:"
        base = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
        self.fx.write("packages/mod/schemas/set/v1/defs.schema.json", json.dumps(
            {**base, "$id": f"{prefix}defs:v1", "$defs": {"text": {"type": "string"}}}))
        self.fx.write("packages/mod/schemas/set/v1/main.schema.json", json.dumps(
            {**base, "$id": f"{prefix}main:v1", "properties": {"a": {"$ref": f"{prefix}defs:v1#/$defs/text"}, **extra}}))
        return self.fx.run("run", "--unit", "mod", "--step", "contracts")

    def test_contracts_accept_an_open_extension_slot_and_check_the_rest_of_the_set(self):
        slot = {"opts": {"$ref": "urn:swissknifeman:mod:set:extension:options:v1"}}
        out = self.slot_set(slot)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        broken = self.slot_set({**slot, "b": {"$ref": "urn:swissknifeman:mod:set:defs:v1#/$defs/nope"}})
        self.assertEqual(broken.returncode, 1, broken.stdout + broken.stderr)  # the slot does not excuse a real ref
        self.assertIn("nope", broken.stderr)
        self.assertEqual(self.slot_set({"c": {"$ref": "urn:swissknifeman:mod:set:other:v1"}}).returncode, 1)

    def test_secrets_step_applies_the_plan_reference_rule_of_the_hygiene_gate(self):
        self.module([])
        self.fx.write("scripts/public-hygiene.py", (HUB / "scripts/public-hygiene.py").read_text(encoding="utf-8"))
        self.fx.write("packages/mod/notes.md", "clean\n")
        subprocess.run(["git", "init", "-q"], cwd=self.fx.root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.fx.root, check=True)
        self.assertEqual(self.fx.run("run", "--unit", "mod", "--step", "secrets").returncode, 0)
        self.fx.write("packages/mod/notes.md", "see plan " + "2026.10.07" + "-№1-SKM-ECOSYSTEM\n")  # not a literal: the gate reads this file too
        subprocess.run(["git", "add", "-A"], cwd=self.fx.root, check=True)
        out = self.fx.run("run", "--unit", "mod", "--step", "secrets")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("packages/mod/notes.md", out.stderr)

    def test_compat_base_invalid_is_a_reported_skip(self):
        self.fake_compat(1, "SCHEMA_COMPAT_BASE_INVALID: x/v1 at the base: unknown schema kind")
        out = self.fx.run("run", "--unit", "mod", "--step", "schema-compat", "--base-ref", "HEAD")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("skip mod schema-compat", out.stdout)

    def test_a_real_compat_error_still_fails(self):
        self.fake_compat(1, "SCHEMA_COMPAT_BREAKING: x/v1 removed property a")
        out = self.fx.run("run", "--unit", "mod", "--step", "schema-compat", "--base-ref", "HEAD")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)


class RealHubTests(unittest.TestCase):
    def test_the_real_hub_has_the_typecheck_step_and_its_workflow_job(self):
        module = eu_module()
        steps = module.build_steps(HUB, module.hub_unit(HUB))
        self.assertEqual([s["id"] for s in steps], ["typecheck"])
        self.assertEqual(steps[0]["argv"], ["bash", "scripts/typecheck.sh", "--baseline"])
        self.assertIn("ci-matrix.py run --unit hub --step typecheck",
                      (HUB / ".github/workflows/modules.yml").read_text(encoding="utf-8"))

    def test_every_unit_of_the_hub_is_in_the_matrix(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "list", "--json"], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        listed = {e["unit"] for e in json.loads(out.stdout)["include"]}
        folders = {p.parent.name for pattern in ("packages/*/unit.json", "bridges/*/unit.json") for p in HUB.glob(pattern)}
        self.assertEqual(listed, folders)

    def test_the_compat_tool_reads_the_base_of_every_module_with_schemas(self):
        """No module needs the SCHEMA_COMPAT_BASE_INVALID skip: the loader reads the base ref of all of them."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home, "SKM_HOME": home + "/skm", "PYTHONPATH": str(HUB / "packages/aicore/lib")}
            for unit in sorted(p.parent for p in HUB.glob("packages/*/unit.json")):
                if not any((unit / "schemas").glob("*/v*/*.schema.json")):
                    continue
                code = ("import sys; from aicore.util.schemacompat import main; "
                        f"sys.exit(main(['compat', '--base', 'HEAD', '--root', '{unit}/schemas', '--unit', '{unit}/unit.json']))")
                out = subprocess.run([sys.executable, "-c", code], cwd=HUB, env=env, capture_output=True, text=True, timeout=120)
                self.assertEqual(out.returncode, 0, f"{unit.name}: {out.stdout}{out.stderr}")

    def test_the_legacy_workflows_are_gone_and_the_check_passes(self):
        self.assertFalse((HUB / ".github/workflows/test.yml").exists())
        self.assertFalse((HUB / ".github/workflows/validate.yml").exists())
        out = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
