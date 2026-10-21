"""The round of checks: cheapest first, fail-fast, phase checks after green item checks, reuse of green evidence of the
same candidate, and the environment (``SKM_CHECK_*``, the share of the jobs budget) of a check."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import checks  # noqa: E402
from orch.conductor.domain import report as report_rules  # noqa: E402
from orch.conductor.stages import checks_stage, finish  # noqa: E402


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=str(root), check=True,
                   capture_output=True)


def check(check_id, cmd=None, **extra):
    row = {"id": check_id, "kind": "acceptance", **extra}
    if cmd is not None:
        row["cmd"] = cmd
    return row


def doc(*specs):
    """Checks as ``(id, cmd)`` pairs, or as dicts."""
    return {"input_id": "T.W1@abc", "acceptance": {"checks": [spec if isinstance(spec, dict) else check(*spec)
                                                               for spec in specs]}}


class Case(unittest.TestCase):
    """A git project and, beside it, the folder of the logs and of the files the checks leave to be counted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.out = Path(self.tmp.name) / "out"
        self.out.mkdir()
        git(self.root, "init", "-q")
        (self.root / "tracked.txt").write_text("one\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("counts/\nlocal/\n*.local\n", encoding="utf-8")  # ignored: counters, inputs
        self.counts = self.root / "counts"
        self.counts.mkdir()
        git(self.root, "add", "tracked.txt", ".gitignore")
        git(self.root, "commit", "-q", "-m", "x")
        patcher = mock.patch.dict(os.environ, {"SKM_TEST_JOBS": "8"})  # a runner worker may hold a budget of 1
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [name for name in os.environ if name.endswith(("_ROOT", "_PY"))]:  # roots of the machine: not this test's
            del os.environ[name]
        self.calls = 0

    def run_round(self, document, *, run_id="cnd-1", number=1, **options):
        self.calls += 1
        options.setdefault("run_id", options.pop("run_id_of_reuse", run_id))
        return checks.run_checks(document, project=self.root, evidence_dir=self.root / "ev",
                                 log_dir=self.out / f"log{self.calls}", timeout_s=30,
                                 evidence_prefix=f"{run_id}:T.W1:checks.{number}", **options)

    def count(self, name="count") -> int:
        """How many times check V1 really ran (a log per run; a reused check leaves none), or the lines of a counter file."""
        if name == "count":
            return len(list(self.out.glob("log*/V1.log")))
        path = self.counts / name
        return len(path.read_text(encoding="utf-8").split()) if path.exists() else 0

    def counting(self, name="count") -> str:
        """A command that does nothing for ``count`` (the logs count the runs), else one that appends to a counter file."""
        return "true" if name == "count" else f"echo x >> {self.counts / name}"

    def evidence(self, check_id="V1") -> Path:
        return self.root / "ev" / f"{check_id}.json"


class ScheduleTests(unittest.TestCase):
    def ids(self, *args):
        items, phase = checks.schedule(*args)
        return [c["id"] for c in items], [c["id"] for c in phase]

    def test_red_checks_of_the_round_before_go_first_then_the_cheapest_then_the_unknown(self):
        wanted = [check(name, "true") for name in ("A", "B", "C", "D", "E")]
        previous = [{"id": "B", "seconds": 30.0, "green": True}, {"id": "C", "seconds": 2.0, "green": True},
                    {"id": "E", "seconds": 5.0, "green": False}]
        self.assertEqual(self.ids(wanted, previous, ["E"]), (["E", "C", "B", "A", "D"], []))

    def test_the_latest_time_of_a_check_counts_and_skipped_or_reused_rows_do_not_hide_it(self):
        wanted = [check(name, "true") for name in ("A", "B", "C")]
        previous = [{"id": "A", "seconds": 1.0}, {"id": "B", "seconds": 5.0},
                    {"id": "A", "seconds": 9.0},  # the latest of A
                    {"id": "B", "skipped": True, "green": False},  # says nothing
                    {"id": "C", "reused": True, "seconds": 0, "original_seconds": 3}]  # the time of the run it stands for
        self.assertEqual(self.ids(wanted, previous, [])[0], ["C", "B", "A"])

    def test_phase_checks_are_kept_apart_in_input_order(self):
        wanted = [check("A", "true"), check("P1", "true", cadence="phase"), check("B", "true"),
                  check("P2", "true", cadence="phase")]
        self.assertEqual(self.ids(wanted, [], []), (["A", "B"], ["P1", "P2"]))


class OrderTests(Case):
    def test_checks_run_cheapest_first_and_the_rows_keep_the_input_order(self):
        order = self.counts / "order"
        document = doc(*[(name, f"echo {name} >> {order}") for name in ("V1", "V2", "V3")])
        previous = [{"id": "V1", "seconds": 9}, {"id": "V2", "seconds": 1}]
        rows = self.run_round(document, parallel=1, previous=previous, reuse=False)
        self.assertEqual(order.read_text(encoding="utf-8").split(), ["V2", "V1", "V3"])
        self.assertEqual([row["id"] for row in rows], ["V1", "V2", "V3"])


class FailFastTests(Case):
    def document(self):
        return doc(("V1", "exit 1"), ("V2", self.counting("b")), ("V3", self.counting("c")))

    def test_sequential_a_red_check_skips_the_rest(self):
        rows = self.run_round(self.document(), parallel=1)
        self.assertEqual([(row["id"], row["green"], bool(row.get("skipped")), row.get("skip_reason")) for row in rows],
                         [("V1", False, False, None), ("V2", False, True, "fail_fast"), ("V3", False, True, "fail_fast")])
        self.assertEqual((self.count("b"), self.count("c")), (0, 0))
        self.assertIsNone(rows[1]["evidence"])
        self.assertFalse(self.evidence("V2").exists())

    def test_in_parallel_the_check_that_runs_beside_the_red_one_ends_and_the_next_is_not_started(self):
        document = doc(("V1", "sleep 0.3; exit 1"), ("V2", "sleep 1.2; echo x >> " + str(self.counts / "b")),
                       ("V3", self.counting("c")))
        seen = []
        rows = self.run_round(document, parallel=2, on_result=seen.append)
        self.assertEqual([(row["id"], row["green"], row.get("skip_reason")) for row in rows],
                         [("V1", False, None), ("V2", True, None), ("V3", False, "fail_fast")])
        self.assertEqual((self.count("b"), self.count("c")), (1, 0))
        self.assertEqual(sorted(row["id"] for row in seen), ["V1", "V2", "V3"])  # the skipped row is reported too

    def test_without_fail_fast_every_check_runs(self):
        rows = self.run_round(self.document(), parallel=1, fail_fast=False)
        self.assertEqual([row["green"] for row in rows], [False, True, True])
        self.assertFalse(any(row.get("skipped") for row in rows))

    def test_a_procedure_check_neither_ends_nor_is_skipped_by_fail_fast(self):
        document = doc(check("V1", procedure="look"), ("V2", "exit 1"), ("V3", "true"))
        rows = self.run_round(document, parallel=1)
        self.assertEqual([(row["id"], row.get("skip_reason")) for row in rows],
                         [("V1", None), ("V2", None), ("V3", "fail_fast")])
        self.assertFalse(rows[0].get("skipped"))


class PhaseTests(Case):
    def document(self, item_cmd):
        return doc(("V1", item_cmd), check("V2", self.counting("phase"), cadence="phase"),
                   check("V3", None, procedure="look", cadence="phase"))

    def test_phase_checks_wait_for_green_item_checks(self):
        rows = self.run_round(self.document("exit 1"), parallel=1)
        self.assertEqual((rows[1].get("skip_reason"), rows[1]["skipped"], rows[1]["green"]), ("phase_after_red", True, False))
        self.assertEqual(self.count("phase"), 0)
        self.assertFalse(rows[2].get("skipped"))  # a procedure check is never skipped
        ok = self.run_round(self.document("true"), parallel=1, number=2)
        self.assertEqual([row["green"] for row in ok[:2]], [True, True])
        self.assertEqual(self.count("phase"), 1)

    def test_phase_checks_are_skipped_after_a_fail_fast_skip_too(self):
        document = doc(("V1", "exit 1"), ("V2", "true"), check("V3", "true", cadence="phase"))
        rows = self.run_round(document, parallel=1)
        self.assertEqual([row.get("skip_reason") for row in rows], [None, "fail_fast", "phase_after_red"])


class RowKindsTests(Case):
    def test_failed_skipped_and_reused_rows_differ(self):
        document = doc(("V1", self.counting()), ("V2", "exit 1"), ("V3", "true"))
        first = self.run_round(document, parallel=1, previous=[{"id": "V1", "seconds": 1}, {"id": "V2", "seconds": 2},
                                                                {"id": "V3", "seconds": 9}])
        self.assertEqual([bool(row.get("skipped")) for row in first], [False, False, True])
        again = self.run_round(doc(("V1", self.counting()), ("V2", "exit 1")), parallel=1, number=2)
        failed, reused = again[1], again[0]
        self.assertTrue(reused["reused"] and reused["green"] and not reused.get("skipped"))
        self.assertTrue(not failed["green"] and not failed.get("reused") and not failed.get("skipped"))
        self.assertEqual(checks_stage.red_signature(first)[0], ("V2",))


class ReuseTests(Case):
    def one(self, cmd="true", **extra):
        return doc(check("V1", cmd, **extra))

    def test_a_green_check_of_the_same_candidate_is_not_run_again_and_its_evidence_stays(self):
        document = self.one(self.counting())
        first = self.run_round(document)[0]
        raw = self.evidence().read_bytes()
        stamp = self.evidence().stat().st_mtime_ns
        second = self.run_round(document, number=2)[0]
        self.assertTrue(second["reused"] and second["green"])
        self.assertEqual((second["seconds"], second["exit"], second["evidence"]), (0, 0, first["evidence"]))
        self.assertEqual(second["reused_from"], "cnd-1:T.W1:checks.1:V1")
        self.assertEqual(self.count(), 1)
        self.assertFalse((self.out / "log2" / "V1.log").exists())
        self.assertEqual((self.evidence().read_bytes(), self.evidence().stat().st_mtime_ns), (raw, stamp))
        self.assertNotIn("reused", first)

    def test_reuse_off_runs_the_check_and_writes_the_evidence_again(self):
        document = self.one(self.counting())
        self.run_round(document)
        again = self.run_round(document, number=2, reuse=False)[0]
        self.assertNotIn("reused", again)
        self.assertEqual(self.count(), 2)
        self.assertIn(":checks.2:", json.loads(self.evidence().read_text(encoding="utf-8"))["evidence_id"])

    def test_nothing_is_reused_without_a_run(self):
        document = self.one(self.counting())
        self.run_round(document, run_id="cnd-1", run_id_of_reuse="")
        self.run_round(document, number=2, run_id_of_reuse="")
        self.assertEqual(self.count(), 2)

    def test_a_changed_tree_or_commit_runs_the_check(self):
        document = self.one(self.counting())
        self.run_round(document)
        (self.root / "tracked.txt").write_text("two\n", encoding="utf-8")  # another dirty digest
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)
        self.run_round(document, number=3)  # the same candidate again
        self.assertEqual(self.count(), 2)
        git(self.root, "commit", "-q", "-am", "y")  # another head
        self.run_round(document, number=4)
        self.assertEqual(self.count(), 3)

    def test_an_untracked_file_is_part_of_the_candidate(self):
        document = self.one(self.counting())
        self.run_round(document)
        (self.root / "new.txt").write_text("n\n", encoding="utf-8")
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_another_command_or_directory_runs_the_check(self):
        (self.root / "sub").mkdir()
        self.run_round(self.one(self.counting()))
        self.run_round(self.one(self.counting() + "; true"), number=2)  # same id, other command
        self.assertEqual(self.count(), 2)
        self.run_round(self.one(self.counting() + "; true", cwd="sub"), number=3)  # same id and command, other directory
        self.assertEqual(self.count(), 3)
        self.run_round(self.one(self.counting() + "; true", cwd="sub"), number=4)
        self.assertEqual(self.count(), 3)

    def test_the_directory_is_compared_after_normalisation(self):
        (self.root / "sub").mkdir()
        self.run_round(self.one(self.counting(), cwd="sub"))
        self.run_round(self.one(self.counting(), cwd="sub/../sub"), number=2)
        self.assertEqual(self.count(), 1)

    def test_a_directory_outside_the_project_is_refused_before_any_receipt_is_read(self):
        self.run_round(self.one(self.counting()))
        with self.assertRaises(ValueError):
            self.run_round(self.one(self.counting(), cwd=".."), number=2)

    def test_a_red_check_or_a_foreign_run_runs_again(self):
        flag = self.out / "flag"
        document = self.one(f"{self.counting()}; test -e {flag}")
        self.assertFalse(self.run_round(document)[0]["green"])
        flag.write_text("", encoding="utf-8")
        self.assertTrue(self.run_round(document, number=2)[0]["green"])  # a red receipt is never reused
        self.assertEqual(self.count(), 2)
        self.run_round(document, number=3, run_id="cnd-2")  # the receipt belongs to run cnd-1
        self.assertEqual(self.count(), 3)
        self.assertTrue(self.run_round(document, number=4, run_id="cnd-2")[0]["reused"])  # its own run's receipt
        self.assertEqual(self.count(), 3)

    def test_a_run_id_that_only_starts_alike_is_a_foreign_run(self):
        document = self.one(self.counting())
        self.run_round(document, run_id="cnd-1")
        self.run_round(document, run_id="cnd-10", number=2)
        self.assertEqual(self.count(), 2)

    def test_a_damaged_receipt_is_a_miss(self):
        document = self.one(self.counting())
        self.run_round(document)
        good = self.evidence().read_text(encoding="utf-8")
        damaged = [
            "{not json", "[]", "",
            json.dumps({**json.loads(good), "unknown_field": 1}),  # outside exec/v1
            json.dumps({k: v for k, v in json.loads(good).items() if k != "environment"}),  # no fingerprint
            json.dumps({**json.loads(good), "environment": {"env_digest": "0" * 64}}),
            json.dumps({**json.loads(good), "exit": 1}),
            json.dumps({**json.loads(good), "producer": {"kind": "executor"}}),
            json.dumps({**json.loads(good), "evidence_id": "other:T.W1:checks.1:V1"}),
            json.dumps({**json.loads(good), "candidate": {"head": "0" * 40, "dirty_digest": "0" * 64}}),
        ]
        for number, text in enumerate(damaged, 2):
            with self.subTest(text=text[:40]):
                self.evidence().write_text(text, encoding="utf-8")
                before = self.count()
                self.run_round(document, number=number)
                self.assertEqual(self.count(), before + 1)
        self.assertTrue(json.loads(self.evidence().read_text(encoding="utf-8"))["exit"] == 0)  # the run mended it

    def test_a_missing_receipt_is_a_miss(self):
        document = self.one(self.counting())
        self.run_round(document)
        self.evidence().unlink()
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_a_check_that_changed_the_tree_leaves_no_reusable_receipt(self):
        document = self.one("echo generated > gen.txt")
        self.run_round(document)
        self.assertNotIn("environment", json.loads(self.evidence().read_text(encoding="utf-8")))
        self.run_round(self.one("echo quiet"), number=2)
        self.assertIn("env_digest", json.loads(self.evidence().read_text(encoding="utf-8"))["environment"])

    def test_the_evidence_and_log_folders_are_not_part_of_the_candidate(self):
        candidate = checks.dirty_digest(self.root)
        self.run_round(self.one("true"))
        self.assertNotEqual(checks.dirty_digest(self.root), candidate)  # the evidence is an untracked file ...
        self.assertEqual(checks.dirty_digest(self.root, exclude=["ev"]), candidate)  # ... that is left out of the candidate


