"""`gui serve` and `gui open` as real processes: the URL line, the token exchange over TCP, single instance,
graceful SIGTERM and reuse of a live backend."""
import http.client
import json
import os
import re
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
from gui.backend import BackendState, InstanceLock, read_runtime  # noqa: F401 - imported for the lock test

MODULE_ROOT = Path(__file__).resolve().parents[1]


def setUpModule():
    deps.activate()  # the serve process needs the packages too: fail here, not by a timeout


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "home").mkdir()
        (self.tmp / "units").mkdir()
        self.env = {**os.environ, "HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"),
                    "SKM_UNITS_PATH": str(self.tmp / "units"), "GUI_PYDEPS_DIR": str(deps.site_dir()),
                    "PYTHONPATH": os.pathsep.join(str(Path(module.__file__).resolve().parents[1])
                                                  for module in (gui, aicore))}
        self.env.pop("SKM_PROJECT_ROOT", None)
        self.state = self.tmp / "skm" / "state" / "gui"
        self.processes = []
        self.addCleanup(self.stop_all)

    def gui(self, *argv, **kwargs):
        return subprocess.run([sys.executable, "-m", "gui.cli", *argv], env=self.env, cwd=str(self.tmp),
                              capture_output=True, text=True, timeout=60, **kwargs)

    def serve(self, *argv):
        process = subprocess.Popen([sys.executable, "-m", "gui.cli", "serve", "--no-browser", *argv], env=self.env,
                                   cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        line = process.stdout.readline()
        self.assertTrue(line.startswith("GUI_URL "), line + process.stderr.read() if not line else line)
        return process, line.split(" ", 1)[1].strip()

    def stop_all(self):
        for process in self.processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
            for stream in (process.stdout, process.stderr):
                if stream:
                    stream.close()
        info = read_runtime(self.state)
        if info and info["pid"] not in [p.pid for p in self.processes]:
            try:
                os.kill(info["pid"], signal.SIGTERM)
            except OSError:
                pass


def get(port, path, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class TestServe(CliCase):
    def test_url_exchange_single_instance_and_sigterm(self):
        process, url = self.serve()
        match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/\?t=([A-Za-z0-9_-]+)", url)
        self.assertIsNotNone(match, url)
        port, token = int(match.group(1)), match.group(2)
        info = read_runtime(self.state)
        self.assertEqual((process.pid, port), (info["pid"], info["port"]))
        self.assertEqual(0o600, os.stat(self.state / "backend.json").st_mode & 0o777)

        status, headers, _ = get(port, f"/?t={token}")
        self.assertEqual(303, status)
        cookie = headers["set-cookie"].split(";", 1)[0]
        self.assertTrue(cookie.startswith("skm_gui_session="))
        status, _, body = get(port, "/v1/bootstrap", {"Cookie": cookie})
        self.assertEqual(200, status)
        self.assertEqual(info["epoch"], json.loads(body)["epoch"])
        self.assertEqual(401, get(port, f"/?t={token}")[0])
        self.assertEqual(403, get(port, "/v1/bootstrap", {"Cookie": cookie, "Host": f"evil.example:{port}"})[0])

        second = self.gui("serve", "--no-browser")
        self.assertEqual(1, second.returncode)
        self.assertIn("BACKEND_RUNNING", second.stderr)

        process.send_signal(signal.SIGTERM)
        self.assertEqual(0, process.wait(timeout=15))
        self.assertFalse((self.state / "backend.json").exists())
        log = (self.state / "backend.log")
        if log.exists():
            self.assertNotIn(info["session_secret"], log.read_text())

    def test_project_flag_registers_the_project(self):
        project = self.tmp / "proj"
        (project / ".git").mkdir(parents=True)
        process, url = self.serve("--project", str(project))
        port = int(re.search(r":(\d+)/", url).group(1))
        info = read_runtime(self.state)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", "/v1/projects", headers={"Authorization": f"Bearer {info['session_secret']}"})
        listing = json.loads(connection.getresponse().read())
        connection.close()
        self.assertEqual([str(project)], [entry["root"] for entry in listing["projects"]])


class TestOpen(CliCase):
    def test_open_reuses_a_live_backend(self):
        process, url = self.serve()
        port = re.search(r":(\d+)/", url).group(1)
        opened = self.gui("open", "--no-browser")
        self.assertEqual(0, opened.returncode, opened.stderr)
        line = opened.stdout.strip().splitlines()[-1]
        self.assertTrue(line.startswith(f"GUI_URL http://127.0.0.1:{port}/?t="), line)
        self.assertNotEqual(url, line.split(" ", 1)[1])
        self.assertEqual(process.pid, read_runtime(self.state)["pid"])

    def test_open_starts_a_detached_backend_and_registers_the_project(self):
        project = self.tmp / "proj"
        (project / ".swissknifeman").mkdir(parents=True)
        opened = self.gui("open", "--no-browser", "--project", str(project))
        self.assertEqual(0, opened.returncode, opened.stderr)
        info = read_runtime(self.state)
        self.assertIsNotNone(info)
        self.processes.append(_Detached(info["pid"]))
        self.assertIn(f"GUI_URL http://127.0.0.1:{info['port']}/?t=", opened.stdout)
        connection = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=10)
        connection.request("GET", "/v1/projects", headers={"Authorization": f"Bearer {info['session_secret']}"})
        listing = json.loads(connection.getresponse().read())
        connection.close()
        self.assertEqual([("open", str(project))], [(e["source"], e["root"]) for e in listing["projects"]])
        log = (self.state / "backend.log").read_text()
        self.assertNotIn("?t=", log)
        self.assertNotIn(info["session_secret"], log)


class _Detached:
    """A backend started by `gui open` (not our child): stopped by SIGTERM to its pid."""

    def __init__(self, pid):
        self.pid = pid
        self.stdout = self.stderr = None

    def poll(self):
        try:
            os.kill(self.pid, 0)
        except OSError:
            return 0
        return None

    def send_signal(self, number):
        os.kill(self.pid, number)

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.poll() is not None:
                return 0
            time.sleep(0.05)
        raise subprocess.TimeoutExpired("gui serve", timeout)

    def kill(self):
        self.send_signal(signal.SIGKILL)


class TestLock(unittest.TestCase):
    def test_second_lock_is_backend_running(self):
        from gui.backend import BackendError

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        first = InstanceLock(folder).acquire()
        self.addCleanup(first.release)
        script = ("import sys; from pathlib import Path; from gui.backend import InstanceLock, BackendError\n"
                  "try:\n    InstanceLock(Path(sys.argv[1])).acquire()\nexcept BackendError as e:\n"
                  "    print(e.code)\n")
        result = subprocess.run([sys.executable, "-c", script, str(folder)], capture_output=True, text=True,
                                timeout=30)
        self.assertEqual("BACKEND_RUNNING", result.stdout.strip(), result.stderr)
        self.assertTrue(issubclass(BackendError, Exception))


if __name__ == "__main__":
    unittest.main()
