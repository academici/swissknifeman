"""Heartbeat and health of a run (PLAN9 P8.1): ``heartbeat.json`` written by the conductor's own thread of control, the identity of the
owner in ``lease.json``, signs of progress besides the growth of the stream (tool steps, the CPU of the process tree),
``STALL_SUSPECTED`` and ``CHECK_IDLE`` beacons, and ``health.classify`` behind ``status`` and ``runs``. Fake roles; processes
synchronise on pipes and marker files, never on a fixed sleep."""
from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from aicore.util import timefmt

from orch.conductor import checks as checks_mod, cli, health, process, progress, records, signals
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import heartbeat as heartbeat_mod, work_source
from orch.conductor.infrastructure.files import RUN_FILE, runs_root
from orch.conductor.infrastructure.lease import CheckoutLock, RunLease
from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok

ROOT = Path(__file__).resolve().parents[1]
NOW = timefmt.epoch("2026-11-01T10:20:00Z")


def ago(seconds: float) -> str:
    return timefmt.utc_stamp(NOW - seconds)


def ahead(seconds: float) -> str:
    return timefmt.utc_stamp(NOW + seconds)


def beat(**over) -> dict:
    """A valid heartbeat document written 5 s before ``NOW``, of the owner (4242, 777, boot-a)."""
    return {"$schema": "urn:swissknifeman:orch:records:heartbeat:v1", "run_id": "cnd-x", "pid": 4242, "start_ticks": 777,
            "boot_id": "boot-a", "host": "box", "seq": 3, "at": ago(5), **over}


def lease(**over) -> dict:
    return {"held": True, "owner": {"pid": 4242, "start_ticks": 777, "boot_id": "boot-a"}, "flag": True, **over}


def running(**over) -> dict:
    return {"status": "running", "reason_code": None, "last_ts": ago(5), "items": [], "current": None, **over}


def classify(summary=None, state=None, heartbeat="fresh", lease_doc=None, **thresholds) -> dict:
    return health.classify(summary or running(), state or {}, beat() if heartbeat == "fresh" else heartbeat,
                           lease_doc or lease(), NOW, health.Thresholds(**thresholds))


class LeaseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def test_lease_json_names_the_process_by_pid_start_ticks_and_boot(self):
        with RunLease(self.directory).acquire("run"):
            doc = records.read(self.directory / "lease.json", "lease")  # records/v1 accepts it
        self.assertEqual(doc["pid"], os.getpid())
        self.assertEqual(doc["start_ticks"], process.start_ticks(os.getpid()))
        self.assertTrue(isinstance(doc["boot_id"], str) or doc["boot_id"] is None)
        self.assertEqual(doc["boot_id"], process.boot_id())
        self.assertEqual(doc["launcher"], "terminal")

    def test_the_launcher_comes_from_the_environment_and_an_unknown_one_is_a_terminal(self):
        for given, expected in (("gui", "gui"), ("supervisor", "supervisor"), ("cron", "terminal"), ("", "terminal")):
            with self.subTest(given=given), mock.patch.dict(os.environ, {"SKM_ORCH_LAUNCHER": given}):
                folder = self.directory / (given or "empty")
                folder.mkdir()
                with RunLease(folder).acquire("run"):
                    self.assertEqual(RunLease.owner(folder)["launcher"], expected)

    def test_a_checkout_lock_carries_the_identity_and_the_run(self):
        lock = CheckoutLock(self.directory, self.directory).acquire("run", "cnd-1")
        try:
            doc = records.read(lock.metadata, "lease")
        finally:
            lock.release()
        self.assertEqual((doc["run"], doc["start_ticks"], doc["launcher"]), ("cnd-1", process.start_ticks(os.getpid()), "terminal"))

    def test_a_lease_from_before_the_identity_still_reads(self):
        old = {"pid": 4242, "host": "box", "started_at": "2026-10-22T12:00:00Z", "command": "run"}
        for doc in (old, {"$schema": "urn:swissknifeman:orch:records:lease:v1", **old}):
            (self.directory / "lease.json").write_text(json.dumps(doc), encoding="utf-8")
            read = records.read(self.directory / "lease.json", "lease")
            self.assertEqual((read["pid"], read.get("start_ticks"), read.get("launcher")), (4242, None, None))

    def test_an_unknown_launcher_in_a_lease_document_is_refused(self):
        bad = {"pid": 1 + os.getpid(), "launcher": "cron"}
        self.assertTrue(records.problems(bad, "lease"))
        self.assertEqual(records.problems({"pid": 7, "launcher": "gui", "start_ticks": None, "boot_id": None}, "lease"), [])


class HeartbeatWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.now = [100.0]
        self.beat = heartbeat_mod.Heartbeat(self.directory, "cnd-x", monotonic=lambda: self.now[0])

    def doc(self) -> dict:
        return records.read(self.directory / "heartbeat.json", "heartbeat")

    def test_a_beat_is_written_at_most_every_five_seconds_unless_the_kind_of_progress_changes(self):
        self.assertTrue(self.beat.beat(progress_kind="stage_start"))
        self.assertEqual(self.doc()["seq"], 1)
        self.now[0] += 4.9
        self.assertFalse(self.beat.beat(progress_kind="stage_start"))  # same kind, too soon
        self.assertFalse(self.beat.beat(stream_bytes=10))
        self.assertEqual(self.doc()["seq"], 1)
        self.assertTrue(self.beat.beat(progress_kind="tool_use"))  # another kind: at once
        self.assertEqual((self.doc()["seq"], self.doc()["last_progress_kind"], self.doc()["stream_bytes"]), (2, "tool_use", 10))
        self.now[0] += 5.0
        self.assertTrue(self.beat.beat())
        self.assertEqual(self.doc()["seq"], 3)
        self.assertTrue(self.beat.beat(force=True))
        self.assertEqual(self.doc()["seq"], 4)

    def test_the_document_names_the_owner_and_validates_on_write_and_read(self):
        self.beat.beat(item="P2.1", step="executor.1", role="executor", progress_kind="stage_start", force=True)
        doc = self.doc()
        self.assertEqual((doc["pid"], doc["start_ticks"], doc["boot_id"], doc["run_id"]),
                         (os.getpid(), process.start_ticks(os.getpid()), process.boot_id(), "cnd-x"))
        self.assertEqual((doc["item"], doc["step"], doc["role"], doc["waiting"]), ("P2.1", "executor.1", "executor", None))
        self.assertEqual(records.problems(doc, "heartbeat"), [])

    def test_a_document_outside_the_schema_is_refused_on_write(self):
        self.beat.beat(force=True)
        with self.assertRaises(Stop) as caught:
            self.beat.beat(progress_kind="heartbeat", force=True)  # not a kind of progress
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertEqual(self.doc()["seq"], 1)  # the file is as it was

    def test_waiting_is_written_before_and_after_the_call_and_nests(self):
        with self.beat.waiting("work_source", "WORK_SOURCE_CALL", 600):
            inside = self.doc()["waiting"]
            self.assertEqual((inside["kind"], inside["reason_code"]), ("work_source", "WORK_SOURCE_CALL"))
            self.assertGreater(timefmt.epoch(inside["deadline"]), timefmt.epoch(inside["since"]) + 590)
            with self.beat.waiting("git", "GIT_CALL", 60):
                self.assertEqual(self.doc()["waiting"]["kind"], "git")
            self.assertEqual(self.doc()["waiting"]["kind"], "work_source")
        self.assertIsNone(self.doc()["waiting"])

    def test_a_wait_without_a_deadline_is_refused_but_for_a_question(self):
        with self.assertRaises(ValueError):
            with self.beat.waiting("provider", "PROVIDER_WAIT"):
                pass
        with self.beat.waiting("question", "QUESTION_OPEN"):
            self.assertIsNone(self.doc()["waiting"]["deadline"])

    def test_the_wait_is_cleared_when_the_call_raises(self):
        with self.assertRaises(RuntimeError):
            with self.beat.waiting("subprocess", "X", 10):
                raise RuntimeError("boom")
        self.assertIsNone(self.doc()["waiting"])

    def test_the_heartbeat_is_written_by_the_callers_thread_never_by_a_timer(self):
        source = inspect.getsource(heartbeat_mod)
        self.assertNotIn("Timer", source)
        self.assertNotIn("Thread(", source)
        before = threading.active_count()
        self.beat.beat(force=True)
        self.now[0] += 3600
        self.assertEqual(threading.active_count(), before)
        self.assertEqual(self.doc()["seq"], 1)  # an hour of silence writes nothing

    def test_cpu_growth_is_recorded_apart_from_progress(self):
        self.beat.beat(progress_kind="tool_use", tree_cpu_s=1.0, force=True)
        first = self.doc()
        self.beat.beat(progress_kind="cpu", tree_cpu_s=4.5, force=True)
        second = self.doc()
        self.assertEqual((second["last_progress_at"], second["last_progress_kind"]), (first["last_progress_at"], "tool_use"))
        self.assertEqual(second["tree_cpu_s"], 4.5)
        self.assertIsNotNone(second["last_cpu_at"])

    def test_a_write_that_fails_is_said_once_and_the_next_one_tries_again(self):
        said = []
        writer = heartbeat_mod.Heartbeat(self.directory, "cnd-y", monotonic=lambda: self.now[0], on_failure=said.append)
        real = records.write
        with mock.patch.object(records, "write", side_effect=OSError("disk full")):
            self.assertFalse(writer.beat(force=True))
            self.assertFalse(writer.beat(force=True))
        self.assertEqual(len(said), 1)
        self.assertTrue(writer.beat(force=True))  # the disk is back
        self.assertEqual(records.read(self.directory / "heartbeat.json", "heartbeat")["run_id"], "cnd-y")
        self.assertIs(records.write, real)

    def test_read_tells_a_missing_a_broken_and_a_good_heartbeat(self):
        self.assertEqual(heartbeat_mod.read(self.directory), (None, "HEARTBEAT_MISSING"))
        (self.directory / "heartbeat.json").write_text("{not json", encoding="utf-8")
        self.assertTrue(heartbeat_mod.read(self.directory)[1].startswith("HEARTBEAT_INVALID"))
        (self.directory / "heartbeat.json").write_text(json.dumps({"pid": 1}), encoding="utf-8")
        self.assertTrue(heartbeat_mod.read(self.directory)[1].startswith("HEARTBEAT_INVALID"))
        self.beat.beat(force=True)
        doc, problem = heartbeat_mod.read(self.directory)
        self.assertEqual((doc["run_id"], problem), ("cnd-x", None))

    def test_the_progress_lines_drive_the_step_fields(self):
        self.beat.observe({"event": "run.start"})
        self.beat.observe({"event": "stage.start", "item": "P1", "stage": "executor.1", "role": "executor"})
        self.assertEqual((self.doc()["item"], self.doc()["step"], self.doc()["last_progress_kind"]),
                         ("P1", "executor.1", "stage_start"))
        self.beat.observe({"event": "stage.end", "item": "P1", "stage": "executor.1"})
        self.assertEqual((self.doc()["step"], self.doc()["role"], self.doc()["last_progress_kind"]), (None, None, "stage_end"))