class FingerprintTests(Case):
    def test_a_changed_environment_runs_the_check(self):
        document = self.one_check()
        with mock.patch.dict(os.environ, {"SKM_FINGERPRINT_PROBE": "1"}):
            self.run_round(document)
        with mock.patch.dict(os.environ, {"SKM_FINGERPRINT_PROBE": "1"}):
            self.run_round(document, number=2)
        self.assertEqual(self.count(), 1)
        with mock.patch.dict(os.environ, {"SKM_FINGERPRINT_PROBE": "2"}):
            self.run_round(document, number=3)
        self.assertEqual(self.count(), 2)

    def one_check(self, cmd=None):
        return doc(check("V1", cmd or self.counting()))

    def test_the_round_and_the_jobs_share_do_not_change_the_fingerprint(self):
        document = self.one_check()
        self.run_round(document, run_env={"SKM_CHECK_ROUND": "1"})
        with mock.patch.dict(os.environ, {"SKM_TEST_JOBS": "3"}):
            self.run_round(document, number=2, run_env={"SKM_CHECK_ROUND": "2"})
        self.assertEqual(self.count(), 1)

    def test_a_changed_program_outside_the_project_runs_the_check(self):
        tool = self.out / "tool.sh"
        tool.write_text(f"#!/bin/sh\n{self.counting()}\n", encoding="utf-8")
        tool.chmod(0o755)
        document = self.one_check(str(tool))
        self.run_round(document)
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 1)
        tool.write_text(f"#!/bin/sh\n{self.counting()}\n# changed\n", encoding="utf-8")
        self.run_round(document, number=3)
        self.assertEqual(self.count(), 2)

    def test_a_program_found_on_the_path_is_followed_through_the_path(self):
        bin_dir = self.out / "bin"
        bin_dir.mkdir()
        tool = bin_dir / "probe-tool"
        tool.write_text(f"#!/bin/sh\n{self.counting()}\n", encoding="utf-8")
        tool.chmod(0o755)
        document = self.one_check("probe-tool")
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}):
            self.run_round(document)
            tool.write_text(f"#!/bin/sh\n{self.counting()}\n# v2\n", encoding="utf-8")
            self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_a_partner_root_outside_the_project_is_part_of_the_fingerprint(self):
        partner = self.out / "partner"
        partner.mkdir()
        git(partner, "init", "-q")
        (partner / "f.txt").write_text("1\n", encoding="utf-8")
        git(partner, "add", "f.txt")
        git(partner, "commit", "-q", "-m", "p")
        document = self.one_check()
        with mock.patch.dict(os.environ, {"SKM_PROBE_ROOT": str(partner)}):
            self.run_round(document)
            self.run_round(document, number=2)
            self.assertEqual(self.count(), 1)
            (partner / "f.txt").write_text("2\n", encoding="utf-8")  # the partner moved
            self.run_round(document, number=3)
        self.assertEqual(self.count(), 2)

    def test_a_partner_root_that_cannot_be_read_is_never_reused(self):
        elsewhere = self.out / "plain"
        elsewhere.mkdir()  # not a repository: its state is not known
        document = self.one_check()
        with mock.patch.dict(os.environ, {"SKM_PROBE_ROOT": str(elsewhere)}):
            self.run_round(document)
            self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)


