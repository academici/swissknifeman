"""Terminal core (stdlib, a real /bin/sh on a PTY): environment, credits, closing, limits, timers, platform."""
import json
import os
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from gui import errors
from gui.core import terminal as core

SECRET = "s3cr3t-terminal-value-0123456789"
WAIT_S = 15.0


def alive(pid: int) -> bool:
    """A process that exists and is not a zombie."""
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_until(session, pattern: str, timeout: float = WAIT_S) -> str:
    """Output (credit granted as needed) until ``pattern`` matches; every wait is bounded."""
    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        if session.gate.available < 4096:
            session.gate.grant(4096)
        chunk = session.take_output()
        if chunk is None:
            session.wait_readable(0.05)
            continue
        text += chunk[1].decode("utf-8", "replace")
        if re.search(pattern, text):
            return text
    raise AssertionError(f"timeout waiting for {pattern!r}; got {len(text)} characters")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        self.clock = [0.0]
        self.audits = []
        self.env = {"PATH": os.environ["PATH"], "HOME": self.root, "SKM_TEST_SECRET": SECRET, "GUI_TOKEN": SECRET,
                    "API_TOKEN": SECRET, "LANG": "C.UTF-8", "SKM_EXT_PROTOCOL": "1"}
        self.limits = core.Limits(max_sessions=2, idle_timeout_s=30, max_session_s=120, credit_bytes=4096,
                                  output_chunk_bytes=1024)
        self.manager = core.TerminalManager(
            self.limits, env=self.env, clock=lambda: self.clock[0], grace_s=0.3,
            audit=lambda action, target, decision, details: self.audits.append((action, target, decision, details)))
        self.addCleanup(self.manager.close_all)

    def start(self, cols=80, rows=24):
        return self.manager.start("proj-1", self.root, cols, rows)

    def with_background(self):
        """A session whose shell started ``sleep 300 &``; returns ``(session, pid of sleep)``."""
        session = self.start()
        session.write(b"sleep 300 & echo BG$!\n")
        pid = int(re.search(r"BG(\d+)", read_until(session, r"BG\d+")).group(1))
        self.assertTrue(alive(pid))
        return session, pid

    def assert_gone(self, session, pid):
        self.assertIsNotNone(session.proc.returncode)
        with self.assertRaises(ChildProcessError):  # reaped: no zombie is left for the backend
            os.waitpid(session.proc.pid, os.WNOHANG)
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(alive(pid), "a descendant of the shell survived")
        self.assertEqual(-1, session._master)


@unittest.skipUnless(core.supported(), "needs a POSIX PTY")
class TestEnvironment(Base):
    def test_shell_runs_in_the_project_root_without_secrets(self):
        session = self.start()
        session.write(b"pwd; echo T=$TERM C=$COLORTERM L=$LANG; env\n")
        text = read_until(session, r"\n\$ $")
        self.assertIn(self.root, text)
        self.assertIn("T=xterm-256color C=truecolor L=C.UTF-8", text)
        self.assertNotIn(SECRET, text)
        for name in ("SKM_TEST_SECRET", "GUI_TOKEN", "API_TOKEN", "SKM_EXT_PROTOCOL"):
            self.assertNotRegex(text, rf"(?m)^{name}=", name)

    def test_shell_environment_function(self):
        env = core.shell_environment({**self.env, "TERM": "dumb"})
        self.assertEqual("xterm-256color", env["TERM"])
        self.assertEqual("truecolor", env["COLORTERM"])
        self.assertEqual("C.UTF-8", env["LANG"])
        self.assertTrue(all(SECRET not in value for value in env.values()))
        self.assertFalse([name for name in env if name.startswith(("GUI_", "SKM_EXT_"))])

    def test_shell_choice(self):
        shells = Path(self.root) / "shells"
        shells.write_text("# shells\n/bin/sh\n/bin/ls\n", encoding="utf-8")
        self.assertEqual("/bin/ls", core.pick_shell({"SHELL": "/bin/ls"}, str(shells)))
        self.assertEqual("/bin/sh", core.pick_shell({"SHELL": "/bin/cat"}, str(shells)))  # not listed
        self.assertEqual("/bin/sh", core.pick_shell({"SHELL": "relative/sh"}, str(shells)))
        self.assertEqual("/bin/sh", core.pick_shell({}, str(shells)))
        self.assertEqual("/bin/sh", core.pick_shell({"SHELL": "/bin/ls"}, str(shells) + ".missing"))

    def test_resize_reaches_the_shell(self):
        session = self.start(cols=80, rows=24)
        session.write(b"stty size\n")
        read_until(session, r"24 80")
        session.resize(100, 30)
        session.write(b"stty size\n")
        read_until(session, r"30 100")
        self.assertEqual((100, 30), (session.cols, session.rows))
        for cols, rows in ((9, 24), (501, 24), (80, 1), (80, 201), (True, 24), ("80", 24)):
            with self.assertRaises(errors.GuiError, msg=(cols, rows)):
                session.resize(cols, rows)


