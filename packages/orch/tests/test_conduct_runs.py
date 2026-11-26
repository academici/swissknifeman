"""``orch conduct runs``: the runs of a project, newest first, from the run folders only (no new contract)."""
from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from orch.conductor import cli, contract, observer, process, runs
from orch.conductor.infrastructure.files import RUN_FILE, runs_root
from orch.conductor.infrastructure.lease import RunLease


def line(ts: str, event: str, **fields) -> str:
    return json.dumps({"ts": ts, "run": "cnd-fixture", "event": event, **fields})


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
        self.assertEqual({"run_id": "cnd-old", "health": "finished", "status": "finished", "reason_code": None,
                          "created": "2026-10-16T10:00:00Z", "items": ["P1.1"], "resumes": 0, "owner": None}, rows[1])
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
        self.assertEqual({"run_id": "cnd-broken", "status": "unreadable", "owner": None}, rows["cnd-broken"])
        self.assertEqual({"run_id": "cnd-list", "status": "unreadable", "owner": None}, rows["cnd-list"])
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


class ConductObservabilityTests(ConductRunsTests):
    def test_observer_keeps_group_findings_and_distinguishes_clean_from_unavailable_reviews(self):
        group = {"format": "findings", "error": None, "counts": {"Blocker": 1, "Major": 2, "Minor": 0},
                 "refs": ["P2.1", "P2.2"], "file": "group-review-1.md", "followup": "fix.json"}
        minor = {"id": "F1", "severity": "Minor", "confidence": "high", "location": "a.py:1",
                 "failure_scenario": "a typo in a message", "basis": "read"}  # a closed review-findings entry (records/v1)
        legacy = {"steps": {"review.1": {"status": "done", "result": {
            "findings": {"verdict": "ATTENTION", "findings": [minor]}}}}}
        directory = self.make("cnd-groups", [
            line("2026-10-21T10:00:00Z", "run.start", run="cnd-groups"),
            line("2026-10-21T10:00:01Z", "info", run="cnd-groups", reason_code="GROUP_REVIEW"),
            line("2026-10-21T10:00:02Z", "info", run="cnd-groups", reason_code="GROUP_REVIEW"),
            line("2026-10-21T10:00:03Z", "run.end", run="cnd-groups")])
        cases = [
            (None, True, {"Minor": 1}, False),
            ({"1": group}, False, {"Blocker": 1, "Major": 2}, False),
            ({"1": group}, True, {"Blocker": 1, "Major": 2, "Minor": 1}, False),
            ({"1": group, "2": dict(group, counts={"Blocker": 0, "Major": 0, "Minor": 1})},
             False, {"Blocker": 1, "Major": 2, "Minor": 1}, False),
            ({"1": dict(group, format="none", counts={"Blocker": 0, "Major": 0, "Minor": 0})}, False, {}, False),
            ({"1": dict(group, error="ROLE_FAILED")}, False, {}, True),
            ({"1": dict(group, format="malformed")}, False, {}, True),
            ({"1": dict(group, format="empty", error="EMPTY_DIFF")}, False, {}, True),
            ({"1": dict(group, counts={"Major": "bad"})}, False, {}, True),
            (None, False, {}, False),
        ]
        for number, (groups, item_review, expected, incomplete) in enumerate(cases):
            with self.subTest(case=number):
                state = {"status": "finished", "items": {"P1": legacy} if item_review else {}}
                if groups is not None:
                    state["group_reviews"] = groups
                (directory / "state.json").write_text(json.dumps(state), encoding="utf-8")
                report = observer.build(directory, self.project)
                self.assertEqual(report["findings_by_severity"], expected)
                self.assertEqual(report["group_reviews"], groups or {})
                self.assertEqual(bool(report["incomplete_group_reviews"]), incomplete)
                text = observer.markdown(report)
                if incomplete:
                    self.assertIn("Review findings: unavailable", text)
                elif not expected:
                    self.assertIn("Review findings: none", text)
        # A failed review with missing structured state is still not a clean zero-findings review.
        with (directory / "progress.jsonl").open("a", encoding="utf-8") as output:
            output.write("\n" + line("2026-10-21T10:00:04Z", "info", run="cnd-groups",
                                      reason_code="GROUP_REVIEW_FAILED"))
        report = observer.build(directory, self.project)
        self.assertEqual(report["incomplete_group_reviews"], ["GROUP_REVIEW_FAILED"])
        self.assertIn("Review findings: unavailable", observer.markdown(report))

    def test_owner_requires_a_live_lock_and_legacy_status_stays_running(self):
        directory = self.make("cnd-lease", [line("2026-10-16T10:00:00Z", "run.start")], doc={"lease": True})
        with RunLease(directory).acquire("run"):
            owner = RunLease.owner(directory)
            self.assertEqual(owner, runs.listing(self.project)[0]["owner"])
            code, out, err = self.conduct("status", "--run", directory.name, "--json")
            self.assertEqual(0, code, err)
            self.assertEqual(owner, json.loads(out)["lease"])
            self.assertEqual("running", json.loads(out)["status"])
        # Stale metadata is not proof of ownership.
        (directory / "lease.json").write_text(json.dumps(owner))
        code, out, err = self.conduct("status", "--run", directory.name, "--json")
        self.assertEqual(0, code, err)
        self.assertEqual(("orphaned", "RUN_ORPHANED", None),
                         tuple(json.loads(out)[key] for key in ("status", "reason_code", "lease")))
        row = runs.listing(self.project)[0]
        self.assertEqual(("orphaned", None), (row["status"], row["owner"]))
        legacy = self.make("cnd-legacy", [line("2026-10-16T10:00:00Z", "run.start")])
        self.assertEqual("running", runs._row(legacy)["status"])

    def test_status_additions_use_frozen_files_and_effective_raises(self):
        codes = ("BUDGET_OVER", "BUDGET_UNMETERED", "STAGE_INTERRUPTED", "ROLE_ORPHAN_KILLED", "LIMIT_RAISED")
        lines = [line("2026-10-16T10:00:00Z", "run.start"), line("2026-10-16T10:00:00Z", "item.start", item="W1")]
        lines += [line("2026-10-16T10:00:00Z", "info", reason_code=code, message="old") for code in codes]
        lines += [line("2026-10-16T10:00:01Z", "info", reason_code="BUDGET_OVER", message="new")]
        directory = self.make("cnd-status", lines, doc={"limits_run": {
            "run_tokens_hard_max": {"value": 1000, "source": "config:machine"}}})
        folder = directory / "W1"
        folder.mkdir()
        state = {"items": {"W1": {"tokens": {"input": 15, "output": 6}, "usage_incomplete": True}},
                 "tokens": {"input": 15, "output": 6}, "stop": None,
                 "limit_raises": [{"key": "tokens_hard_max", "from": 10, "to": 0}]}
        (directory / "state.json").write_text(json.dumps(state))
        (folder / "options.json").write_text(json.dumps({"options": {"limits": {"tokens_max": 5, "tokens_hard_max": 10}}}))
        (folder / "routes.json").write_text(json.dumps({"executor": {"provider": "codex", "model": "used",
            "model_class": "implementation", "effort": "high", "argv": ["SECRET_ARGV"], "env": {"X": "SECRET_ENV"}}}))
        before = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        code, out, err = self.conduct("status", "--run", directory.name, "--json")
        self.assertEqual(0, code, err)
        found = json.loads(out)
        from orch.conductor import progress
        legacy = progress.summarize(progress.read_lines(directory))
        self.assertEqual(legacy, {**{key: found[key] for key in legacy}, "items": [
            {key: found["items"][0][key] for key in legacy["items"][0]}]})
        item = found["items"][0]
        self.assertEqual(state["items"]["W1"]["tokens"], item["tokens"])
        self.assertTrue(item["usage_incomplete"])
        self.assertEqual({"provider", "model", "effort", "class"}, set(item["routes"]["executor"]))
        self.assertNotIn("SECRET_", out)
        self.assertEqual(0, found["limits"]["items"]["W1"]["tokens_hard_max"])
        self.assertEqual("config:machine", found["limits"]["run_tokens_hard_max"]["source"])
        self.assertEqual(5, len(found["beacons"]))
        self.assertEqual("new", found["beacons"][-1]["message"])
        self.assertEqual(before, {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()})
        state["limit_raises"].append({"key": "run_tokens_hard_max", "from": 1000, "to": 2000})
        (directory / "state.json").write_text(json.dumps(state))
        code, out, err = self.conduct("status", "--run", directory.name, "--json")
        self.assertEqual(0, code, err)
        self.assertEqual({"value": 2000, "source": "invocation:--raise-limit"},
                         json.loads(out)["limits"]["run_tokens_hard_max"])

    def test_status_without_new_files_has_all_additive_keys(self):
        self.make("cnd-empty", [line("2026-10-16T10:00:00Z", "run.start"), line("2026-10-16T10:00:00Z", "item.start", item="W1")])
        code, out, err = self.conduct("status", "--json")
        self.assertEqual(0, code, err)
        doc = json.loads(out)
        self.assertEqual((None, {}, []), (doc["lease"], doc["limits"], doc["beacons"]))
        self.assertEqual((None, None, {}), tuple(doc["items"][0][key] for key in ("tokens", "usage_incomplete", "routes")))

    def test_json_redacts_before_shortening_short_and_long_strings(self):
        token = "sk-" + "A" * 40
        directory = self.make("cnd-secret", [line("2026-10-16T10:00:00Z", "run.start"), line("2026-10-16T10:00:00Z", "item.start", item="W1")])
        folder = directory / "W1"
        folder.mkdir()
        (folder / "routes.json").write_text(json.dumps({"executor": {"provider": "codex", "argv": ["codex"], "model": token}}))
        (directory / "state.json").write_text(json.dumps({"stop": {"code": "ROLE_FAILED", "message": token + "x" * 700}}))
        with RunLease(directory).acquire("run"):
            (directory / "lease.json").write_text(json.dumps({"pid": 1, "host": token, "command": "run"}))
            for argv in (("status", "--json"), ("runs", "--json")):
                code, out, err = self.conduct(*argv)
                self.assertEqual(0, code, err)
                self.assertNotIn(token[:20], out)
                self.assertIn("‹redacted›", out)
        self.assertEqual({"provider": None, "model": None, "effort": None, "class": None},
                         runs.public_route({"model": {"argv": "PRIVATE"}, "effort": ["PRIVATE"]}))

    def test_prompt_step_and_resolved_path_reject_traversal_and_symlinks(self):
        directory = self.make("cnd-prompt")
        prompts = directory / "W1" / "prompts"
        prompts.mkdir(parents=True)
        for step in ("../x", "a/b", "executor.1/../x", "Executor", "executor.1\n"):
            code, out, err = self.conduct("prompt", "explain", "--run", directory.name, "--item", "W1", "--step", step, "--json")
            self.assertEqual((1, ""), (code, out))
            self.assertIn("PROMPT_PATH_INVALID", err)
        outside = self.project / "outside.json"
        outside.write_text('{"text": "PRIVATE"}')
        (prompts / "executor.1.manifest.json").symlink_to(outside)
        code, out, err = self.conduct("prompt", "explain", "--item", "W1", "--step", "executor.1", "--json")
        self.assertEqual((1, ""), (code, out))
        self.assertIn("PROMPT_PATH_INVALID", err)
        (prompts / "executor.1.manifest.json").unlink()
        prompts.rmdir()
        prompts.symlink_to(self.project, target_is_directory=True)
        code, out, err = self.conduct("prompt", "explain", "--item", "W1", "--step", "executor.1", "--json")
        self.assertEqual(1, code)
        self.assertIn("PROMPT_PATH_INVALID", err)

    def test_valid_prompt_steps_still_read_the_manifest(self):
        directory = self.make("cnd-prompt")
        folder = directory / "W1" / "prompts"
        folder.mkdir(parents=True)
        for step in ("scout", "executor.1", "executor.1-q2", "context-scout"):
            doc = {"step": step, "blocks": []}
            (folder / f"{step}.manifest.json").write_text(json.dumps(doc))
            code, out, err = self.conduct("prompt", "explain", "--item", "W1", "--step", step, "--json")
            self.assertEqual(0, code, err)
            self.assertEqual(doc, json.loads(out))


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


