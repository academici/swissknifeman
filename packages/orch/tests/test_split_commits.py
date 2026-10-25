"""commit.mode ``implementation-and-fixes`` (P7.7): the checkpoint commit before the review, one fix commit per green correction
round, the final commit of what is left, the receipts per stage, the review base and the group review across the commits of a
piece. The default ``final-only`` keeps its one commit, its message and its receipts. Fake roles and a fake work source only."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from orch import adhoc, journal
from orch.conductor import records, review_batch
from orch.conductor.domain.stop import Stop
from orch.conductor.application import recovery
from orch.conductor.infrastructure import commit_stages
from orch.worksource_file import FileWorkSource
from tests.test_conductor import FINDING, GREEN, ConductorCase, executor_ok, report
from tests.test_conductor_review_plan import answer
from tests.test_records_contract import EXAMPLES

SPLIT = {"commit": {"mode": "implementation-and-fixes"}}
REPRO = {"cmd": "cat out/W1.txt", "exit": 0, "observed": "ok"}
TRIAGE = {"result": {"confirmed": [{"finding": "F1", "reproduction": REPRO, "fix": "write done instead of ok"}],
                     "rejected": []}}
CORRECTED = {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}


class SplitCase(ConductorCase):
    def options(self, doc=None, name="split-options.json") -> tuple:
        path = self.project.parent / name
        path.write_text(json.dumps(SPLIT if doc is None else doc), encoding="utf-8")
        return ("--options", path)

    def run_split(self, *extra, items=("W1",)) -> str:
        code, _, err = self.run_items(*items, extra=self.options() + extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return err

    def commits(self) -> list:
        return self.source()["commits"]

    def message(self, sha: str) -> str:
        return self.git("log", "-1", "--format=%B", sha)

    def files(self, sha: str) -> list:
        return self.git("show", "--name-only", "--format=", sha).split()

    def receipts(self, err: str, ref: str = "W1") -> Path:
        return journal.run_dir(self.state(err)["items"][ref]["orch_run"], project=self.project) / "receipts"

    def trailers(self, sha: str) -> dict:
        return dict(line.split(": ", 1) for line in self.message(sha).splitlines() if line.startswith("Plan-"))


class FinalOnlyTests(SplitCase):
    def test_a_the_default_is_one_commit_with_the_old_message_and_receipts(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        [only] = self.commits()
        self.assertEqual((only["paths"] != [], "stage" in only, "role" in only, "trailers" in only), (True, False, False, False))
        self.assertEqual(self.message(only["sha"]).strip(), "feat: W1")
        self.assertEqual(self.git("rev-list", "--count", f"{base}..HEAD").strip(), "1")
        self.assertEqual(sorted(path.name for path in self.receipts(err).glob("commit*")),
                         ["commit-request.json", "commit.json"])
        self.assertNotIn("commits", self.state(err)["items"]["W1"])
        self.assertEqual(self.state(err)["items"]["W1"]["steps"].keys() & {"checkpoint"}, set())

    def test_the_same_run_with_the_mode_named_final_only_is_the_default(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options({"commit": {"mode": "final-only"}}))
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.commits()), 1)


class SplitCommitTests(SplitCase):
    def test_b_a_green_first_review_gives_the_implementation_and_the_final_commit(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        err = self.run_split()
        implementation, final = self.commits()
        self.assertEqual((implementation["stage"], implementation["role"], implementation["paths"]),
                         ("implementation", "executor", ["out/W1.txt"]))
        self.assertEqual((final["stage"], final["role"]), ("final", "executor"))
        self.assertEqual(self.files(implementation["sha"]), ["out/W1.txt"])
        self.assertTrue(all(path.startswith("plans/T/artifacts/W1/") for path in self.files(final["sha"])), self.files(final["sha"]))
        orch_run = self.state(err)["items"]["W1"]["orch_run"]
        first = self.trailers(implementation["sha"])
        self.assertEqual((first["Plan-Run"], first["Plan-Stage"], bool(first["Plan-Attempt"])), (orch_run, "implementation", True))
        self.assertEqual(self.trailers(final["sha"])["Plan-Stage"], "final")
        self.assertEqual(self.state(err)["items"]["W1"]["commits"],
                         [{"stage": "implementation", "sha": implementation["sha"], "parent": base}])
        self.assertEqual(sorted(path.name for path in self.receipts(err).glob("commit*")),
                         ["commit-implementation-request.json", "commit-implementation.json", "commit-request.json",
                          "commit.json"])
        started = [row["stage"] for row in self.lines(err) if row["event"] == "stage.start"]
        self.assertLess(started.index("checkpoint"), started.index("review.1"))  # the checkpoint is before the review

    def test_c_a_correction_is_a_fix_commit_between_the_implementation_and_the_final(self):
        self.script({"executor": [executor_ok("W1"), CORRECTED], "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        err = self.run_split()
        implementation, fix, final = self.commits()
        self.assertEqual([(row["stage"], row["role"]) for row in (implementation, fix, final)],
                         [("implementation", "executor"), ("correction.1", "fix"), ("final", "executor")])
        self.assertEqual(self.git("show", f"{implementation['sha']}:out/W1.txt"), "ok\n")  # the fix did not move into it
        self.assertEqual(self.git("show", f"{fix['sha']}:out/W1.txt"), "done\n")
        self.assertEqual(self.files(fix["sha"]), ["out/W1.txt"])
        verdict = json.loads((self.project / "plans/T/artifacts/W1/review-verdict.json").read_text())
        key = verdict["rounds"][0]["findings"][0]["key"]
        trailers = self.trailers(fix["sha"])
        self.assertEqual((trailers["Plan-Stage"], trailers["Plan-Findings"]), ("correction.1", key))
        self.assertEqual(trailers["Plan-Review"], f"{self.run_dir(err).name}/W1/review.1")
        self.assertEqual([row["stage"] for row in self.state(err)["items"]["W1"]["commits"]], ["implementation", "correction.1"])
        self.assertIn("commit-correction.1.json", [path.name for path in self.receipts(err).glob("commit*")])

    def test_d_the_review_starts_from_the_parent_of_the_first_commit_and_its_diff_is_not_empty(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.script({"executor": [executor_ok("W1"), CORRECTED], "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        err = self.run_split()
        steps = self.state(err)["items"]["W1"]["steps"]
        self.assertEqual([steps[key]["result"]["base"] for key in ("review.1", "review.2")], [base, base])
        for number in (1, 2):  # HEAD as the base would show no change: the implementation is already committed
            self.assertIn("diff --git a/out/W1.txt", self.prompt("reviewer", number))
        self.assertNotEqual(base, self.git("rev-parse", "HEAD").strip())

    def test_the_review_base_is_head_without_a_stage_commit(self):
        item = mock.Mock(state={})
        owner = mock.Mock(project=self.project)
        self.assertEqual(self.review_base(owner, item), self.git("rev-parse", "HEAD").strip())
        item.state = {"commits": [{"stage": "implementation", "sha": "b" * 40, "parent": "a" * 40}]}
        self.assertEqual(self.review_base(owner, item), "a" * 40)

    @staticmethod
    def review_base(owner, item) -> str:
        from orch.conductor.stages import review
        return review.review_base(owner, item)

    def overlapping(self) -> None:
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "checks": {"parallel": 2, "overlap_review": True}}}]}})

    def stages(self, err: str) -> list:
        return [row["stage"] for row in self.lines(err) if row["event"] == "stage.start"]

    def test_the_review_does_not_overlap_the_checks_of_a_split_run(self):
        """An overlapping review.1 would start before the checkpoint and could end before a red check, whose combined
        correction the checkpoint would then take along."""
        self.overlapping()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        err = self.run_split()
        started = self.stages(err)
        self.assertLess(started.index("checks.1"), started.index("checkpoint"))
        self.assertLess(started.index("checkpoint"), started.index("review.1"))
        self.assertNotIn("at the same time", self.prompt("reviewer", 1))

    def test_a_red_check_and_a_finding_keep_the_implementation_and_the_correction_in_their_own_commits(self):
        self.overlapping()
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1"), CORRECTED],
                     "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        err = self.run_split()
        stages = [row["stage"] for row in self.commits()]
        self.assertEqual(stages, ["implementation", "correction.1", "final"])
        self.assertEqual(self.git("show", f"{self.commits()[0]['sha']}:out/W1.txt"), "ok\n")
        fix = self.trailers(self.commits()[1]["sha"])
        self.assertEqual((fix["Plan-Stage"], fix["Plan-Review"]), ("correction.1", f"{self.run_dir(err).name}/W1/review.1"))
        self.assertRegex(fix["Plan-Findings"], r"^fk-[0-9a-f]{16}$")
        started = self.stages(err)
        self.assertLess(started.index("checkpoint"), started.index("review.1"))

    def test_g_a_stage_commit_takes_only_the_paths_of_the_piece(self):
        (self.project / "scratch.txt").write_text("owner\n", encoding="utf-8")  # someone else's, untracked
        self.write_config(extra='[orch.conductor]\nforeign_untracked = "keep"\n')
        stray = {"write": {"out/W1.txt": "ok\n", "tests/evidence/run.log": "log\n"}, "result": report("W1")}
        self.script({"executor": [stray], "reviewer": [GREEN]})
        self.run_split()
        for row in self.commits():
            names = self.files(row["sha"])
            self.assertNotIn("scratch.txt", names, row["stage"])
            self.assertFalse([name for name in names if name.startswith((".swissknifeman/", "tests/evidence/"))], names)
        implementation = self.commits()[0]
        self.assertEqual(self.files(implementation["sha"]), ["out/W1.txt"])
        self.assertIn("scratch.txt", self.git("status", "--porcelain"))
        self.assertNotIn("plans/", " ".join(self.files(implementation["sha"])))  # the records wait for the final commit


class RecoveryTests(SplitCase):
    def test_e_a_crash_between_the_commit_and_its_receipt_commits_the_stage_once(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        original = journal.write_doc

        def crash(directory, name, doc):
            if name == "receipts/commit-implementation.json":
                raise RuntimeError("killed between the commit of the stage and its receipt")
            return original(directory, name, doc)

        with mock.patch.object(journal, "write_doc", side_effect=crash):
            code, _, err = self.run_items("W1", extra=self.options())
        self.assertEqual(code, 1, err)
        self.assertEqual(self.outcome(err), ("stopped", "CONDUCTOR_CRASHED"))
        run_id = self.run_dir(err).name
        [taken] = self.commits()
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["checkpoint"]["status"], "started")
        code, _, resumed = self.conduct("resume", "--run", run_id, "--json-lines")
        self.assertEqual(code, 0, resumed)
        self.assertEqual([row["stage"] for row in self.commits()], ["implementation", "final"])  # one commit of the stage
        self.assertEqual(self.git("log", "--format=%B").count("Plan-Stage: implementation"), 1)
        item = self.state(resumed)["items"]["W1"]
        self.assertEqual(item["steps"]["checkpoint"]["result"]["sha"], taken["sha"])  # found by its trailer
        self.assertEqual([row["sha"] for row in item["commits"]], [taken["sha"]])
        said = [row["message"] for row in self.lines(resumed) if row.get("reason_code") == "STAGE_INTERRUPTED"]
        self.assertIn("closed from the Plan-Stage trailer of the commit", said)

    def test_a_source_that_dies_after_the_commit_is_recovered_from_its_trailer_on_resume(self):
        """The source process is killed after git commit, before its receipt: the conductor gets no answer and stops the step
        (COMMIT_REFUSED), it does not stay ``started``. The resume finds the one commit, keeps the base of the review."""
        base = self.git("rev-parse", "HEAD").strip()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        original = journal.write_doc

        def killed(directory, name, doc):
            if name == "receipts/commit-implementation.json":
                raise SystemExit(137)  # the transport of the tests turns it into an exit code and an empty answer
            return original(directory, name, doc)

        with mock.patch.object(journal, "write_doc", side_effect=killed):
            code, _, err = self.run_items("W1", extra=self.options())
        self.assertEqual((code, self.outcome(err)[0]), (1, "stopped"))
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["checkpoint"]["status"], "stopped")
        self.assertNotIn("commits", self.state(err)["items"]["W1"])
        [taken] = self.commits()
        code, _, resumed = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual(code, 0, resumed)
        item = self.state(resumed)["items"]["W1"]
        self.assertEqual(item["commits"], [{"stage": "implementation", "sha": taken["sha"], "parent": base}])
        self.assertEqual([row["stage"] for row in self.commits()], ["implementation", "final"])
        self.assertEqual(item["steps"]["review.1"]["result"]["base"], base)
        self.assertIn("diff --git a/out/W1.txt", self.prompt("reviewer", 1))

    def test_a_crash_between_the_closed_fix_step_and_its_record_still_reaches_the_state_and_the_audit(self):
        from orch.conductor.stages import execute, finish
        extra = {"write": {"out/W1.txt": "done\n", "out/extra.txt": "more\n"}, "result": report("W1")}
        self.script({"executor": [executor_ok("W1"), extra], "reviewer": [FINDING, GREEN], "triager": [TRIAGE]})
        record = finish.record_commit

        def crash(owner, item, stage, result):
            if stage == "correction.1":
                raise RuntimeError("killed after the step closed, before the record")
            return record(owner, item, stage, result)

        with mock.patch.object(finish, "record_commit", side_effect=crash):
            code, _, err = self.run_items("W1", extra=self.options())
        self.assertEqual(self.outcome(err), ("stopped", "CONDUCTOR_CRASHED"))
        self.assertEqual(self.state(err)["items"]["W1"]["steps"]["fix-commit.1"]["status"], "done")
        code, _, resumed = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual(code, 0, resumed)
        state = self.state(resumed)
        item = state["items"]["W1"]
        self.assertEqual([row["stage"] for row in item["commits"]], ["implementation", "correction.1"])
        self.assertEqual(len([row for row in self.commits() if row.get("stage") == "correction.1"]), 1)
        fix = item["commits"][1]["sha"]
        owner = mock.Mock(state=state, directory=self.run_dir(resumed))
        self.assertIn(fix[:12], execute.handoff_of(owner, "W1"))
        self.assertIn("out/extra.txt", self.prompt("reviewer", 2))  # the corrected audit reads what the fix commit took

    def test_a_stage_without_its_commit_in_the_history_is_repeated(self):
        """A request that never led to a commit (the crash was before the effect) is not closed by an older commit."""
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        err = self.run_split()
        item = self.state(err)["items"]["W1"]
        claim = {"attempt_id": "att-other"}
        other = recovery.Item("W1", item["orch_run"], item, self.run_dir(err) / "W1", claim)
        self.assertIsNone(commit_stages.committed_stage(other, "implementation", project=self.project))

    def test_the_step_keys_and_receipt_names_of_the_stages(self):
        self.assertEqual([commit_stages.stage_of(key) for key in ("checkpoint", "fix-commit.2", "commit", "register")],
                         ["implementation", "correction.2", None, None])
        self.assertEqual([commit_stages.receipt_stem(key) for key in ("checkpoint", "fix-commit.2", "commit", "close")],
                         ["commit-implementation", "commit-correction.2", "commit", "register"])
        self.assertEqual([commit_stages.stage_step(stage) for stage in ("implementation", "correction.3")],
                         ["checkpoint", "fix-commit.3"])


class GroupReviewTests(SplitCase):
    def test_f_the_group_review_reads_the_diff_from_the_first_to_the_last_commit_of_a_piece(self):
        repo = Path(tempfile.mkdtemp(dir=self.project.parent))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(repo)])

        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

        git("init", "-q", "-b", "main")
        for key, value in (("user.name", "T"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
            git("config", key, value)
        shas = []
        for name, text in (("init.txt", "init\n"), ("base.txt", "base\n"), ("lib/a.py", "a = 1\n"), ("lib/a.py", "a = 2\n"),
                           ("lib/b.py", "b = 1\n")):
            (repo / name).parent.mkdir(exist_ok=True)
            (repo / name).write_text(text, encoding="utf-8")
            git("add", "-A")
            git("commit", "-q", "-m", name)
            shas.append(git("rev-parse", "HEAD"))
        state = {"items": {
            "W1": {"commits": [{"stage": "implementation", "sha": shas[2], "parent": shas[1]},
                               {"stage": "correction.1", "sha": shas[3], "parent": shas[2]}],
                   "steps": {"commit": {"status": "done", "result": {"outcome": "committed", "sha": shas[4]}}}},
            "W2": {"steps": {"commit": {"status": "done", "result": {"outcome": "committed", "sha": shas[1]}}}}}}
        refs, found = review_batch.commits_of_state(state)
        self.assertEqual((refs, found), (["W1", "W2"], [shas[2:], shas[1]]))
        self.assertEqual(review_batch.last_sha(found[0]), shas[4])
        diff = review_batch.diff_of(repo, found[:1], ["."], [])
        self.assertIn("+a = 2", diff)       # the correction
        self.assertIn("+b = 1", diff)       # the last commit
        self.assertNotIn("-a = 1", diff)    # one range: the implementation and its correction are one change
        self.assertNotIn("+base", diff)
        self.assertIn("+base", review_batch.diff_of(repo, found[1:], ["."], []))  # a one-commit piece is read as before

    def test_f_a_split_run_in_a_group_review_gives_the_reviewer_the_checkpoint_commit(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN], "triager": [answer("single", [["W1"]])]})
        options = self.options({**SPLIT, "review": {"strategy": "single"}})
        code, _, err = self.run_items("W1", extra=options)
        self.assertEqual(code, 0, err)
        # the final commit alone holds only the records of the piece, which the group review leaves out
        self.assertIn("diff --git a/out/W1.txt", self.prompt("reviewer", 1))


class FollowupCommitTests(unittest.TestCase):
    """The commit of a group-review follow-up names the plan, the pieces and the findings it answers (K2-N7)."""

    def repo(self) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(folder)])
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@example.invalid"],
                     ["config", "commit.gpgsign", "false"]):
            subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True)
        (folder / "a.py").write_text("a = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=folder, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=folder, check=True, capture_output=True)
        return folder

    def followup(self, folder: Path, **fields) -> dict:
        provenance = adhoc.support_provenance("review_followup", **fields)
        doc = adhoc.build_adhoc_input("Correct the findings", ["a.py"], procedures=["V1=fixed"], provenance=provenance)
        path = folder.parent / f"{folder.name}-followup.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        (folder / "a.py").write_text("a = 2\n", encoding="utf-8")
        answer = FileWorkSource(path, project=folder, commit=True).commit(
            plan=str(path), ref=doc["input_id"], run_id="run-x", attempt_id="att-run-x-a", paths=["a.py"],
            trailers=["Plan-Run: run-x"])
        self.assertEqual(answer["outcome"], "committed", answer)
        return dict(line.split(": ", 1) for line in subprocess.run(
            ["git", "log", "-1", "--format=%B"], cwd=folder, capture_output=True, text=True, check=True).stdout.splitlines()
            if line.startswith("Plan"))

    def test_the_provenance_of_a_followup_gives_the_trailers_of_its_commit(self):
        trailers = self.followup(self.repo(), plan="PLAN9", items=["W1", "W2"],
                                 findings=["fk-0123456789abcdef", "fk-fedcba9876543210"],
                                 session_ref={"run": "cnd-1", "item": "W2", "items": ["W1", "W2"]})
        self.assertEqual(trailers, {"Plan-Run": "run-x", "Plan": "PLAN9", "Plan-Review": "cnd-1",
                                    "Plan-Findings": "fk-0123456789abcdef,fk-fedcba9876543210", "Plan-Items": "W1,W2"})

    def test_a_followup_without_plan_or_keys_adds_only_what_the_caller_asked_for(self):
        self.assertEqual(self.followup(self.repo(), item="W1"), {"Plan-Run": "run-x"})

    def test_the_provenance_accepts_the_lists_and_refuses_an_unknown_field(self):
        self.assertEqual(adhoc.support_provenance("review_followup", items=["W1"], findings=["fk-1"]),
                         {"kind": "review_followup", "items": ["W1"], "findings": ["fk-1"]})
        with self.assertRaises(adhoc.AdhocError):
            adhoc.support_provenance("review_followup", keys=["fk-1"])


class HandoffTests(unittest.TestCase):
    def test_the_handoff_of_a_split_piece_names_every_commit(self):
        from types import SimpleNamespace
        from orch.conductor.stages import execute
        piece = {"commits": [{"stage": "implementation", "sha": "a" * 40, "parent": "0" * 40},
                             {"stage": "correction.1", "sha": "b" * 40, "parent": "a" * 40}],
                 "steps": {"commit": {"status": "done", "result": {"outcome": "committed", "sha": "c" * 40}}}}
        owner = SimpleNamespace(state={"items": {"W1": piece, "W2": {"steps": {"commit": {
            "status": "done", "result": {"outcome": "committed", "sha": "d" * 40}}}}}}, directory=Path(tempfile.gettempdir()))
        self.assertIn("(commits aaaaaaaaaaaa, bbbbbbbbbbbb, cccccccccccc)", execute.handoff_of(owner, "W1"))
        self.assertIn("(commit dddddddddddd)", execute.handoff_of(owner, "W2"))  # one commit: as before


class RecordsTests(unittest.TestCase):
    """The state of a piece keeps ``commits``; a state written before this change is read and resumed as it was."""

    def test_a_state_with_commits_is_a_valid_record_and_one_without_them_still_is(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("green.json", "split-commits.json"):
                doc = json.loads((EXAMPLES / "valid" / "state" / name).read_text(encoding="utf-8"))
                path = Path(folder) / name
                records.write(path, doc, "state")
                loaded = records.read(path, "state")
                self.assertEqual(loaded["items"]["W1"].get("commits"), doc["items"]["W1"].get("commits"))
        old = json.loads((EXAMPLES / "valid" / "state" / "green.json").read_text(encoding="utf-8"))
        self.assertEqual(review_batch.commits_of_state(old)[1], ["3f" * 32])  # the single commit of a final-only piece

    def test_the_invalid_examples_are_refused(self):
        for name in ("pattern-commit-stage.json", "required-commit-parent.json"):
            doc = json.loads((EXAMPLES / "invalid" / "state" / name).read_text(encoding="utf-8"))
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(Stop) as refused:
                path = Path(folder) / "state.json"
                path.write_text(json.dumps(doc), encoding="utf-8")
                records.read(path, "state")
            self.assertEqual(refused.exception.code, "STATE_INVALID", name)


if __name__ == "__main__":
    unittest.main()
