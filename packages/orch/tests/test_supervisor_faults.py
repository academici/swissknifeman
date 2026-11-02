"""Fault injection for the supervisor (PLAN9 P8.2, scenarios a–j of knowledge/p8-design#p8-supervisor).

Real conductors run as processes of their own on the fake roles and the fake work source of the conductor tests; they are
killed (SIGKILL) or stopped (SIGSTOP) while a fake role is mid-step, and ``orch conduct supervise --once`` is run as a process
too. Nothing sleeps for a fixed time: the processes meet at marker files and every wait polls until a deadline. The policy of
the machine lives where a user puts it, in ``$HOME/.local/share/swissknifeman/config/config.toml`` of a temporary home
(``machine_policy``); without it ``--recover resume`` is cut to ``notify``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

from aicore.ext import events as journal
from aicore.state import machine_config_file
from aicore.util import timefmt
from aicore.util.lock import probe_free

from orch.conductor import process, progress, records, runs
from orch.conductor.application import supervisor
from orch.conductor.infrastructure import heartbeat as heartbeat_mod
from orch.conductor.infrastructure.files import STATE_FILE, RunStore, runs_root
from orch.conductor.infrastructure.lease import RunLease
from tests.test_conductor import FIXTURES, INPUT, check, report

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "scripts" / "orch.py"
AICORE = ROOT.parent / "aicore"
FAKE_ROLE = FIXTURES / "fake_role.py"
SOURCE = FIXTURES / "source"
DEADLINE_S = 90

# A fake role that holds its step open: the first GATE_BLOCK_CALLS calls of the executor announce themselves in $GATE_DIR and
# wait for the marker ``go``; every other call, and every other role, is fake_role.py itself.
GATE_ROLE = textwrap.dedent('''
    import os, subprocess, sys, time
    from pathlib import Path
    role, gate = sys.argv[1], Path(os.environ["GATE_DIR"])
    prompt = sys.stdin.buffer.read()
    if role == "executor":
        calls = gate / "calls"
        number = int(calls.read_text()) + 1 if calls.exists() else 1
        calls.write_text(str(number))
        if number <= int(os.environ.get("GATE_BLOCK_CALLS", "1")):
            (gate / f"role-{number}.pid").write_text(str(os.getpid()))
            end = time.monotonic() + 300
            while not (gate / "go").exists() and time.monotonic() < end:
                time.sleep(0.05)
    done = subprocess.run([sys.executable, os.environ["FAKE_ROLE"], role], input=prompt)
    sys.exit(done.returncode)
''')

# The first claim of the work source waits for the marker ``released``: the conductor is inside a call with a known limit.
SLOW_PLUGIN = textwrap.dedent('''
    import os, runpy, time
    from pathlib import Path
    gate = Path(os.environ["GATE_DIR"])
    if not (gate / "source-entered").exists():
        (gate / "source-entered").write_text("1")
        end = time.monotonic() + 120
        while not (gate / "released").exists() and time.monotonic() < end:
            time.sleep(0.05)
    runpy.run_path(os.environ["FAKE_PLUGIN"], run_name="__main__")
''')


def machine_policy(home: Path, recover: str | None = "resume", max_recoveries: int = 2, window_s: int = 3600,
                   base: str = "", **extra) -> Path:
    """Write ``[orch.supervisor]`` into the machine layer of ``home`` (the file ``aicore config paths`` names as
    ``machine_config_file``), after ``base`` (the rest of the machine configuration). ``recover=None`` leaves the key out, so
    the default (``notify``) holds. ``extra`` adds more keys of the section (``hung_after_s``, ``grace_s``)."""
    path = machine_config_file(env={}, home=home)
    assert Path(path) == Path(home) / ".local/share/swissknifeman/config/config.toml", path
    lines = ["[orch.supervisor]"]
    if recover is not None:
        lines.append(f'recover = "{recover}"')
    lines += [f"max_recoveries = {max_recoveries}", f"window_s = {window_s}"]
    lines += [f"{key} = {value}" for key, value in extra.items()]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(base + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return Path(path)


def eventually(test: unittest.TestCase, condition, what: str, seconds: float = DEADLINE_S):
    """Poll ``condition`` until it gives a true value; fail with ``what`` at the deadline."""
    end = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        if time.monotonic() >= end:
            test.fail(f"timeout ({seconds} s): {what}")
        time.sleep(0.05)


def alive(pid: int) -> bool:
    """A process that has not exited (a zombie waiting for its parent is gone for this purpose)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except OSError:
        return False
    return stat != "Z"


