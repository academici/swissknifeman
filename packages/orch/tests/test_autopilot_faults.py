"""Fault injection for the autopilot (PLAN9 P8.5, scenarios a-g, k, o-q and u of knowledge/p8-design#p8-autopilot).

The controller (``orch conduct autopilot start``) and its children (``conduct run|continue|resume``) are real processes on the
fake roles and the fake work source of the conductor tests. The executor waits at a marker (``GATE_ROLE`` of the supervisor
fault tests) so that a test can kill, pause, drain or stop while a run is mid-step; nothing sleeps for a fixed time, every wait
polls until a deadline. The machine layer of a temporary home allows and enables the autopilot with ``poll_s = 0.2``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

from aicore.ext import events as journal

from orch.conductor import contract, process, progress, records
from orch.conductor.application import autopilot
from orch.conductor.infrastructure.files import STATE_FILE, runs_root
from orch.conductor.infrastructure.lease import RunLease
from tests.test_conductor import check, quota_failure, report
from tests.test_conductor_questions import ASK
from tests.test_supervisor_faults import DEADLINE_S, ORCH, FaultCase, alive, eventually

DIGEST = "sha256:" + "b" * 64


def made(ref: str) -> dict:
    return {"write": {f"out/{ref}.txt": "ok\n"}, "result": report(ref)}


def asks(ref: str, **write) -> dict:
    return {"write": write, "result": report(ref, "blocked", changed_paths=list(write), checks_run=[], questions=[dict(ASK)],
                                              open_issues=[{"text": "needs an answer from the owner", "kind": "escalation"}])}


def blocked(ref: str) -> dict:
    return {"result": report(ref, "blocked", changed_paths=[], checks_run=[], open_issues=[
        {"text": "SCOPE_EXPANSION: needs bridges/other", "kind": "escalation", "escalation_class": "scope"}])}


class AutopilotCase(FaultCase):
    recover = None  # the supervisor stays at notify: recovery here is the autopilot's
    items = ("W1", "W2")
    executor: list = []
    machine_autopilot = {"allowed": "true", "enabled": "true", "poll_s": 1}
    source_extra: dict = {}

    def setUp(self):
        super().setUp()
        with open(self.project / ".gitignore", "a", encoding="utf-8") as handle:  # the artifacts of a blocked piece stay
            handle.write("plans/T/artifacts/\n")                                # out of the tree a next lane needs clean
        self.git("commit", "-q", "-am", "ignore the artifacts of the source")
        self.script_file.write_text(json.dumps({"executor": self.executor or [made(ref) for ref in self.items]}),
                                    encoding="utf-8")
        self.controllers: list = []

    def write_machine(self, recover, **extra) -> Path:
        path = super().write_machine(recover, **extra)
        lines = ["", "[orch.autopilot]", *[f"{key} = {value}" for key, value in self.machine_autopilot.items()]]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path

    def set_items(self) -> None:
        items = {ref: {"status": "todo", "title": f"Work {ref}", "scenario": self.scenario, "write_set": [f"out/{ref}.txt"],
                       "checks": [check(ref)], "options": [{"source": f"item:{ref}", "options": {"on_blocked": "stop"}}]}
                 for ref in self.items}
        self.state_file.write_text(json.dumps({
            "order": list(self.items), "items": items, "registered": {}, "commits": [], "calls": [],
            "readiness": {"phase": "P1", "phases": [{"id": "P1", "status": "ready", "digest": DIGEST}]},
            **self.source_extra}), encoding="utf-8")

    def source(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------------------------------------ the controller

    def start_autopilot(self, *flags, env: dict | None = None) -> subprocess.Popen:
        log = open(self.logs / f"autopilot-{len(self.controllers)}.log", "wb")
        self.addCleanup(log.close)
        child = subprocess.Popen([sys.executable, str(ORCH), "--project", str(self.project), "conduct", "autopilot", "start",
                                  "--plan", "T", "--poll-s", "0.2", *map(str, flags)], env={**self.env, **(env or {})},
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        self.children.append(child)
        self.controllers.append(child)
        return child

    def log(self, number: int = -1) -> str:
        return sorted(self.logs.glob("autopilot-*.log"))[number].read_text(encoding="utf-8", errors="replace")

    def finish(self, controller: subprocess.Popen, code: int) -> dict:
        self.assertEqual(code, controller.wait(timeout=DEADLINE_S), self.log())
        return self.state()

    def state(self) -> dict:
        return records.read(runs_root(self.project) / autopilot.STATE_DOC, "autopilot-state")

    def current(self, state: str = "running") -> dict:
        return eventually(self, lambda: ((self.state_or_none() or {}).get("current") or {}).get("state") == state
                          and self.state_or_none()["current"], f"a current run in state {state}")

    def current_of(self, kind: str, state: str = "running") -> dict:
        def found():
            current = (self.state_or_none() or {}).get("current") or {}
            return current if (current.get("kind"), current.get("state")) == (kind, state) else None
        return eventually(self, found, f"a current {kind} in state {state}")

    def until(self, condition, what: str):
        """``eventually`` with the log of the controller in the failure."""
        try:
            return eventually(self, condition, what)
        except AssertionError as error:
            raise AssertionError(f"{error}\n{self.log()}") from None

    def stays(self, condition, seconds: float, what: str) -> None:
        """``condition`` holds at every poll until the deadline (the opposite of ``eventually``)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.assertTrue(condition(), what)
            time.sleep(0.05)

    def state_or_none(self):
        try:
            return self.state()
        except Exception:  # noqa: BLE001 — a file being replaced is read again at the next poll
            return None

    def request(self, action: str) -> None:
        done = self.orch("conduct", "autopilot", action)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)

    def run_status(self, run_id: str) -> str:
        return progress.summarize(progress.read_lines(runs_root(self.project) / run_id))["status"]

    def run_dirs(self) -> list:
        return sorted(path.name for path in runs_root(self.project).glob("cnd-*") if (path / "run.json").is_file())

    def go(self) -> None:
        (self.gate / "go").touch()

    def stopped_events(self) -> list:
        return [event.data for event in journal.read_events(self.project)[0] if event.type == "orch.autopilot.stopped"]