class HealthRulesTests(unittest.TestCase):
    """One case per rule of the table, in its order (knowledge/p8-design#p8-health-model)."""

    def test_1_a_finished_run(self):
        self.assertEqual(classify(running(status="finished"))["health"], "finished")

    def test_2_a_quota_stop_with_a_known_reset_waits_for_the_budget(self):
        stopped = running(status="stopped", reason_code="PROVIDER_QUOTA", reset_until=NOW + 600)
        state = {"stop": {"code": "PROVIDER_QUOTA"}}
        found = classify(stopped, state)
        self.assertEqual((found["health"], found["reason_code"]), ("waiting_budget_reset", "PROVIDER_QUOTA"))
        past = classify(dict(stopped, reset_until=NOW - 1), state)  # the reset has passed: only a stop
        self.assertEqual(past["health"], "stopped")
        self.assertEqual(classify(dict(stopped, reset_until=None), state)["health"], "stopped")

    def test_3_a_decision_wait_is_the_owners_not_a_hang(self):
        stale = beat(at=ago(4000))
        for case, summary, state in (("outcome", running(status="waiting", reason_code="WAITING_DECISION"), {}),
                                     ("state", running(status="stopped"), {"status": "waiting"}),
                                     ("item", running(status="stopped"), {"items": {"P1": {"waiting": {"question_ids": ["Q1"]}}}})):
            with self.subTest(case=case):
                found = classify(summary, state, stale)
                self.assertEqual((found["health"], found["reason_code"]), ("waiting_owner", "WAITING_DECISION"))

    def test_3_a_waiting_piece_does_not_hide_a_stuck_conductor_that_still_runs(self):
        state = {"items": {"P1": {"waiting": {"question_ids": ["Q1"]}}}}
        self.assertEqual(classify(running(), state)["health"], "running")
        self.assertEqual(classify(running(), state, beat(at=ago(400)))["health"], "hung")

    def test_4_a_stopped_run_names_its_code(self):
        found = classify(running(status="stopped", reason_code="ITEM_BLOCKED"))
        self.assertEqual((found["health"], found["reason_code"]), ("stopped", "ITEM_BLOCKED"))

    def test_5_a_run_without_a_lease_holder_is_orphaned(self):
        found = classify(running(), lease_doc=lease(held=False, owner=None))
        self.assertEqual((found["health"], found["reason_code"]), ("orphaned", "RUN_ORPHANED"))
        self.assertEqual(classify(running(status="orphaned"))["health"], "orphaned")

    def test_6_a_lease_that_cannot_be_probed_is_unknown(self):
        found = classify(running(), lease_doc=lease(held=None, owner=None))
        self.assertEqual((found["health"], found["reason_code"]), ("unknown", "LEASE_UNKNOWN"))

    def test_7_no_heartbeat_is_running_with_a_detail_and_a_broken_one_is_unknown(self):
        missing = classify(heartbeat=None)
        self.assertEqual((missing["health"], missing["reason_code"]), ("running", "HEARTBEAT_MISSING"))
        self.assertIn("heartbeat.json", missing["detail"])
        broken = classify(heartbeat={health.INVALID: "HEARTBEAT_INVALID: /seq: required"})
        self.assertEqual((broken["health"], broken["reason_code"]), ("unknown", "HEARTBEAT_INVALID"))

    def test_8_a_heartbeat_of_another_process_than_the_lease_owner(self):
        for key, value in (("pid", 99), ("start_ticks", 1), ("boot_id", "boot-b")):
            with self.subTest(key=key):
                found = classify(heartbeat=beat(**{key: value}))
                self.assertEqual((found["health"], found["reason_code"]), ("suspected_stall", "HEARTBEAT_OWNER_MISMATCH"))
        legacy = classify(lease_doc=lease(owner={"pid": 4242}))  # a lease from before the identity: the pid only
        self.assertEqual(legacy["health"], "running")

    def test_9_a_question_wait_is_the_owners(self):
        wait = {"kind": "question", "reason_code": "QUESTION_OPEN", "since": ago(9000), "deadline": None}
        found = classify(heartbeat=beat(at=ago(9000), waiting=wait))
        self.assertEqual((found["health"], found["reason_code"]), ("waiting_owner", "QUESTION_WAITING"))

    def test_10_a_wait_inside_its_deadline_is_not_a_hang_however_old_the_heartbeat(self):
        wait = {"kind": "work_source", "reason_code": "WORK_SOURCE_CALL", "since": ago(400), "deadline": ahead(200)}
        found = classify(heartbeat=beat(at=ago(400), waiting=wait))
        self.assertEqual((found["health"], found["reason_code"]), ("waiting_tool", "WORK_SOURCE_CALL"))
        provider = dict(wait, kind="provider", reason_code="PROVIDER_WAIT")
        found = classify(heartbeat=beat(at=ago(400), waiting=provider))
        self.assertEqual((found["health"], found["reason_code"]), ("waiting_provider", "PROVIDER_WAIT"))
        self.assertEqual(found["waiting"]["kind"], "provider")

    def test_11_a_wait_far_past_its_deadline_is_hung(self):
        wait = {"kind": "work_source", "reason_code": "WORK_SOURCE_CALL", "since": ago(2000), "deadline": ago(301)}
        found = classify(heartbeat=beat(at=ago(1500), waiting=wait))
        self.assertEqual((found["health"], found["reason_code"]), ("hung", "HEARTBEAT_STALE"))

    def test_12_a_wait_past_its_deadline_and_grace_is_suspected(self):
        wait = {"kind": "work_source", "reason_code": "WORK_SOURCE_CALL", "since": ago(900), "deadline": ago(61)}
        found = classify(heartbeat=beat(at=ago(100), waiting=wait))
        self.assertEqual((found["health"], found["reason_code"]), ("suspected_stall", "WAIT_DEADLINE_PASSED"))

    def test_13_a_wait_just_past_its_deadline_is_still_a_wait(self):
        wait = {"kind": "git", "reason_code": "GIT_CALL", "since": ago(90), "deadline": ago(10)}
        found = classify(heartbeat=beat(at=ago(10), waiting=wait))
        self.assertEqual((found["health"], found["reason_code"]), ("waiting_tool", "GIT_CALL"))

    def test_14_a_stale_heartbeat_without_a_wait_is_hung(self):
        found = classify(heartbeat=beat(at=ago(301)))
        self.assertEqual((found["health"], found["reason_code"], found["heartbeat_age_s"]), ("hung", "HEARTBEAT_STALE", 301))
        self.assertEqual(classify(heartbeat=beat(at=ago(299)))["health"], "running")
        self.assertEqual(classify(heartbeat=beat(at=ago(299)), hung_after_s=100)["health"], "hung")

    def test_15_a_role_without_a_tool_step_for_the_window_is_suspected(self):
        at = {"role": "executor", "step": "executor.1", "last_progress_at": ago(2000), "at": ago(3)}
        cold = classify(heartbeat=beat(**at, last_cpu_at=ago(2000)))
        self.assertEqual((cold["health"], cold["reason_code"]), ("suspected_stall", "STALL_SUSPECTED"))
        self.assertEqual(cold["silent_s"], 2000)
        busy = classify(heartbeat=beat(**at, last_cpu_at=ago(10), repeat={"command": "Bash: x", "count": 2}))
        self.assertEqual(busy["health"], "running")  # quiet but at work: not a stall
        looping = classify(heartbeat=beat(**at, last_cpu_at=ago(10), repeat={"command": "Bash: x", "count": 5}))
        self.assertEqual((looping["health"], looping["reason_code"]), ("suspected_stall", "STALL_SUSPECTED"))
        self.assertEqual(classify(heartbeat=beat(**at, last_cpu_at=ago(2000)), stall_window_s=0)["health"], "running")
        recent = dict(at, last_progress_at=ago(60))
        self.assertEqual(classify(heartbeat=beat(**recent, last_cpu_at=ago(2000)))["health"], "running")

    def test_16_otherwise_running(self):
        found = classify()
        self.assertEqual((found["health"], found["reason_code"], found["heartbeat_age_s"]), ("running", None, 5))

    def test_the_classes_are_exactly_those_of_the_table(self):
        self.assertEqual(set(health.CLASSES), {"running", "waiting_provider", "waiting_tool", "waiting_owner",
                                               "waiting_budget_reset", "suspected_stall", "hung", "orphaned", "stopped",
                                               "finished", "unknown"})

    def test_classify_reads_neither_the_clock_nor_the_disk(self):
        source = inspect.getsource(health)
        for word in ("time.time", "time.monotonic", "open(", "read_text", "subprocess", "os.kill"):
            self.assertNotIn(word, source)