class FaultCase(unittest.TestCase):
    scenario = "scout-solo"
    recover: str | None = "resume"
    machine_extra: dict = {}
    block_calls = 1
    checks: list | None = None

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.home, self.project, self.fake, self.gate = base / "home", base / "project", base / "fake", base / "gate"
        self.logs = base / "logs"
        for folder in (self.home, self.project, self.gate, self.logs):
            folder.mkdir()
        self.fake = self.project / "vendor" / "fake"
        self.fake.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false")):
            self.git("config", key, value)
        (self.project / ".gitignore").write_text(".swissknifeman/state/\nvendor/\n", encoding="utf-8")
        (self.project / "README.md").write_text("test\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.state_file, self.script_file = base / "source.json", base / "script.json"
        (base / "gate_role.py").write_text(GATE_ROLE, encoding="utf-8")
        self.plugin = SOURCE
        self.set_items()
        self.script_file.write_text(json.dumps({"executor": [{"write": {"out/W1.txt": "ok\n"}, "result": report("W1")}]}),
                                    encoding="utf-8")
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C.UTF-8", "TMPDIR": str(base),
                    "SKM_AICORE_EVENTS__DELIVERY": "off", "SKM_CONTRACTS_STRICT": "1", "AICORE_ROOT": str(AICORE),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "FAKE_CS_STATE": str(self.state_file),
                    "FAKE_CS_INPUT": str(INPUT), "FAKE_ROLE_SCRIPT": str(self.script_file), "FAKE_ROLE_STATE": str(self.fake),
                    "FAKE_ROLE": str(FAKE_ROLE), "GATE_DIR": str(self.gate), "GATE_BLOCK_CALLS": str(self.block_calls),
                    "FAKE_PLUGIN": str(SOURCE / "plugin.py")}
        self.write_machine(self.recover, **self.machine_extra)
        patcher = mock.patch.dict(os.environ, self.env)  # this process reads the runs of the project the way the children do
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("SKM_HOME", None)
        self.children: list = []
        self.addCleanup(self.cleanup_processes)

    # ------------------------------------------------------------------------------------------------ fixtures

    def git(self, *args) -> str:
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def set_items(self) -> None:
        item = {"status": "todo", "title": "Work W1", "scenario": self.scenario, "write_set": ["out/W1.txt"],
                "checks": self.checks or [check("W1")]}
        self.state_file.write_text(json.dumps({"order": ["W1"], "items": {"W1": item}, "registered": {}, "commits": [],
                                               "calls": []}), encoding="utf-8")

    def write_machine(self, recover, **extra) -> Path:
        roles = {role: [sys.executable, str(self.gate.parent / "gate_role.py"), role]
                 for role in ("context-scout", "executor", "reviewer", "triager")}
        base = "\n".join(["schema_version = 1", "", "[orch]", 'work_source = "fake-cs"', "", "[orch.conductor.argv]",
                          *[f"{role} = {json.dumps(argv)}" for role, argv in roles.items()], "",
                          "[aicore.plugins.fake-cs]", f"manifest = {json.dumps(str(self.plugin / 'extension.json'))}",
                          "trusted = true", ""])
        return machine_policy(self.home, recover=recover, base=base, **extra)

    def slow_source(self) -> None:
        """The work source waits for ``released`` at its first call."""
        folder = self.gate.parent / "slow-source"
        folder.mkdir()
        manifest = json.loads((SOURCE / "extension.json").read_text(encoding="utf-8"))
        manifest["entrypoint"] = ["python3", "slow_plugin.py"]
        manifest["permissions"]["env"] += ["GATE_DIR", "FAKE_PLUGIN"]
        (folder / "extension.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "slow_plugin.py").write_text(SLOW_PLUGIN, encoding="utf-8")
        self.plugin = folder
        self.write_machine(self.recover, **self.machine_extra)

    # ------------------------------------------------------------------------------------------------ processes

    def cleanup_processes(self) -> None:
        """Every process the test started, and the role groups it left (never the group of this process)."""
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.communicate() if child.stdout else child.wait()
        for path in self.gate.glob("role-*.pid"):
            pid = int(path.read_text())
            try:
                if pid != os.getpid() and os.getpgid(pid) == pid != os.getpgrp():
                    os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        (self.gate / "go").touch()
        for line in (self.project / ".swissknifeman").rglob("lease.json"):
            try:
                pid = json.loads(line.read_text(encoding="utf-8")).get("pid")
                if isinstance(pid, int) and pid not in (os.getpid(), 1) and alive(pid):
                    os.kill(pid, signal.SIGCONT)
                    os.kill(pid, signal.SIGKILL)
            except (OSError, ValueError):
                pass

    def orch(self, *args, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ORCH), "--project", str(self.project), *map(str, args)], env=self.env,
                              capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)

    def start_conductor(self, *args) -> subprocess.Popen:
        """``conduct run --plan T --items W1`` as a process of this process group, like one started from a terminal."""
        log = open(self.logs / f"conductor-{len(self.children)}.log", "wb")
        self.addCleanup(log.close)
        child = subprocess.Popen([sys.executable, str(ORCH), "--project", str(self.project), "conduct", "run", "--plan", "T",
                                  "--items", "W1", "--quiet", *map(str, args)], env=self.env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log)
        self.children.append(child)
        return child

    def supervise(self, *flags) -> dict:
        done = self.orch("conduct", "supervise", "--once", "--json", *flags)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return json.loads(done.stdout)

    def actions(self, document: dict) -> list:
        return [action["action"] for action in document["actions"]]

    def run_dir(self) -> Path:
        return eventually(self, lambda: next(iter(sorted(runs_root(self.project).glob("cnd-*"))), None), "the run folder")

    def lease_pid(self, directory: Path) -> int:
        return eventually(self, lambda: RunLease.owner(directory).get("pid"), "the lease of the run")

    def role_pid(self, number: int = 1) -> int:
        path = self.gate / f"role-{number}.pid"
        eventually(self, path.exists, f"role {number} reached its gate")
        return int(path.read_text())

    def journal(self, directory: Path) -> list:
        return progress.read_lines(directory)

    def lines(self, directory: Path) -> list:
        path = directory / supervisor.ACTIONS_FILE
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def crash(self, conductor: subprocess.Popen, directory: Path, number: int = 1) -> int:
        """Wait until the executor is inside its gate, then kill only the conductor. Returns the pid of the role."""
        role = self.role_pid(number)
        self.assertEqual(self.lease_pid(directory), conductor.pid)
        conductor.kill()
        conductor.wait(timeout=10)
        self.assertTrue(process._group_alive(role), "the role must outlive its conductor")
        found = eventually(self, lambda: runs.effective_status(directory, progress.summarize(self.journal(directory))),
                           "the journal")
        self.assertEqual("orphaned", found["status"])
        return role

    def finished(self, directory: Path) -> bool:
        return progress.summarize(self.journal(directory))["status"] == "finished"

    def wait_finished(self, directory: Path) -> None:
        eventually(self, lambda: self.finished(directory), "the resumed run finished")

    def events(self) -> list:
        return [event for event in journal.read_events(self.project)[0] if event.type == "orch.conductor.health"]


