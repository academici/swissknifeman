"""Invariant I2: every mutation of the run state and every save of ``state.json`` happens under the one lock of the run
store, whichever thread makes it (the main loop, the threads of the checks, the thread of a role)."""
import itertools
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import checks  # noqa: E402
from orch.conductor.domain.item import Item  # noqa: E402
from orch.conductor.engine import Conductor  # noqa: E402
from orch.conductor.infrastructure.files import RunStore  # noqa: E402


def _repo(tmp: str) -> Path:
    for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
    return Path(tmp)


class CountingLock:
    """A re-entrant lock that counts its acquisitions and remembers the threads that took it."""

    def __init__(self):
        self._lock = threading.RLock()
        self.count = 0
        self.threads = set()

    def acquire(self, *args, **kwargs):
        taken = self._lock.acquire(*args, **kwargs)
        if taken:
            self.count += 1  # under the lock
            self.threads.add(threading.get_ident())
        return taken

    def release(self):
        self._lock.release()

    def owned(self) -> bool:
        return self._lock._is_owned()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def conductor(tmp: str):
    """A conductor in a temporary project with a run store whose lock counts."""
    (Path(tmp) / "project").mkdir()
    project = _repo(str(Path(tmp) / "project"))
    cond = Conductor(project=project, settings=SimpleNamespace(conductor={}), mode="quiet")
    store = RunStore(project, "cnd-lock")
    store.directory = Path(tmp) / "run"
    store.directory.mkdir()
    store.lock = CountingLock()
    state = {"items": {"T.W1": {"steps": {}}}, "claims": {}, "agents": 0}
    cond._open("cnd-lock", {"items": ["T.W1"]}, state, store)
    cond._beacon_event = lambda *args, **kwargs: None
    cond._stage_event = lambda *args, **kwargs: None
    item = Item(ref="T.W1", orch_run="o-1", state=state["items"]["T.W1"], directory=Path(tmp) / "item", claim={})
    return cond, item, store


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_threads_that_mutate_and_save_never_break_state_json(self):
        store = RunStore(Path(self.tmp.name), "cnd-lock")
        store.directory = Path(self.tmp.name) / "run"
        store.directory.mkdir()
        state = {"items": {}, "claims": {}}  # records/v1 state: the threads add pieces, the main thread claims
        failures = []

        def worker(number: int) -> None:
            try:
                for index in range(200):
                    with store.mutating():
                        state["items"][f"k{number}_{index}"] = {"retries_used": index}
                        if index % 10 == 0:  # a durable save is an fsync: not every iteration
                            store.save(state)
            except Exception as error:  # noqa: BLE001 — the test reports any
                failures.append(error)

        threads = [threading.Thread(target=worker, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for index in range(200):  # the main thread changes a nested dict meanwhile
            with store.mutating():
                state["claims"][f"m{index}"] = {"v": index}
        for thread in threads:
            thread.join()
        store.save(state)
        self.assertEqual(failures, [])
        saved = json.loads((store.directory / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["items"]), 8 * 200)
        self.assertEqual(len(saved["claims"]), 200)

    def test_every_writer_of_the_state_takes_the_lock_of_the_store(self):
        """The lock is really used (counted acquisitions), not merely absent from a lucky run."""
        cond, item, store = conductor(self.tmp.name)
        lock = store.lock

        def taken(call) -> int:
            before = lock.count
            call()
            return lock.count - before

        self.assertGreater(taken(lambda: store.save(cond.state)), 0)
        self.assertGreater(taken(lambda: store.next_agent(cond.state)), 0)
        self.assertGreater(taken(lambda: cond._plan_note(item, "a note")), 0)
        self.assertGreater(taken(lambda: cond._start_step(item, "checks.1")), 0)
        self.assertGreater(taken(lambda: cond._step(item, "review.1", lambda: {"findings": {"findings": [], "verdict": "GREEN"}})), 0)
        cond._local.agent = {"id": "a1"}
        cond._step_tokens = {"input": 0, "output": 0}
        self.assertGreater(taken(lambda: cond._tokens(item, {"input": 3, "output": 4})), 0)
        cond._shared_session = lambda *args: True
        self.assertGreater(taken(lambda: cond._keep_session(item, "executor", {}, SimpleNamespace(error=None, session="s1"))),
                           0)
        item.options = {"limits": {"run_warn_s": 1}}
        cond._active_s = lambda: 5.0
        self.assertGreater(taken(lambda: cond._run_clock(item, stop=False)), 0)
        self.assertEqual(cond.state["run_warned"], 5)

    def test_a_save_waits_for_a_mutation_in_progress(self):
        store = RunStore(Path(self.tmp.name), "cnd-lock")
        store.directory = Path(self.tmp.name) / "run"
        store.directory.mkdir()
        saved = threading.Event()
        with store.mutating():
            thread = threading.Thread(target=lambda: (store.save({"status": "running"}), saved.set()))
            thread.start()
            self.assertFalse(saved.wait(0.3))  # the other thread cannot save while a mutation holds the lock
        self.assertTrue(saved.wait(10))
        thread.join()

    def test_checks_that_warn_while_the_state_is_saved_keep_state_json_valid(self):
        cond, item, store = conductor(self.tmp.name)
        item.options = {"limits": {"run_warn_s": 1}}
        ticks = itertools.count(1)
        cond._active_s = lambda: float(next(ticks))  # every tick crosses a new threshold: a plan note and a state change
        parsed, failures = [], []
        original = store.save

        def checked(state):
            original(state)
            try:
                json.loads((store.directory / "state.json").read_text(encoding="utf-8"))
                parsed.append(1)
            except ValueError as error:
                failures.append(error)

        store.save = checked
        stop = threading.Event()

        def saver():
            while not stop.is_set():
                cond._save()

        thread = threading.Thread(target=saver)
        document = {"input_id": "T.W1@abc", "acceptance": {"checks": [
            {"id": f"V{number}", "cmd": "sleep 1.2", "kind": "acceptance"} for number in range(1, 7)]}}
        project = Path(self.tmp.name) / "project"
        with mock.patch.dict("os.environ", {"SKM_TEST_JOBS": "8"}), mock.patch.object(checks, "POLL_S", 0.2):
            thread.start()
            try:
                rows = checks.run_checks(
                    document, project=project, evidence_dir=project / "ev", log_dir=Path(self.tmp.name) / "log",
                    timeout_s=60, evidence_prefix="cnd-lock:T.W1:checks.1", parallel=4, warn_s=1, fail_fast=False,
                    on_slow=lambda check_id, elapsed, pid: cond._run_clock(item, stop=False))
            finally:
                stop.set()
                thread.join()
        cond._save()
        self.assertEqual(failures, [])
        self.assertGreater(len(parsed), 1)
        self.assertEqual([row["green"] for row in rows], [True] * 6)
        saved = json.loads((store.directory / "state.json").read_text(encoding="utf-8"))
        self.assertGreater(saved["run_warned"], 0)
        self.assertTrue(saved["items"]["T.W1"]["plan_notes"])

    def test_a_check_thread_and_the_main_loop_change_the_state_at_the_same_moment(self):
        """``checks.overlap_review``: the review (main thread) closes steps while a check thread adds plan notes."""
        cond, item, store = conductor(self.tmp.name)
        rounds = 200
        barrier = threading.Barrier(2)
        failures = []

        def checks_thread():
            try:
                for number in range(rounds):
                    barrier.wait(10)
                    cond._plan_note(item, f"run active {number}s")  # what run_clock does from a check tick
            except Exception as error:  # noqa: BLE001
                failures.append(error)
                barrier.abort()

        thread = threading.Thread(target=checks_thread)
        thread.start()
        try:
            for number in range(rounds):
                barrier.wait(10)
                cond._step(item, f"review.{number + 1}", lambda: {"findings": {"findings": [], "verdict": "GREEN"}})  # start, close, save (json.dumps)
        finally:
            thread.join()
        cond._save()
        self.assertEqual(failures, [])
        saved = json.loads((store.directory / "state.json").read_text(encoding="utf-8"))
        piece = saved["items"]["T.W1"]
        self.assertEqual(len(piece["plan_notes"]), rounds)
        self.assertEqual(sum(1 for step in piece["steps"].values() if step["status"] == "done"), rounds)
        self.assertGreaterEqual(len(store.lock.threads), 2)  # both sides took the lock
        self.assertGreater(store.lock.count, rounds * 2)


    def test_an_unmetered_attempt_flags_the_piece_under_the_lock_and_announces_after_it(self):
        cond, item, store = conductor(self.tmp.name)
        cond._local.agent = {"id": "a1"}
        cond._step_tokens = {"input": 0, "output": 0}
        seen = []
        original = store.save

        def saving(state):
            seen.append(("save", store.lock.owned(), item.state.get("usage_incomplete")))
            original(state)

        store.save = saving
        cond.progress.emit = lambda *args, **kwargs: seen.append((kwargs.get("reason_code"), store.lock.owned()))
        # another thread holds the lock: the flag cannot appear until it lets go
        held, release = threading.Event(), threading.Event()

        def holder():
            with store.mutating():
                held.set()
                release.wait(10)

        thread = threading.Thread(target=holder)
        thread.start()
        held.wait(10)
        worker = threading.Thread(target=lambda: cond._tokens(item, {"input": 1, "output": 1}, usage_complete=False))
        worker.start()
        worker.join(0.3)
        self.assertTrue(worker.is_alive())
        self.assertNotIn("usage_incomplete", item.state)
        release.set()
        worker.join(10)
        thread.join()
        self.assertIn(("save", True, True), seen)  # saved with the flag, under the lock
        self.assertIn(("BUDGET_UNMETERED", False), seen)  # announced after leaving it
        saved = json.loads((store.directory / "state.json").read_text(encoding="utf-8"))
        self.assertIs(saved["items"]["T.W1"]["usage_incomplete"], True)

    def test_the_history_of_the_checks_is_read_as_a_snapshot_beside_a_new_step(self):
        from orch.conductor.stages import checks_stage
        for number in (1, 3):
            with self.subTest(round=number), tempfile.TemporaryDirectory() as tmp:
                cond, item, store = conductor(tmp)
                entered, proceed = threading.Event(), threading.Event()

                class Slow(dict):
                    def items(self, entered=entered, proceed=proceed):  # the reader is paused half-way through the steps
                        for position, pair in enumerate(list(dict.items(self))):
                            if position == 1:
                                entered.set()
                                proceed.wait(5)
                            yield pair

                item.state["steps"] = Slow({"scout": {"status": "done", "result": {}},
                                            "executor.1": {"status": "done", "result": {}},
                                            "checks.1": {"status": "done", "result": [{"id": "V1", "green": False}]}})
                item.options = {"checks": {"parallel": 2, "fail_fast": True, "reuse": True, "red_first": True,
                                           "kinds": ["acceptance"], "cadence": ["item"]},
                                "limits": {"check_timeout_s": 5}}
                item.routes = {"executor": {}}
                item.artifacts = Path(tmp) / "art"
                cond._disk_guard = lambda *args: None
                cond._actor = lambda route: {}
                cond._evidence_dir = lambda found: found.artifacts / "evidence"
                outcome = {}

                def computing(outcome=outcome, cond=cond, item=item, number=number):
                    try:
                        with mock.patch.object(checks_stage.checks_mod, "run_checks", return_value=[]) as run:
                            outcome["rows"] = checks_stage.compute_checks(cond, item, number, {})
                            outcome["call"] = run.call_args
                    except Exception as error:  # noqa: BLE001
                        outcome["error"] = error

                reader = threading.Thread(target=computing)
                reader.start()
                self.assertTrue(entered.wait(10))

                def adding(store=store, item=item):
                    with store.mutating():  # what start_step does for the review beside the checks
                        item.state["steps"]["review.1"] = {"status": "started"}

                writer = threading.Thread(target=adding)
                writer.start()
                writer.join(0.3)
                self.assertTrue(writer.is_alive())  # the lock keeps the writer out while the history is read
                proceed.set()
                reader.join(10)
                writer.join(10)
                self.assertNotIn("error", outcome)
                self.assertEqual(outcome["rows"], [])
                self.assertIn("review.1", item.state["steps"])
                kwargs = outcome["call"].kwargs
                self.assertEqual(kwargs["previous"], [{"id": "V1", "green": False}] if number == 3 else [])
                self.assertEqual(kwargs["first"], ["V1"] if number == 3 else [])


if __name__ == "__main__":
    unittest.main()