class StreamMarkerTests(unittest.TestCase):
    """The tool steps of a stream, read incrementally: nothing is read twice, a line is judged when it is whole."""

    CLAUDE_USE = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -x"}}]}})
    CLAUDE_RESULT = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}})
    CODEX_STARTED = json.dumps({"type": "item.started", "item": {"type": "command_execution", "command": "ls -la"}})
    CODEX_DONE = json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "ls -la"}})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "stream.jsonl"
        self.path.write_bytes(b"")

    def append(self, text: str) -> None:
        with open(self.path, "ab") as handle:
            handle.write(text.encode("utf-8"))

    def test_claude_and_grok_streams_show_tool_use_and_tool_result(self):
        for provider in ("claude-code", "grok"):
            with self.subTest(provider=provider):
                self.path.write_bytes(b"")
                scan = signals.StreamScan(self.path, signals.markers_of("jsonl", provider))
                self.append(self.CLAUDE_USE + "\n")
                self.assertEqual(scan.advance(), (False, "tool_use", ["Bash: pytest -x"]))
                self.append(self.CLAUDE_RESULT + "\n")
                self.assertEqual(scan.advance(), (False, "tool_result", []))
                self.append("")
                self.assertEqual(scan.advance(), (False, None, []))  # nothing new, nothing read again

    def test_codex_item_events_are_tool_steps(self):
        scan = signals.StreamScan(self.path, signals.markers_of("jsonl", "codex"))
        self.append(self.CODEX_STARTED + "\n" + self.CODEX_DONE + "\n")
        found = scan.advance()
        self.assertEqual((found[1], found[2]), ("tool_result", ["command_execution: ls -la"]))

    def test_a_line_that_is_written_in_pieces_counts_once_and_when_whole(self):
        scan = signals.StreamScan(self.path, signals.markers_of("jsonl", "claude-code"))
        half = len(self.CLAUDE_USE) // 2
        self.append(self.CLAUDE_USE[:half])
        self.assertEqual(scan.advance(), (False, None, []))
        self.append(self.CLAUDE_USE[half:] + "\n")
        self.assertEqual(scan.advance(), (False, "tool_use", ["Bash: pytest -x"]))
        self.assertEqual(scan.advance(), (False, None, []))

    def test_a_marker_in_the_text_of_the_model_is_no_tool_step(self):
        said = json.dumps({"type": "assistant", "message": {"content": [{"type": "text",
                                                                          "text": 'the line {"type":"tool_use"} is a marker'}]}})
        scan = signals.StreamScan(self.path, signals.markers_of("jsonl", "claude-code"))
        self.append(said + "\n")
        self.assertEqual(scan.advance(), (False, None, []))

    def test_the_final_result_line_is_seen_even_without_its_newline(self):
        scan = signals.StreamScan(self.path, signals.markers_of("jsonl", "claude-code"))
        self.append('{"type":"result","result":"done"}')
        self.assertTrue(scan.advance()[0])

    def test_a_text_transport_has_no_markers(self):
        self.assertEqual(signals.markers_of("text", "claude-code"), {})
        scan = signals.StreamScan(self.path, signals.markers_of("text", None))
        self.append(self.CLAUDE_USE + "\n")
        self.assertEqual(scan.advance(), (False, None, []))

    def test_an_unlisted_provider_is_read_for_every_marker(self):
        scan = signals.StreamScan(self.path, signals.markers_of("jsonl", "other"))
        self.append(self.CODEX_STARTED + "\n" + self.CLAUDE_USE + "\n")
        self.assertEqual(scan.advance()[2], ["command_execution: ls -la", "Bash: pytest -x"])

    def test_the_tree_cpu_of_this_process_counts_itself_and_its_children(self):
        if not Path("/proc/self/stat").exists():
            self.skipTest("no /proc")
        base = process.tree_cpu_ticks(os.getpid())
        self.assertIsInstance(base, int)
        spin = subprocess.Popen([sys.executable, "-c", "import time\nt=time.process_time()\nwhile time.process_time()-t<0.6: pass"])
        spin.wait()
        self.assertIsNone(process.tree_cpu_ticks(2 ** 22 + 12345))  # no such process

    def test_the_stall_watch_says_a_repeated_command_once_and_a_silent_window_each_window(self):
        watch = signals.StallWatch(3, 100)
        use = signals.TickInfo("tool_use", 10, None, ("Bash: x",))
        self.assertEqual(watch.feed(1, use), [])
        self.assertEqual(watch.feed(2, use), [])
        self.assertEqual(watch.feed(3, use), ["same command 3 times: Bash: x"])
        self.assertEqual(watch.feed(4, use), [])  # said once for this command
        self.assertEqual(watch.repeat, {"command": "Bash: x", "count": 4})
        self.assertEqual(watch.feed(5, signals.TickInfo("tool_use", 11, None, ("Bash: y",))), [])  # another command resets
        self.assertEqual(watch.repeat["count"], 1)
        grow = lambda size: signals.TickInfo(None, size, None, ())  # noqa: E731
        self.assertEqual(watch.feed(50, grow(20)), [])
        self.assertEqual(watch.feed(106, grow(30)), ["stream grew without a tool step for 101 s"])
        self.assertEqual(watch.feed(107, grow(40)), [])  # the next window starts now
        self.assertEqual(watch.feed(300, signals.TickInfo(None, 40, None, ())), [])  # a stream that does not grow is idle, not stalled
        self.assertEqual(signals.StallWatch(0, 0).feed(9999, grow(5)), [])