class RecoveryAfterSigkillTests(FaultCase):
    """(a) the reference case K4-N1, (b) the breaker, (h) a stop that needs the owner, (i) monotonic policy."""

    def test_a_sigkill_during_the_executor_is_reaped_and_resumed_to_a_finished_run(self):
        conductor = self.start_conductor()
        directory = self.run_dir()
        role = self.crash(conductor, directory)
        document = self.supervise("--recover", "resume")
        self.assertEqual(["reap", "resume"], self.actions(document))
        self.assertFalse(process._group_alive(role), "reap must stop the group of the orphaned role")
        results = [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("W1/agents/*/result.json")]
        self.assertIn("ORPHANED", [(found.get("error") or {}).get("code") for found in results])
        (self.gate / "go").touch()  # the second executor needs no gate (GATE_BLOCK_CALLS=1), but a late one must not wait
        self.wait_finished(directory)
        self.assertEqual(["reap", "resume"], [line["action"] for line in self.lines(directory)])
        for line in self.lines(directory):
            self.assertEqual([], records.problems(line, "supervisor-action"))
        codes = [line.get("reason_code") for line in self.journal(directory) if line["event"] == "info"]
        self.assertIn("SUPERVISOR_REAPED", codes)
        self.assertIn("SUPERVISOR_RESUMED", codes)
        self.assertEqual(["reap", "resume"], [event.data["action"] for event in self.events()])
        self.assertEqual("supervisor", RunLease.owner(directory).get("launcher", "supervisor"))
        memory = records.read(runs_root(self.project) / supervisor.STATE_DOC, "supervisor-state")
        self.assertEqual(1, len(memory["runs"][directory.name]["recoveries"]))

    block_calls = 3

    def test_b_the_third_crash_within_the_window_is_given_up_and_not_resumed(self):
        conductor = self.start_conductor()
        directory = self.run_dir()
        self.crash(conductor, directory, 1)
        self.assertEqual(["reap", "resume"], self.actions(self.supervise("--recover", "resume")))
        second = eventually(self, lambda: RunLease.held(directory) is True and RunLease.owner(directory).get("pid"),
                            "the resumed conductor holds the run")
        self.role_pid(2)
        os.kill(second, signal.SIGKILL)
        eventually(self, lambda: RunLease.held(directory) is False, "the second conductor is gone")
        self.assertEqual(["reap", "resume"], self.actions(self.supervise("--recover", "resume")))
        third = eventually(self, lambda: RunLease.held(directory) is True and RunLease.owner(directory).get("pid"),
                           "the conductor resumed twice holds the run")
        self.role_pid(3)
        os.kill(third, signal.SIGKILL)
        eventually(self, lambda: RunLease.held(directory) is False, "the third conductor is gone")
        logs = len(list((directory / "supervisor").glob("resume-*.log")))
        document = self.supervise("--recover", "resume")
        self.assertEqual(["reap", "given_up"], self.actions(document))
        self.assertEqual(logs, len(list((directory / "supervisor").glob("resume-*.log"))), "no third resume was started")
        self.assertEqual("SUPERVISOR_GAVE_UP", [line.get("reason_code") for line in self.journal(directory)
                                                 if line["event"] == "info"][-1])
        self.assertIn("given_up", [event.data["action"] for event in self.events()])
        self.assertTrue(records.read(runs_root(self.project) / supervisor.STATE_DOC,
                                     "supervisor-state")["runs"][directory.name]["given_up"])
        self.assertEqual([], self.supervise("--recover", "resume")["actions"], "a run given up is left alone")

    def test_h_a_run_whose_last_stop_needs_the_owner_is_reaped_and_not_resumed(self):
        conductor = self.start_conductor()
        directory = self.run_dir()
        role = self.crash(conductor, directory)
        state = records.read(directory / STATE_FILE, "state")
        state["last_stop"] = {"code": "STAGE_RECOVERY_UNKNOWN", "message": "no recovery rule", "resume": 1}
        records.write(directory / STATE_FILE, state, "state")
        document = self.supervise("--recover", "resume")
        self.assertEqual(["reap", "notify"], self.actions(document))
        self.assertIn("STAGE_RECOVERY_UNKNOWN", document["actions"][1]["detail"])
        self.assertFalse(process._group_alive(role))
        self.assertEqual([], list((directory / "supervisor").glob("resume-*.log")), "no resume was started")
        self.assertEqual(0, sum(1 for line in self.journal(directory) if line["event"] == "run.resume"))

    def test_i_a_flag_cannot_widen_the_policy_of_the_machine(self):
        self.recover = None  # the machine layer sets no recover: the default, notify
        self.write_machine(None)
        conductor = self.start_conductor()
        directory = self.run_dir()
        role = self.crash(conductor, directory)
        document = self.supervise("--recover", "resume")
        self.assertEqual("notify", document["recover"])
        self.assertEqual(["notify"], self.actions(document))
        self.assertTrue(process._group_alive(role), "notify sends no signal")
        self.assertEqual([], list((directory / "supervisor").glob("*")))
        self.assertEqual(0, sum(1 for line in self.journal(directory) if line["event"] == "run.resume"))
        again = self.supervise("--recover", "resume")
        self.assertEqual([], again["actions"], "the same trouble is said once")


