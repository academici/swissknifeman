"""``verify``: plans load through the planner store and the errors of ``check`` are compared as sets of (code, where)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import workspace_fixture as fx
from workspace_fixture import PLAN_NAME, ARCHIVED_NAME, BridgeCase

import partners  # noqa: E402
import verify  # noqa: E402

WORKSPACE = partners.workspace_module_root()
CONTRACT = WORKSPACE / "schemas" / "plans-migrator" / "v1" if WORKSPACE is not None else None


def break_item(plan_dir: Path, item: str = "P2.2", status: str = "not-a-status") -> None:
    path = plan_dir / "phases" / item.split(".")[0] / f"{item}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["status"] = status
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


class VerifyTests(BridgeCase):
    def copy_of_plans(self) -> Path:
        copy = self.tmp / "copy"
        shutil.copytree(self.plans, copy, ignore=shutil.ignore_patterns("views", "context", ".lock", "__pycache__"))
        return copy

    def test_plan_folders_cover_live_and_archived_plans_only(self):
        names = [name for name, _folder in verify.plan_folders(self.plans)]
        self.assertEqual(sorted(names), sorted([PLAN_NAME, ARCHIVED_NAME]))

    def test_loaded_plan_reports_its_check_codes(self):
        report = verify.compare_roots(self.plans, None)
        self.assertTrue(report["ok"], report)
        for row in report["plans"]:
            self.assertTrue(row["loaded"])
            self.assertEqual(row["problems"], [])
            self.assertNotIn("new_errors", row)

    def test_a_copy_has_the_same_error_set_as_its_source(self):
        break_item(self.plans / PLAN_NAME)
        copy = self.copy_of_plans()
        report = verify.compare_roots(copy, self.plans, unbound=True)
        row = next(row for row in report["plans"] if row["name"] == PLAN_NAME)
        self.assertTrue(row["check_codes"], "the red plan is red")
        self.assertEqual(row["new_errors"], [])
        self.assertTrue(report["ok"], report)

    def test_new_errors_of_the_copy_fail_the_verification(self):
        copy = self.copy_of_plans()
        break_item(copy / PLAN_NAME)
        report = verify.compare_roots(copy, self.plans, unbound=True)
        row = next(row for row in report["plans"] if row["name"] == PLAN_NAME)
        self.assertTrue(row["new_errors"])
        self.assertFalse(report["ok"])
        other = next(row for row in report["plans"] if row["name"] == ARCHIVED_NAME)
        self.assertEqual(other["new_errors"], [])

    def test_fewer_errors_in_the_copy_are_not_a_failure(self):
        copy = self.copy_of_plans()
        break_item(self.plans / PLAN_NAME)
        report = verify.compare_roots(copy, self.plans, unbound=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual(next(row for row in report["plans"] if row["name"] == PLAN_NAME)["new_errors"], [])

    def test_an_unreadable_document_is_a_problem(self):
        copy = self.copy_of_plans()
        (copy / PLAN_NAME / "phases/P1/P1.1.json").write_text("{broken", encoding="utf-8")
        report = verify.compare_roots(copy, None, unbound=True)
        row = next(row for row in report["plans"] if row["name"] == PLAN_NAME)
        self.assertFalse(row["loaded"])
        self.assertEqual(row["problems"][0]["file"], "phases/P1/P1.1.json")
        self.assertFalse(report["ok"])

    def test_a_plan_without_a_baseline_is_not_compared(self):
        copy = self.copy_of_plans()
        fx.make_plan(copy, "2026.10.06-№8-DEMO-NEW")
        report = verify.compare_roots(copy, self.plans, unbound=True)
        row = next(row for row in report["plans"] if row["name"] == "2026.10.06-№8-DEMO-NEW")
        self.assertNotIn("new_errors", row)

    def test_warnings_are_not_compared(self):
        check = partners.planner_engine("plan.check")
        issue = check.Issue("warning", "ONLY_A_WARNING", "plan.json", "x")
        plan_issues = check.check
        with mock.patch.object(check, "check", lambda plan: [*plan_issues(plan), issue]):
            result = verify.check_plan(self.plans / PLAN_NAME)
        self.assertNotIn(("ONLY_A_WARNING", "plan.json"), result["errors"])

    def test_unbound_check_does_not_need_a_checkout(self):
        copy = self.copy_of_plans()
        report = verify.compare_roots(copy, None, unbound=True)
        self.assertTrue(report["ok"], report)

    def test_verify_op_of_the_plugin(self):
        copy = self.copy_of_plans()
        document = {"protocol": "1", "request_id": "r1", "op": "invoke", "point": "workspace:plans-migrator",
                    "input": {"op": "verify", "plans_root": str(copy), "compare_to": str(self.plans),
                              "unbound": True}}
        done = subprocess.run([sys.executable, str(partners.BRIDGE / "migrator.py")], input=json.dumps(document),
                              capture_output=True, text=True, encoding="utf-8", check=False, cwd=self.tmp,
                              env=dict(os.environ, AICORE_ROOT=str(partners.aicore_lib().parent)))
        answer = json.loads(done.stdout)
        self.assertEqual(answer["status"], "ok", answer)
        self.assertTrue(answer["output"]["ok"], answer)
        if CONTRACT is not None:
            from aicore.util import schema
            registry = schema.load_contract_set(CONTRACT)[0]
            self.assertEqual(schema.validate(answer["output"], "response", registry), [])


class PartnerTests(unittest.TestCase):
    def test_workspace_module_root_follows_the_variable_first(self):
        with mock.patch.dict(os.environ, {"SKM_WORKSPACE_MODULE_ROOT": "/nonexistent/place"}):
            self.assertIsNone(partners.workspace_module_root())
        if WORKSPACE is not None:
            with mock.patch.dict(os.environ, {"SKM_WORKSPACE_MODULE_ROOT": str(WORKSPACE)}):
                self.assertEqual(partners.workspace_module_root(), WORKSPACE.resolve())

    def test_planner_root_follows_the_variables(self):
        with mock.patch.dict(os.environ, {"PLANNER_ROOT": "/nonexistent/place"}):
            self.assertIsNone(partners.planner_root())
        with mock.patch.dict(os.environ, {"PLANNER_ROOT": ""}), mock.patch.dict(os.environ, {"PLANNER_PLAN_PY": str(fx.PLANNER / "scripts/plan.py")}):
            self.assertEqual(partners.planner_root(), fx.PLANNER.resolve())

    def test_a_missing_partner_is_exit_3(self):
        with mock.patch.dict(os.environ, {"PLANNER_ROOT": "/nonexistent/place"}), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                partners.require_planner_root()
        self.assertEqual(caught.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
