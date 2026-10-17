"""Terminal endpoints and the WebSocket at the ASGI level (a real /bin/sh on a PTY behind the real middleware)."""
import base64
import json
import re
import threading
import time
import unittest
from pathlib import Path

from tests.http_support import PORT, SECRET_VALUE, Backend

from starlette.websockets import WebSocketDisconnect

from gui import contracts
from gui.core import terminal as core

ORIGIN = {"Host": f"127.0.0.1:{PORT}", "Origin": f"http://127.0.0.1:{PORT}"}
SESSIONS = "/v1/terminal/sessions"
LINE = "TERMINAL-LINE-0f3a9c-must-not-be-stored"


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def code_of(response) -> str:
    return response.json()["error"]["code"]


class Case(unittest.TestCase):
    ENABLED = True
    EXTRA = {}

    def setUp(self):
        extra = dict(self.EXTRA)
        if self.ENABLED:
            extra["SKM_GUI_TERMINAL__ENABLED"] = "true"
        self.backend = Backend(env_extra=extra)
        self.addCleanup(self.backend.close)
        self.state = self.backend.state
        self.state.terminals.grace_s = 0.3
        self.addCleanup(self.state.terminals.close_all)
        # A hung receive would block the test for good: the watchdog ends every session, which closes the sockets.
        watchdog = threading.Timer(40, self.state.terminals.close_all)
        watchdog.daemon = True
        watchdog.start()
        self.addCleanup(watchdog.cancel)
        self.client = self.backend.client()
        self.project = self.backend.project()

    def request(self, **extra):
        body = {"$schema": contracts.urn("terminal"), "kind": "session_request", "project_id": self.project.id,
                "cols": 80, "rows": 24}
        body.update(extra)
        return body

    def open_session(self, **extra):
        first = self.client.post(SESSIONS, json=self.request(**extra))
        self.assertEqual(428, first.status_code, first.text)
        confirm = first.json()["error"]["details"]["confirm"]
        second = self.client.post(SESSIONS, json=self.request(confirm=confirm, **extra))
        self.assertEqual(201, second.status_code, second.text)
        return second.json()

    def connect(self, session_id, client=None):
        return (client or self.client).websocket_connect(f"/v1/terminal/{session_id}/io", headers=ORIGIN)

    @staticmethod
    def receive_until(ws, pattern, limit=400):
        """Output frames (seq checked) until the decoded text matches; the frame list is bounded."""
        text, seqs = "", []
        for _ in range(limit):
            frame = json.loads(ws.receive_text())
            if frame["t"] != "output":
                return frame, text
            seqs.append(frame["seq"])
            text += base64.b64decode(frame["data"]).decode("utf-8", "replace")
            if re.search(pattern, text):
                assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), seqs
                return None, text
        raise AssertionError(f"no match for {pattern!r}")


class TestPrivilege(Case):
    ENABLED = False

    def test_disabled_by_default(self):
        response = self.client.post(SESSIONS, json=self.request())
        self.assertEqual(403, response.status_code)
        self.assertEqual("PERMISSION_DENIED", code_of(response))
        self.assertEqual("terminal_disabled", response.json()["error"]["details"]["reason"])
        self.assertNotIn("terminal", self.client.get("/v1/bootstrap").json()["features"])
        confirm = "0" * 64
        self.assertEqual(403, self.client.post(SESSIONS, json=self.request(confirm=confirm)).status_code)
        self.assertEqual(0, self.state.terminals.count())

    def test_listing_works_when_disabled_and_is_empty(self):
        self.assertEqual({"$schema": contracts.urn("terminal"), "kind": "session_list", "sessions": []},
                         self.client.get(SESSIONS).json())


