"""`gui serve --sidecar` as a real process: handshake on stdin, one GUI_READY line, desktop mode over TCP, no secret
in argv, environ, state folder or logs, shutdown by EOF on stdin and by SIGTERM, refusal of a second backend."""
import http.client
import json
import os
import secrets
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import aicore

import gui
from gui import deps

READY_TIMEOUT_S = 30


def handshake(secret, port=0, **changes):
    return (json.dumps({"v": 1, "secret": secret, "port": port, "shell_version": "0.1.0", **changes}) + "\n").encode()


def request(port, path, headers=None, method="GET", body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class SidecarCase(unittest.TestCase):
    def setUp(self):
        try:
            site = deps.site_dir()
        except deps.GuiDepsError as error:
            self.skipTest(f"gui deps path is unavailable: {error}")
        deps.activate()  # installed packages are required: fail here, not by a timeout
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "home").mkdir()
        (self.tmp / "units").mkdir()
        self.secret = secrets.token_urlsafe(32)
        self.env = {**os.environ, "HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"),
                    "SKM_UNITS_PATH": str(self.tmp / "units"), "GUI_PYDEPS_DIR": str(site),
                    "PYTHONPATH": os.pathsep.join(str(Path(module.__file__).resolve().parents[1])
                                                  for module in (gui, aicore))}
        self.env.pop("SKM_PROJECT_ROOT", None)
        self.state = self.tmp / "skm" / "state" / "gui"
        self.processes = []
        self.addCleanup(self.stop_all)

    def start(self, *extra, secret=None, data=None, close_stdin=False):
        process = subprocess.Popen([sys.executable, "-m", "gui.cli", "serve", "--sidecar", *extra], env=self.env,
                                   cwd=str(self.tmp), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        self.processes.append(process)
        process.stdin.write(handshake(secret or self.secret) if data is None else data)
        process.stdin.flush()
        if close_stdin:
            process.stdin.close()
        return process

    def ready(self, process):
        """The decoded GUI_READY line (waits up to READY_TIMEOUT_S)."""
        ready, _, _ = select.select([process.stdout], [], [], READY_TIMEOUT_S)
        if not ready:
            process.kill()
            self.fail("no GUI_READY line; stderr: " + process.stderr.read().decode(errors="replace"))
        line = process.stdout.readline().decode()
        if not line.startswith("GUI_READY "):  # read stderr only on failure: the process is alive and its stderr stays open
            process.kill()
            self.fail(f"not a GUI_READY line: {line!r}; stderr: " + process.stderr.read().decode(errors="replace"))
        self.assertTrue(line.endswith("\n"))
        return json.loads(line[len("GUI_READY "):])

    def stop_all(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass

    def bearer(self):
        return {"Authorization": f"Bearer {self.secret}"}


class TestSidecar(SidecarCase):
    def test_ready_desktop_mode_and_no_secret_anywhere(self):
        process = self.start()
        ready = self.ready(process)
        self.assertEqual({"v", "port", "epoch", "pid", "backend", "gui_protocol"}, set(ready))
        self.assertEqual(process.pid, ready["pid"])
        port = ready["port"]
        self.assertGreater(port, 0)

        # the port answers right after the line
        status, _, body = request(port, "/v1/bootstrap", self.bearer())
        self.assertEqual(200, status)
        document = json.loads(body)
        self.assertEqual(("desktop", ready["epoch"], {"version": "0.1.0"}),
                         (document["mode"], document["epoch"], document["shell"]))
        self.assertEqual(401, request(port, "/v1/bootstrap")[0])
        self.assertEqual(404, request(port, "/?t=anything")[0])
        self.assertEqual(404, request(port, "/", self.bearer())[0])
        status, _, body = request(port, "/v1/session/tokens", {**self.bearer(), "Content-Type": "application/json"},
                                  "POST", b"{}")
        self.assertEqual((403, "PERMISSION_DENIED"), (status, json.loads(body)["error"]["code"]))

        # no secret in argv, environ or any file of the state and the home
        secret = self.secret.encode()
        self.assertNotIn(secret, Path(f"/proc/{process.pid}/cmdline").read_bytes())
        self.assertNotIn(secret, Path(f"/proc/{process.pid}/environ").read_bytes())
        self.assertFalse((self.state / "backend.json").exists())
        for folder in (self.tmp / "skm", self.tmp / "home"):
            for path in folder.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret, path.read_bytes(), str(path))

        # EOF on stdin ends the backend gracefully; stdout stayed empty after READY
        process.stdin.close()
        self.assertEqual(0, process.wait(timeout=20))
        self.assertEqual(b"", process.stdout.read())
        self.assertNotIn(secret, process.stderr.read())
        self.assertFalse((self.state / "backend.json").exists())

    def test_fixed_port_from_the_handshake(self):
        probe = __import__("socket").socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        process = self.start(data=handshake(self.secret, port=port))
        self.assertEqual(port, self.ready(process)["port"])

    def test_sigterm_is_graceful(self):
        process = self.start()
        self.ready(process)
        process.send_signal(signal.SIGTERM)
        self.assertEqual(0, process.wait(timeout=20))
        self.assertEqual(b"", process.stdout.read())

    def test_closed_stdin_after_the_handshake_stops_the_backend(self):
        process = self.start(close_stdin=True)
        self.assertEqual(0, process.wait(timeout=READY_TIMEOUT_S))
        self.assertTrue(process.stdout.read().startswith(b"GUI_READY "))

    def test_second_sidecar_is_refused(self):
        first = self.start()
        self.ready(first)
        second = self.start()
        self.assertEqual(1, second.wait(timeout=READY_TIMEOUT_S))
        self.assertIn(b"BACKEND_RUNNING", second.stderr.read())
        self.assertEqual(b"", second.stdout.read())
        self.assertIsNone(first.poll())

    def test_project_flag_registers_the_project(self):
        project = self.tmp / "proj"
        (project / ".git").mkdir(parents=True)
        process = self.start("--project", str(project))
        port = self.ready(process)["port"]
        status, _, body = request(port, "/v1/projects", self.bearer())
        self.assertEqual(200, status)
        self.assertEqual([str(project)], [entry["root"] for entry in json.loads(body)["projects"]])


class TestRefusals(SidecarCase):
    def refused(self, process, code=2):
        self.assertEqual(code, process.wait(timeout=READY_TIMEOUT_S))
        self.assertEqual(b"", process.stdout.read())
        error = process.stderr.read().decode()
        self.assertTrue(error.startswith("SIDECAR_HANDSHAKE_INVALID: "), error)
        self.assertNotIn(self.secret, error)
        return error

    def test_invalid_handshakes(self):
        cases = {
            "not json": b"nope\n",
            "version": handshake(self.secret, v=2),
            "short secret": handshake("A" * 31),
            "port": handshake(self.secret, port=70000),
            "shell version": handshake(self.secret, shell_version="x"),
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.refused(self.start(data=data))
        self.assertFalse((self.state / "backend.json").exists())

    def test_stdin_closed_without_a_line(self):
        process = self.start(data=b"", close_stdin=True)
        self.assertIn("closed", self.refused(process))

    def test_no_line_in_ten_seconds(self):
        process = self.start(data=b"")  # stdin stays open and silent
        started = time.monotonic()
        error = self.refused(process)
        self.assertIn("no handshake line", error)
        self.assertGreaterEqual(time.monotonic() - started, 9)

    def test_sidecar_refuses_port_and_detached(self):
        for flag in (["--port", "5000"], ["--detached"]):
            with self.subTest(flag):
                process = self.start(*flag)
                self.assertEqual(2, process.wait(timeout=READY_TIMEOUT_S))
                self.assertIn(b"usage", process.stderr.read())
                self.assertEqual(b"", process.stdout.read())


if __name__ == "__main__":
    unittest.main()
