"""The supervisor without processes (PLAN9 P8.2): the policy and its layers, what each class of health leads to, the breaker,
the records it writes, the commands. The classes of health are forced where a live conductor would be needed; the processes
themselves (a killed, a stopped, a healthy conductor) are in ``test_supervisor_faults.py``."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

from aicore.config import ConfigError
from aicore.ext import events as journal
from aicore.util import timefmt
from aicore.util.lock import FileLock

from orch import settings
from orch.conductor import agents, cli, contract, process, progress, records, runs
from orch.conductor.application import supervisor
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import RunStore, runs_root, write_json
from orch.conductor.infrastructure.lease import CheckoutLock, RunLease, checkout_toplevel
from orch.settings import SettingsError

NOW = timefmt.epoch("2026-11-01T10:20:00Z")
SECRET = "s3cr3t-value-123456"


def health(name: str, code: str | None = None, detail: str = "forced for the test", silent_s: int | None = 400) -> dict:
    return {"health": name, "since": None, "silent_s": silent_s, "reason_code": code, "detail": detail,
            "heartbeat_age_s": silent_s, "waiting": None}


class SupervisorCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.home, self.project = base / "home", base / "project"
        (self.home / "skm" / "config").mkdir(parents=True)
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        env = {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm"), "SKM_AICORE_EVENTS__DELIVERY": "off",
               "SKM_CONTRACTS_STRICT": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.spawn = mock.Mock(return_value={"pid": 4242, "log": str(base / "resume-1.log")})

    def machine(self, text: str) -> None:
        (self.home / "skm" / "config" / "config.toml").write_text("schema_version = 1\n" + text, encoding="utf-8")

    def policy(self, recover: str | None = None, **flags) -> supervisor.Policy:
        return supervisor.Policy.build(settings.load(project=self.project), recover=recover, **flags)

    def make_run(self, run_id: str = "cnd-one", lease: bool = True, state: dict | None = None) -> Path:
        store = RunStore(self.project, run_id)
        store.create({"run_id": run_id, "items": ["W1"], "lease": lease})
        store.save(state or {"status": "running", "items": {"W1": {"steps": {}}}})
        progress.Progress(run_id, store.directory, "quiet").emit("run.start")
        return store.directory

    def forced(self, *classes):
        """``runs.health_of`` answers these documents in turn (the last one repeats)."""
        queue = list(classes)
        return mock.patch.object(runs, "health_of", side_effect=lambda *a, **k: dict(queue.pop(0) if len(queue) > 1 else queue[0]))

    def once(self, policy: supervisor.Policy, run: str | None = None, now: float = NOW) -> list:
        return supervisor.supervise_once(self.project, policy, run=run, now=now, spawn=self.spawn)

    def names(self, actions: list) -> list:
        return [action["action"] for action in actions]

    def conduct(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def orphan(self, directory: Path, pid: int = 424242) -> Path:
        handle = agents.start(directory / "W1", "agent-1", role="executor", route={"provider": "codex"}, step="executor.1",
                              attempt=1, prompt="prompts/executor.1.md", parent=None, started_at="2026-10-20T10:00:00Z")
        write_json(handle["directory"] / "process.json", {"pid": pid, "pgid": pid, "start_ticks": 123})
        return handle["directory"]

    def lines(self, directory: Path) -> list:
        return [json.loads(line) for line in (directory / "supervisor.jsonl").read_text(encoding="utf-8").splitlines()]

    def info(self, directory: Path) -> list:
        return [line["reason_code"] for line in progress.read_lines(directory)
                if line["event"] == "info" and str(line.get("reason_code", "")).startswith("SUPERVISOR_")]


class PolicyTests(SupervisorCase):
    def test_the_default_is_notify_and_the_section_is_filled(self):
        found = settings.load(project=self.project).supervisor
        self.assertEqual(("notify", 2, 3600, 60, 300, 60, False),
                         (found["recover"], found["max_recoveries"], found["window_s"], found["grace_s"],
                          found["hung_after_s"], found["interval_s"], found["notify_send"]))
        self.assertEqual("notify", self.policy().recover)

    def test_the_effective_recover_is_the_lowest_of_the_machine_and_the_invocation(self):
        for machine, flag, expected in (("resume", None, "resume"), ("resume", "stop-only", "stop-only"),
                                        ("resume", "notify", "notify"), ("notify", "resume", "notify"),
                                        ("stop-only", "resume", "stop-only"), ("notify", "stop-only", "notify")):
            with self.subTest(machine=machine, flag=flag):
                self.assertEqual(expected, settings.effective_recover(machine, flag))
        self.assertEqual("notify", settings.effective_recover("resume", "stop-only", "notify"))
        with self.assertRaises(SettingsError) as caught:
            settings.effective_recover("resume", "kill")
        self.assertEqual("RECOVER_UNKNOWN", caught.exception.code)

    def test_a_flag_never_widens_what_the_machine_allows(self):
        self.assertEqual("notify", self.policy("resume").recover)  # no machine layer: the default
        self.machine('[orch.supervisor]\nrecover = "stop-only"\nmax_recoveries = 3\n')
        self.assertEqual("stop-only", self.policy("resume").recover)
        self.assertEqual("notify", self.policy("notify").recover)
        self.assertEqual(3, self.policy().max_recoveries)
        self.assertEqual(1, self.policy(max_recoveries=1).max_recoveries)
        self.assertEqual(3, self.policy(max_recoveries=9).max_recoveries)

    def test_an_invocation_config_file_can_only_lower_the_machine_policy(self):
        self.machine('[orch.supervisor]\nrecover = "resume"\nmax_recoveries = 3\n')
        invocation = self.project.parent / "invocation.toml"
        invocation.write_text('schema_version = 1\n[orch.supervisor]\nrecover = "stop-only"\nmax_recoveries = 9\n', encoding="utf-8")
        found = settings.load(project=self.project, config_file=invocation).supervisor
        self.assertEqual(("stop-only", 3), (found["recover"], found["max_recoveries"]))
        invocation.write_text('schema_version = 1\n[orch.supervisor]\nrecover = "resume"\n', encoding="utf-8")
        self.machine('[orch.supervisor]\nrecover = "notify"\n')
        self.assertEqual("notify", settings.load(project=self.project, config_file=invocation).supervisor["recover"])

    def test_a_project_file_cannot_set_the_authority_keys(self):
        (self.project / ".swissknifeman").mkdir()
        for line in ('recover = "resume"', "max_recoveries = 9", "window_s = 10"):
            with self.subTest(line=line):
                (self.project / ".swissknifeman" / "config.toml").write_text(
                    f"schema_version = 1\n[orch.supervisor]\n{line}\n", encoding="utf-8")
                with self.assertRaises(ConfigError) as caught:
                    settings.load(project=self.project)
                self.assertEqual("CONFIG_LAYER_FORBIDDEN", caught.exception.code)
        (self.project / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[orch.supervisor]\nhung_after_s = 120\ninterval_s = 30\n", encoding="utf-8")
        found = settings.load(project=self.project).supervisor
        self.assertEqual((120, 30, "notify"), (found["hung_after_s"], found["interval_s"], found["recover"]))


class ClassTableTests(SupervisorCase):
    """What each class of health leads to, at each level of the policy."""

    def run_class(self, state: dict, recover: str, forced=None):
        directory = self.make_run()
        with mock.patch.object(supervisor, "stop_conductor") as stop, mock.patch.object(supervisor, "reap") as reap, \
                mock.patch.object(supervisor, "snapshot") as shot, self.forced(*forced or [state]):
            actions = self.once(self.policy(recover))
        return directory, actions, stop, reap, shot

    def reset(self) -> None:
        """Forget the run and what the supervisor remembers of it (the next level of a loop starts clean)."""
        shutil.rmtree(runs_root(self.project) / "cnd-one", ignore_errors=True)
        (runs_root(self.project) / supervisor.STATE_DOC).unlink(missing_ok=True)

    def levelled(self, recover: str) -> None:
        self.machine(f'[orch.supervisor]\nrecover = "{recover}"\n')

    def test_a_healthy_or_waiting_run_gets_no_action_at_any_level(self):
        for recover in ("notify", "stop-only", "resume"):
            self.levelled(recover)
            for name, code in (("running", None), ("waiting_provider", "PROVIDER_WAIT"), ("waiting_tool", "WORK_SOURCE_CALL"),
                               ("waiting_budget_reset", "PROVIDER_QUOTA"), ("stopped", "PROVIDER_QUOTA"), ("finished", None),
                               ("unknown", "LEASE_UNKNOWN")):
                with self.subTest(recover=recover, health=name):
                    _, actions, stop, reap, shot = self.run_class(health(name, code), recover)
                    self.assertEqual([], actions)
                    for mocked in (stop, reap, shot):
                        mocked.assert_not_called()
                    self.spawn.assert_not_called()
                    self.reset()

    def test_a_suspected_stall_is_only_said_and_never_signalled(self):
        for recover in ("notify", "stop-only", "resume"):
            self.levelled(recover)
            directory, actions, stop, reap, shot = self.run_class(
                health("suspected_stall", "STALL_SUSPECTED", "no tool step for 2100 s"), recover)
            self.assertEqual(["notify"], self.names(actions), recover)
            self.assertEqual("STALL_SUSPECTED", actions[0]["reason_code"])
            for mocked in (stop, reap, shot):
                mocked.assert_not_called()
            self.spawn.assert_not_called()
            self.reset()

    def test_the_same_trouble_is_said_once_until_the_class_changes(self):
        directory = self.make_run()
        policy = self.policy()
        with self.forced(health("suspected_stall", "STALL_SUSPECTED")):
            self.assertEqual(["notify"], self.names(self.once(policy)))
            self.assertEqual([], self.once(policy))
        with self.forced(health("running")):
            self.assertEqual([], self.once(policy))
        with self.forced(health("suspected_stall", "STALL_SUSPECTED")):
            self.assertEqual(["notify"], self.names(self.once(policy)), "a new episode is said again")
        self.assertEqual(2, len(self.lines(directory)))

    def test_a_question_that_waits_past_its_warning_is_said(self):
        self.make_run()
        with self.forced(health("waiting_owner", "WAITING_DECISION")):
            with mock.patch.object(supervisor.questions, "listing", return_value=[]):
                self.assertEqual([], self.once(self.policy()))
            overdue = [{"item": "W1", "id": "q1", "overdue": True, "age_s": 4000}]
            with mock.patch.object(supervisor.questions, "listing", return_value=overdue):
                found = self.once(self.policy("resume"))
        self.assertEqual(["notify"], self.names(found))
        self.assertIn("W1:q1", found[0]["detail"])
        self.assertEqual("waiting_owner", found[0]["health"])

    def test_a_hung_conductor_at_notify_is_only_said(self):
        self.levelled("notify")
        _, actions, stop, reap, shot = self.run_class(health("hung", "HEARTBEAT_STALE", "the heartbeat is 400 s old"), "resume")
        self.assertEqual(["notify"], self.names(actions))
        self.assertIn("not stopped", actions[0]["detail"])
        for mocked in (stop, reap, shot):
            mocked.assert_not_called()

    def hung_pass(self, recover: str, stopped: dict, after: str = "orphaned"):
        self.levelled(recover)
        directory = self.make_run()
        taken = []

        def snap(run_dir, h=None, now=None):
            taken.append(run_dir)
            return run_dir / "supervisor" / "snapshot-x.json"

        def stop(run_dir, policy, *, before_signal=None):
            if stopped["outcome"] in ("stopped", "failed") and before_signal:
                before_signal()
            return stopped

        with mock.patch.object(supervisor, "stop_conductor", side_effect=stop), \
                mock.patch.object(supervisor, "snapshot", side_effect=snap), \
                mock.patch.object(supervisor, "reap", return_value={"killed": 1, "closed": 1}) as reap, \
                self.forced(health("hung", "HEARTBEAT_STALE", "the heartbeat is 400 s old"), health(after, "RUN_ORPHANED")):
            actions = self.once(self.policy(recover))
        return directory, actions, taken, reap

    def test_a_hung_conductor_is_snapshotted_and_stopped_at_stop_only_and_not_resumed(self):
        stopped = {"outcome": "stopped", "pid": 4242, "signal": "SIGKILL", "detail": "conductor pid 4242 freed the lease after SIGKILL"}
        directory, actions, taken, reap = self.hung_pass("stop-only", stopped)
        self.assertEqual(["snapshot", "stop", "reap"], self.names(actions))
        self.assertEqual((4242, "SIGKILL"), (actions[1]["pid"], actions[1]["signal"]))
        self.assertEqual([directory], taken)
        reap.assert_called_once()
        self.spawn.assert_not_called()

    def test_a_hung_conductor_is_resumed_after_stop_and_reap_at_resume(self):
        stopped = {"outcome": "stopped", "pid": 4242, "signal": "SIGTERM", "detail": "freed after SIGTERM"}
        directory, actions, _, _ = self.hung_pass("resume", stopped)
        self.assertEqual(["snapshot", "stop", "reap", "resume"], self.names(actions))
        self.spawn.assert_called_once()
        self.assertEqual(["SUPERVISOR_STOPPED", "SUPERVISOR_REAPED", "SUPERVISOR_RESUMED"], self.info(directory))

    def test_a_conductor_that_stopped_cooperatively_ends_the_pass_for_that_run(self):
        stopped = {"outcome": "stopped", "pid": 4242, "signal": "SIGINT", "detail": "freed after SIGINT"}
        _, actions, _, reap = self.hung_pass("resume", stopped, after="stopped")
        self.assertEqual(["snapshot", "stop"], self.names(actions))
        reap.assert_not_called()
        self.spawn.assert_not_called()

    def test_a_conductor_that_died_on_the_way_is_reaped_without_a_stop(self):
        free = {"outcome": "free", "detail": "nobody holds the lease"}
        _, actions, taken, reap = self.hung_pass("resume", free)
        self.assertEqual(["reap", "resume"], self.names(actions))
        self.assertEqual([], taken)
        reap.assert_called_once()

    def test_a_refused_identity_sends_nothing_and_writes_no_snapshot(self):
        mismatch = {"outcome": "identity_mismatch", "pid": 4242, "detail": "no signal sent: pid 4242 is another process now"}
        directory, actions, taken, reap = self.hung_pass("resume", mismatch)
        self.assertEqual(["identity_mismatch"], self.names(actions))
        self.assertEqual([], taken)
        reap.assert_not_called()
        self.spawn.assert_not_called()
        self.assertEqual(["SUPERVISOR_NOTIFIED"], self.info(directory))

    def test_a_conductor_that_cannot_be_stopped_is_said(self):
        failed = {"outcome": "failed", "pid": 4242, "detail": "the lease is still held 1 s after SIGKILL to pid 4242"}
        _, actions, _, reap = self.hung_pass("resume", failed)
        self.assertEqual(["snapshot", "notify"], self.names(actions))
        reap.assert_not_called()

    def test_an_orphaned_run_at_each_level(self):
        for recover, expected in (("notify", ["notify"]), ("stop-only", ["reap"]), ("resume", ["reap", "resume"])):
            self.levelled(recover)
            self.make_run()  # the lease flag is set and nobody holds it: orphaned for real
            with mock.patch.object(supervisor, "reap", return_value={"killed": 1, "closed": 1}) as reap:
                actions = self.once(self.policy(recover))
            self.assertEqual(expected, self.names(actions), recover)
            self.assertEqual(0 if recover == "notify" else 1, reap.call_count)
            self.assertEqual(1 if recover == "resume" else 0, self.spawn.call_count)
            self.spawn.reset_mock()
            self.reset()

    def test_a_run_held_by_a_live_owner_is_busy_and_nothing_is_touched(self):
        self.levelled("resume")
        directory = self.make_run()
        with mock.patch.object(supervisor, "reap", side_effect=Stop("RUN_BUSY", "run cnd-one is held by pid 7")):
            actions = self.once(self.policy())
        self.assertEqual(["busy"], self.names(actions))
        self.assertEqual([], self.info(directory), "busy leaves the journal alone")
        self.spawn.assert_not_called()

    def test_no_auto_resume_for_a_stop_that_needs_the_owner(self):
        self.levelled("resume")
        for code in sorted(supervisor.NO_AUTO_RESUME):
            for where in ("stop", "last_stop"):
                with self.subTest(code=code, where=where):
                    self.make_run(state={"status": "running", "items": {"W1": {"steps": {}}},
                                                     where: {"code": code, "message": "m"}})
                    with mock.patch.object(supervisor, "reap", return_value={"killed": 0, "closed": 0}):
                        actions = self.once(self.policy())
                    self.assertEqual(["reap", "notify"], self.names(actions))
                    self.assertIn(code, actions[1]["detail"])
                    self.spawn.assert_not_called()
                    self.reset()
        self.assertEqual({"STAGE_RECOVERY_UNKNOWN", "TOKEN_BUDGET", "STATE_CORRUPT", "OPTIONS_INVALID", "OPTIONS_UNTRUSTED",
                          "SANDBOX_UNAVAILABLE", "PROVIDER_AUTH", "PROVIDER_AUTHZ"}, set(supervisor.NO_AUTO_RESUME))

    def test_another_stop_code_is_resumed(self):
        self.levelled("resume")
        self.make_run(state={"status": "running", "items": {"W1": {"steps": {}}}, "last_stop": {"code": "ROLE_FAILED", "message": "m"}})
        with mock.patch.object(supervisor, "reap", return_value={"killed": 0, "closed": 0}):
            self.assertEqual(["reap", "resume"], self.names(self.once(self.policy())))

    def test_a_run_that_cannot_be_read_is_said_and_the_others_still_get_a_look(self):
        self.levelled("resume")
        broken = self.make_run("cnd-a-broken")
        (broken / "state.json").write_text("{not json", encoding="utf-8")
        other = self.make_run("cnd-b-fine")
        with mock.patch.object(supervisor, "reap", return_value={"killed": 0, "closed": 0}):
            actions = self.once(self.policy())
        self.assertEqual({"cnd-a-broken": ["notify"], "cnd-b-fine": ["reap", "resume"]},
                         {run: [a["action"] for a in actions if a["run_id"] == run] for run in ("cnd-a-broken", "cnd-b-fine")})
        self.assertIn("STATE_CORRUPT", actions[0]["detail"])
        self.assertTrue(other.is_dir())


class BreakerTests(SupervisorCase):
    def setUp(self):
        super().setUp()
        self.machine('[orch.supervisor]\nrecover = "resume"\nmax_recoveries = 2\nwindow_s = 3600\n')
        self.directory = self.make_run()
        self.reap = mock.patch.object(supervisor, "reap", return_value={"killed": 0, "closed": 0})
        self.reap.start()
        self.addCleanup(self.reap.stop)

    def memory(self) -> dict:
        return records.read(runs_root(self.project) / supervisor.STATE_DOC, "supervisor-state")["runs"][self.directory.name]

    def test_the_third_recovery_within_the_window_is_given_up(self):
        policy = self.policy()
        self.assertEqual(["reap", "resume"], self.names(self.once(policy, now=NOW)))
        self.assertEqual(["reap", "resume"], self.names(self.once(policy, now=NOW + 600)))
        found = self.once(policy, now=NOW + 1200)
        self.assertEqual(["reap", "given_up"], self.names(found))
        self.assertEqual(2, self.spawn.call_count)
        self.assertIn("orch conduct resume --run cnd-one", found[1]["detail"])
        self.assertEqual("SUPERVISOR_GAVE_UP", self.info(self.directory)[-1])
        self.assertTrue(self.memory()["given_up"])
        self.assertEqual([], self.once(policy, now=NOW + 1800), "a run given up is left alone")
        self.assertEqual(2, self.spawn.call_count)

    def test_recoveries_outside_the_window_do_not_count(self):
        policy = self.policy()
        self.once(policy, now=NOW)
        self.once(policy, now=NOW + 100)
        self.assertEqual(["reap", "resume"], self.names(self.once(policy, now=NOW + 3650)),
                         "the first recovery left the window; one is within it")
        self.assertEqual(2, len(self.memory()["recoveries"]))
        self.assertEqual(3, self.spawn.call_count)

    def test_no_recoveries_allowed_gives_up_at_once(self):
        found = self.once(self.policy(max_recoveries=0))
        self.assertEqual(["reap", "given_up"], self.names(found))
        self.spawn.assert_not_called()

    def test_a_resume_by_hand_closes_the_breaker(self):
        policy = self.policy(max_recoveries=1)
        self.once(policy, now=NOW)
        self.assertEqual(["reap", "given_up"], self.names(self.once(policy, now=NOW + 10)))
        self.assertEqual([], self.once(policy, now=NOW + 20))
        progress.Progress("cnd-one", self.directory, "quiet").emit("run.resume", message="resume 1")  # the owner, not the supervisor
        found = self.once(policy, now=NOW + 30)
        self.assertEqual(["reap", "resume"], self.names(found), "the breaker is closed: the run is a candidate again")
        self.assertIsNone(self.memory()["given_up"])

    def test_the_memory_is_a_valid_record_and_a_damaged_one_stops_the_pass(self):
        self.once(self.policy())
        path = runs_root(self.project) / supervisor.STATE_DOC
        self.assertEqual([], records.problems(json.loads(path.read_text(encoding="utf-8")), "supervisor-state"))
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            self.once(self.policy())
        self.assertEqual("STATE_CORRUPT", caught.exception.code)
        self.spawn.assert_called_once()  # the damaged memory started nothing


class RecordTests(SupervisorCase):
    def test_every_action_is_a_line_a_journal_info_and_an_event(self):
        self.machine('[orch.supervisor]\nrecover = "resume"\n')
        directory = self.make_run()
        os.environ["MY_API_TOKEN"] = SECRET
        self.addCleanup(os.environ.pop, "MY_API_TOKEN", None)
        with mock.patch.object(supervisor, "reap", return_value={"killed": 2, "closed": 1}):
            actions = self.once(self.policy(), now=NOW)
        self.assertEqual(["reap", "resume"], self.names(actions))
        lines = self.lines(directory)
        self.assertEqual(actions, lines)
        for line in lines:
            self.assertEqual([], records.problems(line, "supervisor-action"))
            self.assertEqual(("cnd-one", "orphaned", "RUN_ORPHANED"), (line["run_id"], line["health"], line["reason_code"]))
        self.assertEqual("stopped 2 orphaned role group(s), closed 1 agent record(s)", lines[0]["detail"])
        self.assertEqual(["SUPERVISOR_REAPED", "SUPERVISOR_RESUMED"], self.info(directory))
        sent = [event for event in journal.read_events(self.project)[0] if event.type == "orch.conductor.health"]
        self.assertEqual(["reap", "resume"], [event.data["action"] for event in sent])
        self.assertEqual({"conductor_run_id": "cnd-one", "health": "orphaned", "action": "reap", "reason_code": "RUN_ORPHANED"},
                         {key: sent[0].data[key] for key in ("conductor_run_id", "health", "action", "reason_code")})
        self.assertEqual("orphaned", sent[1].data["previous"])
        self.assertEqual("cnd-one", sent[0].correlationid)

    def test_events_can_be_switched_off(self):
        self.machine('[orch.events]\nenabled = false\n[orch.supervisor]\nrecover = "stop-only"\n')
        self.make_run()
        with mock.patch.object(supervisor, "reap", return_value={"killed": 0, "closed": 0}):
            self.assertEqual(["reap"], self.names(self.once(self.policy())))
        self.assertEqual([], [e for e in journal.read_events(self.project)[0] if e.type == "orch.conductor.health"])

    def test_a_record_that_breaks_its_contract_is_refused(self):
        directory = self.make_run()
        with self.assertRaises(Stop) as caught:
            supervisor._record(self.project, directory, self.policy(), health="hung", reason_code=None, action="kill",
                               detail="x", previous=None, at="2026-11-01T10:20:00Z")
        self.assertEqual("RECORD_INVALID", caught.exception.code)
        self.assertFalse((directory / "supervisor.jsonl").exists())

    def test_the_lines_survive_a_torn_tail(self):
        directory = self.make_run()
        (directory / "supervisor.jsonl").write_text('{"torn": ', encoding="utf-8")
        supervisor._record(self.project, directory, self.policy(), health="orphaned", reason_code="RUN_ORPHANED", action="notify",
                           detail="x", previous=None, at="2026-11-01T10:20:00Z")
        rows = (directory / "supervisor.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(rows))
        self.assertEqual("notify", json.loads(rows[1])["action"])

    def test_notify_send_is_called_for_a_notification_and_its_failure_is_ignored(self):
        directory = self.make_run()
        with mock.patch.object(supervisor.shutil, "which", return_value="/usr/bin/notify-send"), \
                mock.patch.object(supervisor.subprocess, "run", side_effect=OSError("no display")) as run:
            self.assertEqual(["notify"], self.names(self.once(self.policy(notify_send=True))))
        self.assertEqual(["/usr/bin/notify-send", "SKM run cnd-one: orphaned"], run.call_args.args[0][:2])
        self.assertTrue(directory.is_dir())


class SnapshotTests(SupervisorCase):
    def test_the_snapshot_holds_the_evidence_and_is_redacted(self):
        directory = self.make_run()
        os.environ["MY_API_TOKEN"] = SECRET
        self.addCleanup(os.environ.pop, "MY_API_TOKEN", None)
        progress.Progress("cnd-one", directory, "quiet").emit("info", reason_code="SOMETHING", message=f"token {SECRET} seen")
        write_json(directory / "W1" / "agents" / "a" / "process.json", {"pid": os.getpid(), "pgid": os.getpgrp(), "start_ticks": 1})
        path = supervisor.snapshot(directory, now=NOW)
        self.assertEqual(directory / "supervisor" / "snapshot-20261101T102000Z.json", path)
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        doc = records.read(path, "supervisor-snapshot")
        self.assertEqual(("cnd-one", "orphaned"), (doc["run_id"], doc["health"]["health"]))
        self.assertEqual("orphaned", doc["status"]["status"])
        self.assertEqual(["run.start", "info"], [line["event"] for line in doc["progress_tail"]])
        self.assertNotIn(SECRET, path.read_text(encoding="utf-8"))
        self.assertIn(os.getpid(), [row["pid"] for row in doc["processes"]], "the processes of the role groups are listed")
        self.assertTrue(all(len(row["args"]) <= 200 for row in doc["processes"]))
        again = supervisor.snapshot(directory, now=NOW)
        self.assertNotEqual(path, again, "two snapshots in one second keep both")

    def test_the_snapshot_keeps_the_last_fifty_lines_only(self):
        directory = self.make_run()
        log = progress.Progress("cnd-one", directory, "quiet")
        for number in range(70):
            log.emit("info", reason_code="TICK", message=f"line {number}")
        doc = records.read(supervisor.snapshot(directory, now=NOW), "supervisor-snapshot")
        self.assertEqual(50, len(doc["progress_tail"]))
        self.assertEqual("line 69", doc["progress_tail"][-1]["message"])


class StopConductorTests(SupervisorCase):
    """The signals and the identity check, with the processes faked (the real ones are in test_supervisor_faults)."""

    def owner(self, **over) -> dict:
        return {"pid": 4242, "host": socket.gethostname(), "start_ticks": 777, "boot_id": "boot-a", **over}

    def test_every_missing_or_wrong_part_of_the_identity_is_a_reason_not_to_signal(self):
        with mock.patch.object(process, "boot_id", return_value="boot-a"), mock.patch.object(process, "start_ticks", return_value=777):
            self.assertIsNone(supervisor.identity_problem(self.owner()))
            for over, word in (({"pid": os.getpid()}, "supervisor itself"), ({"pid": 1}, "no usable pid"),
                               ({"pid": None}, "no usable pid"), ({"start_ticks": None}, "start_ticks"),
                               ({"boot_id": None}, "boot_id"), ({"boot_id": "boot-b"}, "another boot"),
                               ({"start_ticks": 778}, "another process"), ({"host": "elsewhere"}, "host elsewhere")):
                with self.subTest(over=over):
                    self.assertIn(word, supervisor.identity_problem(self.owner(**over)))
        with mock.patch.object(process, "boot_id", return_value="boot-a"), mock.patch.object(process, "start_ticks", return_value=None):
            self.assertIn("does not exist", supervisor.identity_problem(self.owner()))

    def ladder(self, frees_after: int, identity=None):
        """Run ``stop_conductor`` with a conductor that frees its lease after the ``frees_after``-th signal (0: never)."""
        directory = self.make_run()
        sent = []
        state = {"held": True, "signals": 0}

        def kill(pid, number):
            sent.append((pid, signal.Signals(number).name))
            state["signals"] += 1
            if state["signals"] == frees_after:
                state["held"] = False

        with mock.patch.object(supervisor.RunLease, "held", side_effect=lambda d: state["held"]), \
                mock.patch.object(supervisor.RunLease, "owner", return_value=self.owner()), \
                mock.patch.object(supervisor, "identity_problem", side_effect=identity or (lambda owner: None)), \
                mock.patch.object(supervisor, "_wait_free", side_effect=lambda d, s: not state["held"]), \
                mock.patch.object(supervisor.os, "kill", side_effect=kill), \
                mock.patch.object(supervisor.os, "killpg", side_effect=AssertionError("killpg of a conductor")):
            return supervisor.stop_conductor(directory, self.policy(), before_signal=lambda: sent.append(("snapshot", None))), sent

    def test_sigint_then_sigterm_then_sigkill_each_only_when_the_lease_is_still_held(self):
        result, sent = self.ladder(frees_after=1)
        self.assertEqual([("snapshot", None), (4242, "SIGINT")], sent)
        self.assertEqual(("stopped", "SIGINT"), (result["outcome"], result["signal"]))
        result, sent = self.ladder(frees_after=2)
        self.assertEqual([(4242, "SIGINT"), (4242, "SIGTERM")], sent[1:])
        result, sent = self.ladder(frees_after=3)
        self.assertEqual(["SIGINT", "SIGTERM", "SIGKILL"], [name for _, name in sent[1:]])
        self.assertEqual("SIGKILL", result["signal"])

    def test_a_lease_that_never_frees_is_a_failure_after_sigkill(self):
        result, sent = self.ladder(frees_after=0)
        self.assertEqual("failed", result["outcome"])
        self.assertEqual("SIGKILL", sent[-1][1])
        self.assertIn("still held", result["detail"])

    def test_the_snapshot_comes_before_the_first_signal_and_a_refusal_before_the_snapshot(self):
        _, sent = self.ladder(frees_after=1)
        self.assertEqual("snapshot", sent[0][0])
        result, sent = self.ladder(frees_after=1, identity=lambda owner: "pid 4242 is another process now")
        self.assertEqual([], sent)
        self.assertEqual("identity_mismatch", result["outcome"])

    def test_an_identity_that_changes_between_signals_stops_the_ladder(self):
        calls = iter([None, None, "pid 4242 is another process now"])
        result, sent = self.ladder(frees_after=0, identity=lambda owner: next(calls, "gone"))
        self.assertEqual([(4242, "SIGINT")], sent[1:])
        self.assertEqual("identity_mismatch", result["outcome"])

    def test_a_free_lease_needs_no_signal(self):
        directory = self.make_run()
        with mock.patch.object(supervisor.os, "kill", side_effect=AssertionError("no signal")):
            self.assertEqual("free", supervisor.stop_conductor(directory, self.policy())["outcome"])

    def test_the_module_never_signals_a_group_of_a_conductor(self):
        source = Path(supervisor.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"os\.killpg\(")


class ReapTests(SupervisorCase):
    def test_reap_closes_the_agent_of_a_dead_role_and_changes_nothing_else(self):
        directory = self.make_run()
        agent = self.orphan(directory)
        before = {name: (directory / name).read_bytes() for name in ("state.json", "run.json")}
        done = supervisor.reap(self.project, "cnd-one")
        self.assertEqual({"killed": 0, "closed": 1}, done)
        self.assertEqual("ORPHANED", json.loads((agent / "result.json").read_text(encoding="utf-8"))["error"]["code"])
        self.assertEqual(before, {name: (directory / name).read_bytes() for name in before})
        self.assertFalse((directory / "heartbeat.json").exists(), "reap is not a conductor and writes no heartbeat")
        self.assertEqual({"killed": 0, "closed": 0}, supervisor.reap(self.project, "cnd-one"), "a second reap finds nothing")
        failed = [e for e in journal.read_events(self.project)[0] if e.type == "orch.agent.failed"]
        self.assertEqual(1, len(failed))
        self.assertFalse((directory / "lease.json").exists(), "the lease is released")

    def test_reap_of_a_live_owner_is_run_busy_and_touches_nothing(self):
        directory = self.make_run()
        agent = self.orphan(directory)
        with RunLease(directory).acquire("run"):
            with self.assertRaises(Stop) as caught:
                supervisor.reap(self.project, "cnd-one")
        self.assertEqual("RUN_BUSY", caught.exception.code)
        self.assertFalse((agent / "result.json").exists())

    def test_reap_waits_for_no_one_when_the_checkout_is_driven_by_another_run(self):
        directory = self.make_run()
        agent = self.orphan(directory)
        with CheckoutLock(runs_root(self.project), checkout_toplevel(self.project)).acquire("run", "cnd-other"):
            with self.assertRaises(Stop) as caught:
                supervisor.reap(self.project, "cnd-one")
        self.assertEqual("WORKTREE_BUSY", caught.exception.code)
        self.assertFalse((agent / "result.json").exists())

    def test_a_run_the_journal_does_not_call_running_has_nothing_to_reap(self):
        directory = self.make_run()
        agent = self.orphan(directory)
        progress.Progress("cnd-one", directory, "quiet").emit("run.end", outcome="stopped", reason_code="ROLE_FAILED")
        done = supervisor.reap(self.project, "cnd-one")
        self.assertEqual(0, done["closed"])
        self.assertIn("skipped", done)
        self.assertFalse((agent / "result.json").exists())

    def test_reap_does_not_signal_its_own_group_or_a_reused_pid(self):
        directory = self.make_run()
        agent = self.orphan(directory, pid=os.getpid())
        write_json(agent / "process.json", {"pid": os.getpid(), "pgid": os.getpid(), "start_ticks": 1})  # the pid is ours now
        with mock.patch("orch.conductor.application.recovery.os.killpg", side_effect=AssertionError("killpg")):
            done = supervisor.reap(self.project, "cnd-one")
        self.assertEqual({"killed": 0, "closed": 1}, done)


class CommandTests(SupervisorCase):
    def test_once_json_prints_a_supervise_result(self):
        self.machine('[orch.supervisor]\nrecover = "stop-only"\n')
        self.make_run()
        with mock.patch.object(supervisor, "reap", return_value={"killed": 0, "closed": 0}):
            code, out, err = self.conduct("supervise", "--once", "--json")
        self.assertEqual((0, ""), (code, err))
        doc = json.loads(out)
        self.assertEqual([], contract.problems(doc, "supervise-result"))
        self.assertEqual((False, "stop-only", ["reap"]), (doc["busy"], doc["recover"], [a["action"] for a in doc["actions"]]))

    def test_the_flag_is_cut_to_the_policy_of_the_machine(self):
        self.make_run()
        code, out, _ = self.conduct("supervise", "--once", "--json", "--recover", "resume")
        doc = json.loads(out)
        self.assertEqual((0, "notify", ["notify"]), (code, doc["recover"], [a["action"] for a in doc["actions"]]))

    def test_text_output_and_a_pass_without_action(self):
        code, out, _ = self.conduct("supervise", "--once")
        self.assertEqual((0, "no action (recover notify)\n"), (code, out))
        self.make_run()
        code, out, _ = self.conduct("supervise", "--once")
        self.assertIn("cnd-one: notify (orphaned)", out)

    def test_a_second_supervisor_is_busy_with_exit_zero(self):
        self.make_run()
        lock = FileLock(runs_root(self.project) / supervisor.LOCK_FILE)
        runs_root(self.project).mkdir(parents=True, exist_ok=True)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        code, out, _ = self.conduct("supervise", "--once", "--json")
        doc = json.loads(out)
        self.assertEqual((0, True, []), (code, doc["busy"], doc["actions"]))
        self.assertEqual([], contract.problems(doc, "supervise-result"))
        code, out, _ = self.conduct("supervise", "--once")
        self.assertEqual((0, "busy: another supervisor holds this project\n"), (code, out))
        self.assertFalse(list((runs_root(self.project) / "cnd-one").glob("supervisor*")))

    def test_the_loop_runs_a_pass_per_interval_and_stops_on_request(self):
        self.make_run()
        passes, waits = [], []
        stop = {"now": False}
        supervisor.supervise(self.project, self.policy(), stop=lambda: stop["now"] or len(passes) >= 2,
                             wait=lambda seconds: waits.append(seconds), report=passes.append)
        self.assertEqual(2, len(passes))
        self.assertEqual([60, 60], waits)
        self.assertEqual(["notify"], self.names(passes[0]))
        self.assertEqual([], passes[1])
        lock = FileLock(runs_root(self.project) / supervisor.LOCK_FILE)
        self.assertTrue(lock.acquire(), "the lock is released when the loop ends")
        lock.release()

    def test_an_unknown_run_and_wrong_numbers_are_refused(self):
        code, _, err = self.conduct("supervise", "--once", "--run", "cnd-nope")
        self.assertEqual(1, code)
        self.assertIn("RUN_UNKNOWN", err)
        for flags in (["--interval", "0"], ["--max-recoveries", "-1"]):
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()):
                self.conduct("supervise", "--once", *flags)
            self.assertEqual(2, caught.exception.code)

    def test_reap_prints_the_result_and_records_it(self):
        directory = self.make_run()
        self.orphan(directory)
        code, out, err = self.conduct("reap", "--run", "cnd-one")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("closed 1 agent record(s)", out)
        self.assertEqual(["reap"], [line["action"] for line in self.lines(directory)])
        self.assertEqual(["SUPERVISOR_REAPED"], self.info(directory))

    def test_reap_of_a_held_run_exits_one_with_run_busy(self):
        directory = self.make_run()
        with RunLease(directory).acquire("run"):
            code, out, err = self.conduct("reap", "--run", "cnd-one")
        self.assertEqual((1, ""), (code, out))
        self.assertTrue(err.startswith("RUN_BUSY:"), err)
        self.assertFalse((directory / "supervisor.jsonl").exists())
        code, _, err = self.conduct("reap", "--run", "cnd-nope")
        self.assertEqual(1, code)
        self.assertIn("RUN_UNKNOWN", err)

    def test_resume_detached_starts_the_documented_command_in_its_own_session(self):
        self.make_run()
        child = mock.Mock(pid=4321)
        with mock.patch.object(supervisor.subprocess, "Popen", return_value=child) as popen:
            started = supervisor.resume_detached(self.project, "cnd-one", config_file=Path("/x/c.toml"))
        argv = popen.call_args.args[0]
        self.assertEqual(["conduct", "resume", "--run", "cnd-one", "--quiet"], argv[-5:])
        self.assertEqual(str(supervisor.ORCH_SCRIPT), argv[1])
        self.assertEqual(["--config", "/x/c.toml", "--project", str(self.project)], argv[2:6])
        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["start_new_session"], True)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual("supervisor", kwargs["env"]["SKM_ORCH_LAUNCHER"])
        self.assertEqual(4321, started["pid"])
        self.assertTrue(started["log"].endswith("supervisor/resume-1.log"))


if __name__ == "__main__":
    unittest.main()
