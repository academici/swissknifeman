"""analyst orch report: the reader (event journal + artifacts, contracts only) and the report, with a golden on a fixture
journal. The fixture ``tests/fixtures/orch`` holds the data of the events of one run and a second, other run, the artifact
folder of a plan and the run folder of the conductor; formats are those of orch ``schemas/event-data/v1``,
``review-verdict.json`` and ``prompt-manifest/v1``."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from aicore.ext import events as aicore_events
from aicore.state.locations import project_state_dir

from analyst import orch_report
from analyst.cli import main
from analyst.readers import orch as reader

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "orch"
GOLDEN = FIXTURE / "report.golden.json"


class OrchCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home, self.project = Path(tmp.name) / "home", Path(tmp.name) / "project"
        (self.home / "skm").mkdir(parents=True)
        self.project.mkdir()
        (self.project / ".git").mkdir()
        old = {key: os.environ.get(key) for key in ("HOME", "SKM_HOME", "SKM_AICORE_EVENTS__DELIVERY")}
        os.environ.update(HOME=str(self.home), SKM_HOME=str(self.home / "skm"), SKM_AICORE_EVENTS__DELIVERY="off")
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])
        for row in json.loads((FIXTURE / "events.json").read_text(encoding="utf-8")):
            aicore_events.emit(row["type"], row["data"], source="orch", subject=row["subject"], project=self.project,
                               strict=True)
        shutil.copytree(FIXTURE / "plans", self.project / "plans")
        shutil.copytree(FIXTURE / "runs", project_state_dir(self.project, "orch") / "conductor")

    def run_cmd(self, *args):
        out, err = io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.project)
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    main([str(self.project), "orch", *args])
                except SystemExit as exc:
                    code = exc.code or 0
        finally:
            os.chdir(cwd)
        return code, out.getvalue(), err.getvalue()

    def full(self):
        return orch_report.build(reader.read(self.project, plan="T"), json.loads((FIXTURE / "planned.json").read_text()),
                                 json.loads((FIXTURE / "baseline.json").read_text()))


class TestReader(OrchCase):
    def test_events_are_orch_only_and_filtered_by_run(self):
        everything = reader.read_events(self.project)
        self.assertTrue(all(row["type"].startswith("orch.") for row in everything))
        mine = reader.read_events(self.project, run="cnd-1")
        self.assertEqual(len(everything) - len(mine), 1)
        self.assertEqual({row["data"]["run_id"] for row in mine}, {"cnd-1"})

    def test_artifacts_need_a_plan_and_a_missing_plan_is_a_problem_not_a_guess(self):
        self.assertEqual(reader.read(self.project)["artifacts"], {})
        data = reader.read(self.project, plan="NOPE")
        self.assertEqual(data["artifacts"], {})
        self.assertTrue(any("NOPE" in text for text in data["problems"]))

    def test_run_folder_gives_manifests_and_risk(self):
        runs = reader.read(self.project, run="cnd-1")["runs"]
        self.assertEqual(runs["W1"]["risk"]["score"], 45)
        self.assertEqual(runs["W1"]["manifests"][0]["step"], "executor.1")

    def test_a_broken_artifact_is_reported_and_skipped(self):
        (self.project / "plans" / "T" / "artifacts" / "W1" / "stage-report.json").write_text("{nope", encoding="utf-8")
        data = reader.read(self.project, plan="T")
        self.assertTrue(any("stage-report.json" in text for text in data["problems"]))
        self.assertIsNone(data["artifacts"]["W1"]["stage_report"])


class TestReport(OrchCase):
    def test_numbers(self):
        report = self.full()
        self.assertEqual(report["tokens"]["total"], {"input": 6000, "cached": 400, "output": 1500})
        self.assertEqual(report["tokens"]["by_role"]["executor"]["output"], 1000)
        self.assertEqual(report["tokens"]["by_skill_estimated"], {"python-tests": 1200})
        self.assertEqual(report["review"]["findings_by_severity"], {"major": 1, "minor": 1})
        self.assertEqual((report["deviations"]["recorded"], report["deviations"]["resolved"]), (2, 1))
        self.assertEqual(report["providers"]["fallbacks"][0]["to"], "codex")
        self.assertEqual(report["long_stages"][0]["duration_ms"], 120000)
        self.assertEqual(report["budgets_over"][0]["class"], "skills")
        self.assertEqual(report["plan_vs_actual"][0]["delta_duration_ms"], 240000 - 200000)
        self.assertEqual(report["baseline"]["delta"]["deviations_without_impact_or_next"], 1)
        self.assertEqual(report["warnings"], {"RUN_SLOW": 1, "LIMIT_OVER": 1})

    def test_the_report_matches_its_golden(self):
        text = json.dumps(self.full(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if os.environ.get("ANALYST_RECAPTURE"):
            GOLDEN.write_text(text, encoding="utf-8")
        self.assertEqual(text, GOLDEN.read_text(encoding="utf-8"))

    def test_an_empty_journal_gives_an_empty_report(self):
        report = orch_report.build({"events": [], "artifacts": {}, "runs": {}, "problems": []})
        self.assertEqual((report["tokens"]["total"], report["plan_vs_actual"], report["long_stages"]), ({}, [], []))


class TestCommand(OrchCase):
    def test_json_and_text(self):
        code, out, _ = self.run_cmd("report", "--plan", "T", "--run", "cnd-1", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["agents"], {"started": 3, "ended": 3, "failed": 1})
        code, out, _ = self.run_cmd("report", "--plan", "T", "--planned", str(FIXTURE / "planned.json"),
                                    "--baseline", str(FIXTURE / "baseline.json"))
        self.assertEqual(code, 0)
        self.assertIn("baseline delta:", out)
        self.assertIn("vs plan", out)

    def test_unknown_subcommand_and_bad_file_fail(self):
        self.assertEqual(self.run_cmd("nope")[0], 2)
        self.assertEqual(self.run_cmd("report", "--planned", str(self.home / "missing.json"))[0], 2)


if __name__ == "__main__":
    unittest.main()