class MutationTests(Case):
    """Reuse never outlives a change of what the check reads."""

    def test_a_check_after_one_that_changed_the_tree_is_not_reused(self):
        (self.root / "src.txt").write_text("good\n", encoding="utf-8")
        git(self.root, "add", "src.txt")
        git(self.root, "commit", "-q", "-m", "src")
        verify = "grep -q good src.txt"
        warm = self.run_round(doc(("V2", verify)))  # green evidence of V2 on this candidate
        self.assertTrue(warm[0]["green"])
        raw = self.evidence("V2").read_bytes()
        seen = []
        rows = self.run_round(doc(("V1", "echo bad > src.txt"), ("V2", verify)), number=2, parallel=1,
                              previous=[{"id": "V1", "seconds": 0.1}, {"id": "V2", "seconds": 5}], on_changed=seen.append)
        self.assertEqual(seen, [["src.txt"]])
        self.assertTrue(rows[0]["green"])
        self.assertFalse(rows[1].get("reused"))  # the receipt names the tree before V1
        self.assertFalse(rows[1]["green"])  # verify ran on the generated content and failed
        self.assertNotEqual(self.evidence("V2").read_bytes(), raw)

    def test_a_check_that_commits_leaves_a_clean_tree_and_still_voids_the_reuse(self):
        (self.root / "src.txt").write_text("good\n", encoding="utf-8")
        git(self.root, "add", "src.txt")
        git(self.root, "commit", "-q", "-m", "src")
        verify = "grep -q good src.txt"
        self.assertTrue(self.run_round(doc(("V2", verify)))[0]["green"])
        commit = ("printf bad > src.txt && git add src.txt && git -c user.name=t -c user.email=t@t commit -q -m changed")
        rows = self.run_round(doc(("V1", commit), ("V2", verify)), number=2, parallel=1,
                              previous=[{"id": "V1", "seconds": 0.1}, {"id": "V2", "seconds": 5}])
        self.assertEqual(checks.dirty_files(self.root).keys() - {"ev/V1.json", "ev/V2.json"}, set())  # the tree is clean again
        self.assertTrue(rows[0]["green"])
        self.assertFalse(rows[1].get("reused"))
        self.assertFalse(rows[1]["green"])  # verify read the committed content
        self.assertNotIn("environment", json.loads(self.evidence("V1").read_text(encoding="utf-8")))  # HEAD moved

    def test_an_unchanged_candidate_still_reuses_the_receipt_untouched(self):
        warm = self.run_round(doc(("V1", self.counting())))
        raw = self.evidence().read_bytes()
        again = self.run_round(doc(("V1", self.counting())), number=2)
        self.assertTrue(again[0]["reused"])
        self.assertEqual((self.count(), self.evidence().read_bytes()), (1, raw))
        self.assertEqual(again[0]["evidence"], warm[0]["evidence"])


