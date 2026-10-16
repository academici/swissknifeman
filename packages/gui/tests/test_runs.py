"""gui.core.runs: transitions by the table, publication after commit, documents, mark_lost, logs and pruning."""
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from gui import contracts
from gui.core import procinfo, run_states, runs
from gui.storage import db


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def make(store, **extra):
    fields = dict(command="xdemo.echo", owner="xdemo", dry_run=False, context={"project_id": "p-1a2b3c4d"},
                  input={"name": "x"}, actor={"kind": "user", "id": "cli"}, correlation_id="c" * 32,
                  permission={"decision": "allowed", "effects": [{"effect": "process.spawn", "enforcement": "advisory"}],
                              "grants": []})
    fields.update(extra)
    return store.create(**fields)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.conn = db.open_db(self.tmp / "gui.db")
        self.addCleanup(self.conn.close)
        self.published = []
        self.store = runs.RunStore(self.conn, publish=self.on_publish)

    def on_publish(self, doc):
        # The state must already be committed: another connection sees it.
        other = db.open_db(self.tmp / "gui.db")
        try:
            state = other.execute("SELECT state FROM runs WHERE run_id = ?", (doc["run_id"],)).fetchone()[0]
        finally:
            other.close()
        self.published.append((doc["state"], state))


class TestTransitions(StoreCase):
    def test_lifecycle_documents_and_publication_after_commit(self):
        run = make(self.store)
        self.assertRegex(run["run_id"], r"^run-[0-9a-f]{32}$")
        self.assertEqual([], contracts.validate(run, "run"))
        for target in ("authorizing", "starting", "running"):
            self.store.transition(run["run_id"], target)
        final = self.store.transition(run["run_id"], "succeeded", exit={"code": 0, "signal": None},
                                      log={"stdout_bytes": 3, "stderr_bytes": 0, "truncated": False})
        self.assertEqual([], contracts.validate(final, "run"))
        self.assertIn("finished_at", final)
        self.assertEqual({"code": 0, "signal": None}, final["exit"])
        self.assertEqual([(state, state) for state in ("queued", "authorizing", "starting", "running", "succeeded")],
                         self.published)
        self.assertEqual([(None, "queued"), ("queued", "authorizing"), ("authorizing", "starting"),
                          ("starting", "running"), ("running", "succeeded")], self.store.transitions(run["run_id"]))

    def test_forbidden_transitions_change_nothing(self):
        run = make(self.store)
        for target in ("running", "succeeded", "cancelling"):
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                self.store.transition(run["run_id"], target)
        self.assertEqual("queued", self.store.get(run["run_id"])["state"])
        with self.assertRaises(KeyError):
            self.store.transition("run-" + "0" * 32, "authorizing")

    def test_every_table_transition_is_accepted(self):
        for source, targets in run_states.TRANSITIONS.items():
            for target in targets:
                with self.subTest(source=source, target=target):
                    run = make(self.store)
                    self.conn.execute("UPDATE runs SET state = ? WHERE run_id = ?", (source, run["run_id"]))
                    self.assertEqual(target, self.store.transition(run["run_id"], target)["state"])

    def test_list_and_pages(self):
        made = [make(self.store, context={"project_id": "a-00000000" if i % 2 else "b-00000000"})["run_id"]
                for i in range(5)]
        self.assertEqual(5, len(self.store.list()))
        self.assertEqual(2, len(self.store.list(project_id="a-00000000")))
        page = self.store.list(limit=2)
        rest = self.store.list(limit=10, before=f"{page[-1]['created_at']}|{page[-1]['run_id']}")
        self.assertEqual(set(made), {run["run_id"] for run in page + rest})
        self.assertEqual([], self.store.list(state="running"))


class TestMarkLost(StoreCase):
    def running(self, pid=None, started=None):
        run = make(self.store)
        for target in ("authorizing", "starting"):
            self.store.transition(run["run_id"], target)
        self.store.transition(run["run_id"], "running", pid=pid, pid_start=started)
        return run["run_id"]

    def test_unfinished_runs_become_lost(self):
        queued = make(self.store)["run_id"]
        authorizing = make(self.store)["run_id"]
        self.store.transition(authorizing, "authorizing")
        done = make(self.store)["run_id"]
        self.store.transition(done, "cancelled")
        gone = self.running(pid=2 ** 22 + 7, started="1")
        lost = self.store.mark_lost(grace_s=0.5)
        self.assertEqual({queued, authorizing, gone}, set(lost))
        for run_id in lost:
            doc = self.store.get(run_id)
            self.assertEqual("lost", doc["state"])
            self.assertEqual([], contracts.validate(doc, "run"))
            self.assertFalse(doc["error"]["details"]["orphan_killed"])
        self.assertEqual("cancelled", self.store.get(done)["state"])

    def test_live_process_of_a_lost_run_is_killed_with_its_group(self):
        process = subprocess.Popen(["/bin/sh", "-c", "sleep 1000 & wait"], start_new_session=True)
        self.addCleanup(kill_group, process)
        time.sleep(0.2)
        run_id = self.running(pid=process.pid, started=procinfo.start_time(process.pid))
        self.store.mark_lost(grace_s=1)
        process.wait(timeout=10)
        self.assertFalse(runs.group_alive(process.pid))
        self.assertTrue(self.store.get(run_id)["error"]["details"]["orphan_killed"])

    def test_reused_pid_is_never_signalled(self):
        process = subprocess.Popen(["/bin/sh", "-c", "sleep 1000"], start_new_session=True)
        self.addCleanup(kill_group, process)
        run_id = self.running(pid=process.pid, started="not-its-start-time")
        self.store.mark_lost(grace_s=0.2)
        time.sleep(0.2)
        self.assertIsNone(process.poll())
        self.assertFalse(self.store.get(run_id)["error"]["details"]["orphan_killed"])


class TestLogs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_read_log_from_a_cursor_skips_broken_lines(self):
        folder = self.tmp / "run-x"
        folder.mkdir()
        lines = ['{"chunk": 0, "at": "2026-10-16T00:00:00Z", "text": "a", "truncated": false}', "broken",
                 '{"chunk": 1, "at": "2026-10-16T00:00:00Z", "text": "b", "truncated": true}']
        (folder / "stdout.jsonl").write_text("\n".join(lines) + "\n")
        self.assertEqual(["a", "b"], [c["text"] for c in runs.read_log(self.tmp, "run-x", "stdout")])
        self.assertEqual(["b"], [c["text"] for c in runs.read_log(self.tmp, "run-x", "stdout", cursor=1)])
        self.assertEqual(["a"], [c["text"] for c in runs.read_log(self.tmp, "run-x", "stdout", limit=1)])
        self.assertEqual([], runs.read_log(self.tmp, "run-x", "stderr"))

    def test_prune_by_age_and_size_keeps_active(self):
        now = time.time()
        for index, age_days in enumerate((40, 20, 10, 1)):
            folder = self.tmp / f"run-{index}"
            folder.mkdir()
            (folder / "stdout.jsonl").write_bytes(b"x" * 600_000)
            os.utime(folder, (now - age_days * 86400, now - age_days * 86400))
        removed = runs.prune_logs(self.tmp, max_age_days=30, max_total_mb=1, keep={"run-1"}, now_s=now)
        self.assertEqual(["run-0", "run-2"], removed)
        self.assertEqual({"run-1", "run-3"}, {path.name for path in self.tmp.iterdir()})
        self.assertEqual([], runs.prune_logs(self.tmp / "missing", max_age_days=1, max_total_mb=1))


if __name__ == "__main__":
    unittest.main()