class TestSessions(Case):
    def test_feature_is_announced_only_when_enabled(self):
        self.assertIn("terminal", self.client.get("/v1/bootstrap").json()["features"])

    def test_desktop_mode_has_no_terminal(self):
        self.state.mode = "desktop"
        self.assertNotIn("terminal", self.state.bootstrap()["features"])
        response = self.client.post(SESSIONS, json=self.request())
        self.assertEqual("PERMISSION_DENIED", code_of(response))
        self.assertEqual("terminal_unsupported", response.json()["error"]["details"]["reason"])

    def test_confirmation_is_required_and_bound_to_the_request(self):
        first = self.client.post(SESSIONS, json=self.request())
        self.assertEqual(428, first.status_code)
        details = first.json()["error"]["details"]
        self.assertEqual("high", details["risk"])
        self.assertIn(str(self.backend.tmp / "proj"), details["summary"])
        self.assertEqual(0, self.state.terminals.count())
        wrong = self.client.post(SESSIONS, json=self.request(confirm=details["confirm"], cols=100))
        self.assertEqual(428, wrong.status_code)  # another size is another request
        self.assertEqual(0, self.state.terminals.count())
        junk = self.client.post(SESSIONS, json=self.request(confirm="x"))
        self.assertEqual("INPUT_INVALID", code_of(junk))

    def test_session_document_audit_and_list(self):
        document = self.open_session()
        self.assertEqual([], contracts.validate(document, "terminal"))
        self.assertRegex(document["session_id"], r"^term-[0-9a-f]{32}$")
        self.assertEqual(self.project.id, document["project_id"])
        listed = self.client.get(SESSIONS).json()
        self.assertEqual([], contracts.validate(listed, "terminal"))
        self.assertEqual([document["session_id"]], [entry["session_id"] for entry in listed["sessions"]])
        closed = self.client.post(f"{SESSIONS}/{document['session_id']}:close", json={})
        self.assertEqual(200, closed.status_code, closed.text)
        self.assertEqual([], contracts.validate(closed.json(), "terminal"))
        self.assertIn("ended_at", closed.json())
        self.assertEqual([], self.client.get(SESSIONS).json()["sessions"])
        again = self.client.post(f"{SESSIONS}/{document['session_id']}:close", json={})
        self.assertEqual(200, again.status_code)
        rows = self.backend.conn.execute("SELECT action, target, details_json FROM audit WHERE action LIKE 'terminal.%' "
                                         "ORDER BY id").fetchall()
        self.assertEqual(["terminal.start", "terminal.end"], [row["action"] for row in rows])
        self.assertEqual(document["session_id"], rows[0]["target"])
        self.assertEqual("closed", json.loads(rows[1]["details_json"])["reason"])

    def test_unknown_project_unknown_session_and_bad_bodies(self):
        self.assertEqual(404, self.client.post(SESSIONS, json=self.request(project_id="nope-00000000")).status_code)
        self.assertEqual("NOT_FOUND", code_of(self.client.post(f"{SESSIONS}/term-{'0' * 32}:close", json={})))
        for body in ({}, {**self.request(), "extra": 1}, self.request(cols=5), self.request(rows=500),
                     {**self.request(), "kind": "session"}):
            response = self.client.post(SESSIONS, json=body)
            self.assertEqual(422, response.status_code, body)
        self.assertEqual(0, self.state.terminals.count())

    def test_project_must_be_registered_and_trusted(self):
        self.backend.conn.execute("UPDATE projects SET trusted = 0 WHERE id = ?", (self.project.id,))
        response = self.client.post(SESSIONS, json=self.request())
        self.assertEqual("PERMISSION_DENIED", code_of(response))
        self.assertEqual("project_untrusted", response.json()["error"]["details"]["reason"])

    def test_requests_need_authentication(self):
        anonymous = self.backend.client(bearer=False)
        self.assertEqual(401, anonymous.post(SESSIONS, json=self.request()).status_code)
        self.assertEqual(401, anonymous.get(SESSIONS).status_code)


class TestLimit(Case):
    EXTRA = {"SKM_GUI_TERMINAL__MAX_SESSIONS": "1"}

    def test_session_limit(self):
        document = self.open_session()
        response = self.client.post(SESSIONS, json=self.request())
        self.assertEqual(429, response.status_code)
        self.assertEqual("TERMINAL_LIMIT", code_of(response))
        self.assertTrue(response.json()["error"]["retryable"])
        self.client.post(f"{SESSIONS}/{document['session_id']}:close", json={})
        self.open_session()  # the slot is free again


