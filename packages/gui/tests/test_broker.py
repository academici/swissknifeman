"""gui.core.broker with real processes: limits, logs, timeouts, cancel of the whole group, cleaning, redaction,
invoke commands, denial and shutdown."""
import asyncio
import dataclasses
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aicore.ext.plugins import Registration, invoke_one, load_manifest
from aicore.util.redact import env_secrets

from gui import contracts
from gui.core import broker as broker_mod
from gui.core.broker import Broker, LogSink
from gui.core.events import EventHub
from gui.core.runs import RunStore, frame_run, group_alive
from gui.errors import GuiError
from gui.settings import load
from gui.storage import db

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "units" / "exec-demo" / "xdemo"
COMMANDS = {c["id"]: c for c in json.loads((FIXTURE / "gui.json").read_text(encoding="utf-8"))["commands"]}
SECRET = "Sup3r-Secret-Value-For-Broker-Tests-42"


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split(") ", 1)[1][0] != "Z"
    except OSError:
        return True


class BrokerCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.conn = db.open_db(self.tmp / "gui.db")
        self.addCleanup(self.conn.close)
        self.lock = threading.RLock()
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp), "SKM_TEST_SECRET": SECRET,
                    "SKM_HOME": str(self.tmp / "skm")}
        base = load(self.env)
        self.settings = dataclasses.replace(base, runs=dataclasses.replace(base.runs, cancel_grace_s=1))
        self.hub = EventHub("epoch-test", ring_frames=100000, queue_frames=100000)
        self.frames = self.hub.subscribe("all", {}, None, None)
        self.store = RunStore(self.conn, lock=self.lock, publish=lambda doc: self.hub.publish_run(doc, frame_run(doc)))
        self.emitted = []
        self.broker = Broker(store=self.store, hub=self.hub, settings=lambda: self.settings, conn=self.conn,
                             db_lock=self.lock, env=self.env, runs_dir=self.tmp / "runs", secrets=lambda: env_secrets(self.env),
                             emit=lambda *args, **kwargs: self.emitted.append((args, kwargs)))

    async def asyncTearDown(self):
        await self.broker.shutdown(timeout=10)

    def limits(self, **changes):
        self.settings = dataclasses.replace(self.settings, runs=dataclasses.replace(self.settings.runs, **changes))

    async def submit(self, command_id, values=None, *, trusted=True, dry_run=False, project=True, invoke=None):
        return await self.broker.submit(
            owner="xdemo", owner_root=FIXTURE, trusted=trusted, command=COMMANDS[command_id],
            context={"project_id": "proj-00000000"} if project else {},
            project_root=str(self.project) if project else None, values=values or {}, dry_run=dry_run,
            confirmed=False, correlation_id="c" * 32, actor={"kind": "user", "id": "test"}, invoke=invoke)

    async def finish(self, run, timeout=20):
        active = self.broker.active.get(run["run_id"])
        if active is not None:
            await asyncio.wait_for(active.done.wait(), timeout)
        await asyncio.sleep(0.05)
        doc = self.store.get(run["run_id"])
        self.assertEqual([], contracts.validate(doc, "run"))
        return doc

    def stored(self, run, stream="stdout"):
        path = self.tmp / "runs" / run["run_id"] / f"{stream}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def text(self, run, stream="stdout"):
        return "".join(chunk["text"] for chunk in self.stored(run, stream))

    def published(self):
        found = []
        while True:
            frame = self.frames.get_nowait()
            if frame is None:
                return found
            found.append(frame)

    async def wait_output(self, run, needle, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if needle in self.text(run):
                return self.text(run)
            await asyncio.sleep(0.05)
        self.fail(f"{needle!r} never appeared")


class TestRuns(BrokerCase):
    async def test_echo_succeeds_in_the_project_with_audit_and_frames(self):
        run = await self.submit("xdemo.echo", {"name": "World", "loud": True})
        self.assertEqual("running", run["state"])
        self.assertEqual({"path": os.path.realpath(FIXTURE / "bin" / "echo-args"),
                          "digest": run["executable"]["digest"]}, run["executable"])
        done = await self.finish(run)
        self.assertEqual(("succeeded", {"code": 0, "signal": None}), (done["state"], done["exit"]))
        self.assertEqual(f"arg:--\narg:World\narg:--loud\ncwd:{self.project}\n", self.text(run))
        self.assertEqual(done["log"]["stdout_bytes"], len(self.text(run).encode()))
        actions = [row["action"] for row in self.conn.execute("SELECT action FROM audit ORDER BY id")]
        self.assertEqual(["run.requested", "run.decided", "run.started", "run.finished"], actions)
        frames = self.published()
        for frame in frames:
            self.assertEqual([], contracts.validate(frame, "stream"), frame)
        states = [frame["run"]["state"] for frame in frames if frame["kind"] == "run"]
        self.assertEqual(["queued", "authorizing", "starting", "running", "succeeded"], states)
        last_log = max(frame["seq"] for frame in frames if frame["kind"] == "log")
        self.assertLess(last_log, frames[-1]["seq"])
        await asyncio.sleep(0.2)
        self.assertEqual(["gui.run.started", "gui.run.succeeded"], [args[0] for args, _ in self.emitted])

    async def test_dry_run_appends_its_argument(self):
        done = await self.finish(await self.submit("xdemo.echo", {"name": "x"}, dry_run=True))
        self.assertIn("arg:--dry-run", self.text(done))
        self.assertTrue(done["dry_run"])

    async def test_failure_keeps_the_exit_code(self):
        done = await self.finish(await self.submit("xdemo.fail", project=False))
        self.assertEqual(("failed", 3), (done["state"], done["exit"]["code"]))
        self.assertEqual("HANDLER_FAILED", done["error"]["code"])
        self.assertEqual("failing\n", self.text(done, "stderr"))

    async def test_untrusted_extension_is_denied(self):
        done = await self.finish(await self.submit("xdemo.fail", project=False, trusted=False))
        self.assertEqual(("denied", "PERMISSION_DENIED"), (done["state"], done["error"]["code"]))
        self.assertEqual("denied", done["permission"]["decision"])
        self.assertEqual({"advisory"}, {e["enforcement"] for e in done["permission"]["effects"]})
        self.assertNotIn("executable", done)

    async def test_project_command_needs_a_project(self):
        with self.assertRaises(GuiError) as caught:
            await self.submit("xdemo.echo", {"name": "x"}, project=False)
        self.assertEqual("INPUT_INVALID", caught.exception.code)
        self.assertEqual([], self.store.list())


class TestLimits(BrokerCase):
    async def test_limits_refuse_before_a_run_exists(self):
        self.limits(max_global=1)
        run = await self.submit("xdemo.ticks", project=False)
        with self.assertRaises(GuiError) as caught:
            await self.submit("xdemo.fail", project=False)
        self.assertEqual("CONCURRENCY_LIMIT", caught.exception.code)
        self.assertEqual(1, len(self.store.list()))
        await self.broker.cancel(run["run_id"])
        await self.finish(run)

    async def test_owner_project_and_key_limits(self):
        fake = broker_mod.Active("run-x", "proj-00000000", "xdemo", "xdemo-echo:proj-00000000", {}, None, "c")
        self.broker.active["run-x"] = fake
        try:
            self.limits(max_per_owner=1)
            with self.assertRaises(GuiError):
                self.broker._admit(None, "xdemo", None)
            self.limits(max_per_owner=5, max_per_project=1)
            with self.assertRaises(GuiError):
                self.broker._admit("proj-00000000", "other", None)
            self.limits(max_per_project=5)
            key = self.broker._key(COMMANDS["xdemo.echo"], {"project_id": "proj-00000000"})
            self.assertEqual("xdemo-echo:proj-00000000", key)
            with self.assertRaises(GuiError):
                self.broker._admit("proj-00000000", "other", key)
            self.broker._admit("proj-11111111", "other", "xdemo-echo:proj-11111111")
        finally:
            self.broker.active.pop("run-x")


class TestStopping(BrokerCase):
    async def test_cancel_kills_the_group(self):
        run = await self.submit("xdemo.ticks", project=False)
        text = await self.wait_output(run, "tick 2")
        child = int(re.search(r"child:(\d+)", text).group(1))
        cancelling = await self.broker.cancel(run["run_id"])
        self.assertEqual("cancelling", cancelling["state"])
        done = await self.finish(run)
        self.assertEqual(("cancelled", "SIGTERM"), (done["state"], done["exit"]["signal"]))
        self.assertFalse(group_alive(int(self.conn.execute("SELECT pid FROM runs WHERE run_id = ?",
                                                           (run["run_id"],)).fetchone()[0])))
        self.assertFalse(alive(child))
        with self.assertRaises(GuiError) as caught:
            await self.broker.cancel(run["run_id"])
        self.assertEqual("RUN_NOT_CANCELLABLE", caught.exception.code)

    async def test_sigterm_ignored_means_sigkill_after_grace(self):
        self.limits(cancel_grace_s=0)
        run = await self.submit("xdemo.stubborn", project=False)
        await self.wait_output(run, "ready")
        await self.broker.cancel(run["run_id"])
        done = await self.finish(run)
        self.assertEqual(("cancelled", "SIGKILL"), (done["state"], done["exit"]["signal"]))

    async def test_command_without_cancel_is_not_cancellable(self):
        run = await self.submit("xdemo.quiet", project=False)
        with self.assertRaises(GuiError) as caught:
            await self.broker.cancel(run["run_id"])
        self.assertEqual("RUN_NOT_CANCELLABLE", caught.exception.code)
        await self.finish(run)

    async def test_total_timeout(self):
        run = await self.submit("xdemo.quiet", project=False)
        done = await self.finish(run)
        self.assertEqual(("timed_out", "HANDLER_TIMEOUT", "total"),
                         (done["state"], done["error"]["code"], done["error"]["details"]["reason"]))

    async def test_idle_timeout(self):
        self.limits(idle_timeout_s=1)
        done = await self.finish(await self.submit("xdemo.silent", project=False))
        self.assertEqual(("timed_out", "idle"), (done["state"], done["error"]["details"]["reason"]))

    async def test_grandchild_of_a_finished_leader_is_killed(self):
        run = await self.submit("xdemo.daemon", project=False)
        done = await self.finish(run)
        self.assertEqual("succeeded", done["state"])
        grandchild = int(re.search(r"grandchild:(\d+)", self.text(run)).group(1))
        await asyncio.sleep(0.2)
        self.assertFalse(alive(grandchild))

    async def test_shutdown_cancels_active_runs(self):
        run = await self.submit("xdemo.ticks", project=False)
        await self.wait_output(run, "tick 1")
        await self.broker.shutdown(timeout=10)
        self.assertEqual("cancelled", self.store.get(run["run_id"])["state"])


class TestOutput(BrokerCase):
    async def test_hostile_terminal_sequences_never_reach_storage_or_frames(self):
        run = await self.submit("xdemo.hostile", project=False)
        await self.finish(run)
        text = self.text(run)
        self.assertEqual("red link plain\nbell backspace clear\n", text)
        for frame in self.published():
            if frame["kind"] == "log":
                self.assertIsNone(re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", frame["text"]))

    async def test_secret_never_reaches_logs_frames_audit_or_argv(self):
        run = await self.submit("xdemo.leak", project=False)
        done = await self.finish(run)
        self.assertEqual("succeeded", done["state"], self.text(run, "stderr"))
        files = "".join(path.read_text() for path in (self.tmp / "runs" / run["run_id"]).iterdir())
        self.assertNotIn(SECRET, files)
        self.assertNotIn(SECRET[:5] + SECRET[5:], files)
        self.assertIn("before ", self.text(run))
        frames = json.dumps(self.published())
        self.assertNotIn(SECRET, frames)
        audit = json.dumps([tuple(row) for row in self.conn.execute("SELECT * FROM audit")])
        self.assertNotIn(SECRET, audit)
        self.assertNotIn(SECRET, json.dumps(done))

    async def test_log_limit_truncates(self):
        self.limits(log_max_bytes=5000, chunk_bytes=1024)
        run = await self.submit("xdemo.flood", project=False)
        done = await self.finish(run)
        chunks = self.stored(run)
        self.assertTrue(done["log"]["truncated"])
        self.assertLessEqual(done["log"]["stdout_bytes"], 5000)
        self.assertTrue(chunks[-1]["truncated"])
        self.assertFalse(any(chunk["truncated"] for chunk in chunks[:-1]))
        self.assertTrue(all(len(chunk["text"].encode()) <= 1024 for chunk in chunks))
        self.assertEqual(list(range(len(chunks))), [chunk["chunk"] for chunk in chunks])


class TestInvoke(BrokerCase):
    def registration(self):
        handler = FIXTURE / "handler" / "extension.json"
        manifest = load_manifest(handler)
        return Registration(id=manifest.id, manifest_path=str(handler), trusted=True, timeout_seconds=30,
                            enabled=True, manifest=manifest, problem=None)

    async def test_invoke_ok_and_error(self):
        plugin = self.registration()
        payload = {"id": "xdemo.hello", "context": {}, "input": {"name": "Ann"}}
        run = await self.submit("xdemo.hello", {"name": "Ann"}, project=False,
                                invoke=lambda: invoke_one(plugin, "gui:command", payload, env=self.env))
        done = await self.finish(run, timeout=60)
        self.assertEqual("succeeded", done["state"])
        self.assertIn("hello Ann", self.text(run))
        self.assertNotIn(SECRET, self.text(run))
        broken = {"id": "xdemo.broken", "context": {}, "input": {}}
        run = await self.submit("xdemo.broken", project=False,
                                invoke=lambda: invoke_one(plugin, "gui:command", broken, env=self.env))
        done = await self.finish(run, timeout=60)
        self.assertEqual(("failed", "HANDLER_FAILED", "XDEMO_BROKEN"),
                         (done["state"], done["error"]["code"], done["error"]["details"]["plugin_code"]))


class TestLogSink(unittest.TestCase):
    def sink(self, secrets=(SECRET,)):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        self.frames = []
        return LogSink({"run_id": "run-x", "owner": "o", "context": {}}, "stdout", folder, limit=10 ** 6,
                       chunk_bytes=64, secrets=secrets, publish=lambda *args: self.frames.append(args))

    def joined(self):
        return "".join(args[3] for args in self.frames)

    def test_secret_split_across_blocks_is_redacted(self):
        sink = self.sink()
        data = f"x {SECRET} y {SECRET}".encode()
        for size in (1, 3, 7, len(SECRET) - 1):
            with self.subTest(size=size):
                sink = self.sink()
                for start in range(0, len(data), size):
                    sink.feed(data[start:start + size])
                sink.close()
                self.assertNotIn(SECRET, self.joined())
                for cut in range(4, len(SECRET)):
                    self.assertNotIn(SECRET[:cut], self.joined())
                self.assertTrue(self.joined().startswith("x "))

    def test_escape_split_across_blocks_and_utf8(self):
        sink = self.sink(secrets=())
        for part in (b"a\x1b[3", b"1mb\x1b]0;ti", b"tle\x07c ", "привет".encode()[:3], "привет".encode()[3:]):
            sink.feed(part)
        sink.close()
        self.assertEqual("abc привет", self.joined())

    def test_sanitize(self):
        self.assertEqual("ab\tc\n\r", broker_mod.sanitize("a\x1b[1;31mb\t\x1b(Bc\x00\x07\n\r\x9b"))


if __name__ == "__main__":
    unittest.main()