class TestCreditGate(unittest.TestCase):
    def test_limit_and_validation(self):
        gate = core.CreditGate(100)
        gate.grant(60)
        gate.grant(40)
        self.assertEqual(100, gate.available)
        for bad in (1, 0, -5, True, 1.5, "7", None):
            with self.assertRaises(ValueError, msg=bad):
                gate.grant(bad)
        self.assertEqual(30, gate.take(30))
        self.assertEqual(70, gate.available)
        self.assertEqual(70, gate.take(500))
        self.assertEqual(0, gate.take(1))
        gate.grant(100)
        gate.give_back(0)


@unittest.skipUnless(core.supported(), "needs a POSIX PTY")
class TestBackpressure(Base):
    def test_no_credit_no_read(self):
        session = self.start()
        session.write(b"echo FIRST\n")
        deadline = time.monotonic() + 2
        while not session.readable_now() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
        self.assertIsNone(session.take_output())
        self.assertEqual(0, session.bytes_out)  # the master was not read at zero credit
        session.gate.grant(4096)
        self.assertIn("FIRST", read_until(session, r"FIRST"))

    def test_fast_source_is_slowed_down_ordered_and_lossless(self):
        session = self.start()
        session.write(b"seq 1 20000; echo FIN$((1+1))\n")
        received, sizes, seqs = b"", [], []
        deadline = time.monotonic() + 30
        while b"FIN2\r\n" not in received[-64:] and time.monotonic() < deadline:
            time.sleep(0.002)  # a consumer slower than the source
            if session.gate.available < 512:
                session.gate.grant(512)
            chunk = session.take_output()
            if chunk is None:
                session.wait_readable(0.05)
                continue
            seqs.append(chunk[0])
            sizes.append(len(chunk[1]))
            received += chunk[1]
            self.assertLessEqual(session.gate.available, self.limits.credit_bytes * core.CREDIT_FACTOR)
        self.assertIn(b"FIN2\r\n", received[-64:])
        self.assertEqual(list(range(len(seqs))), seqs)  # in order, without gaps
        self.assertLessEqual(max(sizes), self.limits.output_chunk_bytes)  # nothing larger is held by the server
        numbers = [int(line) for line in re.findall(rb"(?m)^(?:\$ )?(\d+)\r$", received)]
        self.assertEqual(list(range(1, 20001)), numbers)  # no byte lost
        self.assertEqual(len(received), session.bytes_out)

    def test_a_chunk_never_exceeds_the_credit(self):
        session = self.start()
        session.write(b"seq 1 2000\n")
        session.gate.grant(100)
        deadline = time.monotonic() + WAIT_S
        chunk = None
        while chunk is None and time.monotonic() < deadline:
            session.wait_readable(0.05)
            chunk = session.take_output()
        self.assertIsNotNone(chunk)
        self.assertLessEqual(len(chunk[1]), 100)
        self.assertEqual(100 - len(chunk[1]), session.gate.available)