class FixtureTests(Case):
    """Files outside the project that a command reads are part of what a green result stands on."""

    def setUp(self):
        super().setUp()
        self.fixture = self.out / "fixture.txt"
        self.fixture.write_text("good\n", encoding="utf-8")
        self.verify = doc(("V1", f'test "$(cat {self.fixture})" = good && {self.counting()}'))

    def test_a_changed_data_file_between_rounds_runs_the_check(self):
        self.assertTrue(self.run_round(self.verify)[0]["green"])
        self.assertTrue(self.run_round(self.verify, number=2)[0]["reused"])
        self.assertEqual(self.count(), 1)
        self.fixture.write_text("bad\n", encoding="utf-8")
        row = self.run_round(self.verify, number=3)[0]
        self.assertFalse(row.get("reused"))
        self.assertFalse(row["green"])  # not a false GREEN from the old receipt

    def test_a_data_file_changed_by_the_check_leaves_no_reusable_receipt(self):
        document = doc(("V1", f"{self.counting()}; cat {self.fixture} > /dev/null; echo changed > {self.fixture}"))
        self.run_round(document)
        self.assertNotIn("environment", json.loads(self.evidence().read_text(encoding="utf-8")))
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_an_unreadable_input_is_never_reused(self):
        if os.geteuid() == 0:
            self.skipTest("root reads everything")
        document = doc(("V1", f"cat {self.fixture} > /dev/null; {self.counting()}"))
        self.fixture.chmod(0)
        self.addCleanup(self.fixture.chmod, 0o644)
        self.run_round(document)
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_a_file_named_by_the_environment_is_an_input_too(self):
        config = self.out / "config.json"
        config.write_text("{}", encoding="utf-8")
        document = doc(("V1", self.counting()))
        with mock.patch.dict(os.environ, {"PROBE_CONFIG": str(config)}):
            self.run_round(document)
            self.run_round(document, number=2)
            self.assertEqual(self.count(), 1)
            config.write_text('{"a": 1}', encoding="utf-8")
            self.run_round(document, number=3)
        self.assertEqual(self.count(), 2)