def prepare(test, code: str, **limits):  # a role run for the process tests
    return process.run_role([sys.executable, "-c", code.replace("\\n", "\n")], "prompt", transport="stream-json",
                            cwd=Path(test.tmp.name), raw_path=Path(test.tmp.name) / "out.jsonl", provider="claude-code", **limits)


RESULT = "print('{\"type\":\"result\",\"result\":\"done\",\"usage\":{}}', flush=True)"
CPU_THEN_RESULT = ("import sys,time\\nsys.stdin.read()\\nt=time.process_time()\\nwhile time.process_time()-t<3: pass\\n" + RESULT)
SLEEP_THEN_RESULT = "import sys,time\\nsys.stdin.read()\\ntime.sleep(3)\\n" + RESULT


@unittest.skipUnless(Path("/proc/self/stat").exists(), "the CPU of a process tree is read from /proc")
class QuietWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(process, "POLL_S", 0.2)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_role_that_computes_in_silence_is_not_stopped_by_the_idle_limit(self):
        run = prepare(self, CPU_THEN_RESULT, timeout_s=0, idle_timeout_s=2)  # 3 s of CPU, nothing written
        self.assertIsNone(run.error, run.detail)
        self.assertEqual(run.text, "done")

    def test_a_sleeping_role_is_still_stopped_by_the_idle_limit(self):
        run = prepare(self, SLEEP_THEN_RESULT, timeout_s=0, idle_timeout_s=2)  # the same silence without CPU
        self.assertEqual(run.error, "TIMEOUT")
        self.assertIn("no output for 2 s", run.detail)

    def test_the_ticks_carry_what_the_look_saw(self):
        ticks = []
        code = ("import sys,time,json\\nsys.stdin.read()\\nprint(json.dumps({'type':'assistant','message':{'content':["
                "{'type':'tool_use','name':'Bash','input':{'command':'make test'}}]}}), flush=True)\\ntime.sleep(1)\\n" + RESULT)
        run = prepare(self, code, timeout_s=0, idle_timeout_s=0, on_tick=lambda *tick: ticks.append(tick))
        self.assertIsNone(run.error, run.detail)
        infos = [tick[3] for tick in ticks]
        self.assertTrue(any(info.new_tool_use and info.command == "Bash: make test" for info in infos), infos)
        self.assertTrue(all(isinstance(info, signals.TickInfo) for info in infos))
        self.assertTrue(any(info.tree_cpu_s is not None for info in infos))
        self.assertGreater(max(info.stream_bytes for info in infos), 0)

    def test_a_check_that_computes_in_silence_is_not_stopped_but_a_sleeping_one_is(self):
        spin = ["python3", "-c", "import time\nt=time.process_time()\nwhile time.process_time()-t<3: pass"]
        with mock.patch.object(checks_mod, "POLL_S", 0.2), open(Path(self.tmp.name) / "spin.log", "wb") as out:
            self.assertEqual(checks_mod._run_command(spin, cwd=Path(self.tmp.name), out=out, timeout_s=0, warn_s=0, idle_s=2), 0)
        with mock.patch.object(checks_mod, "POLL_S", 0.2), open(Path(self.tmp.name) / "sleep.log", "wb") as out:
            self.assertEqual(checks_mod._run_command(["sleep", "30"], cwd=Path(self.tmp.name), out=out, timeout_s=0,
                                                     warn_s=0, idle_s=1), 124)
        self.assertIn("no output for 1 s", (Path(self.tmp.name) / "sleep.log").read_text())

    def test_the_cpu_watch_needs_a_second_measure_and_a_second_of_work(self):
        spin = subprocess.Popen([sys.executable, "-c", "import time\nt=time.process_time()\nwhile time.process_time()-t<1.5: pass"])
        self.addCleanup(spin.wait)
        watch = process.CpuWatch(spin.pid)
        self.assertFalse(watch.sample(0))  # the first measure is the baseline
        spin.wait()
        self.assertFalse(process.CpuWatch(spin.pid).sample(0))  # a process that is gone is no work


