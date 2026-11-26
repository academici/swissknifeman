"""aicore.ext.process.run_json: one JSON object out, no hangs, no leftovers, no leaked secrets."""
import os
import sys
import json
import tempfile
import time
import unittest
import urllib.parse
import uuid
from pathlib import Path

from aicore.ext.process import GRACE_S, MAX_STDOUT, STDERR_TAIL, ProcessResult, run_json

PROCS = Path(__file__).resolve().parent / "fixtures" / "procs"
SENTINEL = "s3cr3t-" + uuid.uuid4().hex


def proc(name, *args):
    return [sys.executable, str(PROCS / name), *args]


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_gone(pid, limit=2.0):
    """True when ``pid`` is no longer a running process (a zombie awaiting its reaper counts as gone)."""
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if not alive(pid) or _is_zombie(pid):
            return True
        time.sleep(0.02)
    return not alive(pid) or _is_zombie(pid)


def _is_zombie(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    return text.rsplit(")", 1)[-1].split()[0] == "Z"


class RunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pidfile = str(Path(self.tmp.name) / "grandchild.pid")

    def run_proc(self, argv, payload=None, **kwargs):
        kwargs.setdefault("deadline_s", 10)
        kwargs.setdefault("env", None)
        kwargs.setdefault("cwd", None)
        return run_json(argv, {} if payload is None else payload, **kwargs)

    def grandchild(self):
        return int(Path(self.pidfile).read_text(encoding="utf-8").strip())


class TestProtocol(RunCase):
    def test_echo(self):
        result = self.run_proc(proc("echo.py"), {"a": 1, "b": ["x", "é"]})
        self.assertIsInstance(result, ProcessResult)
        self.assertTrue(result.ok, result)
        self.assertIsNone(result.code)
        self.assertEqual(result.exit, 0)
        self.assertEqual(result.document, {"a": 1, "b": ["x", "é"]})
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_garbage_is_protocol_error(self):
        result = self.run_proc(proc("garbage.py"))
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "PROTOCOL_STDOUT")
        self.assertIsNone(result.document)

    def test_two_documents_are_protocol_error(self):
        result = self.run_proc(proc("two_docs.py"))
        self.assertEqual(result.code, "PROTOCOL_STDOUT")
        self.assertIsNone(result.document)

    def test_non_object_is_protocol_error(self):
        for text in ("[1]", "3", '"s"', "null"):
            result = self.run_proc([sys.executable, "-c", f"print({text!r})"])
            self.assertEqual(result.code, "PROTOCOL_STDOUT", text)

    def test_invalid_utf8_is_protocol_error(self):
        result = self.run_proc([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')"])
        self.assertEqual(result.code, "PROTOCOL_STDOUT")

    def test_empty_stdout_gives_no_document(self):
        result = self.run_proc([sys.executable, "-c", "pass"])
        self.assertTrue(result.ok, result)
        self.assertIsNone(result.document)

    def test_huge_stdout_is_too_large(self):
        result = self.run_proc(proc("big_stdout.py", str(40 * 1024 * 1024)))
        self.assertEqual(result.code, "PROTOCOL_STDOUT_TOO_LARGE")
        self.assertIsNone(result.document)
        self.assertFalse(result.timed_out)

    def test_stdout_limit_is_configurable(self):
        result = self.run_proc(proc("echo.py"), {"k": "v" * 100}, max_stdout=50)
        self.assertEqual(result.code, "PROTOCOL_STDOUT_TOO_LARGE")
        result = self.run_proc(proc("echo.py"), {"k": "v" * 100}, max_stdout=500)
        self.assertTrue(result.ok, result)
        self.assertEqual(MAX_STDOUT, 1048576)

    def test_nonzero_exit(self):
        result = self.run_proc(proc("exit_code.py", "3"))
        self.assertFalse(result.ok)
        self.assertEqual((result.code, result.exit), ("PROCESS_EXIT", 3))
        self.assertEqual(result.document, {"done": True})

    def test_missing_command_is_spawn_error(self):
        result = self.run_proc([str(Path(self.tmp.name) / "no-such-command")])
        self.assertEqual(result.code, "PROCESS_SPAWN")
        self.assertIsNone(result.exit)
        self.assertFalse(result.ok)

    def test_not_executable_and_bad_cwd_are_spawn_errors(self):
        plain = Path(self.tmp.name) / "plain.txt"
        plain.write_text("x", encoding="utf-8")
        self.assertEqual(self.run_proc([str(plain)]).code, "PROCESS_SPAWN")
        self.assertEqual(self.run_proc([sys.executable, "-c", "pass"], cwd=str(plain)).code, "PROCESS_SPAWN")

    def test_child_that_ignores_stdin_does_not_break_the_host(self):
        for _ in range(3):
            result = self.run_proc(proc("ignores_stdin.py"), {"pad": "p" * 200000})
            self.assertTrue(result.ok, result)
            self.assertEqual(result.document, {"ok": True})

    def test_large_payload_is_delivered(self):
        payload = {"pad": "q" * 300000}
        result = self.run_proc(proc("echo.py"), payload, max_stdout=2 * 1024 * 1024)
        self.assertTrue(result.ok, result)
        self.assertEqual(result.document, payload)

    def test_env_and_cwd_are_used(self):
        code = "import json, os, sys; json.dump({'x': os.environ.get('SKM_TEST_X'), 'cwd': os.getcwd()}, sys.stdout)"
        env = dict(os.environ, SKM_TEST_X="1")
        result = self.run_proc([sys.executable, "-c", code], env=env, cwd=self.tmp.name)
        self.assertEqual(result.document, {"x": "1", "cwd": os.path.realpath(self.tmp.name)})

    def test_env_none_is_a_copy_of_os_environ(self):
        os.environ["SKM_TEST_COPY"] = "yes"
        self.addCleanup(os.environ.pop, "SKM_TEST_COPY", None)
        code = "import os; print('{\"v\": \"%s\"}' % os.environ.get('SKM_TEST_COPY'))"
        self.assertEqual(self.run_proc([sys.executable, "-c", code], env=None).document, {"v": "yes"})

    def test_invalid_arguments_raise(self):
        for argv in ([], "echo", [1], None):
            with self.assertRaises((ValueError, TypeError)):
                run_json(argv, {}, deadline_s=1, env=None, cwd=None)
        with self.assertRaises(ValueError):
            run_json(["x"], {}, deadline_s=0, env=None, cwd=None)
        with self.assertRaises(TypeError):
            run_json(["x"], [1], deadline_s=1, env=None, cwd=None)
        with self.assertRaises(TypeError):
            run_json(["x"], {"f": 1.5}, deadline_s=1, env=None, cwd=None)


class TestDeadlineAndGroup(RunCase):
    def test_timeout_kills_child_and_grandchild(self):
        result = self.run_proc(proc("sleeper_with_grandchild.py", self.pidfile), deadline_s=1)
        self.assertEqual(result.code, "PROCESS_TIMEOUT")
        self.assertTrue(result.timed_out)
        self.assertFalse(result.ok)
        grandchild = self.grandchild()
        self.assertTrue(wait_gone(grandchild), "the grandchild survived the call")

    def test_child_exit_kills_leftover_group_members(self):
        started = time.monotonic()
        result = self.run_proc(proc("leaves_grandchild.py", self.pidfile), deadline_s=10)
        self.assertLess(time.monotonic() - started, GRACE_S + 3, "the call waited for the grandchild")
        self.assertTrue(result.ok, result)
        self.assertEqual(result.document, {})
        self.assertTrue(wait_gone(self.grandchild()), "the leftover grandchild survived the call")

    def test_sleep_command_is_killed_on_timeout(self):
        result = self.run_proc([sys.executable, "-c", "import time; time.sleep(30)"], deadline_s=1)
        self.assertEqual(result.code, "PROCESS_TIMEOUT")
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration_ms, 3000)

    def test_sigterm_ignoring_child_is_killed_after_grace(self):
        result = self.run_proc(proc("ignores_term.py"), deadline_s=0.5, grace_s=0.5)
        self.assertEqual(result.code, "PROCESS_TIMEOUT")
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration_ms, 3000)
        self.assertEqual(result.exit, -9)

    def test_child_that_closed_its_pipes_is_still_bound_by_the_deadline(self):
        result = self.run_proc(proc("closes_pipes_then_sleeps.py"), deadline_s=0.5, grace_s=0.5)
        self.assertEqual(result.code, "PROCESS_TIMEOUT")
        self.assertLess(result.duration_ms, 3000)

    def test_killing_does_not_touch_the_hosts_own_group(self):
        before = os.getpgrp()
        self.run_proc(proc("sleeper_with_grandchild.py", self.pidfile), deadline_s=0.5, grace_s=0.5)
        self.assertEqual(os.getpgrp(), before)