class QuotedInputTests(Case):
    """Names with spaces, quotes and variables, and the git-ignored files of the project, are inputs too."""

    def rounds(self, document, change, count=3):
        """Run three rounds with ``change`` applied before the third; return the rows of the third."""
        self.assertTrue(self.run_round(document)[0]["green"])
        self.assertTrue(self.run_round(document, number=2)[0]["reused"])
        self.assertEqual(self.count(), 1)
        change()
        return self.run_round(document, number=3)[0]

    def test_a_quoted_external_path_with_a_space_inside_a_substitution(self):
        fixture = self.out / "fixture file.txt"
        fixture.write_text("good\n", encoding="utf-8")
        row = self.rounds(doc(("V1", f"test \"$(cat '{fixture}')\" = good")), lambda: fixture.write_text("bad\n"))
        self.assertFalse(row.get("reused"))
        self.assertFalse(row["green"])
        self.assertEqual(self.count(), 2)

    def test_a_path_with_an_escaped_space(self):
        fixture = self.out / "fixture file.txt"
        fixture.write_text("good\n", encoding="utf-8")
        escaped = str(fixture).replace(" ", "\\ ")
        row = self.rounds(doc(("V1", f'test "$(cat {escaped})" = good')), lambda: fixture.write_text("bad\n"))
        self.assertFalse(row["green"])
        self.assertFalse(row.get("reused"))

    def test_a_path_built_from_an_unset_variable_is_never_reused(self):
        document = doc(("V1", 'test -z "$SKM_UNSET_PROBE_DIR/x.txt" || true'))
        self.run_round(document)
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_a_path_built_from_a_set_variable_follows_the_file(self):
        fixture = self.out / "fixture.txt"
        fixture.write_text("good\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"SKM_PROBE_DIR": str(self.out)}):
            row = self.rounds(doc(("V1", 'test "$(cat "$SKM_PROBE_DIR/fixture.txt")" = good')),
                              lambda: fixture.write_text("bad\n"))
        self.assertFalse(row["green"])
        self.assertFalse(row.get("reused"))

    def test_a_git_ignored_fixture_of_the_project_read_by_path(self):
        fixture = self.root / "local" / "fixture.txt"
        fixture.parent.mkdir()
        fixture.write_text("good\n", encoding="utf-8")
        row = self.rounds(doc(("V1", 'test "$(cat local/fixture.txt)" = good')), lambda: fixture.write_text("bad\n"))
        self.assertFalse(row.get("reused"))
        self.assertFalse(row["green"])  # not a stale GREEN: only the ignored fixture changed
        self.assertEqual(self.count(), 2)

    def test_a_git_ignored_fixture_read_by_a_bare_name_or_a_quoted_name_with_a_space(self):
        bare = self.root / "data.local"
        bare.write_text("good\n", encoding="utf-8")
        row = self.rounds(doc(("V1", "grep -q good data.local")), lambda: bare.write_text("bad\n"))
        self.assertFalse(row["green"])
        self.assertFalse(row.get("reused"))
        spaced = self.root / "local" / "my fixture.txt"
        spaced.parent.mkdir(exist_ok=True)
        spaced.write_text("good\n", encoding="utf-8")
        for log in self.out.glob("log*"):
            for old in log.glob("*"):
                old.unlink()
            log.rmdir()
        row = self.rounds(doc(("V1", "grep -q good './local/my fixture.txt'")), lambda: spaced.write_text("bad\n"))
        self.assertFalse(row["green"])
        self.assertFalse(row.get("reused"))

    def test_a_git_ignored_folder_that_is_named_is_an_unknown_input(self):
        (self.root / "local").mkdir()
        document = doc(("V1", "ls local/ > /dev/null"))
        self.run_round(document)
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 2)

    def test_a_tracked_file_and_the_evidence_folder_do_not_void_the_reuse(self):
        document = doc(("V1", "cat tracked.txt > /dev/null; ls ev > /dev/null 2>&1; true"))
        self.run_round(document)
        self.run_round(document, number=2)
        self.assertEqual(self.count(), 1)