WRAPPER = '''
import io, json, os, runpy, sys, time
role, marker, mode, fake = sys.argv[1:5]
prompt = sys.stdin.read()
COMMAND = "pytest -x tests/test_a.py"
def use(command):
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": command}}]}}), flush=True)
if role == "executor":
    if mode == "repeat":
        for _ in range(5):
            use(COMMAND)
    deadline = time.time() + 60
    while not os.path.exists(marker) and time.time() < deadline:   # until the conductor has said it
        if mode == "grow":
            print(json.dumps({"type": "progress"}), flush=True)
        time.sleep(0.05)
    if mode == "repeat":
        for _ in range(3):
            use(COMMAND)
sys.stdin = io.StringIO(prompt)
sys.argv = [fake, role]
runpy.run_path(fake, run_name="__main__")
'''


class BeaconCase(ConductorCase):
    def limits(self, **limits) -> dict:
        return {"options": [{"source": "item:W1", "options": {"limits": limits}}]}

    def beacons(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]


class StallBeaconTests(BeaconCase):
    def run_with_wrapper(self, mode: str, **limits) -> tuple:
        wrapper = self.project.parent / "stall-role.py"
        wrapper.write_text(WRAPPER, encoding="utf-8")
        marker = self.project.parent / "beacon.seen"
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] = [sys.executable, str(wrapper), "executor", str(marker), mode, str(FIXTURES / "fake_role.py")]
        self.write_config(argv)
        self.set_items({"W1": self.limits(**limits)})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        real = progress.Progress.emit

        def emit(progress_self, event, **fields):
            line = real(progress_self, event, **fields)
            if fields.get("reason_code") == "STALL_SUSPECTED":
                marker.touch()  # the conductor has said it: the fake role may go on
            return line

        with mock.patch.object(process, "POLL_S", 0.2), mock.patch.object(progress.Progress, "emit", emit):
            return self.run_items("W1")

    def test_the_same_command_five_times_is_one_beacon_and_nothing_is_stopped(self):
        code, _, err = self.run_with_wrapper("repeat", stall_repeat_n=5, stall_window_s=0)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        found = self.beacons(err, "STALL_SUSPECTED")
        self.assertEqual(len(found), 1, found)  # three more identical commands after it: still one
        self.assertIn("same command 5 times: Bash: pytest -x tests/test_a.py", found[0]["message"])
        self.assertEqual((found[0]["item"], found[0]["stage"], found[0]["role"]), ("W1", "executor.1", "executor"))

    def test_a_stream_that_grows_without_a_tool_step_for_the_window_is_a_beacon_and_nothing_is_stopped(self):
        code, _, err = self.run_with_wrapper("grow", stall_repeat_n=0, stall_window_s=1)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        found = self.beacons(err, "STALL_SUSPECTED")
        self.assertTrue(found, err)
        self.assertIn("stream grew without a tool step for", found[0]["message"])

    def test_the_limits_off_say_nothing(self):
        wrapper = self.project.parent / "stall-role.py"
        wrapper.write_text(WRAPPER, encoding="utf-8")
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        marker = self.project.parent / "never"
        marker.touch()  # the fake role does not wait
        argv["executor"] = [sys.executable, str(wrapper), "executor", str(marker), "repeat", str(FIXTURES / "fake_role.py")]
        self.write_config(argv)
        self.set_items({"W1": self.limits(stall_repeat_n=0, stall_window_s=0)})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(process, "POLL_S", 0.2):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.beacons(err, "STALL_SUSPECTED"), [])