class LaneTests(AutopilotCase):
    """Every lane runs as its own run (``run --items``, never ``--ready``), then the plan is done."""

    block_calls = 0

    def test_two_lanes_two_runs_then_no_work(self):
        state = self.finish(self.start_autopilot(), 0)
        self.assertEqual("AUTOPILOT_NO_WORK", state["stop"]["code"])
        self.assertEqual((2, 2), (state["counters"]["runs"], state["counters"]["items_closed"]))
        self.assertEqual([["W1"], ["W2"]], [row["items_closed"] for row in state["history"]])
        self.assertEqual({"W1": "done", "W2": "done"}, {ref: item["status"] for ref, item in self.source()["items"].items()})
        options = json.loads((runs_root(self.project) / autopilot.OPTIONS_DOC).read_text(encoding="utf-8"))
        self.assertEqual({"scope": {"outside": "block"}}, options)
        for run_id in self.run_dirs():
            doc = records.read(runs_root(self.project) / run_id / "run.json", "run")
            self.assertEqual((False, str(runs_root(self.project) / autopilot.OPTIONS_DOC)), (doc["batch"], doc["options_file"]))
        self.assertIn("AUTOPILOT_NO_WORK: ", self.log())
        self.assertEqual(["AUTOPILOT_NO_WORK"], [data["code"] for data in self.stopped_events()])

    def test_detach_prints_the_acknowledged_controller_which_runs_to_its_stop(self):
        done = self.orch("conduct", "autopilot", "start", "--plan", "T", "--poll-s", "0.2", "--detach")
        self.assertEqual(0, done.returncode, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual([], contract.problems(printed, "detach-result"))
        state = eventually(self, lambda: (self.state_or_none() or {}).get("stop") and self.state(), "the detached session ended")
        self.assertEqual(("AUTOPILOT_NO_WORK", printed["pid"]), (state["stop"]["code"], state["pid"]))
        eventually(self, lambda: not alive(printed["pid"]), "the detached controller exited")
        self.assertIn("AUTOPILOT_NO_WORK: ", Path(printed["log"]).read_text(encoding="utf-8"))


class RecoveryTests(AutopilotCase):
    """(a) a conductor killed mid-executor is reaped and resumed once; a second crash of the same run exhausts it."""

    items = ("W1",)
    block_calls = 2

    def test_a_sigkill_of_the_child_is_resumed_once_then_exhausted(self):
        controller = self.start_autopilot()
        first = self.current()
        directory = runs_root(self.project) / first["run_id"]
        self.role_pid(1)
        pid = eventually(self, lambda: RunLease.owner(directory).get("pid"), "the child holds the run")
        os.kill(pid, signal.SIGKILL)
        second = self.current_of("resume")
        self.assertEqual(first["run_id"], second["run_id"])
        self.role_pid(2)
        self.assertEqual(second["pid"], RunLease.owner(directory).get("pid"), "the resumed child holds the run")
        os.kill(second["pid"], signal.SIGKILL)
        state = self.finish(controller, 1)
        self.assertEqual("AUTOPILOT_RECOVERY_EXHAUSTED", state["stop"]["code"])
        self.assertEqual({first["run_id"]: 1}, state["recoveries"])
        self.assertEqual(1, len(state["history"]))
        self.assertIn(f"orch conduct reap --run {first['run_id']}", state["stop"]["message"])


class RecoveryFinishesTests(AutopilotCase):
    items = ("W1",)
    block_calls = 1

    def test_a_the_resumed_run_finishes_and_the_autopilot_goes_on(self):
        controller = self.start_autopilot()
        first = self.current()
        directory = runs_root(self.project) / first["run_id"]
        role = self.role_pid(1)
        os.kill(eventually(self, lambda: RunLease.owner(directory).get("pid"), "the child holds the run"), signal.SIGKILL)
        state = self.finish(controller, 0)
        self.assertEqual("AUTOPILOT_NO_WORK", state["stop"]["code"])
        self.assertEqual(({first["run_id"]: 1}, 1), (state["recoveries"], state["counters"]["recoveries"]))
        self.assertEqual([(first["run_id"], "finished")], [(row["run_id"], row["status"]) for row in state["history"]])
        self.assertFalse(alive(role), "the role the dead child left was reaped")


class ControllerCrashTests(AutopilotCase):
    """(b) a killed controller is replaced by a new start that adopts the live run and starts no second conductor; (o) a
    controller that dies right after the spawn, before it saw the acknowledgement: the run is adopted, one history entry."""

    block_calls = 1

    def adopt(self, first: dict) -> subprocess.Popen:
        directory = runs_root(self.project) / first["run_id"]
        second = self.start_autopilot()
        eventually(self, lambda: (self.state_or_none() or {}).get("pid") == second.pid, "the new controller took the session")
        self.assertEqual(first["run_id"], self.current()["run_id"], "the run of the dead controller is adopted")
        self.assertEqual([first["run_id"]], self.run_dirs(), "no second conductor is started")
        self.assertTrue(RunLease.held(directory))
        return second

    def test_b_a_new_start_adopts_the_run_of_a_killed_controller(self):
        controller = self.start_autopilot()
        first = self.current()
        self.role_pid(1)
        controller.kill()
        controller.wait(timeout=10)
        self.assertEqual(("running", None), (self.state()["mode"], self.state()["stop"]))
        self.assertEqual("dead", json.loads(self.orch("conduct", "autopilot", "status", "--json").stdout)["status"])
        second = self.adopt(first)
        self.go()
        state = self.finish(second, 0)
        self.assertEqual("AUTOPILOT_NO_WORK", state["stop"]["code"])
        self.assertEqual([first["run_id"]], [row["run_id"] for row in state["history"] if "W1" in row["items_closed"]])
        self.assertEqual(2, len(state["history"]), "one entry per run: the adopted one and the lane of W2")

    def test_o_a_crash_after_the_spawn_is_adopted_with_one_history_entry(self):
        controller = self.start_autopilot(env={autopilot.CRASH_ENV: "after_spawn"})
        self.assertEqual(9, controller.wait(timeout=DEADLINE_S), self.log())
        first = self.state()["current"]
        self.assertEqual("launching", first["state"])
        self.role_pid(1)
        second = self.adopt(first)
        self.go()
        state = self.finish(second, 0)
        self.assertEqual([1], [sum(1 for row in state["history"] if row["run_id"] == first["run_id"])])
        self.assertEqual("finished", next(row for row in state["history"] if row["run_id"] == first["run_id"])["status"])


class RequestTests(AutopilotCase):
    """(c) pause takes no new work until resume, (d) drain ends after the current run, (e) stop interrupts the child."""

    block_calls = 1

    def at_gate(self) -> tuple:
        controller = self.start_autopilot()
        first = self.current()
        self.role_pid(1)
        return controller, first

    def test_c_pause_then_resume(self):
        controller, first = self.at_gate()
        self.request("pause")
        eventually(self, lambda: self.state()["mode"] == "paused", "the controller read the pause")
        self.go()
        eventually(self, lambda: self.state()["current"] is None and self.state()["history"][0]["status"] == "finished",
                   "the current run ended")
        self.assertEqual("paused", json.loads(self.orch("conduct", "autopilot", "status", "--json").stdout)["status"])
        self.stays(lambda: self.run_dirs() == [first["run_id"]], 1.5, "no new run while paused")  # several looks of 0.2 s
        self.request("resume")
        state = self.finish(controller, 0)
        self.assertEqual(("AUTOPILOT_NO_WORK", 2), (state["stop"]["code"], len(self.run_dirs())))

    def test_d_drain_ends_after_the_current_run(self):
        controller, first = self.at_gate()
        self.request("drain")
        eventually(self, lambda: self.state()["mode"] == "draining", "the controller read the drain")
        self.go()
        state = self.finish(controller, 0)
        self.assertEqual(("AUTOPILOT_DRAINED", [first["run_id"]]), (state["stop"]["code"], self.run_dirs()))
        self.assertEqual("todo", self.source()["items"]["W2"]["status"])

    def test_e_stop_interrupts_the_child_which_stays_resumable(self):
        controller, first = self.at_gate()
        self.request("stop")
        state = self.finish(controller, 0)
        self.assertEqual("AUTOPILOT_STOPPED", state["stop"]["code"])
        directory = runs_root(self.project) / first["run_id"]
        run_state = records.read(directory / STATE_FILE, "state")
        self.assertEqual(("stopped", "INTERRUPTED"), (run_state["status"], run_state["stop"]["code"]))
        self.assertEqual(("interrupted", 130), (state["history"][0]["status"], state["history"][0]["exit"]))
        self.assertFalse(RunLease.held(directory))
        self.assertIsNone(state["current"])


class QuotaTests(AutopilotCase):
    """(f) a provider quota with a near reset is waited for and the run resumed; a far reset stops."""

    items = ("W1",)
    block_calls = 0

    def set_items(self) -> None:
        super().set_items()
        doc = self.source()
        doc["items"]["W1"]["options"][0]["options"]["limits"] = {"provider_wait_max_s": 0}
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def test_f_a_near_reset_is_waited_for_then_resumed(self):
        self.script_file.write_text(json.dumps({"executor": [quota_failure(2), made("W1")]}), encoding="utf-8")
        state = self.finish(self.start_autopilot(), 0)
        self.assertEqual(("AUTOPILOT_NO_WORK", 1, 1), (state["stop"]["code"], state["counters"]["quota_waits"],
                                                      len(state["history"])))
        self.assertEqual("finished", state["history"][0]["status"])

    def test_f_a_reset_past_quota_wait_max_s_stops(self):
        self.machine_autopilot = dict(AutopilotCase.machine_autopilot, quota_wait_max_s=60)
        self.write_machine(self.recover)
        self.script_file.write_text(json.dumps({"executor": [quota_failure(3600), made("W1")]}), encoding="utf-8")
        state = self.finish(self.start_autopilot(), 1)
        self.assertEqual(("AUTOPILOT_QUOTA", 0), (state["stop"]["code"], state["counters"]["quota_waits"]))


class BlockerTests(AutopilotCase):
    """(g) the same blocker of the same piece twice in a row stops."""

    items = ("W1",)
    block_calls = 0
    source_extra = {"reopen_blocked": True}
    executor = [{"result": report("W1", "blocked", changed_paths=[], checks_run=[],
                                  open_issues=[{"text": "the design leaves the format open", "kind": "escalation"}])}]

    def test_g_the_same_blocker_twice_stops(self):
        state = self.finish(self.start_autopilot(), 1)
        self.assertEqual("AUTOPILOT_REPEATED_BLOCKER", state["stop"]["code"], self.log())
        self.assertEqual(2, len(state["history"]))
        self.assertEqual(1, len(state["last_blockers"]))
        self.assertIn("W1", state["stop"]["message"])


class WaitingTests(AutopilotCase):
    """(k) a lane that waits for an answer does not hold up an independent lane, and the answer continues it; (u) the only
    waiting run is continued once when its answer comes; (p) a waiting run that left tracked changes needs the owner."""

    block_calls = 0

    def answer(self, run_id: str) -> None:
        done = self.orch("conduct", "answer", "--run", run_id, "--item", "W1", "--question", "Q1", "--option", "rename",
                         "--by", "owner")
        self.assertEqual(0, done.returncode, done.stderr)

    def waiting_run(self) -> str:
        return self.until(lambda: ((self.state_or_none() or {}).get("waiting_runs") or [{}])[0].get("run_id"),
                          "a run waits for an answer")

    def test_k_an_independent_lane_runs_and_the_answer_continues_the_waiting_one(self):
        self.script_file.write_text(json.dumps({"executor": [asks("W1"), made("W2"), made("W1")]}), encoding="utf-8")
        controller = self.start_autopilot()
        waiting = self.waiting_run()
        self.until(lambda: any("W2" in row["items_closed"] for row in self.state()["history"]), "the lane of W2 ran")
        self.assertIsNone(controller.poll(), "the controller waits for the answer")
        self.answer(waiting)
        state = self.finish(controller, 0)
        self.assertEqual("AUTOPILOT_NO_WORK", state["stop"]["code"], self.log())
        entry = next(row for row in state["history"] if row["run_id"] == waiting)
        self.assertEqual(("continue", "finished", ["W1"]), (entry["kind"], entry["status"], entry["items_closed"]))
        self.assertEqual((3, []), (state["counters"]["runs"], state["waiting_runs"]))

    def test_u_the_only_waiting_run_is_continued_once(self):
        self.items = ("W1",)
        self.set_items()
        self.script_file.write_text(json.dumps({"executor": [asks("W1"), made("W1")]}), encoding="utf-8")
        controller = self.start_autopilot()
        waiting = self.waiting_run()
        self.answer(waiting)
        state = self.finish(controller, 0)
        self.assertEqual("AUTOPILOT_NO_WORK", state["stop"]["code"], self.log())
        self.assertEqual(2, state["counters"]["runs"], "one run and exactly one continue")
        self.assertEqual([(waiting, "continue", "finished")], [(row["run_id"], row["kind"], row["status"])
                                                               for row in state["history"]])
        self.assertNotIn("NEXT_", self.log())

    def test_p_a_waiting_run_with_tracked_changes_needs_the_owner_and_they_stay(self):
        self.items = ("W1",)
        self.set_items()
        doc = self.source()
        doc["items"]["W1"]["write_set"] = ["out/W1.txt", "README.md"]
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        self.script_file.write_text(json.dumps({"executor": [asks("W1", **{"README.md": "changed by the executor\n"})]}),
                                    encoding="utf-8")
        state = self.finish(self.start_autopilot(), 1)
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", state["stop"]["code"], self.log())
        self.assertIn("W1 (Q1)", state["stop"]["message"])
        self.assertEqual("changed by the executor\n", (self.project / "README.md").read_text(encoding="utf-8"))
        self.assertIn("README.md", self.git("status", "--porcelain", "--untracked-files=no"))

    def test_p_a_plan_in_a_workspace_excludes_no_plans_folder_of_the_checkout(self):
        """(review F6) the source names no plan folder inside the checkout (``workspace_plan``): a tracked product file
        ``plans/T/module.py`` changed by the waiting piece needs the owner, and the independent lane W2 does not start."""
        (self.project / "plans" / "T").mkdir(parents=True)
        (self.project / "plans" / "T" / "module.py").write_text("product\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "a product module under plans/")
        doc = self.source()
        doc["workspace_plan"] = True
        doc["items"]["W1"]["write_set"] = ["out/W1.txt", "plans/T/module.py"]
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        self.script_file.write_text(json.dumps({"executor": [asks("W1", **{"plans/T/module.py": "changed\n"}), made("W2")]}),
                                    encoding="utf-8")
        state = self.finish(self.start_autopilot(), 1)
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", state["stop"]["code"], self.log())
        self.assertEqual(([], 1), (state["waiting_runs"], len(self.run_dirs())), "no lane of W2")
        self.assertEqual("changed\n", (self.project / "plans/T/module.py").read_text(encoding="utf-8"))
        self.assertEqual("todo", self.source()["items"]["W2"]["status"])


class DeadlineTests(AutopilotCase):
    """(q) the deadline passes while a healthy run works: SIGINT to the child, which stays resumable, then AUTOPILOT_MAX_WALL."""

    items = ("W1",)
    block_calls = 1

    def test_q_the_deadline_interrupts_a_healthy_run(self):
        controller = self.start_autopilot("--max-wall-s", 3)
        first = self.current()
        state = self.finish(controller, 0)
        self.assertEqual("AUTOPILOT_MAX_WALL", state["stop"]["code"], self.log())
        run_state = records.read(runs_root(self.project) / first["run_id"] / STATE_FILE, "state")
        self.assertEqual(("stopped", "INTERRUPTED"), (run_state["status"], run_state["stop"]["code"]))
        self.assertEqual("interrupted", state["history"][0]["status"])
        self.assertIn(f"orch conduct resume --run {first['run_id']}", state["stop"]["message"])


class StoppedChildTests(AutopilotCase):
    """(q, review F2) a child stopped with SIGSTOP cannot answer the SIGINT of the deadline: after grace_s the supervisor library
    stops it by its identity and reaps its role group, and only then the session ends AUTOPILOT_MAX_WALL."""

    items = ("W1",)
    block_calls = 1
    machine_extra = {"grace_s": 1}

    def test_q_a_stopped_child_is_killed_and_reaped_before_the_session_ends(self):
        controller = self.start_autopilot("--max-wall-s", 10)
        first = self.current()
        role = self.role_pid(1)
        self.assertEqual(process.boot_id(), first["boot_id"])
        os.kill(first["pid"], signal.SIGSTOP)
        state = self.finish(controller, 0)
        self.assertEqual("AUTOPILOT_MAX_WALL", state["stop"]["code"], self.log())
        self.assertIn("did not answer SIGINT", state["stop"]["message"])
        self.assertIsNone(state["current"])
        eventually(self, lambda: not alive(first["pid"]), "the stopped conductor is gone")
        eventually(self, lambda: not alive(role), "its role is reaped")
        self.assertFalse(RunLease.held(runs_root(self.project) / first["run_id"]))


if __name__ == "__main__":
    unittest.main()