class ExpandedInputTests(Case):
    """Files that a shell expansion reaches (globs, brace lists, computed paths) are inputs too; when the line does not say
    which files, nothing is reused. The checks run for real: a stale GREEN would show as a reused or green second row."""

    def setUp(self):
        super().setUp()
        self.ext = self.out / "ext"
        self.ext.mkdir()
        self.good = self.ext / "a.txt"
        self.good.write_text("good\n", encoding="utf-8")

    def rounds(self, document, change):
        """Three rounds with ``change`` before the third; the rows of the third."""
        self.assertTrue(self.run_round(document)[0]["green"])
        self.assertTrue(self.run_round(document, number=2)[0]["reused"])
        self.assertEqual(self.count(), 1)
        change()
        return self.run_round(document, number=3)[0]

    def assert_fresh_red(self, document, change):
        """Green, reused, then ``change``: the third round runs the command again and it exits 1."""
        row = self.rounds(document, change)
        self.assertFalse(row.get("reused"))
        self.assertFalse(row["green"])
        self.assertEqual(row["exit"], 1)
        self.assertEqual(self.count(), 2)

    def assert_never_reused(self, document):
        self.assertTrue(self.run_round(document)[0]["green"])
        self.assertFalse(self.run_round(document, number=2)[0].get("reused"))
        self.assertEqual(self.count(), 2)

    def test_an_external_glob_follows_the_files_it_matches(self):
        document = doc(("V1", f'test "$(cat {self.ext}/*.txt)" = good'))
        self.assert_fresh_red(document, lambda: self.good.write_text("bad\n"))

    def test_a_file_that_joins_an_external_glob_runs_the_check(self):
        document = doc(("V1", f'test "$(cat {self.ext}/*.txt)" = good'))
        self.assert_fresh_red(document, lambda: (self.ext / "b.txt").write_text("more\n"))

    def test_a_glob_into_a_git_ignored_folder_is_never_reused(self):
        local = self.root / "local"
        local.mkdir()
        (local / "a.txt").write_text("good\n", encoding="utf-8")
        self.assert_never_reused(doc(("V1", 'test "$(cat local/*.txt)" = good')))

    def test_a_glob_that_matches_git_ignored_files_of_the_project_follows_them(self):
        (self.root / "a.local").write_text("good\n", encoding="utf-8")
        self.assert_fresh_red(doc(("V1", 'test "$(cat *.local)" = good')), lambda: (self.root / "a.local").write_text("bad\n"))

    def test_a_brace_list_follows_its_files(self):
        (self.ext / "b.txt").write_text("good\n", encoding="utf-8")
        document = doc(("V1", f'test "$(cat {self.ext}/{{a,b}}.txt | sort -u)" = good'))
        self.assert_fresh_red(document, lambda: (self.ext / "b.txt").write_text("bad\n"))

    def test_a_brace_range_follows_its_files(self):
        for number in (1, 2):
            (self.ext / f"f{number}.dat").write_text("good\n", encoding="utf-8")
        document = doc(("V1", f'test "$(cat {self.ext}/f{{1..2}}.dat | sort -u)" = good'))
        self.assert_fresh_red(document, lambda: (self.ext / "f2.dat").write_text("bad\n"))

    def test_a_glob_inside_a_quoted_script_follows_its_files(self):
        document = doc(("V1", f"bash -c 'test \"$(cat {self.ext}/*.txt)\" = good'"))
        self.assert_fresh_red(document, lambda: self.good.write_text("bad\n"))

    def test_a_glob_assigned_to_a_variable_follows_its_files(self):
        document = doc(("V1", f'PATTERN={self.ext}/*.txt; test "$(cat $PATTERN)" = good'))
        self.assert_fresh_red(document, lambda: self.good.write_text("bad\n"))

    def test_a_glob_in_an_option_value_follows_its_files(self):
        document = doc(("V1", f"env DATA={self.ext}/*.txt bash -c 'test \"$(cat $DATA)\" = good'"))
        self.assert_fresh_red(document, lambda: self.good.write_text("bad\n"))

    def test_a_glob_through_a_set_variable_follows_its_files(self):
        with mock.patch.dict(os.environ, {"SKM_PROBE_DIR": str(self.ext)}):
            document = doc(("V1", 'test "$(cat $SKM_PROBE_DIR/*.txt)" = good'))
            self.assert_fresh_red(document, lambda: self.good.write_text("bad\n"))

    def test_a_glob_through_an_unset_variable_is_never_reused(self):
        self.assert_never_reused(doc(("V1", 'cat $SKM_UNSET_PROBE_DIR/*.txt > /dev/null; true')))

    def test_a_folder_reached_by_a_glob_outside_the_project_is_never_reused(self):
        (self.ext / "sub").mkdir()
        self.assert_never_reused(doc(("V1", f"ls {self.ext}/* > /dev/null")))

    def test_a_path_computed_by_a_command_is_never_reused(self):
        self.assert_never_reused(doc(("V1", f'test "$(cat "$(echo {self.ext})/a.txt")" = good')))

    def test_a_path_computed_by_backticks_is_never_reused(self):
        self.assert_never_reused(doc(("V1", f'test "$(cat `echo {self.ext}`/a.txt)" = good')))

    def test_an_argument_computed_by_a_command_is_never_reused(self):
        self.assert_never_reused(doc(("V1", f"cat $(ls {self.ext}/a.txt) > /dev/null")))

    def test_a_line_that_cannot_be_read_has_no_known_inputs(self):
        for line in (f"cat {self.ext}/a.txt $(echo x", "cat 'open", f"cat {self.ext}/*.txt ${{open"):
            self.assertIsNone(checks._inputs(line, dict(os.environ), self.root, self.root))

    def test_a_glob_over_the_files_of_the_candidate_keeps_the_reuse(self):
        document = doc(("V1", 'cat tr*.txt > /dev/null; ls *.txt tests/*.nothing > /dev/null 2>&1; echo "a*" "{x,y}" > /dev/null'))
        self.run_round(document)
        self.assertTrue(self.run_round(document, number=2)[0]["reused"])
        self.assertEqual(self.count(), 1)

    def test_a_glob_that_matches_nothing_keeps_the_reuse_and_a_new_match_runs_the_check(self):
        document = doc(("V1", f"cat {self.ext}/*.cfg > /dev/null 2>&1; true"))
        self.run_round(document)
        self.assertTrue(self.run_round(document, number=2)[0]["reused"])
        (self.ext / "x.cfg").write_text("new\n", encoding="utf-8")
        self.assertFalse(self.run_round(document, number=3)[0].get("reused"))
        self.assertEqual(self.count(), 2)


