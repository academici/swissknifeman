"""``orch conduct runs``: the runs of a project, newest first, from the run folders only (no new contract)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from orch.conductor import cli, runs
from orch.conductor.infrastructure.files import RUN_FILE, runs_root


def line(ts: str, event: str, **fields) -> str:
    return json.dumps({"ts": ts, "event": event, **fields})


class ConductRunsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(os.path.realpath(self.tmp.name))
        (self.project / ".git").mkdir()

    def make(self, run_id: str, lines=(), doc=None, raw=None) -> Path:
        directory = runs_root(self.project) / run_id
        directory.mkdir(parents=True)
        (directory / RUN_FILE).write_text(raw if raw is not None else json.dumps(doc if doc is not None else {"items": []}),
                                          encoding="utf-8")
        if lines:
            (directory / "progress.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return directory

    def conduct(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_empty_project_is_a_valid_answer(self):
        self.assertEqual([], runs.listing(self.project))
        code, out, _ = self.conduct("runs", "--json")
        self.assertEqual((0, {"runs": []}), (code, json.loads(out)))
        self.assertEqual((0, "no conductor runs\n"), self.conduct("runs")[:2])

    def test_two_runs_newest_first_with_status_items_and_resumes(self):
        self.make("cnd-old", [line("2026-10-16T10:00:00Z", "run.start"),
                              line("2026-10-16T10:01:00Z", "item.start", item="P1.1"),
                              line("2026-10-16T10:02:00Z", "item.end", item="P1.1", outcome="done"),
                              line("2026-10-16T10:03:00Z", "run.end", outcome="finished")])
        self.make("cnd-new", [line("2026-10-17T09:00:00Z", "run.start"),
                              line("2026-10-17T09:01:00Z", "item.start", item="P2.1"),
                              line("2026-10-17T09:05:00Z", "run.end", outcome="blocked", reason_code="REVIEW_FAILED"),
                              line("2026-10-17T09:10:00Z", "run.resume")])
        rows = runs.listing(self.project)
        self.assertEqual(["cnd-new", "cnd-old"], [row["run_id"] for row in rows])
        self.assertEqual({"run_id": "cnd-old", "status": "finished", "reason_code": None, "created": "2026-10-16T10:00:00Z",
                          "items": ["P1.1"], "resumes": 0}, rows[1])
        self.assertEqual(("running", None, 1, ["P2.1"]), (rows[0]["status"], rows[0]["reason_code"], rows[0]["resumes"],
                                                          rows[0]["items"]))
        self.assertEqual([rows[0]], runs.listing(self.project, 1))
        code, out, _ = self.conduct("runs", "--json", "--limit", "1")
        self.assertEqual((0, ["cnd-new"]), (code, [row["run_id"] for row in json.loads(out)["runs"]]))
        self.assertIn("cnd-new: running", self.conduct("runs")[1])

    def test_ties_are_ordered_by_run_id_and_the_output_is_stable(self):
        stamp = [line("2026-10-17T09:00:00Z", "run.start")]
        for run_id in ("cnd-b", "cnd-a", "cnd-c"):
            self.make(run_id, stamp)
        first = runs.listing(self.project)
        self.assertEqual(["cnd-a", "cnd-b", "cnd-c"], [row["run_id"] for row in first])
        self.assertEqual(first, runs.listing(self.project))

    def test_a_broken_run_json_is_listed_as_unreadable(self):
        self.make("cnd-broken", raw="{not json")
        self.make("cnd-list", raw="[1]")
        self.make("cnd-ok", [line("2026-10-17T09:00:00Z", "run.start")])
        rows = {row["run_id"]: row for row in runs.listing(self.project)}
        self.assertEqual({"run_id": "cnd-broken", "status": "unreadable"}, rows["cnd-broken"])
        self.assertEqual({"run_id": "cnd-list", "status": "unreadable"}, rows["cnd-list"])
        self.assertEqual("running", rows["cnd-ok"]["status"])
        self.assertEqual(0, self.conduct("runs")[0])

    def test_items_fall_back_to_run_json_and_other_folders_are_ignored(self):
        self.make("cnd-fresh", doc={"items": ["P3.1", "P3.2"]})
        (runs_root(self.project) / "not-a-run").mkdir(parents=True)
        (runs_root(self.project) / "cnd-nofile").mkdir(parents=True)
        rows = runs.listing(self.project)
        self.assertEqual(["cnd-fresh"], [row["run_id"] for row in rows])
        self.assertEqual((["P3.1", "P3.2"], None), (rows[0]["items"], rows[0]["created"]))

    def test_limit_must_be_positive_and_no_float_is_printed(self):
        with self.assertRaises(SystemExit) as caught:
            self.conduct("runs", "--limit", "0")
        self.assertEqual(2, caught.exception.code)
        self.make("cnd-one", [line("2026-10-17T09:00:00Z", "run.start")])
        self.assertNotRegex(self.conduct("runs", "--json")[1], r"\d\.\d")


if __name__ == "__main__":
    unittest.main()