class HungConductorTests(FaultCase):
    """(c) a stopped conductor is killed by its pid alone, (e) a reused pid is never signalled."""

    machine_extra = {"hung_after_s": 2, "grace_s": 1}

    def test_c_a_stopped_conductor_is_snapshotted_killed_reaped_and_resumed(self):
        conductor = self.start_conductor()
        directory = self.run_dir()
        role = self.role_pid()
        self.assertEqual(self.lease_pid(directory), conductor.pid)
        os.kill(conductor.pid, signal.SIGSTOP)
        eventually(self, lambda: runs.health_of(directory, runs.effective_status(
            directory, progress.summarize(self.journal(directory))), hung_after_s=2)["health"] == "hung",
                   "the heartbeat of the stopped conductor went stale")
        group = os.getpgrp()
        document = self.supervise("--recover", "resume")
        self.assertEqual(["snapshot", "stop", "reap", "resume"], self.actions(document))
        stop = document["actions"][1]
        self.assertEqual(("SIGKILL", conductor.pid), (stop["signal"], stop["pid"]))
        snapshots = list((directory / "supervisor").glob("snapshot-*.json"))
        self.assertEqual(1, len(snapshots))
        shot = records.read(snapshots[0], "supervisor-snapshot")
        self.assertEqual("hung", shot["health"]["health"])
        self.assertIn(conductor.pid, [row["pid"] for row in shot["processes"]])
        self.assertIn(role, [row["pid"] for row in shot["processes"]], "the role group is in the evidence")
        conductor.wait(timeout=10)
        self.assertEqual(group, os.getpgrp())
        self.assertTrue(alive(os.getpid()), "the group of the test must survive")
        self.assertFalse(process._group_alive(role))
        self.wait_finished(directory)
        self.assertTrue(alive(os.getpid()))

    def test_e_a_pid_of_another_process_is_not_signalled(self):
        directory = runs_root(self.project) / "cnd-reused"
        store = RunStore(self.project, "cnd-reused")
        store.create({"run_id": "cnd-reused", "items": ["W1"], "lease": True})
        store.save({"status": "running", "items": {"W1": {"steps": {}}}})
        progress.Progress("cnd-reused", directory, "quiet").emit("run.start")
        holder = subprocess.Popen([sys.executable, "-I", "-u", "-c", textwrap.dedent(f"""
            import sys; sys.path[:0] = {[str(ROOT / 'lib'), str(AICORE / 'lib')]!r}
            from pathlib import Path
            from orch.conductor.infrastructure.lease import RunLease
            lock = RunLease(Path({str(directory)!r})).acquire('run'); print('held', flush=True); sys.stdin.read()
            """)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=self.env)
        self.children.append(holder)
        self.assertEqual("held", holder.stdout.readline().strip())
        outsider = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        self.children.append(outsider)
        owner = RunLease.owner(directory)
        records.write(directory / "lease.json", {**owner, "pid": outsider.pid, "start_ticks": 1}, "lease")
        old = time.time() - 3600
        records.write(directory / "heartbeat.json", {
            "$schema": "urn:swissknifeman:orch:records:heartbeat:v1", "run_id": "cnd-reused", "pid": outsider.pid,
            "start_ticks": 1, "boot_id": process.boot_id(), "host": owner["host"], "seq": 1,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(old))}, "heartbeat")
        document = self.supervise("--recover", "resume")
        self.assertEqual(["identity_mismatch"], self.actions(document))
        self.assertIn("another process", document["actions"][0]["detail"])
        self.assertTrue(alive(outsider.pid), "the outsider must not be signalled")
        self.assertIsNone(holder.poll())
        self.assertEqual([], list((directory / "supervisor").glob("snapshot-*")), "no evidence is written before a refused signal")
        self.assertEqual([], self.supervise("--recover", "resume")["actions"], "said once")