class CheckIdleBeaconTests(BeaconCase):
    def test_a_silent_check_gets_check_idle_beacons_and_is_not_killed(self):
        slow = {"id": "V1", "cmd": "sleep 3 && test -f out/W1.txt", "expect": "exit 0", "kind": "acceptance"}
        self.set_items({"W1": {"checks": [slow], **self.limits(check_idle_warn_s=1, check_idle_timeout_s=0)}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(checks_mod, "POLL_S", 0.2):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        found = self.beacons(err, "CHECK_IDLE")
        self.assertGreaterEqual(len(found), 1, err)
        self.assertEqual((found[0]["stage"], found[0]["item"]), ("checks.1", "W1"))
        self.assertIn("V1 no output for", found[0]["message"])

    def test_check_idle_off_says_nothing(self):
        slow = {"id": "V1", "cmd": "sleep 2 && test -f out/W1.txt", "expect": "exit 0", "kind": "acceptance"}
        self.set_items({"W1": {"checks": [slow], **self.limits(check_idle_warn_s=0)}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(checks_mod, "POLL_S", 0.2):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.beacons(err, "CHECK_IDLE"), [])


class RunHeartbeatTests(BeaconCase):
    def heartbeat(self, err: str) -> dict:
        return records.read(self.run_dir(err) / "heartbeat.json", "heartbeat")

    def test_a_run_writes_a_valid_heartbeat_from_its_own_lines(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        doc = self.heartbeat(err)
        self.assertEqual((doc["pid"], doc["start_ticks"], doc["run_id"]),
                         (os.getpid(), process.start_ticks(os.getpid()), self.run_dir(err).name))
        self.assertGreater(doc["seq"], 3)
        self.assertEqual(records.problems(doc, "heartbeat"), [])
        self.assertIsNone(doc["waiting"])
        self.assertIn(doc["last_progress_kind"], ("stage_end", "stage_start"))

    def test_the_heartbeat_names_the_wait_for_the_work_source_while_it_lasts(self):
        seen = []
        real = work_source.inprocess_transport

        def transport(argv, cwd, env):
            runs_dir = runs_root(self.project)
            for folder in runs_dir.glob("cnd-*"):
                found, _ = heartbeat_mod.read(folder)
                if found and found["waiting"]:
                    seen.append(found)
                    seen.append(self.status_json(folder.name))
            return real(argv, cwd, env)

        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(work_source, "ORCH_TRANSPORT", transport):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertTrue(seen, "no call of the work source saw a wait in the heartbeat")
        wait = seen[0]["waiting"]
        self.assertEqual((wait["kind"], wait["reason_code"]), ("work_source", "WORK_SOURCE_CALL"))
        self.assertGreater(timefmt.epoch(wait["deadline"]), timefmt.epoch(wait["since"]) + 590)
        inside = seen[1]["health"]
        self.assertEqual((inside["health"], inside["reason_code"]), ("waiting_tool", "WORK_SOURCE_CALL"))
        self.assertIsNone(self.heartbeat(err)["waiting"])  # and it is over when the call is

    def status_json(self, run_id: str) -> dict:
        code, out, _ = self.conduct("status", "--run", run_id, "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_a_heartbeat_that_cannot_be_written_never_stops_the_run(self):
        real = records.write

        def write(path, doc, kind):
            if kind == "heartbeat":
                raise OSError(28, "No space left on device")
            return real(path, doc, kind)

        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(records, "write", write):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(len(self.beacons(err, "HEARTBEAT_NOT_WRITTEN")), 1)
        self.assertFalse((self.run_dir(err) / "heartbeat.json").exists())

    def test_status_and_runs_show_the_health_of_a_finished_run(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        run_id = self.run_dir(err).name
        self.assertEqual(self.status_json(run_id)["health"]["health"], "finished")
        row = json.loads(self.conduct("runs", "--json")[1])["runs"][0]
        self.assertEqual((row["run_id"], row["health"]), (run_id, "finished"))
        code, out, _ = self.conduct("status", "--run", run_id)
        self.assertEqual(code, 0)
        self.assertIn("\n  health: finished", out)


class HealthSurfaceTests(unittest.TestCase):
    """``status`` and ``runs`` on run folders written by hand; a child process holds the lease where the run is alive."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(os.path.realpath(self.tmp.name))
        (self.project / ".git").mkdir()

    def make(self, run_id: str, lines: list, doc=None) -> Path:
        directory = runs_root(self.project) / run_id
        directory.mkdir(parents=True)
        (directory / RUN_FILE).write_text(json.dumps(doc if doc is not None else {"items": []}), encoding="utf-8")
        text = [json.dumps({"ts": ts, "run": run_id, "event": event, **fields}) for ts, event, fields in lines]
        (directory / "progress.jsonl").write_text("\n".join(text) + "\n", encoding="utf-8")
        return directory

    def conduct(self, *argv: str) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def status(self, directory: Path) -> dict:
        code, out, err = self.conduct("status", "--run", directory.name, "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)

    @contextlib.contextmanager
    def holder(self, directory: Path):
        """A child process that holds the lease of ``directory`` until its stdin closes."""
        code = ("import sys; sys.path[:0] = " + repr([str(ROOT / "lib"), str(ROOT.parent / "aicore/lib")]) + "\n"
                "from pathlib import Path\nfrom orch.conductor.infrastructure.lease import RunLease\n"
                "lease = RunLease(Path(sys.argv[1])).acquire('run')\nprint('ready', flush=True)\nsys.stdin.read()")
        child = subprocess.Popen([sys.executable, "-I", "-c", code, str(directory)], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            yield child
        finally:
            child.stdin.close()
            child.wait(timeout=10)

    def write_beat(self, directory: Path, **over) -> None:
        doc = {"run_id": directory.name, "pid": os.getpid(), "start_ticks": process.start_ticks(os.getpid()),
               "boot_id": process.boot_id(), "host": "box", "seq": 9, "at": timefmt.utc_stamp(), **over}
        records.write(directory / "heartbeat.json", doc, "heartbeat")

    def test_a_live_conductor_with_a_stale_heartbeat_is_hung(self):
        directory = self.make("cnd-hung", [("2026-10-16T10:00:00Z", "run.start", {})], {"lease": True, "items": []})
        with self.holder(directory) as child:
            self.write_beat(directory, pid=child.pid, start_ticks=process.start_ticks(child.pid),
                            at=timefmt.utc_stamp(timefmt.epoch(timefmt.utc_stamp()) - 400))
            found = self.status(directory)["health"]
            self.assertEqual((found["health"], found["reason_code"]), ("hung", "HEARTBEAT_STALE"))
            self.assertGreaterEqual(found["heartbeat_age_s"], 400)
            row = json.loads(self.conduct("runs", "--json")[1])["runs"][0]
            self.assertEqual((row["run_id"], row["status"], row["health"]), ("cnd-hung", "running", "hung"))
            self.write_beat(directory, pid=child.pid, start_ticks=process.start_ticks(child.pid))
            self.assertEqual(self.status(directory)["health"]["health"], "running")  # the same run, a fresh heartbeat

    def test_a_heartbeat_of_another_process_than_the_lease_holder_is_suspected(self):
        directory = self.make("cnd-mismatch", [("2026-10-16T10:00:00Z", "run.start", {})], {"lease": True, "items": []})
        with self.holder(directory):
            self.write_beat(directory)  # the heartbeat of this test process, the lease of the child
            found = self.status(directory)["health"]
            self.assertEqual((found["health"], found["reason_code"]), ("suspected_stall", "HEARTBEAT_OWNER_MISMATCH"))

    def test_the_owner_of_the_lease_shows_its_identity_in_status_and_runs(self):
        directory = self.make("cnd-owner", [("2026-10-16T10:00:00Z", "run.start", {})], {"lease": True, "items": []})
        with self.holder(directory) as child:
            owner = self.status(directory)["lease"]
            self.assertEqual((owner["pid"], owner["start_ticks"], owner["launcher"]),
                             (child.pid, process.start_ticks(child.pid), "terminal"))
            self.assertEqual(json.loads(self.conduct("runs", "--json")[1])["runs"][0]["owner"], owner)

    def test_a_run_from_before_heartbeats_is_running_with_a_detail_and_a_broken_heartbeat_is_unknown(self):
        legacy = self.make("cnd-legacy", [("2026-10-16T10:00:00Z", "run.start", {})])  # no lease flag, no heartbeat
        found = self.status(legacy)
        self.assertEqual((found["status"], found["health"]["health"], found["health"]["reason_code"]),
                         ("running", "running", "HEARTBEAT_MISSING"))
        self.assertIn("heartbeat.json", found["health"]["detail"])
        code, out, _ = self.conduct("status", "--run", legacy.name)
        self.assertEqual(code, 0)
        self.assertIn("health: running", out)
        self.assertIn("HEARTBEAT_MISSING", out)
        (legacy / "heartbeat.json").write_text("{broken", encoding="utf-8")
        found = self.status(legacy)["health"]
        self.assertEqual((found["health"], found["reason_code"]), ("unknown", "HEARTBEAT_INVALID"))
        code, out, _ = self.conduct("status", "--run", legacy.name)
        self.assertEqual(code, 0)
        self.assertIn("health: unknown", out)

    def test_a_run_without_a_holder_is_orphaned_in_health_as_in_status(self):
        directory = self.make("cnd-orphan", [("2026-10-16T10:00:00Z", "run.start", {})], {"lease": True, "items": []})
        found = self.status(directory)
        self.assertEqual((found["status"], found["health"]["health"]), ("orphaned", "orphaned"))
        self.assertEqual(json.loads(self.conduct("runs", "--json")[1])["runs"][0]["health"], "orphaned")

    def test_a_wait_inside_its_deadline_is_not_a_hang_and_after_it_the_class_degrades(self):
        directory = self.make("cnd-wait", [("2026-10-16T10:00:00Z", "run.start", {})], {"lease": True, "items": []})
        now = timefmt.epoch(timefmt.utc_stamp())
        with self.holder(directory) as child:
            ident = {"pid": child.pid, "start_ticks": process.start_ticks(child.pid)}
            wait = {"kind": "work_source", "reason_code": "WORK_SOURCE_CALL", "since": timefmt.utc_stamp(now - 400)}
            self.write_beat(directory, **ident, at=timefmt.utc_stamp(now - 400),
                            waiting={**wait, "deadline": timefmt.utc_stamp(now + 200)})
            found = self.status(directory)["health"]
            self.assertEqual((found["health"], found["reason_code"]), ("waiting_tool", "WORK_SOURCE_CALL"))
            self.write_beat(directory, **ident, at=timefmt.utc_stamp(now - 400),
                            waiting={**wait, "deadline": timefmt.utc_stamp(now - 100)})
            self.assertEqual(self.status(directory)["health"]["reason_code"], "WAIT_DEADLINE_PASSED")
            self.write_beat(directory, **ident, at=timefmt.utc_stamp(now - 900),
                            waiting={**wait, "deadline": timefmt.utc_stamp(now - 400)})
            self.assertEqual(self.status(directory)["health"]["health"], "hung")

    def test_a_run_that_stopped_for_a_question_is_waiting_owner_in_status_and_runs(self):
        directory = self.make("cnd-asked", [("2026-10-16T10:00:00Z", "run.start", {}),
                                            ("2026-10-16T10:05:00Z", "run.end", {"outcome": "waiting", "reason_code": "WAITING_DECISION"})],
                              {"items": []})
        found = self.status(directory)
        self.assertEqual((found["status"], found["health"]["health"], found["health"]["reason_code"]),
                         ("waiting", "waiting_owner", "WAITING_DECISION"))
        self.assertEqual(json.loads(self.conduct("runs", "--json")[1])["runs"][0]["health"], "waiting_owner")

    def test_a_quota_stop_with_a_reset_in_the_journal_waits_for_the_budget(self):
        later = timefmt.utc_stamp(timefmt.epoch(timefmt.utc_stamp()) + 3600)
        directory = self.make("cnd-quota", [
            ("2026-10-16T10:00:00Z", "run.start", {}),
            ("2026-10-16T10:01:00Z", "info", {"reason_code": "PROVIDER_WAIT", "message": f"executor: quota; waiting 900 s, until {later}"}),
            ("2026-10-16T10:05:00Z", "run.end", {"outcome": "stopped", "reason_code": "PROVIDER_QUOTA"})], {"items": []})
        state = {"$schema": "urn:swissknifeman:orch:records:state:v1", "status": "stopped",
                 "stop": {"code": "PROVIDER_QUOTA", "message": "the limit resets"}}
        (directory / "state.json").write_text(json.dumps(state), encoding="utf-8")
        found = self.status(directory)["health"]
        self.assertEqual((found["health"], found["reason_code"]), ("waiting_budget_reset", "PROVIDER_QUOTA"))
        self.assertEqual(json.loads(self.conduct("runs", "--json")[1])["runs"][0]["health"], "waiting_budget_reset")

    def test_heartbeat_and_lease_documents_pass_records_read(self):
        directory = self.make("cnd-read", [("2026-10-16T10:00:00Z", "run.start", {})], {"lease": True, "items": []})
        with RunLease(directory).acquire("run"):
            self.write_beat(directory)
            self.assertEqual(records.read(directory / "lease.json", "lease")["pid"], os.getpid())
            self.assertEqual(records.read(directory / "heartbeat.json", "heartbeat")["seq"], 9)


class OptionsTests(unittest.TestCase):
    def test_the_new_limits_have_their_defaults(self):
        from orch.conductor import options
        self.assertEqual({key: options.DEFAULT_LIMITS[key] for key in ("stall_window_s", "stall_repeat_n", "check_idle_warn_s")},
                         {"stall_window_s": 1800, "stall_repeat_n": 5, "check_idle_warn_s": 600})


if __name__ == "__main__":
    unittest.main()