class TestWebSocket(Case):
    def test_output_only_after_credit_input_echo_resize_and_exit(self):
        document = self.open_session()
        session = self.state.terminals.get(document["session_id"])
        with self.connect(document["session_id"]) as ws:
            ws.send_text(json.dumps({"t": "input", "data": b64("echo READY$((1+1))\n")}))
            time.sleep(0.4)
            self.assertEqual(0, session.bytes_out)  # without credit nothing is read from the PTY
            ws.send_text(json.dumps({"t": "credit", "bytes": 4096}))
            frame, text = self.receive_until(ws, r"READY2\r\n")
            self.assertIsNone(frame)
            ws.send_text(json.dumps({"t": "resize", "cols": 100, "rows": 30}))
            ws.send_text(json.dumps({"t": "credit", "bytes": 4096}))
            ws.send_text(json.dumps({"t": "input", "data": b64("stty size\n")}))
            _frame, text = self.receive_until(ws, r"30 100")
            self.assertEqual((100, 30), (session.cols, session.rows))
            ws.send_text(json.dumps({"t": "input", "data": b64("exit 7\n")}))
            frame, _text = self.receive_until(ws, r"never-matches-after-exit")
            self.assertEqual({"t": "exit", "code": 7, "reason": "exit"}, frame)
        self.assertEqual(0, self.state.terminals.count())
        self.assertIsNotNone(session.proc.returncode)

    def test_secret_environment_is_not_visible_and_content_is_not_stored(self):
        self.assertEqual(SECRET_VALUE, self.state.env["SKM_TEST_SECRET"])
        document = self.open_session()
        with self.connect(document["session_id"]) as ws:
            ws.send_text(json.dumps({"t": "credit", "bytes": 8192}))
            ws.send_text(json.dumps({"t": "input", "data": b64(f"echo [$SKM_TEST_SECRET] {LINE}$((1+1))\n")}))
            _frame, text = self.receive_until(ws, rf"{LINE}2\r\n")
            self.assertIn("[] " + LINE + "2", text)
            self.assertNotIn(SECRET_VALUE, text)
        deadline = time.monotonic() + 10
        while self.state.terminals.count() and time.monotonic() < deadline:
            time.sleep(0.05)
        rows = self.backend.conn.execute("SELECT details_json FROM audit").fetchall()
        self.assertNotIn(LINE, json.dumps([row["details_json"] for row in rows]))
        self.backend.conn.execute("PRAGMA wal_checkpoint(FULL)")
        hits = [str(path) for path in (self.backend.tmp / "skm").rglob("*")
                if path.is_file() and LINE.encode() in path.read_bytes()]
        self.assertEqual([], hits)  # in no file of the state folder
        log = self.state.log_path
        self.assertFalse(log is not None and log.exists() and LINE in log.read_text(encoding="utf-8"))

    def test_second_client_is_refused_without_harming_the_first(self):
        document = self.open_session()
        session_id = document["session_id"]
        with self.connect(session_id) as first:
            first.send_text(json.dumps({"t": "credit", "bytes": 4096}))
            with self.connect(session_id) as second:
                frame = json.loads(second.receive_text())
                self.assertEqual("error", frame["t"])
                self.assertEqual("TERMINAL_BUSY", frame["code"])
                with self.assertRaises(WebSocketDisconnect):
                    second.receive_text()
            self.assertIsNotNone(self.state.terminals.get(session_id))  # the refused client did not end it
            first.send_text(json.dumps({"t": "input", "data": b64("echo ALIVE$((1+1))\n")}))
            self.assertIsNone(self.receive_until(first, r"ALIVE2\r\n")[0])

    def test_unknown_session_and_missing_origin(self):
        with self.connect(f"term-{'a' * 32}") as ws:
            self.assertEqual("NOT_FOUND", json.loads(ws.receive_text())["code"])
        with self.connect("not-an-id") as ws:
            self.assertEqual("NOT_FOUND", json.loads(ws.receive_text())["code"])
        document = self.open_session()
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect(f"/v1/terminal/{document['session_id']}/io",
                                               headers={"Host": ORIGIN["Host"]}):
                pass
        self.assertEqual(4403, caught.exception.code)
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.backend.client(bearer=False).websocket_connect(
                    f"/v1/terminal/{document['session_id']}/io", headers=ORIGIN):
                pass
        self.assertEqual(4401, caught.exception.code)
        self.assertIsNotNone(self.state.terminals.get(document["session_id"]))

    def test_cookie_client_can_use_its_session(self):
        browser = self.backend.browser()
        first = browser.post(SESSIONS, json=self.request())
        confirm = first.json()["error"]["details"]["confirm"]
        document = browser.post(SESSIONS, json=self.request(confirm=confirm)).json()
        # The WebSocket URL of the test client has another host name, so the cookie jar does not send the cookie.
        cookie = "; ".join(f"{name}={value}" for name, value in browser.cookies.items())
        with browser.websocket_connect(f"/v1/terminal/{document['session_id']}/io",
                                       headers={"Host": ORIGIN["Host"], "Cookie": cookie}) as ws:
            ws.send_text(json.dumps({"t": "credit", "bytes": 4096}))
            ws.send_text(json.dumps({"t": "input", "data": b64("echo COOKIE$((1+1))\n")}))
            self.assertIsNone(self.receive_until(ws, r"COOKIE2\r\n")[0])

    def test_bad_frames_get_an_error_frame_and_end_the_session(self):
        cases = {
            "not json": "{",
            "unknown type": json.dumps({"t": "paste", "data": ""}),
            "bad base64": json.dumps({"t": "input", "data": "not base64!"}),
            "input too large": json.dumps({"t": "input", "data": b64("x" * (core.MAX_INPUT_BYTES + 1))}),
            "extra field": json.dumps({"t": "input", "data": "", "more": 1}),
            "zero credit": json.dumps({"t": "credit", "bytes": 0}),
            "float credit": json.dumps({"t": "credit", "bytes": 1.5}),
            "credit above the cap": json.dumps({"t": "credit", "bytes": 4 * 65536 + 1}),
            "bad size": json.dumps({"t": "resize", "cols": 3, "rows": 24}),
            "resize without rows": json.dumps({"t": "resize", "cols": 80}),
        }
        for name, raw in cases.items():
            with self.subTest(name):
                document = self.open_session()
                session_id = document["session_id"]
                with self.connect(session_id) as ws:
                    ws.send_text(raw)
                    frame = json.loads(ws.receive_text())
                    self.assertEqual(("error", "INPUT_INVALID"), (frame["t"], frame["code"]))
                deadline = time.monotonic() + 10
                while self.state.terminals.get(session_id) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertIsNone(self.state.terminals.get(session_id))

    def test_blocked_input_write_does_not_stop_credit_from_being_processed(self):
        document = self.open_session()
        session = self.state.terminals.get(document["session_id"])
        release = threading.Event()
        real_write = session.write

        def blocked(data):
            release.wait(10)
            real_write(data)

        session.write = blocked
        try:
            with self.connect(document["session_id"]) as ws:
                ws.send_text(json.dumps({"t": "input", "data": b64("echo X\n")}))
                ws.send_text(json.dumps({"t": "credit", "bytes": 4096}))
                deadline = time.monotonic() + 5
                while session.gate.available == 4096 and not session.bytes_out and time.monotonic() < deadline:
                    time.sleep(0.02)
                # the credit was granted (and maybe spent on the prompt) while the write is still blocked
                self.assertFalse(release.is_set())
                self.assertTrue(session.gate.available > 0 or session.bytes_out > 0)
                release.set()
        finally:
            release.set()

    def test_credit_is_summed_up_to_the_cap(self):
        document = self.open_session()
        with self.connect(document["session_id"]) as ws:
            for _ in range(4):
                ws.send_text(json.dumps({"t": "credit", "bytes": 65536}))
            ws.send_text(json.dumps({"t": "credit", "bytes": 1}))
            frame = json.loads(ws.receive_text())
            self.assertEqual(("error", "INPUT_INVALID"), (frame["t"], frame["code"]))

    def test_closing_the_socket_ends_the_shell_and_its_jobs(self):
        document = self.open_session()
        session = self.state.terminals.get(document["session_id"])
        with self.connect(document["session_id"]) as ws:
            ws.send_text(json.dumps({"t": "credit", "bytes": 4096}))
            ws.send_text(json.dumps({"t": "input", "data": b64("sleep 300 & echo BG$!\n")}))
            _frame, text = self.receive_until(ws, r"BG\d+\r\n")
        pid = int(re.search(r"BG(\d+)", text).group(1))
        deadline = time.monotonic() + 10
        while self.state.terminals.count() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(0, self.state.terminals.count())
        self.assertIsNotNone(session.proc.returncode)
        from tests.test_terminal import alive

        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(pid))
        end = self.backend.conn.execute("SELECT details_json FROM audit WHERE action = 'terminal.end'").fetchone()
        self.assertEqual("closed", json.loads(end["details_json"])["reason"])

    def test_close_endpoint_sends_exit_to_the_socket(self):
        document = self.open_session()
        with self.connect(document["session_id"]) as ws:
            closer = threading.Timer(0.3, lambda: self.state.terminals.close(document["session_id"], "closed"))
            closer.start()
            self.addCleanup(closer.cancel)
            frame, _text = self.receive_until(ws, r"never")
            self.assertEqual("exit", frame["t"])
            self.assertEqual("closed", frame["reason"])

    def test_idle_timer_closes_a_session_without_a_socket(self):
        document = self.open_session()
        session = self.state.terminals.get(document["session_id"])
        self.state.terminals.clock = lambda: session.started + 10_000
        session._clock = self.state.terminals.clock
        self.assertEqual([session.id], self.state.terminals.reap())
        self.assertEqual("idle", session.reason)  # 10 000 s is over idle_timeout_s (900) and under max_session_s

    def test_stop_of_the_backend_closes_the_sessions(self):
        import asyncio

        document = self.open_session()
        session = self.state.terminals.get(document["session_id"])
        asyncio.run(self.state.stop())
        self.assertEqual(0, self.state.terminals.count())
        self.assertEqual("backend_stop", session.reason)
        end = self.backend.conn.execute("SELECT details_json FROM audit WHERE action = 'terminal.end'").fetchone()
        self.assertEqual("backend_stop", json.loads(end["details_json"])["reason"])


