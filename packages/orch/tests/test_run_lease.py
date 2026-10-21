"""Run ownership and recovery, using separate processes and pipe barriers, never providers."""
from __future__ import annotations

import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from aicore.ext import events
from orch import settings
from orch.conductor import agents, cli, engine, process, progress, questions, runs
from orch.conductor.application import recovery, review_plan
from orch.conductor.infrastructure import lease
from orch.conductor.infrastructure.files import RunStore, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
BOOT = "import sys; sys.path[:0] = " + repr([str(ROOT / "lib"), str(ROOT.parent / "aicore/lib")]) + "; "


class RunLeaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        self.store = RunStore(self.project, "cnd-owned")
        self.store.create({"run_id": self.store.run_id, "items": ["W1"], "lease": True})
        self.store.save({"status": "running", "items": {"W1": {"steps": {}}}})
        self.directory = self.store.directory
        progress.Progress(self.store.run_id, self.directory, "quiet").emit("run.start")

    def child(self, script, *args):
        child = subprocess.Popen([sys.executable, "-I", "-u", "-c", BOOT + script, *map(str, args)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
        self.addCleanup(cleanup)
        return child

    def ready(self, child):
        self.assertTrue(select.select([child.stdout], [], [], 15)[0], "child did not reach the pipe barrier")
        line = child.stdout.readline().strip()
        if not line:
            self.fail("child exited before barrier: " + child.stderr.read())
        return line

    def conductor(self):
        return engine.Conductor(project=self.project, settings=settings.load(project=self.project), mode="quiet")

    def conduct(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_two_objects_and_child_observe_run_busy_and_sigkill_releases_it(self):
        with lease.RunLease(self.directory).acquire("run") as first:
            self.assertTrue(fcntl.fcntl(first.lock.fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC)
            self.assertEqual(0o600, os.fstat(first.lock.fd).st_mode & 0o777)
            metadata = (self.directory / "lease.json").read_bytes()
            for _ in range(2):
                self.assertTrue(lease.RunLease.held(self.directory))
            self.assertEqual(metadata, (self.directory / "lease.json").read_bytes())
            with self.assertRaises(engine.Stop) as caught:
                lease.RunLease(self.directory).acquire("resume")
            self.assertEqual("RUN_BUSY", caught.exception.code)
            self.assertIn(f"pid {os.getpid()}", caught.exception.message)
        self.assertFalse((self.directory / "lease.json").exists())
        self.assertTrue((self.directory / "lease.lock").exists())
        child = self.child("from pathlib import Path; from orch.conductor.infrastructure.lease import RunLease; "
                           "lock=RunLease(Path(sys.argv[1])).acquire('run'); print('held', flush=True); input()",
                           self.directory)
        self.assertEqual("held", self.ready(child))
        with self.assertRaises(engine.Stop) as caught:
            lease.RunLease(self.directory).acquire("resume")
        self.assertEqual("RUN_BUSY", caught.exception.code)
        child.kill()
        child.wait(timeout=10)
        with lease.RunLease(self.directory).acquire("resume"):
            self.assertEqual(os.getpid(), lease.RunLease.owner(self.directory)["pid"])

    def test_lock_retries_a_replaced_inode_and_refuses_symlinks(self):
        path = self.directory / "test.lock"
        real = fcntl.flock
        def replace(fd, flags):
            real(fd, flags)
            if not path.with_suffix(".old").exists():
                path.rename(path.with_suffix(".old"))
                path.touch()
        lock = lease.FileLock(path)
        with mock.patch.object(lease.fcntl, "flock", side_effect=replace):
            self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        self.assertTrue(os.path.samestat(os.fstat(lock.fd), path.stat()))
        symlink = self.directory / "symlink.lock"
        symlink.symlink_to(path)
        with self.assertRaises(OSError):
            lease.FileLock(symlink).acquire()

    def test_probe_never_creates_files_or_unlocks_an_owner(self):
        missing = self.directory / "missing.lock"
        self.assertTrue(lease.probe_free(missing))
        self.assertFalse(missing.exists())
        with lease.RunLease(self.directory).acquire("run"):
            self.assertFalse(lease.probe_free(self.directory / "lease.lock"))
            self.assertFalse(lease.probe_free(self.directory / "lease.lock"))

    def test_resume_acquires_checkout_then_run_before_load_and_holds_them_through_loop(self):
        order = []
        acquire, checkout_acquire, load = lease.RunLease.acquire, lease.CheckoutLock.acquire, RunStore.load
        def take(lock, command):
            order.append("run")
            return acquire(lock, command)
        def take_checkout(lock, command, run_id="unknown"):
            order.append("checkout")
            return checkout_acquire(lock, command, run_id)
        def read(store):
            self.assertTrue(lease.RunLease.held(store.directory))
            order.append("load")
            return load(store)
        def loop():
            self.assertTrue(lease.RunLease.held(self.directory))
            with self.assertRaises(engine.Stop) as caught:
                lease.CheckoutLock(self.directory.parent, self.project).acquire("run", "other")
            self.assertEqual("WORKTREE_BUSY", caught.exception.code)
            return 130
        conductor = self.conductor()
        with mock.patch.object(lease.RunLease, "acquire", take), \
                mock.patch.object(lease.CheckoutLock, "acquire", take_checkout), \
                mock.patch.object(RunStore, "load", read), mock.patch.object(conductor, "_loop", loop):
            self.assertEqual(130, conductor.resume(self.store.run_id))
        # CheckoutLock delegates metadata writing to RunLease.acquire as well.
        self.assertLess(order.index("checkout"), order.index("load"))
        self.assertEqual(["checkout", "run", "run", "load"], order[:4])
        self.assertFalse(lease.RunLease.held(self.directory))
        with lease.CheckoutLock(self.directory.parent, self.project).acquire("run", "other"):
            pass

    def test_every_resume_exit_and_run_open_error_release_both_locks(self):
        for operation in ("_open", "_retry", "_save", "_kill_orphaned_roles", "_loop"):
            for error in (RuntimeError("broken"), engine.Stop("ROLE_FAILED", "failed"), KeyboardInterrupt()):
                with self.subTest(operation=operation, error=type(error).__name__):
                    conductor = self.conductor()
                    with mock.patch.object(conductor, operation, side_effect=error):
                        with self.assertRaises(type(error)):
                            conductor.resume(self.store.run_id, retry=["W1"] if operation == "_retry" else [])
                    self.assertFalse(lease.RunLease.held(self.directory))
                    with lease.CheckoutLock(self.directory.parent, self.project).acquire("run", "other"):
                        pass
        conductor = self.conductor()
        with mock.patch.object(conductor, "_open", side_effect=RuntimeError("open")):
            with self.assertRaises(RuntimeError):
                conductor.run(plan="T", plans_root=None, items=["W1"], batch=False, max_items=1)
        with lease.CheckoutLock(self.directory.parent, self.project).acquire("run", "other"):
            pass
        self.assertTrue(all(not lease.RunLease.held(p) for p in self.directory.parent.glob("cnd-*")))

    def test_run_holds_checkout_and_lease_before_first_save(self):
        conductor = self.conductor()
        save = RunStore.save
        def guarded(store, state):
            self.assertTrue(lease.RunLease.held(store.directory))
            with self.assertRaises(engine.Stop) as caught:
                lease.CheckoutLock(store.directory.parent, self.project).acquire("run", "other")
            self.assertEqual("WORKTREE_BUSY", caught.exception.code)
            save(store, state)
        with mock.patch.object(RunStore, "save", guarded), mock.patch.object(conductor, "_loop", return_value=0):
            self.assertEqual(0, conductor.run(plan="T", plans_root=None, items=["W1"], batch=False, max_items=1))
        self.assertIs(True, read_json(conductor.directory / "run.json")["lease"])

    def test_busy_resume_settle_release_leave_state_bytes_unchanged(self):
        before = (self.directory / "state.json").read_bytes()
        with lease.RunLease(self.directory).acquire("run"):
            for args in [("resume",), ("settle", "--item", "W1", "--outcome", "done", "--reason", "test"),
                         ("release", "--item", "W1", "--reason", "test")]:
                code, _, error = self.conduct(*args, "--run", self.store.run_id)
                self.assertEqual(1, code, error)
                self.assertIn("RUN_BUSY", error)
                self.assertEqual(before, (self.directory / "state.json").read_bytes())

    def test_checkout_rejects_second_run_and_resume_but_separate_toplevel_is_free(self):
        root = self.directory.parent
        with lease.CheckoutLock(root, self.project).acquire("run", "cnd-first"):
            before = sorted(path.name for path in root.iterdir())
            for args in [("run", "--plan", "T", "--items", "W1"), ("resume", "--run", self.store.run_id)]:
                code, _, error = self.conduct(*args)
                self.assertEqual(1, code)
                self.assertIn("WORKTREE_BUSY", error)
                self.assertIn("cnd-first", error)
                self.assertEqual(before, sorted(path.name for path in root.iterdir()))
            with lease.CheckoutLock(root, self.project / "other").acquire("run", "cnd-other"):
                pass

    def test_orphaned_status_json_and_runs_keep_legacy_running(self):
        before = (self.directory / "run.json").read_bytes()
        for held in (False, True):
            lock = lease.RunLease(self.directory)
            if held:
                lock.acquire("run")
            try:
                code, out, _ = self.conduct("status", "--run", self.store.run_id, "--json")
                self.assertEqual(0, code)
                expected = ("running", None) if held else ("orphaned", "RUN_ORPHANED")
                found = json.loads(out)
                self.assertEqual(expected, (found["status"], found["reason_code"]))
                row = runs.listing(self.project)[0]
                self.assertEqual(expected, (row["status"], row["reason_code"]))
                self.assertIn(expected[0], self.conduct("status", "--run", self.store.run_id)[1])
            finally:
                lock.release()
        self.assertEqual(before, (self.directory / "run.json").read_bytes())
        self.store.create({"items": ["W1"]})
        self.assertEqual("running", json.loads(self.conduct("status", "--run", self.store.run_id, "--json")[1])["status"])

    def test_status_in_a_read_only_context_is_not_a_traceback(self):
        lock_file = self.directory / "lease.lock"
        with lease.RunLease(self.directory).acquire("run"):
            os.chmod(lock_file, 0o444)  # no write access: the probe opens the file read-only and still sees the owner
            self.addCleanup(os.chmod, lock_file, 0o644)
            self.assertIs(lease.probe_free(lock_file), False)
            found = json.loads(self.conduct("status", "--run", self.store.run_id, "--json")[1])
            self.assertEqual(found["status"], "running")
        os.chmod(lock_file, 0)  # not even readable: whether a conductor holds the run is unknown
        self.assertIsNone(lease.probe_free(lock_file))
        self.assertIsNone(lease.RunLease.held(self.directory))
        code, out, err = self.conduct("status", "--run", self.store.run_id, "--json")
        self.assertEqual(code, 0, err)
        found = json.loads(out)
        self.assertEqual((found["status"], found.get("lease")), ("running", {"lock": "unavailable"}))
        self.assertNotIn("Traceback", err)

    def test_an_answer_to_an_item_without_questions_writes_nothing(self):
        before = sorted(path.name for path in self.directory.iterdir())
        code, _, err = self.conduct("answer", "--run", self.store.run_id, "--item", "TYPO", "--question", "Q1",
                                    "--text", "x")
        self.assertEqual(code, 1)
        self.assertIn(f"QUESTION_UNKNOWN: TYPO has no questions in run {self.store.run_id}", err)
        self.assertEqual(before, sorted(path.name for path in self.directory.iterdir()))

    def test_questions_lock_timeout_is_a_stop(self):
        lock = lease.FileLock(self.directory / "questions.lock")
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        with mock.patch.object(lease.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaises(engine.Stop) as caught:
                with lease.questions_lock(self.directory):
                    self.fail("entered a busy questions lock")
        self.assertEqual("QUESTIONS_LOCKED", caught.exception.code)

    def test_prune_skips_resume_owner_and_resume_cannot_resurrect_a_pruned_directory(self):
        self.directory.joinpath("progress.jsonl").write_text(
            json.dumps({"ts": "2020-01-01T00:00:00Z", "event": "run.end", "outcome": "finished"}) + "\n")
        latest = RunStore(self.project, "cnd-new")
        latest.create({"items": []})
        progress.Progress(latest.run_id, latest.directory, "quiet").emit("run.start")
        with lease.RunLease(self.directory).acquire("resume"):
            rows = runs.prune(self.project, 1, apply=True)
            self.assertEqual([False], [row["removed"] for row in rows])
            self.assertIn("RUN_BUSY", rows[0]["reason"])
        self.assertEqual([True], [row["removed"] for row in runs.prune(self.project, 1, apply=True)])
        with self.assertRaises(engine.Stop) as caught:
            self.conductor().resume(self.store.run_id)
        self.assertEqual("RUN_UNKNOWN", caught.exception.code)
        self.assertFalse(self.directory.exists())

    def test_concurrent_answer_survives_a_conductor_save_of_old_questions(self):
        directory = self.directory / "W1"
        store = {}
        questions.record(store, [{"id": "Q1", "revision": 1, "kind": "clarification", "text": "which?", "blocking": True}],
                         {"run": self.store.run_id, "item": "W1", "step": "executor.1"}, "t")
        questions.save(directory, self.store.run_id, "W1", store)
        child = self.child("from pathlib import Path; from orch.conductor import questions; "
                           "print('ready',flush=True); input(); "
                           "questions.answer_file(Path(sys.argv[1]),'Q1',text='answer',by='owner',now='t'); "
                           "print('answered',flush=True)", directory)
        self.assertEqual("ready", self.ready(child))
        with lease.RunLease(self.directory).acquire("run"):
            child.stdin.write("go\n")
            child.stdin.flush()
            self.assertEqual("answered", self.ready(child))
            child.wait(timeout=10)
            questions.save(directory, self.store.run_id, "W1", store)
        self.assertEqual("answer", questions.read(directory)["questions"][0]["resolution"]["value"])

    def test_process_record_exists_before_wait_and_fd_does_not_survive_exec(self):
        directory = self.directory / "W1/agents/one"
        directory.mkdir(parents=True)
        script = ("import os,sys; target=sys.argv[1]; "
                  "links=[os.readlink('/proc/self/fd/'+n) for n in os.listdir('/proc/self/fd') "
                  "if n.isdigit() and os.path.exists('/proc/self/fd/'+n)]; "
                  "print('inherited' if target in links else 'closed')")
        wait = process._wait
        def inspect(child, *args, **kwargs):
            doc = read_json(directory / "process.json")
            self.assertEqual((child.pid, child.pid), (doc["pid"], doc["pgid"]))
            self.assertIsInstance(doc["start_ticks"], int)
            self.assertIn("started_at", doc)
            return wait(child, *args, **kwargs)
        with lease.RunLease(self.directory).acquire("run"), mock.patch.object(process, "_wait", inspect):
            result = process.run_role([sys.executable, "-I", "-c", script, str(self.directory / "lease.lock")], "",
                                      transport="text", cwd=self.project, timeout_s=5,
                                      raw_path=self.directory / "W1/streams/executor.1.txt", agent_directory=directory)
        self.assertEqual("closed", result.text.strip())

    def test_batch_roles_also_get_agent_process_records(self):
        conductor = self.conductor()
        conductor._open(self.store.run_id, *self.store.load(), self.store)
        item = engine.Item(ref="W1", orch_run="work-one", state=conductor.state["items"]["W1"],
                           directory=self.directory / "W1", claim={})
        route = {"provider": "codex", "model": "fake", "effort": "low", "transport": "text"}
        argv = [sys.executable, "-I", "-c", "print('done')"]
        with self.store.ownership("resume"), mock.patch.object(conductor, "_role_argv", return_value=argv), \
                mock.patch.object(conductor, "_role_env", return_value=None):
            for key, role in [("review-strategist", "triager"), ("group-review-1", "reviewer")]:
                raw = self.directory / "streams" / (key + ".txt")
                result = review_plan.run_agent(conductor, item, key, role, route, "prompt", raw, 5)
                self.assertEqual("done", result.text.strip())
        directories = sorted((item.directory / "agents").iterdir())
        self.assertEqual(2, len(directories))
        for directory in directories:
            self.assertIsInstance(read_json(directory / "process.json")["start_ticks"], int)
            self.assertEqual(0, read_json(directory / "result.json")["exit"])

    def test_sigkill_conductor_leaves_role_then_resume_stops_it_before_loop(self):
        agent = self.directory / "W1/agents/one"
        agent.mkdir(parents=True)
        write_json(agent / "request.json", {"agent_run_id": "one", "step": "executor.1", "role": "executor",
                                           "route": {"provider": "codex"}, "attempt": 1})
        address = str(self.project / "ready.fifo")
        os.mkfifo(address)
        reader = os.open(address, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.addCleanup(os.close, reader)
        role_script = ("import os,signal,sys; fd=os.open(sys.argv[1],os.O_WRONLY); "
                       "os.write(fd,b'ready'); os.close(fd); signal.pause()")
        script = '''
from pathlib import Path
from orch import settings
from orch.conductor import engine, process
p=Path(sys.argv[1]); c=engine.Conductor(project=p, settings=settings.load(project=p), mode='quiet')
def wait(child, *args, **kwargs):
    print(child.pid, flush=True)
    sys.stdin.readline()
process._wait=wait
def loop():
    process.run_role([sys.executable, '-I', '-c', sys.argv[3], sys.argv[4]], '', transport='text', cwd=p,
                     timeout_s=0, raw_path=c.directory/'W1/streams/executor.1.txt',
                     agent_directory=c.directory/'W1/agents/one')
c._loop=loop
c.resume(sys.argv[2])
'''
        child = self.child(script, self.project, self.store.run_id, role_script, address)
        pid = int(self.ready(child))
        def cleanup_role():
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.addCleanup(cleanup_role)
        self.assertTrue(select.select([reader], [], [], 15)[0], "role did not reach its FIFO barrier")
        self.assertEqual(b"ready", os.read(reader, 5))
        self.assertEqual(pid, read_json(agent / "process.json")["pid"])
        child.kill()  # only conductor: the role remains in its own session
        child.wait(timeout=10)
        self.assertTrue(process._group_alive(pid))
        found = json.loads(self.conduct("status", "--run", self.store.run_id, "--json")[1])
        self.assertEqual(("orphaned", "RUN_ORPHANED"), (found["status"], found["reason_code"]))
        conductor = self.conductor()
        def loop():
            self.assertFalse(process._group_alive(pid), "new work started while the old writer was alive")
            return 0
        with mock.patch.object(conductor, "_loop", loop):
            self.assertEqual(0, conductor.resume(self.store.run_id))
        killed = [row for row in progress.read_lines(self.directory) if row.get("reason_code") == "ROLE_ORPHAN_KILLED"]
        self.assertEqual(1, len(killed))
        self.assertEqual("failed", agents.read(self.directory / "W1")[0]["status"])
        self.assertEqual("ORPHANED", read_json(agent / "result.json")["error"]["code"])
        recovery.kill_orphaned_roles(conductor)  # a second recovery preserves the result and event count
        failed = [event for event in events.read_events(self.project)[0] if event.type == "orch.agent.failed"]
        self.assertEqual(1, len(failed))
        self.assertEqual({"class": "orphaned", "code": "ORPHANED"}, failed[0].data["error"])
        self.assertEqual(self.store.run_id, failed[0].correlationid)

    def test_dead_or_reused_process_closes_agent_and_preserves_existing_results(self):
        conductor = self.conductor()
        conductor._open(self.store.run_id, *self.store.load(), self.store)
        conductor.state["items"]["W1"]["orch_run"] = "work-first"
        for number, ticks in enumerate((None, 124), 1):
            handle = agents.start(self.directory / "W1", f"agent-{number}", role="executor", route={"provider": "codex"},
                                  step="executor.1", attempt=1, prompt="prompts/executor.1.md", parent=None,
                                  started_at="2026-10-20T10:00:00Z")
            directory = handle["directory"]
            write_json(directory / "process.json", {"pid": 424242, "pgid": 424242, "start_ticks": 123})
            write_json(directory / "usage.json", {"input": 17, "cached": 0, "output": 0, "usage_complete": False})
            with mock.patch.object(process, "start_ticks", return_value=ticks), \
                    mock.patch.object(recovery.os, "killpg") as kill:
                recovery.kill_orphaned_roles(conductor)
                result = (directory / "result.json").read_bytes()
                recovery.kill_orphaned_roles(conductor)
                kill.assert_not_called()
            self.assertEqual(result, (directory / "result.json").read_bytes())
            self.assertEqual("ORPHANED", read_json(directory / "result.json")["error"]["code"])
            self.assertEqual(17, read_json(directory / "usage.json")["input"])
        rows = agents.read(self.directory / "W1")
        self.assertEqual(["failed", "failed"], [row["status"] for row in rows])
        failed = [event for event in events.read_events(self.project)[0] if event.type == "orch.agent.failed"]
        self.assertEqual(2, len(failed))
        self.assertTrue(all(event.correlationid == "work-first" for event in failed))
        self.assertTrue(all(event.data["role"] == "executor" for event in failed))
        # A finished role's receipt remains authoritative even if its step was not saved before the crash.
        directory = self.directory / "W1/agents/agent-1"
        write_json(directory / "result.json", {"exit": 0})
        with mock.patch.object(process, "start_ticks", return_value=None):
            recovery.kill_orphaned_roles(conductor)
        self.assertEqual({"exit": 0}, read_json(directory / "result.json"))
        self.assertEqual(2, len([event for event in events.read_events(self.project)[0] if event.type == "orch.agent.failed"]))

    def test_reused_pid_and_completed_step_are_not_signalled(self):
        child = subprocess.Popen([sys.executable, "-I", "-u", "-c",
                                  "import signal; print('ready',flush=True); signal.pause()"],
                                 stdout=subprocess.PIPE, text=True, start_new_session=True)
        def cleanup():
            child.kill()
            child.wait(timeout=10)
            child.stdout.close()
        self.addCleanup(cleanup)
        self.assertEqual("ready", self.ready(child))
        directory = self.directory / "W1/agents/one"
        directory.mkdir(parents=True)
        write_json(directory / "request.json", {"step": "executor.1"})
        doc = {"pid": child.pid, "pgid": child.pid, "start_ticks": process.start_ticks(child.pid) + 1}
        write_json(directory / "process.json", doc)
        conductor = self.conductor()
        conductor._open(self.store.run_id, *self.store.load(), self.store)
        with mock.patch.object(recovery.os, "killpg") as kill:
            recovery.kill_orphaned_roles(conductor)
            kill.assert_not_called()
            doc["start_ticks"] -= 1
            write_json(directory / "process.json", doc)
            conductor.state["items"]["W1"]["steps"]["executor.1"] = {"status": "done"}
            recovery.kill_orphaned_roles(conductor)
            kill.assert_not_called()
        self.assertIsNone(child.poll())

    def test_recovery_escalates_to_sigkill_and_refuses_to_continue_with_a_live_group(self):
        directory = self.directory / "W1/agents/one"
        directory.mkdir(parents=True)
        write_json(directory / "request.json", {"step": "executor.1"})
        write_json(directory / "process.json", {"pid": 424242, "pgid": 424242, "start_ticks": 123})
        for remains_alive in (False, True):
            conductor = self.conductor()
            with mock.patch.object(process, "start_ticks", return_value=123), \
                    mock.patch.object(recovery.os, "getpgid", return_value=424242), \
                    mock.patch.object(recovery.os, "killpg") as kill, \
                    mock.patch.object(recovery.time, "monotonic", side_effect=[0, 11, 11, 22]), \
                    mock.patch.object(process, "_group_alive", side_effect=[True, True, True, remains_alive, remains_alive]), \
                    mock.patch.object(conductor, "_loop", return_value=0) as loop:
                if remains_alive:
                    with self.assertRaises(engine.Stop) as caught:
                        conductor.resume(self.store.run_id)
                    self.assertEqual("ROLE_FAILED", caught.exception.code)
                    loop.assert_not_called()
                else:
                    self.assertEqual(0, conductor.resume(self.store.run_id))
                self.assertEqual([mock.call(424242, signal.SIGTERM), mock.call(424242, signal.SIGKILL)], kill.call_args_list)
            self.assertFalse(lease.RunLease.held(self.directory))


if __name__ == "__main__":
    unittest.main()
