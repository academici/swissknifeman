"""Execution preflight finds incomplete briefs before claim and leaves every plan byte intact."""
import copy
import io
import json
from contextlib import redirect_stdout
from unittest import mock

import test_worksource
import preflight
import partners
import worksource

plugins = partners.planner_engine("integration.plugins")


class PreflightTests(test_worksource.Case):
    def setUp(self):
        super().setUp()
        self.root = self.project / "plans" / self.plan
        self.input = plugins.build_input(plan_id=self.plan, short_id="PLAN1", plan_dir=self.root,
                                         plans_root=self.root.parent, project_root=self.project)
        test_worksource.run(self.project, "set", self.plan, "P1.3", "--json",
                            json.dumps({"orchestration": {"scenario": "solo"}}))

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_complete_plan_is_clean_and_read_only(self):
        before = self.tree()
        result = preflight.run(self.input)
        self.assertEqual(result, {"issues": []})
        self.assertEqual(plugins.output_problems(result), [])
        self.assertEqual(self.tree(), before)

    def test_incomplete_brief_and_unknown_scenario_are_item_errors(self):
        path = self.root / "phases/P1/P1.1.json"
        doc = json.loads(path.read_text())
        doc["validation"] = []
        doc["orchestration"] = {"scenario": "unknown-preflight-test"}
        path.write_text(json.dumps(doc))
        before = self.tree()
        result = preflight.run(self.input)
        self.assertEqual(plugins.output_problems(result), [])
        self.assertEqual({i["code"] for i in result["issues"]}, {"BRIEF_INCOMPLETE", "SCENARIO_UNKNOWN"})
        self.assertTrue(all(i["path"] == "phases/P1/P1.1.json" for i in result["issues"]))
        self.assertEqual(self.tree(), before)

    def test_bounds_and_archived_skip(self):
        p = preflight.brief.store.load_plan(self.root)
        template = p.items["P1.1"]
        p.items = {f"P1.{n}": {**copy.deepcopy(template), "id": f"P1.{n}"} for n in range(1, 104)}
        p.phases["P1"]["items"] = list(p.items)
        with mock.patch.object(preflight.brief.store, "load_plan", return_value=p), \
                mock.patch.object(preflight.brief, "build", return_value={}) as build, \
                mock.patch.object(preflight.brief.context, "collect", return_value={}), \
                mock.patch.object(worksource, "policy_exists", return_value=None):
            result = preflight.run(self.input)
            self.assertEqual(build.call_count, 100)
            self.assertEqual(result["issues"][-1]["code"], "PREFLIGHT_TRUNCATED")
            self.assertLessEqual(len(result["issues"]), 500)
            p.plan["status"] = "archived"
            build.reset_mock()
            self.assertEqual(preflight.run(self.input), {"issues": []})
            build.assert_not_called()

    def test_plugin_dispatches_check_point_and_validates_input(self):
        out = io.StringIO()
        with redirect_stdout(out):
            worksource.invoke("a" * 32, {"point": "planner:check", "input": self.input})
        reply = json.loads(out.getvalue())
        self.assertEqual((reply["status"], reply["output"]), ("ok", {"issues": []}))
        with self.assertRaisesRegex(ValueError, "Invalid planner:check input"):
            preflight.run({"plan_dir": str(self.root)})
