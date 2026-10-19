"""``orch conduct runs``: the runs of a project, newest first, from the run folders only (no new contract)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch.conductor import cli, runs
from orch.conductor.infrastructure.files import RUN_FILE, runs_root
from orch.conductor.infrastructure.lease import RunLease


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


class ConductPruneTests(ConductRunsTests):
    NOW = 1792000000.0  # 2026-10-14

    def ended(self, run_id: str, day: str, outcome: str = "done") -> Path:
        directory = self.make(run_id, [line(f"{day}T09:00:00Z", "run.start"),
                                       line(f"{day}T10:00:00Z", "run.end", outcome=outcome)])
        (self.project / ".swissknifeman" / "orch-artifacts" / run_id / "P1.1").mkdir(parents=True)
        (self.project / ".swissknifeman" / "orch" / "reports" / run_id).mkdir(parents=True)
        return directory

    def test_a_dry_run_lists_and_removes_nothing(self):
        old = self.ended("cnd-old", "2026-09-01")
        self.ended("cnd-new", "2026-10-13")
        rows = runs.prune(self.project, 30, now=self.NOW)
        self.assertEqual(["cnd-old"], [row["run_id"] for row in rows])
        self.assertFalse(rows[0]["removed"])
        self.assertTrue(old.is_dir())
        self.assertEqual(3, len(rows[0]["paths"]))

    def test_prune_skips_a_busy_lease_and_checks_status_again_under_ownership(self):
        old = self.ended("cnd-old", "2026-09-01")
        self.ended("cnd-new", "2026-10-13")
        before = (old / RUN_FILE).read_bytes()
        with RunLease(old).acquire("resume"):
            rows = runs.prune(self.project, 30, apply=True, now=self.NOW)
        self.assertEqual([False], [row["removed"] for row in rows])
        self.assertIn("RUN_BUSY", rows[0]["reason"])
        self.assertIn("skipped", runs.prune_text(rows, True))
        self.assertEqual(before, (old / RUN_FILE).read_bytes())
        acquire = RunLease.acquire
        def resumed(lease, command):
            result = acquire(lease, command)
            with open(old / "progress.jsonl", "a") as handle:
                handle.write(line("2026-09-01T11:00:00Z", "run.resume") + "\n")
            return result
        with mock.patch.object(RunLease, "acquire", resumed):
            rows = runs.prune(self.project, 30, apply=True, now=self.NOW)
        self.assertEqual("run is no longer eligible", rows[0]["reason"])
        self.assertTrue(old.is_dir())

    def test_prune_renames_an_old_orphan_under_lease_before_removing_it(self):
        old = self.make("cnd-orphan", [line("2026-09-01T09:00:00Z", "run.start")], doc={"lease": True})
        self.ended("cnd-new", "2026-10-13")
        remove = runs._remove
        def guarded(path):
            if path.name.startswith(".pruning-"):
                self.assertEqual(".pruning-cnd-orphan", path.name)
                self.assertFalse(old.exists())
                self.assertTrue(RunLease.held(path))
            return remove(path)
        with mock.patch.object(runs, "_remove", guarded):
            rows = runs.prune(self.project, 30, apply=True, now=self.NOW)
        self.assertEqual([("orphaned", True)], [(row["status"], row["removed"]) for row in rows])
        self.assertFalse((old.parent / ".pruning-cnd-orphan").exists())

    def test_apply_removes_the_state_the_reports_and_the_artifacts_of_old_runs_only(self):
        old = self.ended("cnd-old", "2026-09-01")
        older = self.ended("cnd-older", "2026-08-01", "blocked")
        recent = self.ended("cnd-new", "2026-10-13")
        rows = runs.prune(self.project, 30, apply=True, now=self.NOW)
        self.assertEqual({"cnd-old", "cnd-older"}, {row["run_id"] for row in rows})
        self.assertTrue(all(row["removed"] for row in rows))
        for path in (old, older):
            self.assertFalse(path.exists())
        for run_id in ("cnd-old", "cnd-older"):
            self.assertFalse((self.project / ".swissknifeman" / "orch-artifacts" / run_id).exists())
            self.assertFalse((self.project / ".swissknifeman" / "orch" / "reports" / run_id).exists())
        self.assertTrue(recent.is_dir())
        self.assertTrue((self.project / ".swissknifeman" / "orch-artifacts" / "cnd-new").is_dir())

    def test_the_latest_a_running_and_an_unreadable_run_stay(self):
        self.ended("cnd-a", "2026-07-01")
        running = self.make("cnd-running", [line("2026-07-02T09:00:00Z", "run.start")])
        self.make("cnd-broken", raw="{")
        latest = self.ended("cnd-z-latest", "2026-07-03")
        os.utime(latest / "progress.jsonl", (self.NOW * 2, self.NOW * 2))  # the last journal to change
        rows = runs.prune(self.project, 1, apply=True, now=self.NOW)
        self.assertEqual(["cnd-a"], [row["run_id"] for row in rows])
        for path in (running, runs_root(self.project) / "cnd-broken", latest):
            self.assertTrue(path.is_dir(), path)

    def test_the_cli_is_a_dry_run_unless_apply_and_checks_its_flag(self):
        self.ended("cnd-old", "2026-01-01")
        self.ended("cnd-last", "2026-01-02")
        os.utime(runs_root(self.project) / "cnd-last" / "progress.jsonl", (self.NOW * 2, self.NOW * 2))
        code, out, _ = self.conduct("prune", "--older-than", "30")
        self.assertEqual(0, code)
        self.assertIn("would remove", out)
        self.assertIn("--apply", out)
        self.assertTrue((runs_root(self.project) / "cnd-old").is_dir())
        code, out, _ = self.conduct("prune", "--older-than", "30", "--apply", "--json")
        self.assertEqual(0, code)
        self.assertEqual([True], [row["removed"] for row in json.loads(out)["runs"]])
        self.assertFalse((runs_root(self.project) / "cnd-old").exists())
        for bad in (("--older-than", "0"), ("--older-than", "5", "--apply", "--dry-run")):
            with self.assertRaises(SystemExit):
                self.conduct("prune", *bad)


if __name__ == "__main__":
    unittest.main()