class HealthyRunTests(FaultCase):
    """(d) quiet work, (f) two supervisors, (g) a healthy run, (j) a wait with a deadline."""

    # A check is looked at every 5 s (POLL_S) and the heartbeat is written at most that often, so the threshold of (d) stays well
    # above one tick, and the test reads the heartbeat right after a write.
    machine_extra = {"hung_after_s": 8, "grace_s": 1}

    def test_g_a_healthy_run_is_left_alone_even_with_resume(self):
        self.machine_extra = {}
        self.write_machine(self.recover)
        conductor = self.start_conductor()
        directory = self.run_dir()
        self.role_pid()
        document = self.supervise("--recover", "resume")
        self.assertEqual([], document["actions"])
        self.assertIsNone(conductor.poll())
        self.assertEqual("running", runs.health_of(directory, runs.effective_status(
            directory, progress.summarize(self.journal(directory))))["health"])
        (self.gate / "go").touch()
        self.assertEqual(0, conductor.wait(timeout=DEADLINE_S))
        self.assertEqual([], self.lines(directory))

    def test_j_a_wait_with_a_deadline_is_not_hung(self):
        self.machine_extra = {"hung_after_s": 2, "grace_s": 1}
        self.slow_source()
        conductor = self.start_conductor()
        directory = self.run_dir()
        eventually(self, lambda: (self.gate / "source-entered").exists(), "the work source was called")
        beat = eventually(self, lambda: heartbeat_mod.read(directory)[0], "a heartbeat")
        eventually(self, lambda: time.time() - timefmt.epoch(heartbeat_mod.read(directory)[0]["at"]) > 3,
                   "the heartbeat is older than hung_after_s (2 s)")
        self.assertEqual("work_source", beat["waiting"]["kind"])
        health = runs.health_of(directory, runs.effective_status(directory, progress.summarize(self.journal(directory))),
                                hung_after_s=2)
        self.assertEqual("waiting_tool", health["health"])
        self.assertEqual([], self.supervise("--recover", "resume", "--run", directory.name)["actions"])
        self.assertIsNone(conductor.poll(), "the process is alive")
        self.assertEqual([], list((directory / "supervisor").glob("*")))
        (self.gate / "released").touch()
        (self.gate / "go").touch()
        self.assertEqual(0, conductor.wait(timeout=DEADLINE_S))

    def test_f_a_second_supervisor_gets_busy_and_does_nothing(self):
        first = subprocess.Popen([sys.executable, str(ORCH), "--project", str(self.project), "conduct", "supervise",
                                  "--interval", "1", "--recover", "resume"], env=self.env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(first)
        lock = runs_root(self.project) / supervisor.LOCK_FILE
        eventually(self, lambda: lock.exists() and probe_free(lock) is False,
                   "the first supervisor holds the project")
        second = self.orch("conduct", "supervise", "--once", "--json")
        self.assertEqual(0, second.returncode, second.stderr)
        found = json.loads(second.stdout)
        self.assertEqual((True, []), (found["busy"], found["actions"]))
        self.assertIsNone(first.poll())
        first.send_signal(signal.SIGINT)
        self.assertEqual(0, first.wait(timeout=30))

    checks = [{"id": "V1", "cmd": "python3 -c \"import time; t=time.process_time()\nwhile time.process_time()-t<10: pass\"",
               "expect": "exit 0", "kind": "acceptance"}]

    def test_d_a_quiet_check_that_works_is_neither_hung_nor_killed(self):
        check_script = self.gate.parent / "quiet_check.py"
        check_script.write_text(
            "from pathlib import Path\n"
            f"started = Path({str(self.gate / 'check-started')!r})\n"
            f"released = Path({str(self.gate / 'check-released')!r})\n"
            "started.touch()\n"
            "while not released.exists(): pass\n", encoding="utf-8")
        self.checks = [{"id": "V1", "cmd": shlex.join([sys.executable, str(check_script)]),
                        "expect": "exit 0", "kind": "acceptance"}]
        self.set_items()
        options = self.gate.parent / "options.json"
        options.write_text(json.dumps({"limits": {"check_idle_warn_s": 2}}), encoding="utf-8")
        (self.gate / "go").touch()
        conductor = self.start_conductor("--options", options)
        directory = self.run_dir()
        heartbeat = heartbeat_mod
        eventually(self, (self.gate / "check-started").exists, "the check runs")
        step = eventually(self, lambda: ((heartbeat.read(directory)[0] or {}).get("step") or "").startswith("checks") or None,
                          "the check runs")
        for _ in range(2):  # two heartbeats of the check: its ticks move the heartbeat although it prints nothing
            first = (heartbeat.read(directory)[0] or {}).get("seq")
            eventually(self, lambda first=first: (heartbeat.read(directory)[0] or {}).get("seq") != first, "the heartbeat moved")
            health = runs.health_of(directory, runs.effective_status(directory, progress.summarize(self.journal(directory))),
                                    hung_after_s=8)
            self.assertEqual("running", health["health"], health)
            document = self.supervise("--recover", "resume", "--run", directory.name)
            self.assertEqual([], document["actions"])
            self.assertIsNone(conductor.poll())
        self.assertTrue(step)
        (self.gate / "check-released").touch()
        self.assertEqual(0, conductor.wait(timeout=DEADLINE_S))
        self.assertTrue(self.finished(directory))


if __name__ == "__main__":
    unittest.main()
