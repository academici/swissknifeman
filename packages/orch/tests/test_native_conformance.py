"""Process scenarios of the native binding, proven on fake argv (a Python one-liner), never on a live provider.

The catalogue points at these tests: ``child-process-cleanup``, ``stdout-stderr-framing`` and
``workspace-permissions``. The roles are short ``python -c`` scripts that start in their own session, as a provider
CLI does.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import process, scope  # noqa: E402

RESULT = '{"type":"result","result":"done","usage":{}}'
# Starts a grandchild that sleeps, records its pid in argv[1], then waits like a role that never finishes.
SPAWNS = ("import subprocess,sys,time\n"
          "kid=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
          "open(sys.argv[1],'w').write(str(kid.pid))\n"
          "sys.stdin.read()\n"
          "time.sleep(60)")
# Gives its result, leaves a background task behind and does not exit.
SPAWNS_AFTER_RESULT = ("import subprocess,sys,time\n"
                       "kid=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
                       "open(sys.argv[1],'w').write(str(kid.pid))\n"
                       "sys.stdin.read()\n"
                       f"print('{RESULT}', flush=True)\n"
                       "time.sleep(60)")


def alive(pid: int) -> bool:
    """Whether ``pid`` still runs; a zombie waiting for its reaper is over."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as handle:
            return handle.read().decode("utf-8", "replace").rpartition(")")[2].split()[0] != "Z"
    except FileNotFoundError:
        return False
    except OSError:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def gone_soon(pid: int, seconds: float = 10.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


class RoleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.dir = self.base / "work"  # the working directory of the role; the stream files stay outside it
        self.dir.mkdir()
        self.raw = self.base / "raw"
        old = process.POLL_S
        process.POLL_S = 0.2
        self.addCleanup(setattr, process, "POLL_S", old)

    def role(self, code, *args, transport="stream-json", **limits):
        limits.setdefault("timeout_s", 0)
        return process.run_role([sys.executable, "-c", code, *args], "prompt", transport=transport, cwd=self.dir,
                                raw_path=self.raw / "out.jsonl", **limits)


@unittest.skipUnless(sys.platform.startswith("linux"), "reads /proc")
class ChildProcessCleanupTests(RoleCase):
    def bystander(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)

        def stop():
            other.kill()
            other.wait()

        self.addCleanup(stop)
        return other

    def test_a_stopped_role_takes_its_descendants_with_it_and_only_them(self):
        other = self.bystander()
        pidfile = self.base / "kid.pid"
        run = self.role(SPAWNS, str(pidfile), idle_timeout_s=1)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no output for 1 s"))
        kid = int(pidfile.read_text(encoding="utf-8"))
        self.assertTrue(gone_soon(kid), "the grandchild of the role outlived it")
        self.assertTrue(alive(other.pid), "a process outside the role was stopped")

    def test_a_role_that_lingers_after_its_result_leaves_no_descendants(self):
        other = self.bystander()
        pidfile = self.base / "kid.pid"
        run = self.role(SPAWNS_AFTER_RESULT, str(pidfile), result_grace_s=1)
        self.assertEqual((run.text, run.lingered, run.error), ("done", True, None))
        self.assertTrue(gone_soon(int(pidfile.read_text(encoding="utf-8"))))
        self.assertTrue(alive(other.pid))

    def test_a_cancelled_role_leaves_no_descendants(self):
        import threading
        cancel = threading.Event()
        pidfile = self.base / "kid.pid"
        threading.Timer(1.5, cancel.set).start()
        run = self.role(SPAWNS, str(pidfile), cancel=cancel)
        self.assertEqual(run.error, "CANCELLED")
        self.assertTrue(gone_soon(int(pidfile.read_text(encoding="utf-8"))))


class StdoutStderrFramingTests(RoleCase):
    SPLIT = "import sys\nsys.stdin.read()\nprint('from-stdout')\nprint('from-stderr', file=sys.stderr)\nsys.exit(%d)"

    def test_the_two_streams_land_in_two_files_without_mixing(self):
        run = self.role(self.SPLIT % 0, transport="text")
        self.assertIsNone(run.error, run.detail)
        self.assertEqual(run.text, "from-stdout")
        self.assertEqual((self.raw / "out.jsonl").read_text(encoding="utf-8"), "from-stdout\n")
        self.assertEqual((self.raw / "out.stderr").read_text(encoding="utf-8"), "from-stderr\n")

    def test_a_failure_is_explained_by_stderr_and_never_by_stdout(self):
        run = self.role(self.SPLIT % 3, transport="text")
        self.assertEqual(run.error, "ROLE_FAILED")
        self.assertIn("exit 3", run.detail)
        self.assertIn("from-stderr", run.detail)
        self.assertNotIn("from-stdout", run.detail)

    def test_stream_lines_become_events_and_stderr_noise_does_not(self):
        code = ("import sys\nsys.stdin.read()\nprint('not json noise', file=sys.stderr)\n"
                f"print('{RESULT}')\nprint('{{\"type\":\"result\",\"result\":\"late\"}}', file=sys.stderr)")
        run = self.role(code)
        self.assertIsNone(run.error, run.detail)
        self.assertEqual(run.text, "done")


class WorkspacePermissionTests(RoleCase):
    def git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.dir), check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                            "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(self.dir)})

    def test_what_a_role_wrote_outside_its_write_set_is_found_from_the_tree(self):
        self.git("init", "-q")
        (self.dir / "kept.txt").write_text("kept", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        code = ("import os,sys\nsys.stdin.read()\nos.makedirs('allowed',exist_ok=True)\n"
                "open('allowed/a.txt','w').write('a')\nopen('stray.txt','w').write('s')\n"
                "open('kept.txt','w').write('changed')\n"
                f"print('{RESULT}')")
        run = self.role(code)
        self.assertIsNone(run.error, run.detail)
        found = scope.dirty(self.dir)
        self.assertEqual(scope.outside(found, ["allowed/**"]), ["kept.txt", "stray.txt"])
        self.assertEqual(scope.outside(found, ["allowed/", "kept.txt", "stray.txt"]), [])

    def test_a_role_confined_to_its_write_set_is_clean(self):
        self.assertEqual(scope.outside(["allowed/a.txt", "allowed/deep/b.txt"], ["allowed/**"]), [])
        self.assertEqual(scope.outside(["allowed/a.txt"], []), [])  # no write set named: nothing to enforce
        self.assertEqual(scope.outside(["../escape.txt"], ["allowed/**"]), ["../escape.txt"])


if __name__ == "__main__":
    unittest.main()
