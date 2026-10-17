"""The sidecar protocol (parser, READY line) and the desktop mode of the backend at ASGI level."""
import io
import json
import time
import unittest

from gui import contracts, sidecar

SECRET = "A" * 43


def line(**changes):
    document = {"v": 1, "secret": SECRET, "port": 0, "shell_version": "0.1.0", **changes}
    return (json.dumps(document) + "\n").encode()


class TestParse(unittest.TestCase):
    def test_valid(self):
        handshake = sidecar.parse_handshake(line(port=8080, shell_version="1.2.3-rc.1+b5"))
        self.assertEqual((SECRET, 8080, "1.2.3-rc.1+b5", 1), (handshake.secret, handshake.port,
                                                              handshake.shell_version, handshake.v))
        self.assertNotIn(SECRET, repr(handshake))
        self.assertEqual(0, sidecar.parse_handshake(line(port=0)).port)
        self.assertEqual(65535, sidecar.parse_handshake(line(port=65535)).port)

    def test_refusals(self):
        document = {"v": 1, "secret": SECRET, "port": 0, "shell_version": "0.1.0"}
        without = lambda name: {k: v for k, v in document.items() if k != name}  # noqa: E731
        cases = {
            "empty": b"\n",
            "not json": b"not json\n",
            "not utf8": b"\xff\xfe\n",
            "array": b"[1]\n",
            "too long": b"{" + b" " * 5000 + b"}\n",
            "no v": json.dumps(without("v")).encode(),
            "v 2": line(v=2),
            "v true": line(v=True),
            "v string": line(v="1"),
            "no secret": json.dumps(without("secret")).encode(),
            "short secret": line(secret="A" * 31),
            "padding": line(secret="A" * 42 + "="),
            "plus": line(secret="A" * 42 + "+"),
            "secret number": line(secret=7),
            "no port": json.dumps(without("port")).encode(),
            "port high": line(port=65536),
            "port negative": line(port=-1),
            "port string": line(port="80"),
            "port bool": line(port=True),
            "port float": line(port=1.5),
            "no version": json.dumps(without("shell_version")).encode(),
            "version two parts": line(shell_version="1.0"),
            "version leading zero": line(shell_version="01.0.0"),
            "version number": line(shell_version=1),
        }
        for name, data in cases.items():
            with self.subTest(name), self.assertRaises(sidecar.HandshakeError) as caught:
                sidecar.parse_handshake(data)
            self.assertNotIn(SECRET, str(caught.exception))
            self.assertTrue(str(caught.exception).startswith("SIDECAR_HANDSHAKE_INVALID: "))

    def test_reason_never_names_a_value(self):
        for data in (line(secret="x" * 40 + "!"), line(v=99), line(shell_version="not-a-version")):
            with self.assertRaises(sidecar.HandshakeError) as caught:
                sidecar.parse_handshake(data)
            self.assertNotIn("!", caught.exception.reason)
            self.assertNotIn("99", caught.exception.reason)
            self.assertNotIn("not-a-version", caught.exception.reason)


class TestRead(unittest.TestCase):
    def test_reads_one_line_and_leaves_the_rest(self):
        stream = io.BytesIO(line() + b"extra\n")
        self.assertEqual(SECRET, sidecar.read_handshake(stream).secret)
        self.assertEqual(b"extra\n", stream.read())

    def test_eof_before_a_line(self):
        with self.assertRaises(sidecar.HandshakeError) as caught:
            sidecar.read_handshake(io.BytesIO(b""))
        self.assertIn("closed", caught.exception.reason)

    def test_timeout(self):
        import os

        read, write = os.pipe()
        stream = os.fdopen(read, "rb")
        self.addCleanup(stream.close)  # runs last: the reader thread must see EOF first
        self.addCleanup(os.close, write)
        started = time.monotonic()
        with self.assertRaises(sidecar.HandshakeError) as caught:
            sidecar.read_handshake(stream, timeout=0.3)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("no handshake line", caught.exception.reason)

    def test_watchdog_fires_once_at_eof(self):
        import os

        read, write = os.pipe()
        stream = os.fdopen(read, "rb")
        self.addCleanup(stream.close)
        fired = []
        thread = sidecar.watch_stdin(stream, lambda: fired.append(1))
        os.write(write, b"noise")
        time.sleep(0.1)
        self.assertEqual([], fired)
        os.close(write)
        thread.join(5)
        self.assertEqual([1], fired)