class DispatchTests(unittest.TestCase):
    def test_a_stale_wait_snapshot_cannot_start_a_check_after_one_failed(self):
        from concurrent.futures import ALL_COMPLETED, wait as real_wait
        started = []

        def run_one(check):
            started.append(check["id"])
            return {"id": check["id"], "green": check["id"] != "V2"}

        calls = []

        def stale_wait(running, return_when):
            if calls:
                return real_wait(list(running), return_when=return_when)
            calls.append(1)
            real_wait(list(running), return_when=ALL_COMPLETED)  # V1 and V2 both ended ...
            first = {future for future, check in running.items() if check["id"] == "V1"}
            return first, set(running) - first  # ... but the dispatcher is told about V1 only

        commands = [check("V1", "true"), check("V2", "true"), check("V3", "true")]
        with mock.patch.object(checks, "wait", stale_wait):
            done, unstarted = checks._dispatch(commands, run_one, 2, True)
        self.assertEqual(sorted(started), ["V1", "V2"])
        self.assertEqual([c["id"] for c in unstarted], ["V3"])
        self.assertEqual(sorted(done), ["V1", "V2"])  # the ones running meanwhile still give their rows

    def test_the_skipped_row_of_the_unstarted_check_says_fail_fast(self):
        from concurrent.futures import ALL_COMPLETED, wait as real_wait

        def run_one(check):
            return {"id": check["id"], "kind": "acceptance", "green": check["id"] != "V2"}

        calls = []

        def stale_wait(running, return_when):
            if calls:
                return real_wait(list(running), return_when=return_when)
            calls.append(1)
            real_wait(list(running), return_when=ALL_COMPLETED)
            first = {future for future, check in running.items() if check["id"] == "V1"}
            return first, set(running) - first

        wanted = [check("V1", "true"), check("V2", "true"), check("V3", "true")]
        with mock.patch.object(checks, "wait", stale_wait):
            rows = checks._run_round(wanted, run_one, previous=[], first=[], fail_fast=True, on_result=None,
                                     begin=lambda commands: 2)
        self.assertEqual([(row["id"], row.get("skip_reason")) for row in rows],
                         [("V1", None), ("V2", None), ("V3", "fail_fast")])


class AdmissionTests(unittest.TestCase):
    def test_a_red_result_published_before_the_next_admission_stops_it(self):
        started = []
        hold = threading.Event()

        def run_one(check):
            started.append(check["id"])
            if check["id"] == "V1":
                hold.wait(10)  # V1 is still running when V2 ends red
            return {"id": check["id"], "kind": "acceptance", "green": check["id"] != "V2"}

        wanted = [check("V1", "true"), check("V2", "true"), check("V3", "true")]
        rows = []
        worker = threading.Thread(target=lambda: rows.extend(checks._run_round(
            wanted, run_one, previous=[], first=[], fail_fast=True, on_result=None, begin=lambda commands: 2)))
        worker.start()
        deadline = time.monotonic() + 10
        while "V2" not in started and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)  # V2 has ended red and published it
        hold.set()
        worker.join(10)
        self.assertEqual(sorted(started), ["V1", "V2"])  # run_one(V3) was never called
        self.assertEqual([(row["id"], row.get("skip_reason")) for row in rows],
                         [("V1", None), ("V2", None), ("V3", "fail_fast")])

    def test_a_red_result_cannot_be_published_while_a_check_is_being_admitted(self):
        started, futures = [], {}
        release = threading.Event()

        def run_one(check):
            started.append(check["id"])
            if check["id"] == "V2":
                release.wait(10)
            return {"id": check["id"], "kind": "acceptance", "green": check["id"] != "V2"}

        class Pool(ThreadPoolExecutor):
            def submit(self, function, *args, **kwargs):
                name = args[0]["id"]
                if name == "V3":  # the admission of V3 is in progress: V2 ends red meanwhile
                    release.set()
                    time.sleep(0.3)
                    futures["V2_done_during_admission"] = futures["V2"].done()
                future = super().submit(function, *args, **kwargs)
                futures[name] = future
                return future

        wanted = [check("V1", "true"), check("V2", "true"), check("V3", "true")]
        with mock.patch.object(checks, "ThreadPoolExecutor", Pool):
            rows = checks._run_round(wanted, run_one, previous=[], first=[], fail_fast=True, on_result=None,
                                     begin=lambda commands: 2)
        # the publication of V2's failure waits for the admission; the check admitted before it is the only one allowed
        self.assertFalse(futures["V2_done_during_admission"])
        self.assertEqual(sorted(started), ["V1", "V2", "V3"])
        self.assertEqual([row["green"] for row in rows], [True, False, True])


