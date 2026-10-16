"""gui.deps: the stdlib installer against a fake PyPI on 127.0.0.1 (no network), lock parsing and activation."""
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from gui import deps


def wheel(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class FakeIndex:
    """``/pypi/<name>/<version>/json`` and ``/files/<filename>`` served from dictionaries."""

    def __init__(self):
        self.meta = {}
        self.files = {}
        self.hits = []
        index = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server API
                index.hits.append(self.path)
                body = index.meta.get(self.path) if self.path.startswith("/pypi/") else index.files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def add(self, name, version, data, *, filename=None, digest=None):
        filename = filename or f"{name}-{version}-py3-none-any.whl"
        self.files[f"/files/{filename}"] = data
        entry = {"packagetype": "bdist_wheel", "filename": filename, "url": f"{self.url}/files/{filename}",
                 "digests": {"sha256": digest or hashlib.sha256(data).hexdigest()}}
        self.meta[f"/pypi/{name}/{version}/json"] = json.dumps({"urls": [entry]}).encode()
        return hashlib.sha256(data).hexdigest()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class DepsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.index = FakeIndex()
        self.addCleanup(self.index.close)
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm")}

    def lock(self, lines):
        path = self.tmp / "requirements.lock"
        path.write_text("# comment\n" + "\n".join(lines) + "\n# test\n", encoding="utf-8")
        return path

    def ensure(self, lock, **kwargs):
        kwargs.setdefault("pip", False)
        return deps.ensure(self.env, lock_path=lock, index_url=self.index.url, **kwargs)


class TestLock(DepsCase):
    def test_reads_pins_and_skips_comments(self):
        lock = self.lock([f"alpha==1.0 --hash=sha256:{'a' * 64}", f"beta==2.0 --hash=sha256:{'b' * 64}  # note"])
        self.assertEqual([("alpha", "1.0", "a" * 64), ("beta", "2.0", "b" * 64)], deps.read_lock(lock))

    def test_malformed_lines_are_refused(self):
        for line in ("alpha>=1.0 --hash=sha256:" + "a" * 64, "alpha==1.0", "alpha==1.0 --hash=sha256:xyz",
                     f"alpha==1.0 --hash=sha256:{'a' * 64} --hash=sha256:{'b' * 64}"):
            with self.subTest(line=line), self.assertRaises(deps.GuiDepsError) as caught:
                deps.read_lock(self.lock([line]))
            self.assertEqual("GUI_DEPS_UNAVAILABLE", caught.exception.code)

    def test_the_real_lock_is_closed_and_pure(self):
        pins = deps.read_lock()
        self.assertTrue({"starlette", "uvicorn", "h11", "wsproto", "anyio", "idna", "click", "httpx"}
                        <= {pin.name for pin in pins})
        self.assertEqual(len(pins), len({pin.name for pin in pins}))

    def test_site_dir_names_python_and_lock_digest(self):
        lock = self.lock([f"alpha==1.0 --hash=sha256:{'a' * 64}"])
        folder = deps.site_dir(self.env, lock_path=lock)
        self.assertEqual(f"py{sys.version_info[0]}{sys.version_info[1]}-{deps.lock_digest(lock)}", folder.name)
        self.assertEqual(Path(self.env["SKM_HOME"]) / "cache" / "gui" / "pydeps", folder.parent)
        self.assertEqual(Path("/x/y"), deps.site_dir({**self.env, "GUI_PYDEPS_DIR": "/x/y"}, lock_path=lock))
        with self.assertRaises(deps.GuiDepsError):
            deps.site_dir({**self.env, "GUI_PYDEPS_DIR": "relative"}, lock_path=lock)


class TestInstall(DepsCase):
    def test_installs_verifies_and_activates(self):
        sha = self.index.add("alpha", "1.0", wheel({"alpha_pkg/__init__.py": "VALUE = 42\n",
                                                    "alpha-1.0.dist-info/METADATA": "Name: alpha\n",
                                                    "alpha-1.0.data/purelib/alpha_extra.py": "X = 1\n",
                                                    "alpha-1.0.data/scripts/tool": "#!/bin/sh\n"}))
        lock = self.lock([f"alpha==1.0 --hash=sha256:{sha}"])
        folder = self.ensure(lock)
        self.assertTrue((folder / "alpha_pkg" / "__init__.py").is_file())
        self.assertTrue((folder / "alpha_extra.py").is_file())
        self.assertFalse((folder / "tool").exists())
        self.assertTrue(deps.is_complete(folder, lock))
        self.assertEqual([], [p for p in folder.parent.iterdir() if p.name.startswith(".")])
        saved = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved))
        self.assertEqual(folder, deps.activate(self.env, lock_path=lock))
        self.assertEqual(str(folder), sys.path[0])

    def test_second_ensure_is_idempotent_and_offline(self):
        sha = self.index.add("alpha", "1.0", wheel({"alpha_pkg/__init__.py": ""}))
        lock = self.lock([f"alpha==1.0 --hash=sha256:{sha}"])
        first = self.ensure(lock)
        hits = len(self.index.hits)
        self.assertEqual(first, self.ensure(lock, offline=True))
        self.assertEqual(hits, len(self.index.hits))

    def test_hash_mismatch_is_refused_and_nothing_is_left(self):
        good = wheel({"alpha_pkg/__init__.py": ""})
        self.index.add("alpha", "1.0", wheel({"alpha_pkg/__init__.py": "evil = 1\n"}),
                       digest=hashlib.sha256(good).hexdigest())
        lock = self.lock([f"alpha==1.0 --hash=sha256:{hashlib.sha256(good).hexdigest()}"])
        with self.assertRaises(deps.GuiDepsError) as caught:
            self.ensure(lock)
        self.assertIn("sha256 mismatch", caught.exception.message)
        self.assert_nothing_installed(lock)

    def test_lock_digest_unknown_to_the_index_is_refused(self):
        self.index.add("alpha", "1.0", wheel({"alpha_pkg/__init__.py": ""}))
        lock = self.lock([f"alpha==1.0 --hash=sha256:{'c' * 64}"])
        with self.assertRaises(deps.GuiDepsError) as caught:
            self.ensure(lock)
        self.assertIn("no wheel with the locked sha256", caught.exception.message)

    def test_platform_wheel_is_refused(self):
        data = wheel({"alpha_pkg/__init__.py": ""})
        sha = self.index.add("alpha", "1.0", data, filename="alpha-1.0-cp312-cp312-manylinux_2_17_x86_64.whl")
        lock = self.lock([f"alpha==1.0 --hash=sha256:{sha}"])
        with self.assertRaises(deps.GuiDepsError) as caught:
            self.ensure(lock)
        self.assertIn("not a py3-none-any wheel", caught.exception.message)
        self.assert_nothing_installed(lock)

    def test_traversal_members_are_refused(self):
        for member in ("../escape.py", "/abs/escape.py", "pkg/../../escape.py", "C:/escape.py", "pkg\\..\\x.py"):
            with self.subTest(member=member):
                sha = self.index.add("alpha", "1.0", wheel({"alpha_pkg/__init__.py": "", member: "boom"}))
                lock = self.lock([f"alpha==1.0 --hash=sha256:{sha}"])
                with self.assertRaises(deps.GuiDepsError) as caught:
                    self.ensure(lock)
                self.assertIn("escapes the install folder", caught.exception.message)
                self.assert_nothing_installed(lock)
                self.assertFalse((self.tmp / "escape.py").exists())

    def test_complete_marker_of_another_lock_triggers_a_reinstall(self):
        sha = self.index.add("alpha", "1.0", wheel({"alpha_pkg/__init__.py": ""}))
        lock = self.lock([f"alpha==1.0 --hash=sha256:{sha}"])
        env = {**self.env, "GUI_PYDEPS_DIR": str(self.tmp / "pinned")}
        (self.tmp / "pinned").mkdir()
        (self.tmp / "pinned" / ".complete").write_text("0123456789abcdef\n")
        (self.tmp / "pinned" / "stale.py").write_text("")
        self.assertFalse(deps.is_complete(self.tmp / "pinned", lock))
        with self.assertRaises(deps.GuiDepsError):
            deps.activate(env, lock_path=lock)
        folder = deps.ensure(env, lock_path=lock, index_url=self.index.url, pip=False)
        self.assertTrue(deps.is_complete(folder, lock))
        self.assertFalse((folder / "stale.py").exists())

    def test_offline_without_install_fails_without_network(self):
        lock = self.lock([f"alpha==1.0 --hash=sha256:{'a' * 64}"])
        with self.assertRaises(deps.GuiDepsError) as caught:
            self.ensure(lock, offline=True)
        self.assertIn("offline", caught.exception.message)
        self.assertEqual([], self.index.hits)

    def test_unreachable_index_is_the_one_code(self):
        lock = self.lock([f"alpha==1.0 --hash=sha256:{'a' * 64}"])
        with self.assertRaises(deps.GuiDepsError) as caught:
            deps.ensure(self.env, lock_path=lock, index_url="http://127.0.0.1:9", pip=False)
        self.assertEqual("GUI_DEPS_UNAVAILABLE", caught.exception.code)
        self.assert_nothing_installed(lock)

    def test_non_http_download_url_is_refused(self):
        data = wheel({"alpha_pkg/__init__.py": ""})
        sha = self.index.add("alpha", "1.0", data)
        meta = json.loads(self.index.meta["/pypi/alpha/1.0/json"])
        meta["urls"][0]["url"] = f"file://{self.tmp}/x.whl"
        self.index.meta["/pypi/alpha/1.0/json"] = json.dumps(meta).encode()
        with self.assertRaises(deps.GuiDepsError) as caught:
            self.ensure(self.lock([f"alpha==1.0 --hash=sha256:{sha}"]))
        self.assertIn("only http(s)", caught.exception.message)

    def test_pip_path_is_used_when_pip_works(self):
        lock = self.lock([f"alpha==1.0 --hash=sha256:{'a' * 64}"])
        calls = []

        def fake_pip(lock_path, work):
            calls.append((lock_path, work))
            (work / "alpha_pkg").mkdir()

        with mock.patch.object(deps, "_pip_works", return_value=True), \
                mock.patch.object(deps, "_pip_install", side_effect=fake_pip):
            folder = deps.ensure(self.env, lock_path=lock, index_url=self.index.url)
        self.assertEqual(1, len(calls))
        self.assertTrue((folder / "alpha_pkg").is_dir())
        self.assertEqual([], self.index.hits)

    def assert_nothing_installed(self, lock):
        folder = deps.site_dir(self.env, lock_path=lock)
        self.assertFalse(folder.exists())
        if folder.parent.exists():
            self.assertEqual([], os.listdir(folder.parent))


class TestPurePython(unittest.TestCase):
    def test_tags(self):
        self.assertTrue(deps._pure_python("a-1.0-py3-none-any.whl"))
        self.assertTrue(deps._pure_python("a-1.0-py2.py3-none-any.whl"))
        self.assertTrue(deps._pure_python("a-1.0-1build-py3-none-any.whl"))
        self.assertFalse(deps._pure_python("a-1.0-cp312-abi3-manylinux_2_17_x86_64.whl"))
        self.assertFalse(deps._pure_python("a-1.0-py3-none-linux_x86_64.whl"))
        self.assertFalse(deps._pure_python("a-1.0.tar.gz"))


if __name__ == "__main__":
    unittest.main()