class TestReady(unittest.TestCase):
    def test_line(self):
        text = sidecar.ready_line(4242, "epoch-0001", 77, "0.1.0", {"min": "1", "max": "1"})
        self.assertTrue(text.startswith("GUI_READY {"))
        self.assertNotIn("\n", text)
        self.assertNotIn(" ", text.split(" ", 1)[1])
        self.assertEqual({"v": 1, "port": 4242, "epoch": "epoch-0001", "pid": 77, "backend": "0.1.0",
                          "gui_protocol": {"min": "1", "max": "1"}}, json.loads(text.split(" ", 1)[1]))


class TestDesktopMode(unittest.TestCase):
    def setUp(self):
        from tests.http_support import Backend  # activates the locked packages: a missing install is an error

        self.backend = Backend()
        self.addCleanup(self.backend.close)
        self.backend.build_frontend()
        self.state = self.backend.state
        self.port = self.state.port
        self.state.mode = "desktop"
        self.state.shell_version = "0.1.0"
        self.client = self.backend.client()

    def test_bootstrap_is_desktop_and_valid(self):
        response = self.client.get("/v1/bootstrap")
        self.assertEqual(200, response.status_code)
        document = response.json()
        self.assertEqual("desktop", document["mode"])
        self.assertEqual({"version": "0.1.0"}, document["shell"])
        self.assertEqual([], [issue for issue in contracts.validate(document, "bootstrap")])

    def test_browser_bootstrap_unchanged(self):
        self.state.mode = "browser"
        document = self.client.get("/v1/bootstrap").json()
        self.assertEqual("browser", document["mode"])
        self.assertNotIn("shell", document)
        self.assertEqual([], contracts.validate(document, "bootstrap"))

    def test_token_exchange_is_gone(self):
        token = self.state.sessions.new_token()
        client = self.backend.client(bearer=False, follow_redirects=False)
        response = client.get(f"/?t={token}")
        self.assertEqual(404, response.status_code)
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual("NOT_FOUND", response.json()["error"]["code"])
        # even with the bearer the exchange is not served
        self.assertEqual(404, self.client.get(f"/?t={token}").status_code)

    def test_cookie_is_ignored(self):
        cookie = self.state.sessions.redeem(self.state.sessions.new_token())
        client = self.backend.client(bearer=False)
        client.headers["Cookie"] = f"skm_gui_session={cookie}"
        response = client.get("/v1/bootstrap")
        self.assertEqual(401, response.status_code)
        self.assertEqual("AUTH_REQUIRED", response.json()["error"]["code"])

    def test_bearer_works_and_wrong_bearer_fails(self):
        self.assertEqual(200, self.client.get("/v1/projects").status_code)
        bad = self.backend.client(bearer=False)
        bad.headers["Authorization"] = "Bearer " + "x" * 43
        self.assertEqual("AUTH_INVALID", bad.get("/v1/bootstrap").json()["error"]["code"])

    def test_session_tokens_denied(self):
        response = self.client.post("/v1/session/tokens", json={})
        self.assertEqual(403, response.status_code)
        self.assertEqual("PERMISSION_DENIED", response.json()["error"]["code"])

    def test_frontend_is_not_served(self):
        for path in ("/", "/index.html", "/assets/app.js", "/plugins"):
            response = self.client.get(path)
            self.assertEqual(404, response.status_code, path)
            self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    def test_host_and_origin_rules_stay(self):
        self.assertEqual(403, self.backend.client(host=f"evil.example:{self.port}").get("/v1/bootstrap").status_code)
        response = self.client.get("/v1/bootstrap", headers={"Origin": "http://evil.example"})
        self.assertEqual(403, response.status_code)
        ok = self.client.get("/v1/bootstrap", headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(200, ok.status_code)

    def test_session_secret_is_the_given_one(self):
        from gui.backend import Sessions

        self.assertTrue(Sessions(SECRET).bearer_ok(SECRET))
        self.assertIn(self.state.sessions.secret, self.state.secrets())


if __name__ == "__main__":
    unittest.main()