@unittest.skipUnless(core.supported(), "needs a POSIX PTY")
class TestClosing(Base):
    def test_close_kills_the_group(self):
        session, pid = self.with_background()
        self.assertTrue(session.close("closed"))
        self.assert_gone(session, pid)
        self.assertEqual("closed", session.exit_info()["reason"])

    def test_eof_of_the_shell_then_close_kills_the_descendants(self):
        session, pid = self.with_background()
        session.write(b"exit 3\n")
        deadline = time.monotonic() + WAIT_S
        while not session.finished() and time.monotonic() < deadline:
            session.take_output() or session.wait_readable(0.05)
            session.gate.grant(4096) if session.gate.available < 4096 else None
        self.assertTrue(session.exited())
        self.assertEqual(3, session.proc.returncode)
        session.close("exit")
        self.assert_gone(session, pid)
        self.assertEqual({"code": 3, "reason": "exit"}, session.exit_info())

    def test_idle_timer_with_an_injected_clock(self):
        session, pid = self.with_background()
        self.clock[0] = 29.0
        self.assertEqual([], self.manager.reap())
        session.write(b"echo again\n")  # input is activity
        self.clock[0] = 58.0
        self.assertEqual([], self.manager.reap())
        self.clock[0] = 59.5
        self.assertEqual([session.id], self.manager.reap())
        self.assert_gone(session, pid)
        self.assertEqual("idle", session.reason)
        self.assertIsNone(self.manager.get(session.id))

    def test_output_is_activity_too(self):
        session = self.start()
        self.clock[0] = 20.0
        session.write(b"echo x\n")
        read_until(session, r"x\r\n")
        self.clock[0] = 45.0
        self.assertEqual([], self.manager.reap())

    def test_max_timer(self):
        session, pid = self.with_background()
        for moment in (50.0, 100.0, 119.0):
            self.clock[0] = moment
            session.write(b"\n")  # activity keeps the idle timer quiet
            self.assertEqual([], self.manager.reap())
        self.clock[0] = 120.0
        self.assertEqual([session.id], self.manager.reap())
        self.assert_gone(session, pid)
        self.assertEqual("max", session.reason)

    def test_stop_of_the_manager(self):
        first, pid_one = self.with_background()
        second, pid_two = self.with_background()
        self.assertEqual(2, self.manager.close_all())
        for session, pid in ((first, pid_one), (second, pid_two)):
            self.assert_gone(session, pid)
            self.assertEqual("backend_stop", session.reason)
        self.assertEqual(0, self.manager.count())
        with self.assertRaises(errors.GuiError) as caught:
            self.start()
        self.assertEqual("PERMISSION_DENIED", caught.exception.code)

    def test_a_shell_that_ignores_hangup_is_killed(self):
        session = self.start()
        session.write(b"trap '' HUP; echo ARMED\n")
        read_until(session, r"ARMED\r\n")
        started = time.monotonic()
        session.close("closed")
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(-9, session.proc.returncode)
        self.assertEqual(9, session.exit_info()["signal"])

    def test_concurrent_close_ends_once(self):
        session, pid = self.with_background()
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.manager.close(session.id, reason)))
                   for reason in ("closed", "idle", "backend_stop", "closed")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT_S)
            self.assertFalse(thread.is_alive())
        self.assert_gone(session, pid)
        self.assertEqual(4, len(results))
        self.assertEqual(1, len([a for a in self.audits if a[0] == "terminal.end"]))

    def test_io_after_close_fails_without_touching_a_reused_descriptor(self):
        session = self.start()
        session.close("closed")
        with self.assertRaises(OSError):
            session.write(b"x")
        self.assertIsNone(session.take_output())
        self.assertFalse(session.wait_readable(0.01))
        session.resize(100, 30)  # a no-op
        self.assertFalse(session.attach())