class TestStderr(RunCase):
    def test_flood_does_not_block_and_keeps_the_tail(self):
        started = time.monotonic()
        result = self.run_proc(proc("stderr_flood.py"))
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(result.ok, result)
        self.assertLessEqual(len(result.stderr_tail.encode("utf-8")), STDERR_TAIL)
        self.assertTrue(result.stderr_tail.rstrip().endswith("END-OF-STDERR"))

    def test_tail_size_is_configurable(self):
        result = self.run_proc(proc("stderr_flood.py"), stderr_tail=64)
        self.assertLessEqual(len(result.stderr_tail.encode("utf-8")), 64)
        result = self.run_proc(proc("stderr_flood.py"), stderr_tail=0)
        self.assertEqual(result.stderr_tail, "")

    def test_secret_in_stderr_is_replaced(self):
        result = self.run_proc(proc("print_secret_stderr.py", SENTINEL), secrets_to_redact=[SENTINEL])
        self.assertNotIn(SENTINEL, result.stderr_tail)
        self.assertIn("token=*** end", result.stderr_tail)
        self.assertNotIn(SENTINEL, repr(result))

    def test_secret_is_kept_when_not_declared(self):
        result = self.run_proc(proc("print_secret_stderr.py", SENTINEL))
        self.assertIn(SENTINEL, result.stderr_tail)

    def test_secret_across_the_tail_boundary_is_not_leaked(self):
        """No whole secret and no fragment of it (a prefix or a suffix) is left, wherever the tail is cut."""
        secret = "S" + SENTINEL
        for filler in range(0, 220, 3):
            result = self.run_proc(proc("print_secret_stderr.py", secret, str(filler)),
                                   secrets_to_redact=[secret], stderr_tail=64)
            tail = result.stderr_tail
            self.assertNotIn(secret, tail, filler)
            for size in range(6, len(secret)):
                self.assertFalse(tail.startswith(secret[-size:]), (filler, size))
                self.assertFalse(tail.endswith(secret[:size]), (filler, size))

    def test_repeated_secret_does_not_expose_a_cut_fragment(self):
        """Redaction shrinks the kept buffer; a fragment of a secret cut by the buffer head must not surface."""
        secret = "S" + SENTINEL
        code = ("import sys; sys.stderr.write('.' * int(sys.argv[2]) + (sys.argv[1] + '.') * 12)")
        for filler in range(0, 80, 7):
            result = self.run_proc([sys.executable, "-c", code, secret, str(filler)],
                                   secrets_to_redact=[secret], stderr_tail=200)
            tail = result.stderr_tail
            self.assertNotIn(secret, tail, filler)
            for size in range(6, len(secret)):
                self.assertFalse(tail.startswith(secret[-size:]), (filler, size))

    def test_escaped_spellings_of_the_secret_are_replaced(self):
        """JSON escapes of any library (Python, PHP ``\\/``, Go ``\\u0026``), mixed, and percent-encoding."""
        secret = 'sk_live/a&b"c\\\u00e9' + SENTINEL
        escaped_all = "".join("\\u%04x" % ord(char) for char in secret)
        escaped_some = secret.replace("\\", "\\\\").replace("/", "\\/").replace("&", "\\u0026").replace('"', '\\"')
        spellings = [secret, json.dumps(secret)[1:-1], json.dumps(secret, ensure_ascii=False)[1:-1], escaped_all,
                     escaped_all.upper().replace("\\U", "\\u"), escaped_some, urllib.parse.quote(secret, safe="")]
        code = "import sys; sys.stderr.write('<' + sys.argv[1] + '>')"
        for spelling in spellings:
            result = self.run_proc([sys.executable, "-c", code, spelling], secrets_to_redact=[secret])
            self.assertEqual(result.stderr_tail, "<***>", spelling)

    def test_astral_character_in_a_secret_is_replaced(self):
        secret = "pre-\U0001f511-" + SENTINEL
        code = "import json, sys; sys.stderr.write(json.dumps(sys.argv[1]) + sys.argv[1])"
        result = self.run_proc([sys.executable, "-c", code, secret], secrets_to_redact=[secret])
        self.assertEqual(result.stderr_tail, '"***"***')

    def test_non_utf8_secret_does_not_raise(self):
        secret = "sekret-\udcff-" + SENTINEL
        result = self.run_proc(proc("echo.py"), secrets_to_redact=[secret])
        self.assertTrue(result.ok, result)
        code = "import os, sys; sys.stderr.buffer.write(b'sekret-\\xff-' + sys.argv[1].encode())"
        result = self.run_proc([sys.executable, "-c", code, SENTINEL], secrets_to_redact=[secret])
        self.assertEqual(result.stderr_tail, "***")

    def test_json_escaped_surrogateescape_secret_is_replaced(self):
        secret = "token-\udcff-" + SENTINEL
        code = "import json, sys; sys.stderr.write(json.dumps(sys.argv[1]).replace('udcff', sys.argv[2]))"
        for case in ("udcff", "uDCFF", "uDcFf"):
            result = self.run_proc([sys.executable, "-c", code, "token-\udcff-" + SENTINEL, case],
                                   secrets_to_redact=[secret])
            self.assertNotIn(SENTINEL, result.stderr_tail, case)

    def test_lone_surrogates_in_a_secret_do_not_raise(self):
        for char in ("\ud800", "\udc7f", "\udd00", "\udfff"):
            result = self.run_proc(proc("echo.py"), secrets_to_redact=["token-" + char + "-" + SENTINEL])
            self.assertTrue(result.ok, (char, result))

    def test_hostile_stderr_cannot_stall_the_redaction(self):
        """Runs of backslashes (an escape and a literal at once) and one long secret must stay fast."""
        code = "import sys; sys.stderr.write('\\\\' * 200000 + 'a' * 200000)"
        for secret in ("\\" * 40 + "X", "a" * 4000 + "b", "%" * 100 + "/" * 100 + "a"):
            started = time.monotonic()
            result = self.run_proc([sys.executable, "-c", code], secrets_to_redact=[secret])
            self.assertTrue(result.ok, result)
            self.assertLess(time.monotonic() - started, 3.0, secret[:8])

    def test_secret_in_the_document_is_replaced(self):
        result = self.run_proc(proc("echo_secret_document.py", SENTINEL), secrets_to_redact=[SENTINEL])
        self.assertTrue(result.ok, result)
        self.assertNotIn(SENTINEL, repr(result))
        self.assertEqual(result.document, {"note": "got ***", "list": ["***"]})

    def test_secret_that_is_a_number_or_literal_is_replaced_in_the_document(self):
        code = "print('{\"n\": 998877665544332211, \"f\": 123456.5, \"t\": true, \"s\": \"998877665544332211\"}')"
        result = self.run_proc([sys.executable, "-c", code], secrets_to_redact=["998877665544332211", "123456.5"])
        self.assertTrue(result.ok, result)
        self.assertEqual(result.document, {"n": "***", "f": "***", "t": True, "s": "***"})
        self.assertNotIn("998877665544332211", repr(result))

    def test_deeply_nested_document_is_a_protocol_error_not_an_exception(self):
        code = "import sys; sys.stdout.write('[' * 200000 + ']' * 200000 + chr(10))"
        for secrets in ((), (SENTINEL,)):
            result = self.run_proc([sys.executable, "-c", code], secrets_to_redact=secrets)
            self.assertEqual(result.code, "PROTOCOL_STDOUT")
        code = "import sys; sys.stdout.write('{\"a\":' * 3000 + '1' + '}' * 3000)"
        result = self.run_proc([sys.executable, "-c", code], secrets_to_redact=[SENTINEL])
        self.assertIn(result.code, (None, "PROTOCOL_STDOUT"))

    def test_nan_and_infinite_limits_are_refused(self):
        for name in ("deadline_s", "grace_s"):
            for bad in (float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    run_json(["x"], {}, **{"deadline_s": 1, "env": None, "cwd": None, name: bad})

    def test_secret_is_absent_from_every_failure_result(self):
        for argv in (proc("print_secret_stderr.py", SENTINEL), proc("garbage.py", SENTINEL),
                     [sys.executable, "-c", f"import sys; sys.stderr.write({SENTINEL!r}); sys.exit(2)"]):
            result = self.run_proc(argv, secrets_to_redact=[SENTINEL])
            self.assertNotIn(SENTINEL, repr(result))


if __name__ == "__main__":
    unittest.main()
