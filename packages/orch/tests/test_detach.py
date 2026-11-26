"""Detached startup: ownership acknowledgements, process sessions, events, units and log pruning (P8.3)."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import MethodType, SimpleNamespace
import unittest
from unittest import mock

from aicore.ext import events as journal
from aicore.util.lock import probe_free
from orch import events, settings
from orch.conductor import checks, contract, engine, progress, records, runs, supervise_cli
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import beacon_events, detach, roles
from orch.conductor.infrastructure.files import RunStore, runs_root
from orch.conductor.infrastructure.lease import CheckoutLock, RunLease, checkout_toplevel
from orch.conductor.stages import checks_stage, step
from tests.test_conductor import ConductorCase, report
from tests.test_supervisor_faults import FaultCase, alive, eventually

ID = "cnd-20261024T100000Z-abcdef"
NONCE = "1234567890abcdef"
LAUNCH = "fedcba9876543210"
INTERNAL_ENV = ("SKM_ORCH_DETACHED", "SKM_ORCH_LAUNCHER", "SKM_ORCH_DETACH_ACK", "SKM_ORCH_DETACH_NONCE",
                "SKM_ORCH_AUTOPILOT_STATE", "SKM_ORCH_AUTOPILOT_LAUNCH_ID", "SKM_ORCH_FENCE_GATE")


def ack(**over):
    return {"nonce": NONCE, "run_id": ID, "pid": 123, "start_ticks": 456, "status": "started",
            "at": "2026-10-24T10:00:00Z", **over}


class HandshakeTests(ConductorCase):
    def setUp(self):
        super().setUp()
        for name in INTERNAL_ENV:  # the caller is external unless a test explicitly simulates an internal launch
            os.environ.pop(name, None)

    def test_checks_and_roles_drop_internal_launch_environment_but_owner_keeps_launcher(self):
        self.scenario = "scout-solo"
        for number, launcher in enumerate(("terminal", "detached", "gui", "supervisor"), 1):
            with self.subTest(launcher=launcher), mock.patch.dict(os.environ, {
                    "SKM_ORCH_DETACHED": "1", "SKM_ORCH_LAUNCHER": launcher}):
                ref = f"W{number}"
                self.set_items({ref: {}})
                self.script({"executor": [{"write": {f"out/{ref}.txt": "ok\n"}, "result": report(ref)}]})
                loop = engine.Conductor._loop
                def owned_loop(owner, expected_launcher=launcher, run_loop=loop):
                    self.assertEqual(RunLease.owner(owner.directory)["launcher"], expected_launcher)
                    return run_loop(owner)
                with mock.patch.object(roles.process, "run_role", wraps=roles.process.run_role) as launched, \
                        mock.patch.object(engine.Conductor, "_loop", owned_loop):
                    code, _, err = self.run_items(ref)
                self.assertEqual(code, 0, err)
                self.assertTrue(launched.called)
                nested = [sys.executable, str(detach.CONDUCT), "run", "--plan", "T", "--items", "W1", "--run-id", ID]
                for call in launched.call_args_list:
                    self.assertFalse(set(INTERNAL_ENV) & call.kwargs["env"].keys())
                role_env = launched.call_args.kwargs["env"]
                rejected = subprocess.run(nested, cwd=self.project, env=role_env, capture_output=True, text=True, timeout=30)
                self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
                self.assertIn("--run-id is reserved", rejected.stderr)
                # Exercise the actual check subprocess boundary as well as the final environment after run overlays.
                self.assertFalse(set(INTERNAL_ENV) & checks.check_env(self.project, run_env={
                    name: "must not be inherited" for name in INTERNAL_ENV}).keys())
                log = self.project.parent / "nested-check.log"
                with log.open("wb") as output:
                    self.assertEqual(checks._run_command(nested, cwd=self.project, out=output,
                                                        timeout_s=30, warn_s=0), 2)
                self.assertIn("--run-id is reserved", log.read_text())
                self.assertEqual(os.environ["SKM_ORCH_LAUNCHER"], launcher)
                self.assertEqual(os.environ["SKM_ORCH_DETACHED"], "1")
                directory = self.run_dir(err)
                stored, problems = journal.read_events(self.project)
                self.assertFalse(problems)
                lifecycle = [event.data for event in stored if event.type == "orch.conductor.lifecycle"
                             and event.data["conductor_run_id"] == directory.name]
                self.assertEqual([event["phase"] for event in lifecycle], ["started", "ended"])
                self.assertEqual({event["launcher"] for event in lifecycle}, {launcher})

    def test_explicit_role_environment_is_copied_and_empty_environment_stays_empty(self):
        explicit = {**{name: "internal" for name in INTERNAL_ENV}, "PATH": "/role/bin", "ROLE_SETTING": "kept"}
        self.assertEqual(detach.subprocess_env(explicit), {"PATH": "/role/bin", "ROLE_SETTING": "kept"})
        self.assertEqual(detach.subprocess_env({}), {})
        self.assertTrue(set(INTERNAL_ENV) <= explicit.keys())

    def test_relative_file_arguments_keep_the_callers_meaning_after_cwd_changes(self):
        def started(argv, **kwargs):
            self.assertIn(str(Path("../config.toml").resolve()), argv)
            self.assertIn("--input=" + str(Path("../input.json").resolve()), argv)
            self.assertIn(str(Path("options.json").resolve()), argv)
            self.assertIsNone(kwargs.get("ack_nonce"), "an ordinary detach lets spawn generate the nonce")
            path = runs_root(self.project) / "detached" / f"{ID}.{NONCE}.ack.json"
            records.write(path, ack(), "detach-ack")
            return {"pid": 123, "log": "/tmp/detached.log", "ack": str(path), "nonce": NONCE}
        with mock.patch.object(detach, "spawn", side_effect=started), redirect_stdout(io.StringIO()):
            self.assertEqual(detach.launch(["--config", "../config.toml", "run", "--input=../input.json", "--options", "options.json", "--detach"],
                                           project=self.project, run_id=ID, launcher="detached", new_run=True), 0)

    def test_malformed_resume_id_is_refused_without_a_traceback(self):
        code, out, err = self.conduct("resume", "--run", "../x", "--detach")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("RUN_UNKNOWN:", err)

    def test_detached_launch_refuses_a_busy_checkout(self):
        with CheckoutLock(runs_root(self.project), checkout_toplevel(self.project)).acquire("test", ID):
            code, out, err = self.run_items("W1", extra=("--detach",))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("WORKTREE_BUSY:", err)

    def test_internal_id_and_incompatible_options_are_usage_errors(self):
        for flags in (("--run-id", ID), ("--detach", "--dry-run"), ("--detach", "--frozen")):
            with self.subTest(flags=flags), self.assertRaises(SystemExit) as stopped:
                self.run_items("W1", extra=flags)
            self.assertEqual(stopped.exception.code, 2)
        with mock.patch.dict(os.environ, {"SKM_ORCH_DETACHED": "1"}):
            for run_id in ("../x", "cnd-anything", ID + "\n"):
                with self.subTest(run_id=run_id), self.assertRaises(SystemExit) as stopped:
                    self.run_items("W1", extra=("--run-id", run_id))
                self.assertEqual(stopped.exception.code, 2)
            (runs_root(self.project) / ID).mkdir(parents=True)
            with self.assertRaises(SystemExit) as stopped:
                self.run_items("W1", extra=("--run-id", ID))
            self.assertEqual(stopped.exception.code, 2)

    def test_resume_detach_with_frozen_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as stopped:
            self.conduct("resume", "--run", ID, "--detach", "--frozen")
        self.assertEqual(stopped.exception.code, 2)

    def test_ack_schema_rejects_missing_nonce_and_unknown_status(self):
        doc = ack()
        for invalid in ({k: v for k, v in doc.items() if k != "nonce"}, dict(doc, status="ready")):
            self.assertTrue(records.problems(invalid, "detach-ack"))
        path = self.project / "ack.json"
        records.write(path, doc, "detach-ack")
        self.assertEqual(records.read(path, "detach-ack")["nonce"], NONCE)

    def test_parent_ignores_foreign_nonce_pid_and_run_then_accepts_matching_ack(self):
        path = self.project / "ack.json"
        child = {"pid": 123, "log": str(self.project / "detached.log")}
        foreign = [ack(nonce="0" * 16), ack(pid=999), ack(run_id="cnd-20261024T100001Z-abcdef"), ack()]
        with mock.patch.object(records, "read", side_effect=foreign), mock.patch.object(detach, "_exited", return_value=False), \
                mock.patch.object(detach.time, "sleep") as pause:
            self.assertEqual(detach.wait_ack(path, NONCE, ID, child)["pid"], 123)
        self.assertEqual(pause.call_count, 3)

    def test_existing_run_json_without_ack_times_out_without_signalling_the_child(self):
        root = runs_root(self.project)
        (root / ID).mkdir(parents=True)
        (root / ID / "run.json").write_text('{}')
        with mock.patch.object(detach, "_exited", return_value=False), \
                mock.patch.object(detach.time, "monotonic", side_effect=[0, 21]), mock.patch.object(os, "kill") as kill:
            with self.assertRaisesRegex(Stop, "no acknowledgement within 20 s") as stopped:
                detach.wait_ack(root / "absent.json", NONCE, ID, {"pid": 123, "log": "child.log"})
            self.assertEqual(stopped.exception.code, "DETACH_FAILED")
        kill.assert_not_called()

    def test_ack_written_between_exit_probe_and_read_is_accepted(self):
        path = self.project / "ack.json"
        def exited(_pid):
            records.write(path, ack(), "detach-ack")
            return True
        with mock.patch.object(detach, "_exited", side_effect=exited):
            self.assertEqual(detach.wait_ack(path, NONCE, ID, {"pid": 123})["status"], "started")

    def test_event_journal_failure_does_not_change_run_outcome_and_disabled_events_stay_off(self):
        with mock.patch.object(engine.Conductor, "_pieces"), mock.patch.object(journal, "emit", side_effect=OSError("journal unavailable")):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("ORCH_EVENT_NOT_EMITTED: orch.conductor.lifecycle", err)
        self.write_config(extra='[orch.events]\nenabled = false\n')
        with mock.patch.object(engine.Conductor, "_pieces"), mock.patch.object(events, "emit", wraps=events.emit) as emit:
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertTrue(emit.called)
        stored, problems = journal.read_events(self.project)
        self.assertFalse(problems)
        self.assertEqual(stored, [])

    def test_child_exiting_before_ack_reports_sanitized_tail_at_most_twenty_lines(self):
        original = detach.spawn

        def failing(argv, **kwargs):
            return original([sys.executable, "-c", "print('\\x1b[31mhidden\\x1b[0m\\n' * 30)", "--run-id", ID], **kwargs)

        err = io.StringIO()
        with mock.patch.object(detach, "spawn", side_effect=failing), redirect_stderr(err):
            code = detach.launch(["resume", "--run", ID], project=self.project, run_id=ID, launcher="detached", new_run=False)
        self.assertEqual(code, 1)
        self.assertIn("DETACH_FAILED: child exited before acknowledging; log", err.getvalue())
        self.assertIn("hidden", err.getvalue())
        self.assertNotIn("\x1b", err.getvalue())
        self.assertLessEqual(len(err.getvalue().splitlines()), 21)
        detach.poll_children()

    def test_internal_ack_sent_only_after_state_and_ownership_and_not_overwritten_afterwards(self):
        path = runs_root(self.project) / "detached" / f"{ID}.{NONCE}.ack.json"
        with mock.patch.dict(os.environ, {"SKM_ORCH_DETACHED": "1", "SKM_ORCH_DETACH_ACK": str(path),
                                          "SKM_ORCH_DETACH_NONCE": NONCE}):
            def initialized(owner):
                self.assertTrue(RunLease.held(owner.directory))
                self.assertEqual(records.read(owner.directory / "state.json", "state")["status"], "running")
                self.assertEqual(records.read(path, "detach-ack")["status"], "started")
                detach.refuse("CONDUCTOR_CRASHED", "a later failure cannot replace startup")
                return 0
            with mock.patch.object(engine.Conductor, "_loop", initialized):
                code, _, err = self.run_items("W1", extra=("--run-id", ID))
            self.assertEqual(code, 0, err)
            self.assertNotIn("SKM_ORCH_DETACH_ACK", os.environ)
        self.assertEqual(records.read(path, "detach-ack")["status"], "started")

    def test_lifecycle_outcomes_cover_waiting_interrupt_crash_and_normal_stop(self):
        outcomes = [(Stop("WAITING_DECISION", "owner decision"), 4, "waiting"),
                    (KeyboardInterrupt(), 130, "interrupted"), (RuntimeError("fault"), 1, "crashed"),
                    (Stop("DISK_LOW", "space"), 1, "stopped"), (None, 0, "finished")]
        for failure, expected, outcome in outcomes:
            with self.subTest(outcome=outcome), mock.patch.object(engine.Conductor, "_pieces", side_effect=failure), \
                    mock.patch.object(engine.Conductor, "_disk_guard"):
                code, _, err = self.run_items("W1")
            self.assertEqual(code, expected, err)
            run_id = self.run_dir(err).name
            stored, problems = journal.read_events(self.project)
            self.assertFalse(problems)
            end = [event for event in stored if event.type == "orch.conductor.lifecycle"
                   and event.data["conductor_run_id"] == run_id and event.data["phase"] == "ended"]
            self.assertEqual(len(end), 1)
            self.assertEqual(end[0].data["outcome"], outcome)

    def test_warning_events_match_each_role_check_and_disk_beacon_once(self):
        owner = SimpleNamespace(run_id=ID, settings=settings.load(project=self.project), project=self.project,
                                config_file=None, progress=mock.Mock(), _local=SimpleNamespace(), heartbeat=None,
                                role_ports=SimpleNamespace(run_clock=mock.Mock()), _run_clock=mock.Mock())
        owner._beacon_event = MethodType(beacon_events.beacon_event, owner)
        item = Item("W1", "work-1", {}, self.project, {}, options={"limits": {
            "stage_warn_s": 10, "stage_idle_warn_s": 5, "check_idle_warn_s": 5, "disk_min_gb": 5}})
        tick = roles.beacons(owner, item, "executor.1", "executor", self.project / "raw")
        with mock.patch.object(roles, "observe_tick", side_effect=[["repeated command"], []]), \
                mock.patch.object(roles.process, "activity", return_value="test process"):
            tick(10, 5, os.getpid(), None)
            tick(10, 5, os.getpid(), None)  # below the next threshold: no duplicate warning
        with mock.patch.object(checks_stage.disk, "shortage", return_value="low space"), \
                mock.patch.object(checks_stage.process, "activity", return_value="test process"):
            checks_stage.check_tick(owner, item, 1, "V1", 10, os.getpid())
            marks = {}
            checks_stage.check_watch(owner, item, 1, marks, "V1", 5, os.getpid())
            checks_stage.check_watch(owner, item, 1, marks, "V1", 5, os.getpid())
            with self.assertRaisesRegex(Stop, "low space"):
                step.disk_guard(owner, item, "executor.1")
        stored, problems = journal.read_events(self.project)
        self.assertFalse(problems)
        codes = [event.data["reason_code"] for event in stored if event.type == "orch.run.warning"]
        self.assertCountEqual(codes, ["STAGE_SLOW", "STAGE_IDLE", "STALL_SUSPECTED", "CHECK_SLOW", "CHECK_IDLE", "DISK_LOW", "DISK_LOW"])
        beacons = [call.kwargs["reason_code"] for call in owner.progress.emit.call_args_list]
        self.assertCountEqual(codes, beacons)

    def test_systemd_unit_text_matches_template_and_missing_tools_are_explicit(self):
        text = io.StringIO()
        with mock.patch.object(supervise_cli.shutil, "which", return_value="/opt/skm/bin/swissknifeman"), redirect_stdout(text):
            self.assertEqual(supervise_cli.systemd_units(self.project, 45), 0)
        key = hashlib.sha256(os.fsencode(self.project.resolve())).hexdigest()[:12]
        name = f"skm-supervise-{key}"
        self.assertEqual(text.getvalue(),
            f"# file: ~/.config/systemd/user/{name}.service\n[Unit]\nDescription=Swiss Knife Man conductor supervisor for {self.project}\n"
            f"[Service]\nType=oneshot\nExecStart=/opt/skm/bin/swissknifeman orch conduct --project {self.project} supervise --once\n"
            f"Environment=SKM_ORCH_LAUNCHER=supervisor\n\n# file: ~/.config/systemd/user/{name}.timer\n"
            f"[Unit]\nDescription=Run the SKM supervisor every 45 s for {self.project}\n[Timer]\nOnBootSec=120\n"
            f"OnUnitActiveSec=45\nUnit={name}.service\n[Install]\nWantedBy=timers.target\n\n")
        text = io.StringIO()
        with mock.patch.object(supervise_cli.shutil, "which", side_effect=lambda name: "/opt/skm/bin/swissknifeman" if name == "swissknifeman" else None), \
                mock.patch.dict(os.environ, {"PATH": ""}), redirect_stdout(text):
            self.assertEqual(supervise_cli.systemd_units(self.project, 60, check=True), 0)
        self.assertIn("systemd-analyze not found: unit text printed only", text.getvalue())
        with mock.patch.object(supervise_cli.shutil, "which", return_value=None), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(supervise_cli.systemd_units(self.project, 60), 1)
        self.assertIn("SUPERVISE_UNIT_UNAVAILABLE", err.getvalue())

    def test_systemd_cli_dispatch_prints_without_starting_supervision(self):
        with mock.patch.object(supervise_cli.shutil, "which", return_value="/opt/skm/bin/swissknifeman"), \
                mock.patch.object(supervise_cli.supervisor, "supervise") as supervise:
            code, out, err = self.conduct("supervise", "--print-systemd-unit", "--interval", "45")
        self.assertEqual(code, 0, err)
        self.assertIn("OnUnitActiveSec=45", out)
        supervise.assert_not_called()

    def test_systemd_verify_writes_only_temporary_units_and_escapes_exec_paths(self):
        project = self.project / "with spaces%and$"
        project.mkdir()
        def verify(argv, **kwargs):
            self.assertEqual(argv[:3], ["/bin/systemd-analyze", "--user", "verify"])
            paths = [Path(path) for path in argv[3:]]
            self.assertTrue(all(path.is_file() and path.parent != self.home for path in paths))
            self.assertIn('"' + str(project).replace('%', '%%').replace('$', '$$') + '"', paths[0].read_text())
            return SimpleNamespace(returncode=0)
        with mock.patch.object(supervise_cli.shutil, "which", side_effect=lambda name: "/bin/" + name), \
                mock.patch.object(supervise_cli.subprocess, "run", side_effect=verify), redirect_stdout(io.StringIO()):
            self.assertEqual(supervise_cli.systemd_units(project, 60, check=True), 0)
        self.assertFalse((self.home / ".config/systemd").exists())

    def test_prune_removes_detached_log_but_keeps_latest(self):
        for run_id in (ID, "cnd-20261024T100001Z-abcdef"):
            store = RunStore(self.project, run_id)
            with store.ownership("test", create=True):
                store.create({"run_id": run_id, "created": "2020-01-01T00:00:00Z", "project": str(self.project),
                              "plan": "T", "items": [], "batch": False, "max_items": 0})
                store.save({"status": "finished", "items": {}, "claims": {}, "tokens": {"input": 0, "output": 0}})
                progress.Progress(run_id, store.directory, "quiet").emit("run.end", outcome="finished")
            log = runs_root(self.project) / "detached" / f"{run_id}.log"
            log.parent.mkdir(exist_ok=True)
            log.write_text("log")
        with mock.patch.object(runs, "_age_days", return_value=10):
            rows = runs.prune(self.project, 1, apply=True)
        self.assertEqual([row["run_id"] for row in rows], [ID])
        self.assertFalse((runs_root(self.project) / "detached" / f"{ID}.log").exists())
        self.assertTrue(log.exists())


class StartupFenceTests(ConductorCase):
    """P8.8: a child of the autopilot checks the launch intent under ``autopilot-launch.lock`` before the checkout lock, the
    run lease, the run folder, any claim and any role; it acknowledges under that lock and lets it go before its work."""

    scenario = "scout-solo"

    def setUp(self):
        super().setUp()
        for name in INTERNAL_ENV:
            os.environ.pop(name, None)
        self.root = runs_root(self.project)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_doc = self.root / "autopilot.json"

    def intent(self, run_id: str = ID, launch_id: str = LAUNCH, state: str = "launching", kind: str = "run",
               current: bool = True) -> None:
        records.write(self.state_doc, {
            "plan": "T", "project": str(self.project), "pid": 4242, "started_at": "2026-10-24T10:00:00Z",
            "updated_at": "2026-10-24T10:00:01Z", "deadline_at": "2026-10-24T22:00:00Z", "mode": "running",
            "limits": {"max_runs": 20, "max_wall_s": 43200, "run_tokens_hard_max": 0, "max_no_progress_runs": 2,
                       "max_auto_decisions": 10, "quota_wait_max_s": 21600},
            "counters": dict.fromkeys(("runs", "items_closed", "no_progress_streak", "auto_decisions", "recoveries",
                                       "quota_waits"), 0),
            "current": {"run_id": run_id, "launch_id": launch_id, "state": state, "kind": kind,
                        "since": "2026-10-24T10:00:01Z"} if current else None,
            "waiting_runs": [], "history": [], "last_blockers": [], "stop": None}, "autopilot-state")

    def child(self, run_id: str = ID, launch_id: str = LAUNCH) -> tuple:
        path = self.root / "detached" / f"{run_id}.{launch_id}.ack.json"
        return path, {"SKM_ORCH_DETACHED": "1", "SKM_ORCH_LAUNCHER": "autopilot", "SKM_ORCH_DETACH_ACK": str(path),
                      "SKM_ORCH_DETACH_NONCE": launch_id, "SKM_ORCH_AUTOPILOT_STATE": str(self.state_doc),
                      "SKM_ORCH_AUTOPILOT_LAUNCH_ID": launch_id}

    def refused(self, path: Path, err: str) -> dict:
        self.assertIn("AUTOPILOT_LAUNCH_CANCELLED: ", err)
        found = records.read(path, "detach-ack")
        self.assertEqual(("refused", "AUTOPILOT_LAUNCH_CANCELLED", LAUNCH), (found["status"], found["code"], found["nonce"]))
        self.assertIs(True, probe_free(self.root / detach.LAUNCH_LOCK), "the launch lock is let go")
        return found

    def finished_run(self) -> str:
        self.script({"executor": [{"write": {"out/W1.txt": "ok\n"}, "result": report("W1")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        return self.run_dir(err).name

    def test_a_cancelled_or_replaced_intent_starts_no_folder_lock_claim_or_role(self):
        cases = {"no autopilot state": None, "no intent": {"current": False}, "another launch": {"launch_id": "0" * 16},
                 "another run": {"run_id": "cnd-20261024T100009Z-abcdef"}, "already running": {"state": "running"}}
        for name, fields in cases.items():
            with self.subTest(name):
                self.state_doc.unlink(missing_ok=True)
                if fields is not None:
                    self.intent(**fields)
                path, env = self.child()
                path.unlink(missing_ok=True)
                with mock.patch.dict(os.environ, env), mock.patch.object(RunStore, "ownership") as owned, \
                        mock.patch.object(roles.process, "run_role") as role:
                    code, out, err = self.run_items("W1", extra=("--run-id", ID))
                self.assertEqual((1, ""), (code, out), err)
                self.refused(path, err)
                owned.assert_not_called()
                role.assert_not_called()
                self.assertFalse((self.root / ID).exists(), "no run folder")
                self.assertEqual("todo", self.source()["items"]["W1"]["status"], "no claim")

    def test_a_matching_intent_acknowledges_under_the_launch_lock_and_works_without_it(self):
        self.intent()
        path, env = self.child()
        seen = []
        acknowledge = detach.acknowledge

        def acknowledged(run_id):
            seen.append(("ack", probe_free(self.root / detach.LAUNCH_LOCK), RunLease.held(self.root / run_id)))
            acknowledge(run_id)

        def owned_loop(owner):
            seen.append(("loop", probe_free(self.root / detach.LAUNCH_LOCK), RunLease.held(owner.directory)))
            return 0
        with mock.patch.dict(os.environ, env), mock.patch.object(detach, "acknowledge", side_effect=acknowledged), \
                mock.patch.object(engine.Conductor, "_loop", owned_loop):
            code, _, err = self.run_items("W1", extra=("--run-id", ID))
            self.assertNotIn("SKM_ORCH_AUTOPILOT_LAUNCH_ID", os.environ, "roles do not inherit the launch context")
        self.assertEqual(code, 0, err)
        self.assertEqual([("ack", False, True), ("loop", True, True)], seen)
        found = records.read(path, "detach-ack")
        self.assertEqual(("started", LAUNCH, ID), (found["status"], found["nonce"], found["run_id"]))

    def test_resume_and_continue_of_a_cancelled_launch_take_no_lease_and_change_nothing(self):
        run_id = self.finished_run()
        before = (self.root / run_id / "state.json").read_text(encoding="utf-8")
        self.intent(run_id=run_id, launch_id="0" * 16, kind="continue")
        for verb in ("resume", "continue"):
            with self.subTest(verb):
                path, env = self.child(run_id)
                with mock.patch.dict(os.environ, env), mock.patch.object(RunStore, "ownership") as owned, \
                        mock.patch.object(RunStore, "load") as loaded:
                    code, _, err = self.conduct(verb, "--run", run_id)
                self.assertEqual(code, 1, err)
                self.refused(path, err)  # continue too: the fence comes before NOT_WAITING
                owned.assert_not_called()
                loaded.assert_not_called()
                self.assertEqual(before, (self.root / run_id / "state.json").read_text(encoding="utf-8"))
                self.assertFalse(any(line["event"] == "run.resume" for line in progress.read_lines(self.root / run_id)))

    def test_continue_passes_the_fence_once_and_resume_of_the_intent_acknowledges(self):
        run_id = self.finished_run()
        self.intent(run_id=run_id, kind="continue")
        path, env = self.child(run_id)
        with mock.patch.dict(os.environ, env):
            code, _, err = self.conduct("continue", "--run", run_id)
        self.assertEqual(code, 1, err)
        self.assertIn("NOT_WAITING: ", err, "the fence passed: the run itself is read")
        self.assertEqual("NOT_WAITING", records.read(path, "detach-ack")["code"])
        self.assertIs(True, probe_free(self.root / detach.LAUNCH_LOCK))
        self.intent(run_id=run_id, kind="resume")
        path.unlink()
        with mock.patch.dict(os.environ, env), mock.patch.object(engine.Conductor, "_loop", return_value=0):
            code, _, err = self.conduct("resume", "--run", run_id)
        self.assertEqual(code, 0, err)
        self.assertEqual(("started", LAUNCH), (records.read(path, "detach-ack")["status"], LAUNCH))

    def test_a_launch_lock_that_stays_busy_refuses_the_start(self):
        self.intent()
        path, env = self.child()
        lock = detach.launch_lock(self.root, 0)
        self.addCleanup(lock.release)
        with mock.patch.dict(os.environ, env), mock.patch.object(detach, "LAUNCH_LOCK_WAIT_S", 0.2):
            code, _, err = self.run_items("W1", extra=("--run-id", ID))
        self.assertEqual(code, 1, err)
        self.assertIn("stayed busy", records.read(path, "detach-ack")["message"])
        self.assertFalse((self.root / ID).exists())

    def test_spawn_binds_the_given_ack_nonce_or_generates_one(self):
        log_dir = self.root / "detached"
        argv = [sys.executable, "-c", "pass", "--run", ID]
        with mock.patch.dict(os.environ, {"SKM_ORCH_AUTOPILOT_LAUNCH_ID": "inherited"}), \
                mock.patch.object(detach.subprocess, "Popen") as popen:
            popen.return_value.pid = os.getpid()
            given = detach.spawn(argv, project=self.project, launcher="autopilot", log_dir=log_dir,
                                 env={"SKM_ORCH_AUTOPILOT_LAUNCH_ID": NONCE}, ack_nonce=NONCE)
            generated = detach.spawn(argv, project=self.project, launcher="detached", log_dir=log_dir)
            with self.assertRaises(Stop) as invalid:
                detach.spawn(argv, project=self.project, launcher="autopilot", log_dir=log_dir, ack_nonce="NOT-HEX")
        detach._CHILDREN.clear()
        self.assertEqual("RECORD_INVALID", invalid.exception.code)
        self.assertEqual(2, popen.call_count)
        first, second = (call.kwargs["env"] for call in popen.call_args_list)
        self.assertEqual((NONCE, str(log_dir / f"{ID}.{NONCE}.ack.json"), NONCE),
                         (first["SKM_ORCH_DETACH_NONCE"], first["SKM_ORCH_DETACH_ACK"], first["SKM_ORCH_AUTOPILOT_LAUNCH_ID"]))
        self.assertEqual((given["nonce"], given["ack"]), (NONCE, first["SKM_ORCH_DETACH_ACK"]))
        self.assertRegex(generated["nonce"], r"^[0-9a-f]{16}$")
        self.assertNotEqual(NONCE, generated["nonce"])
        self.assertEqual(str(log_dir / f"{ID}.{generated['nonce']}.ack.json"), second["SKM_ORCH_DETACH_ACK"])
        self.assertNotIn("SKM_ORCH_AUTOPILOT_LAUNCH_ID", second, "an inherited launch context never reaches another child")


class DetachedProcessTests(FaultCase):
    def launch(self):
        self.slow_source()
        done = self.orch("conduct", "run", "--plan", "T", "--items", "W1", "--quiet", "--detach")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        doc = json.loads(done.stdout)
        self.assertFalse(contract.problems(doc, "detach-result"))
        self.addCleanup(self.stop_child, doc["pid"])
        return doc, runs_root(self.project) / doc["run_id"]

    def stop_child(self, pid):
        # Never signal a reused pid: only this live, same-boot test child with its original start ticks.
        expected = getattr(self, "identities", {}).get(pid)
        if expected is not None and engine.process.start_ticks(pid) == expected and alive(pid):
            os.kill(pid, signal.SIGKILL)

    def finished(self, directory):
        return any(line.get("event") == "run.end" for line in progress.read_lines(directory))

    def release(self, directory):
        (self.gate / "released").touch()
        (self.gate / "go").touch()
        eventually(self, lambda: self.finished(directory), "detached run finishes")
        eventually(self, lambda: not RunLease.held(directory), "detached run releases its lease")

    def test_run_detached_survives_caller_exit_in_another_session_and_emits_lifecycle(self):
        doc, directory = self.launch()
        self.identities = {doc["pid"]: engine.process.start_ticks(doc["pid"])}
        self.assertTrue(doc["detached"])
        self.assertNotEqual(os.getsid(doc["pid"]), os.getsid(0))
        self.assertEqual(RunLease.owner(directory)["launcher"], "detached")
        self.assertEqual((directory.parent / "detached").stat().st_mode & 0o777, 0o700)
        self.release(directory)
        stored, problems = journal.read_events(self.project)
        self.assertFalse(problems)
        phases = [event.data for event in stored if event.type == "orch.conductor.lifecycle"]
        self.assertEqual([event["phase"] for event in phases], ["started", "ended"])
        self.assertEqual(phases[-1]["outcome"], "finished")

    def test_resume_finished_run_acknowledges_new_pid_even_when_run_json_already_exists(self):
        doc, directory = self.launch()
        self.identities = {doc["pid"]: engine.process.start_ticks(doc["pid"])}
        self.release(directory)
        done = self.orch("conduct", "resume", "--run=" + doc["run_id"], "--detach")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        resumed = json.loads(done.stdout)
        self.assertNotEqual(doc["pid"], resumed["pid"])
        self.addCleanup(self.stop_child, resumed["pid"])
        self.identities[resumed["pid"]] = engine.process.start_ticks(resumed["pid"])
        acks = [records.read(path, "detach-ack") for path in directory.parent.glob(f"detached/{doc['run_id']}.*.ack.json")]
        self.assertTrue(any(found["pid"] == resumed["pid"] and found["status"] == "started" for found in acks))
        eventually(self, lambda: not alive(resumed["pid"]), "resumed child exits")
        stored, _ = journal.read_events(self.project)
        self.assertIn("resumed", [event.data["phase"] for event in stored if event.type == "orch.conductor.lifecycle"])

    def test_resume_startup_validation_refuses_before_acknowledging_or_emitting_resumed(self):
        doc, directory = self.launch()
        self.identities = {doc["pid"]: engine.process.start_ticks(doc["pid"])}
        self.release(directory)
        for flags, code in ((("--retry", "W1"), "RETRY_NOT_BLOCKED"),
                            (("--raise-limit", "bad"), "OPTIONS_INVALID")):
            with self.subTest(flags=flags):
                previous = set(directory.parent.glob(f"detached/{doc['run_id']}.*.ack.json"))
                done = self.orch("conduct", "resume", "--run", doc["run_id"], "--detach", *flags)
                self.assertEqual((done.returncode, done.stdout), (1, ""), done.stderr)
                self.assertTrue(done.stderr.startswith(code + ": "), done.stderr)
                current = set(directory.parent.glob(f"detached/{doc['run_id']}.*.ack.json")) - previous
                self.assertEqual(len(current), 1)
                refused = records.read(current.pop(), "detach-ack")
                self.assertEqual((refused["status"], refused["code"]), ("refused", code))
                self.assertNotEqual(refused["pid"], doc["pid"])
                eventually(self, lambda: not RunLease.held(directory), "refused resume releases its lease")
                self.assertEqual(records.read(directory / "state.json", "state")["status"], "finished")
                self.assertFalse(any(line["event"] == "run.resume" for line in progress.read_lines(directory)))
                stored, problems = journal.read_events(self.project)
                self.assertFalse(problems)
                self.assertEqual([event.data["phase"] for event in stored if event.type == "orch.conductor.lifecycle"],
                                 ["started", "ended"])

    def test_resume_stopped_run_starts_a_new_owner(self):
        self.script_file.write_text(json.dumps({"executor": [{"result": report("W1", "blocked", changed_paths=[], checks_run=[])}]}))
        doc, directory = self.launch()
        self.identities = {doc["pid"]: engine.process.start_ticks(doc["pid"])}
        self.release(directory)
        self.assertEqual(records.read(directory / "state.json", "state")["status"], "stopped")
        done = self.orch("conduct", "resume", "--run", doc["run_id"], "--detach")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        resumed = json.loads(done.stdout)
        self.addCleanup(self.stop_child, resumed["pid"])
        self.identities[resumed["pid"]] = engine.process.start_ticks(resumed["pid"])
        eventually(self, lambda: not alive(resumed["pid"]), "resumed stopped run exits")

    def test_live_run_lease_and_invalid_state_produce_refused_ack(self):
        doc, directory = self.launch()
        self.identities = {doc["pid"]: engine.process.start_ticks(doc["pid"])}
        self.release(directory)
        with RunLease(directory).acquire("test"):
            done = self.orch("conduct", "resume", "--run", doc["run_id"], "--detach")
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertTrue(done.stderr.startswith("RUN_BUSY: "), done.stderr)
            self.assertEqual(RunLease.owner(directory)["pid"], os.getpid())
        (directory / "state.json").write_text('{"status": 123}')
        done = self.orch("conduct", "resume", "--run", doc["run_id"], "--detach")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertTrue(done.stderr.startswith("STATE_INVALID: "), done.stderr)
        self.assertFalse(RunLease.held(directory))
        (directory / "state.json").write_text('{')
        done = self.orch("conduct", "resume", "--run", doc["run_id"], "--detach")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertTrue(done.stderr.startswith("STATE_CORRUPT: "), done.stderr)

    def test_unknown_run_is_refused_without_a_false_success(self):
        done = self.orch("conduct", "resume", "--run", "cnd-unknown", "--detach")
        self.assertEqual((done.returncode, done.stdout), (1, ""))
        self.assertTrue(done.stderr.startswith("RUN_UNKNOWN: "), done.stderr)


if __name__ == "__main__":
    unittest.main()