@unittest.skipUnless(core.supported(), "needs a POSIX PTY")
class TestManager(Base):
    def test_session_limit(self):
        self.start()
        self.start()
        with self.assertRaises(errors.GuiError) as caught:
            self.start()
        self.assertEqual("TERMINAL_LIMIT", caught.exception.code)
        self.assertEqual(2, self.manager.count())
        self.manager.close(self.manager.list()[0].id, "closed")
        self.start()  # a free slot again

    def test_ids_documents_and_ended_sessions(self):
        session = self.start(cols=90, rows=20)
        self.assertRegex(session.id, r"^term-[0-9a-f]{32}$")
        document = session.document()
        self.assertEqual(["session", 90, 20], [document["kind"], document["cols"], document["rows"]])
        self.assertNotIn("ended_at", document)
        ended = self.manager.close(session.id, "closed")
        self.assertIn("ended_at", ended)
        self.assertEqual(ended, self.manager.close(session.id, "closed"))  # closing again repeats the answer
        self.assertIsNone(self.manager.close("term-" + "0" * 32, "closed"))

    def test_attach_is_exclusive(self):
        session = self.start()
        self.assertTrue(session.attach())
        self.assertFalse(session.attach())
        session.detach()
        self.assertTrue(session.attach())

    def test_audit_has_metadata_and_no_content(self):
        session = self.start()
        session.write(f"echo {SECRET}\n".encode())
        read_until(session, SECRET + r"\r\n")
        self.manager.close(session.id, "closed")
        self.assertEqual(["terminal.start", "terminal.end"], [entry[0] for entry in self.audits])
        start, end = self.audits[0][3], self.audits[1][3]
        self.assertEqual({"project_id": "proj-1", "shell": "/bin/sh", "cols": 80, "rows": 24}, start)
        self.assertEqual({"project_id", "reason", "exit_code", "bytes_in", "bytes_out", "duration_s", "signal"},
                         set(end))
        self.assertGreater(end["bytes_in"], 0)
        self.assertGreater(end["bytes_out"], 0)
        self.assertNotIn(SECRET, json.dumps(self.audits))

    def test_invalid_sizes_are_refused_before_a_process_starts(self):
        for cols, rows in ((9, 24), (80, 201)):
            with self.assertRaises(errors.GuiError):
                self.manager.start("proj-1", self.root, cols, rows)
        self.assertEqual(0, self.manager.count())

    def test_the_log_of_the_module_never_sees_the_content(self):
        with self.assertNoLogs("gui", level="DEBUG"):
            session = self.start()
            session.write(f"echo {SECRET}\n".encode())
            read_until(session, SECRET)
            self.manager.close(session.id, "closed")


class TestSettings(unittest.TestCase):
    def test_defaults_and_environment_layer(self):
        from gui import settings

        with tempfile.TemporaryDirectory() as tmp:
            env = {"HOME": tmp, "SKM_HOME": tmp + "/skm"}
            self.assertEqual(settings.Terminal(False, 2, 900, 14400, 65536, 16384), settings.load(env).terminal)
            enabled = settings.load({**env, "SKM_GUI_TERMINAL__ENABLED": "true", "SKM_GUI_TERMINAL__MAX_SESSIONS": "5"})
            self.assertTrue(enabled.terminal.enabled)
            self.assertEqual(5, enabled.terminal.max_sessions)
            from aicore.config import ConfigError

            with self.assertRaises(ConfigError):
                settings.load({**env, "SKM_GUI_TERMINAL__MAX_SESSIONS": "9"})
            with self.assertRaises(ConfigError):
                settings.load({**env, "SKM_GUI_TERMINAL__CREDIT_BYTES": "100"})


class TestPlatform(unittest.TestCase):
    def test_import_and_refusal_without_a_pty(self):
        manager = core.TerminalManager(core.Limits(), env={})
        with mock.patch.object(core, "supported", return_value=False):
            with self.assertRaises(errors.GuiError) as caught:
                manager.start("proj-1", "/", 80, 24)
        self.assertEqual("PERMISSION_DENIED", caught.exception.code)
        self.assertIn("POSIX PTY", caught.exception.message)
        self.assertEqual(0, manager.count())

    def test_non_posix_is_unsupported(self):
        with mock.patch.object(core.os, "name", "nt"):
            self.assertFalse(core.supported())

    def test_launcher_is_the_documented_one(self):
        for needle in ("os.setsid()", "TIOCSCTTY", "os.execv"):
            self.assertIn(needle, core.LAUNCHER)
        compile(core.LAUNCHER, "<launcher>", "exec")


if __name__ == "__main__":
    unittest.main()