class TestFrames(unittest.TestCase):
    """The frame definitions of terminal/v1 against their examples."""

    def load(self, folder):
        return [(path.name, json.loads(path.read_text(encoding="utf-8")))
                for path in sorted((contracts.contract_dir("terminal") / "examples" / "frames" / folder).glob("*.json"))]

    def validate(self, document):
        from aicore.util import schema

        registry, kind = contracts.load("terminal")
        root, root_id = registry.for_kind(kind)
        name = f"{document.get('t')}_frame"
        node, owner = registry.resolve(f"#/$defs/{name}", root_id)
        return schema.validate_node(registry, node, owner, document)

    def test_valid_and_invalid_examples(self):
        valid = self.load("valid")
        self.assertGreaterEqual(len(valid), 7)
        for name, document in valid:
            with self.subTest(name):
                self.assertEqual([], self.validate(document))
        from aicore.util import schema

        for name, document in self.load("invalid"):
            with self.subTest(name):
                expected = name[:-len(".json")].rpartition(".")[2]
                self.assertIn(expected, schema.ERROR_CODES)
                self.assertIn(expected, {issue.code for issue in self.validate(document)})

    def test_frame_types_match_the_server(self):
        registry, kind = contracts.load("terminal")
        defs = registry.for_kind(kind)[0]["$defs"]
        self.assertEqual({"input", "resize", "credit"},
                         {defs[name]["properties"]["t"]["const"] for name in ("input_frame", "resize_frame", "credit_frame")})
        self.assertEqual({"output", "exit", "error"},
                         {defs[name]["properties"]["t"]["const"] for name in ("output_frame", "exit_frame", "error_frame")})
        self.assertEqual(list(core.REASONS), defs["end_reason"]["enum"])
        self.assertEqual([core.COLS[0], core.COLS[1]], [defs["cols"]["minimum"], defs["cols"]["maximum"]])
        self.assertEqual([core.ROWS[0], core.ROWS[1]], [defs["rows"]["minimum"], defs["rows"]["maximum"]])


if __name__ == "__main__":
    unittest.main()