ORCH = Path(__file__).resolve().parents[1]
CLAUDE_STREAM = "".join(json.dumps(event) + "\n" for event in (
    {"type": "assistant", "timestamp": "2026-09-01T09:00:01Z", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "python3 -m unittest tests.test_x"}}]}},
    {"type": "user", "timestamp": "2026-09-01T09:00:31Z", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1"}]}},
    {"type": "assistant", "timestamp": "2026-09-01T09:01:00Z", "message": {"content": [{"type": "text", "text": "done"}]}}))
GROK_STREAM = "".join(json.dumps(event) + "\n" for event in (  # no times of its own: the .times file times it
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a.py"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1"}]}}))


class ConductCompressTests(ConductPruneTests):
    STREAMS = ("W1/streams/executor.1.jsonl", "W1/streams/executor.1.stderr", "W1/streams/executor.1.jsonl.times",
               "W1/streams/review.1.jsonl", "W1/streams/review.1.jsonl.times", "W1/streams/scout.txt",
               "W1/attempts/1/streams/executor.1.jsonl", "streams/group-review-1.jsonl")
    KEPT = ("progress.jsonl", RUN_FILE, "W1/prompts/executor.1.md", "W1/streams/notes.md")

    def streamed(self, run_id: str, day: str, outcome: str = "done") -> Path:
        directory = self.ended(run_id, day, outcome)
        contents = {"W1/streams/executor.1.jsonl": CLAUDE_STREAM, "W1/streams/review.1.jsonl": GROK_STREAM,
                    "W1/streams/review.1.jsonl.times": f"1.5 {len(GROK_STREAM.splitlines(True)[0].encode())}\n"
                                                       f"31.5 {len(GROK_STREAM.encode())}\n"}
        for name in self.STREAMS + self.KEPT[2:]:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents.get(name, f"{name}\n" * 50), encoding="utf-8")
        return directory

    def files(self, root: Path) -> dict:
        """Every file below ``root`` and its bytes, but the lock file the lease leaves (as ``prune`` does)."""
        return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*"))
                if path.is_file() and path.name != "lease.lock"}

    def latest(self) -> Path:
        latest = self.streamed("cnd-z-latest", "2026-08-02")
        os.utime(latest / "progress.jsonl", (self.NOW * 2, self.NOW * 2))  # the last journal to change
        return latest

    def test_a_dry_run_lists_the_streams_and_changes_nothing(self):
        old = self.streamed("cnd-old", "2026-09-01")
        self.latest()
        before = self.files(self.project)
        rows = runs.compress(self.project, 30, now=self.NOW)
        self.assertEqual(before, self.files(self.project))
        self.assertEqual(["cnd-old"], [row["run_id"] for row in rows])
        self.assertEqual(sorted(str((old / name).relative_to(self.project)) for name in self.STREAMS), rows[0]["compressed"])
        self.assertEqual(sum((old / name).stat().st_size for name in self.STREAMS), rows[0]["bytes_before"])
        self.assertIsNone(rows[0]["bytes_after"])
        self.assertIn("would be packed", runs.compress_text(rows, False))

    def test_apply_packs_the_streams_of_an_old_terminal_run_only(self):
        old = self.streamed("cnd-old", "2026-09-01")
        recent = self.streamed("cnd-new", "2026-10-13")
        running = self.streamed("cnd-running", "2026-08-01")
        (running / "progress.jsonl").write_text(line("2026-08-01T09:00:00Z", "run.start") + "\n", encoding="utf-8")
        latest = self.latest()
        link = old / "W1" / "streams" / "linked.jsonl"
        link.symlink_to(recent / "W1" / "streams" / "executor.1.jsonl")
        untouched = {path: self.files(path) for path in (recent, running, latest)}
        plain = {name: (old / name).read_bytes() for name in self.STREAMS}
        kept = {name: (old / name).read_bytes() for name in self.KEPT}
        rows = runs.compress(self.project, 30, apply=True, now=self.NOW)
        self.assertEqual(["cnd-old"], [row["run_id"] for row in rows])
        self.assertNotIn("reason", rows[0])
        for name, data in plain.items():
            self.assertFalse((old / name).exists(), name)
            with gzip.open(old / f"{name}.gz", "rb") as handle:
                self.assertEqual(data, handle.read(), name)
        self.assertEqual({name: data for name, data in kept.items()}, {name: (old / name).read_bytes() for name in self.KEPT})
        self.assertTrue(link.is_symlink())
        self.assertEqual([], list(old.rglob("*.partial")))
        self.assertEqual(sum(len(data) for data in plain.values()), rows[0]["bytes_before"])
        self.assertEqual(sum((old / f"{name}.gz").stat().st_size for name in self.STREAMS), rows[0]["bytes_after"])
        self.assertLess(rows[0]["bytes_after"], rows[0]["bytes_before"])
        self.assertEqual(untouched, {path: self.files(path) for path in (recent, running, latest)})
        self.assertEqual([], runs.compress(self.project, 30, apply=True, now=self.NOW))  # nothing left to pack

    def test_a_busy_lease_skips_the_run_with_its_reason(self):
        old = self.streamed("cnd-old", "2026-09-01")
        self.latest()
        before = self.files(old)
        with RunLease(old).acquire("resume"):
            rows = runs.compress(self.project, 30, apply=True, now=self.NOW)
        self.assertIn("RUN_BUSY", rows[0]["reason"])
        self.assertEqual([], rows[0]["compressed"])
        self.assertIn("skipped", runs.compress_text(rows, True))
        self.assertEqual(before, self.files(old))

    def test_a_copy_that_does_not_read_back_keeps_the_stream(self):
        old = self.streamed("cnd-old", "2026-09-01")
        self.latest()
        before = self.files(old)
        with mock.patch.object(runs, "_same", return_value=False):
            rows = runs.compress(self.project, 30, apply=True, now=self.NOW)
        self.assertIn("not packed", rows[0]["reason"])
        self.assertEqual([], rows[0]["compressed"])
        self.assertEqual(rows[0]["bytes_before"], rows[0]["bytes_after"])
        self.assertEqual(before, self.files(old))  # no .gz, no partial file, every stream as it was

    def test_the_readers_of_streams_read_the_packed_files(self):
        old = self.streamed("cnd-old", "2026-09-01")
        self.latest()
        runs.compress(self.project, 30, apply=True, now=self.NOW)
        stream = old / "W1" / "streams" / "executor.1.jsonl"
        self.assertFalse(stream.exists())
        self.assertEqual("Bash: python3 -m unittest tests.test_x", process._last_command(stream))
        with process.open_stream(stream, "r") as handle:
            self.assertEqual(CLAUDE_STREAM, handle.read())
        with self.assertRaises(FileNotFoundError):
            process.open_stream(old / "W1" / "streams" / "missing.jsonl")

        def script(name: str, *argv: str) -> str:
            done = subprocess.run([sys.executable, str(ORCH / "scripts" / name), *argv], capture_output=True, text=True,
                                  cwd=self.project, check=False, timeout=60)
            self.assertEqual(0, done.returncode, done.stderr)
            return done.stdout

        profile = script("step-profile.py", str(stream))
        self.assertIn("Bash: python3 -m unittest tests.test_x", profile)
        self.assertIn("Прогоны тестов/проверок: 1", profile)
        timed = script("step-profile.py", str(old / "W1" / "streams" / "review.1.jsonl"))  # stream and .times packed
        self.assertIn("Read: a.py", timed)
        self.assertNotIn("нет меток времени", timed)
        with open(old / "progress.jsonl", "a", encoding="utf-8") as handle:  # the journal is never packed
            handle.write(line("2026-09-01T10:30:00Z", "stage.end", run="cnd-old", item="W1", stage="executor.1",
                              role="executor", duration_s=90, tokens={"input": 1200, "cached": 300, "output": 45},
                              verdict="done") + "\n")
        usage = script("run-usage.py", "--root", str(runs_root(self.project)), "cnd-old")
        self.assertIn("| W1 | executor.1 | executor  | 1.5 мин | 1,200 | 300 | 45 | done |", usage)

    def test_the_cli_compresses_dry_run_unless_apply_and_checks_its_flags(self):
        old = self.streamed("cnd-old", "2026-09-01")
        self.latest()
        code, out, _ = self.conduct("prune", "--compress-older-than", "30")
        self.assertEqual(0, code)
        self.assertIn("would be packed", out)
        self.assertIn("--apply", out)
        self.assertTrue((old / "W1" / "streams" / "executor.1.jsonl").is_file())
        code, out, _ = self.conduct("prune", "--compress-older-than", "30", "--apply", "--json")
        self.assertEqual(0, code)
        doc = json.loads(out)
        self.assertEqual([], contract.problems(doc, "compress-result"))
        self.assertTrue(doc["apply"])
        self.assertEqual(len(self.STREAMS), len(doc["runs"][0]["compressed"]))
        self.assertTrue((old / "W1" / "streams" / "executor.1.jsonl.gz").is_file())
        self.assertTrue((old / RUN_FILE).is_file())  # packing removes no run
        for bad in (("--compress-older-than", "0"), ("--compress-older-than", "5", "--older-than", "5"),
                    ("--compress-older-than", "5", "--apply", "--dry-run"), ()):
            with self.assertRaises(SystemExit):
                self.conduct("prune", *bad)


if __name__ == "__main__":
    unittest.main()