class EnvironmentTests(Case):
    def read(self, number=1, check_id="V1") -> str:
        return (self.out / f"log{number}" / f"{check_id}.log").read_text(encoding="utf-8")

    def test_a_check_sees_the_run_the_piece_and_the_round(self):
        rows = self.run_round(doc(("V1", "env | grep '^SKM_CHECK_' | sort")), fail_fast=False,
                              run_env={"SKM_CHECK_RUN": "cnd-1", "SKM_CHECK_ITEM": "T.W1", "SKM_CHECK_ROUND": "3"})
        self.assertTrue(rows[0]["green"])
        self.assertEqual(self.read().split(), ["SKM_CHECK_ITEM=T.W1", "SKM_CHECK_ROUND=3", "SKM_CHECK_RUN=cnd-1"])

    def jobs(self, owner, parallel, count):
        document = doc(*[(f"V{n}", 'echo "jobs=$SKM_TEST_JOBS"; sleep 0.3') for n in range(1, count + 1)])
        env = {} if owner is None else {"SKM_TEST_JOBS": str(owner)}
        budgets = []
        with mock.patch.dict(os.environ, env):
            if owner is None:
                os.environ.pop("SKM_TEST_JOBS", None)
            self.run_round(document, parallel=parallel, on_budget=budgets.append, reuse=False)
        return sorted({self.read(self.calls, f"V{n}").strip() for n in range(1, count + 1)}), budgets

    def test_the_owners_budget_is_divided_between_the_checks_that_run_together(self):
        seen, budgets = self.jobs(8, 2, 2)
        self.assertEqual(seen, ["jobs=4"])
        self.assertEqual(budgets, [{"requested": 8, "parallel": 2, "effective": 4}])

    def test_the_division_never_gives_more_than_the_owner_gave(self):
        seen, budgets = self.jobs(3, 2, 2)  # 3 // 2
        self.assertEqual(seen, ["jobs=1"])
        seen, budgets = self.jobs(3, 4, 4)  # three at a time at most, one job each
        self.assertEqual((seen, budgets), (["jobs=1"], [{"requested": 3, "parallel": 3, "effective": 1}]))
        seen, budgets = self.jobs(1, 2, 2)  # a budget of one runs the checks one by one
        self.assertEqual((seen, budgets), (["jobs=1"], [{"requested": 1, "parallel": 1, "effective": 1}]))

    def test_without_an_owner_value_the_cpus_are_the_budget(self):
        cpus = os.cpu_count() or 2
        seen, budgets = self.jobs(None, 2, 2)
        workers = min(2, cpus)
        self.assertEqual(budgets, [{"requested": cpus, "parallel": workers, "effective": max(1, cpus // workers)}])
        self.assertEqual(seen, [f"jobs={max(1, cpus // workers)}"])

    def test_check_env_function(self):
        self.assertEqual(checks.check_env(self.root, environ={"SKM_TEST_JOBS": "6"}, parallel=2)["SKM_TEST_JOBS"], "3")
        self.assertEqual(checks.check_env(self.root, environ={"SKM_TEST_JOBS": "6"})["SKM_TEST_JOBS"], "6")
        self.assertEqual(checks.check_env(self.root, environ={"SKM_TEST_JOBS": "1"}, parallel=4)["SKM_TEST_JOBS"], "1")
        self.assertEqual(checks.check_env(self.root, environ={"SKM_TEST_JOBS": "x"}, parallel=1)["SKM_TEST_JOBS"],
                         str(os.cpu_count() or 2))
        env = checks.check_env(self.root, environ={}, run_env={"SKM_CHECK_RUN": "r"})
        self.assertEqual(env["SKM_CHECK_RUN"], "r")


class SettleTests(unittest.TestCase):
    def test_a_round_with_a_red_check_and_fail_fast_skips_is_not_checks_not_run(self):
        stub = SimpleNamespace(_blocked=report_rules.blocked)
        report = {"status": "done_pending_checks", "open_issues": [{"text": "p", "kind": "pending"}]}
        rows = [{"id": "V1", "green": False}, {"id": "V2", "skipped": True, "skip_reason": "fail_fast", "green": False}]
        self.assertEqual(finish.settle_pending(stub, report, rows)["status"], "done")
        skipped = [dict(row, skipped=True) for row in rows]
        settled = finish.settle_pending(stub, report, skipped)
        self.assertEqual(settled["status"], "blocked")

    def test_the_verdict_of_a_round_names_only_the_checks_that_ran_and_failed(self):
        steps = {}

        def step(item, key, run, verdict=None):
            steps[key] = verdict(run())

        stub = SimpleNamespace(_step=step, _compute_checks=lambda *args: [
            {"id": "V1", "green": False}, {"id": "V2", "skipped": True, "skip_reason": "fail_fast", "green": False},
            {"id": "V3", "green": True, "reused": True}])
        checks_stage.run_checks(stub, SimpleNamespace(), 1, {})
        self.assertEqual(steps["checks.1"], "red V1")


if __name__ == "__main__":
    unittest.main()
