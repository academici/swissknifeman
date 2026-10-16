"""Security of the local API (I9, I6): Host, Origin, body limits, authentication, the one-time token, headers."""
import unittest

from tests.http_support import PORT, SECRET_VALUE, Backend

from starlette.websockets import WebSocketDisconnect

from gui import contracts
from gui.backend import Sessions


def setUpModule():
    global BACKEND
    BACKEND = Backend()


def tearDownModule():
    BACKEND.close()


def error_code(response):
    body = response.json()
    assert contracts.validate(body, "api-error") == [], body
    return body["error"]["code"]


class TestHost(unittest.TestCase):
    def test_foreign_and_rebinding_hosts_are_rejected_before_auth(self):
        for host in ("evil.example:%d" % PORT, "127.0.0.1:%d" % (PORT + 1), "attacker.test:%d" % PORT,
                     "127.0.0.1", "localhost.evil.example:%d" % PORT):
            with self.subTest(host=host):
                response = BACKEND.client(host=host).get("/v1/bootstrap")
                self.assertEqual(403, response.status_code)
                self.assertEqual("HOST_REJECTED", error_code(response))

    def test_the_three_loopback_names_are_accepted(self):
        for host in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT, "[::1]:%d" % PORT):
            with self.subTest(host=host):
                self.assertEqual(200, BACKEND.client(host=host).get("/v1/bootstrap").status_code)

    def test_websocket_with_foreign_host_closes_before_accept(self):
        client = BACKEND.client(host="evil.example:%d" % PORT)
        with self.assertRaises(WebSocketDisconnect) as caught:
            with client.websocket_connect("/v1/events", headers={"Origin": f"http://127.0.0.1:{PORT}"}):
                pass
        self.assertEqual(4403, caught.exception.code)


class TestOrigin(unittest.TestCase):
    def test_foreign_and_null_origins_are_rejected(self):
        for origin in ("http://evil.example", "null", f"http://127.0.0.1:{PORT + 1}", f"https://127.0.0.1:{PORT}"):
            with self.subTest(origin=origin):
                response = BACKEND.client().get("/v1/bootstrap", headers={"Origin": origin})
                self.assertEqual(403, response.status_code)
                self.assertEqual("ORIGIN_REJECTED", error_code(response))

    def test_websocket_without_origin_is_refused(self):
        with self.assertRaises(WebSocketDisconnect) as caught:
            with BACKEND.client().websocket_connect("/v1/events"):
                pass
        self.assertEqual(4403, caught.exception.code)

    def test_cookie_post_without_origin_is_rejected(self):
        browser = BACKEND.browser()
        del browser.headers["Origin"]
        response = browser.post("/v1/projects", json={"path": "/tmp"})
        self.assertEqual("ORIGIN_REJECTED", error_code(response))

    def test_no_cors_headers_even_on_preflight(self):
        response = BACKEND.client().options("/v1/bootstrap", headers={
            "Origin": f"http://127.0.0.1:{PORT}", "Access-Control-Request-Method": "POST"})
        self.assertFalse([name for name in response.headers if name.lower().startswith("access-control-")])
        response = BACKEND.client().get("/v1/bootstrap", headers={"Origin": f"http://127.0.0.1:{PORT}"})
        self.assertFalse([name for name in response.headers if name.lower().startswith("access-control-")])


class TestBody(unittest.TestCase):
    def test_text_plain_post_is_refused(self):
        response = BACKEND.client().post("/v1/session/tokens", content=b"{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(422, response.status_code)
        self.assertEqual("INPUT_INVALID", error_code(response))

    def test_body_over_one_mib_is_refused(self):
        body = b'{"path": "' + b"x" * (1024 * 1024) + b'"}'
        response = BACKEND.client().post("/v1/projects", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(413, response.status_code)
        self.assertEqual("PAYLOAD_TOO_LARGE", error_code(response))

    def test_streamed_body_over_one_mib_is_refused(self):
        def chunks():
            for _ in range(17):
                yield b"x" * 65536

        response = BACKEND.client().post("/v1/projects", content=chunks(), headers={"Content-Type": "application/json"})
        self.assertEqual("PAYLOAD_TOO_LARGE", error_code(response))


class TestAuthentication(unittest.TestCase):
    def test_no_credential(self):
        client = BACKEND.client(bearer=False)
        response = client.get("/v1/bootstrap")
        self.assertEqual((401, "AUTH_REQUIRED"), (response.status_code, error_code(response)))
        page = client.get("/", headers={"Accept": "text/html"})
        self.assertEqual(401, page.status_code)
        self.assertIn("gui open", page.text)
        self.assertNotIn(BACKEND.state.sessions.secret, page.text)

    def test_wrong_bearer_and_wrong_scheme(self):
        for value in ("Bearer nope", "Basic abc", "Bearer", f"Token {BACKEND.state.sessions.secret}"):
            with self.subTest(value=value):
                client = BACKEND.client(bearer=False)
                response = client.get("/v1/bootstrap", headers={"Authorization": value})
                self.assertEqual("AUTH_INVALID", error_code(response))

    def test_unknown_cookie_is_invalid(self):
        client = BACKEND.client(bearer=False)
        client.cookies.set("skm_gui_session", "forged")
        self.assertEqual("AUTH_INVALID", error_code(client.get("/v1/bootstrap")))

    def test_token_exchange_sets_a_strict_cookie_once(self):
        token = BACKEND.state.sessions.new_token()
        client = BACKEND.client(bearer=False, follow_redirects=False)
        response = client.get(f"/?t={token}")
        self.assertEqual(303, response.status_code)
        self.assertEqual("/", response.headers["location"])
        cookie = response.headers["set-cookie"]
        for part in ("skm_gui_session=", "HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(part, cookie)
        self.assertNotIn("Secure", cookie)
        self.assertNotIn(token, cookie)
        self.assertEqual(200, client.get("/v1/bootstrap").status_code)
        again = BACKEND.client(bearer=False, follow_redirects=False).get(f"/?t={token}")
        self.assertEqual(401, again.status_code)
        self.assertNotIn("set-cookie", again.headers)

    def test_expired_token_is_refused(self):
        now = [1000.0]
        sessions = Sessions(clock=lambda: now[0])
        token = sessions.new_token()
        now[0] += 301
        self.assertIsNone(sessions.redeem(token))
        fresh = sessions.new_token()
        self.assertIsNotNone(sessions.redeem(fresh))
        self.assertIsNone(sessions.redeem(fresh))

    def test_unknown_token_is_refused(self):
        response = BACKEND.client(bearer=False, follow_redirects=False).get("/?t=made-up")
        self.assertEqual(401, response.status_code)

    def test_only_the_bearer_issues_tokens(self):
        response = BACKEND.browser().post("/v1/session/tokens", json={})
        self.assertEqual("PERMISSION_DENIED", error_code(response))
        issued = BACKEND.client().post("/v1/session/tokens", json={})
        self.assertEqual(201, issued.status_code)
        self.assertRegex(issued.json()["url"], rf"^http://127\.0\.0\.1:{PORT}/\?t=[A-Za-z0-9_-]{{20,}}$")


class TestHeadersAndSecrets(unittest.TestCase):
    def test_security_headers(self):
        response = BACKEND.client().get("/v1/bootstrap")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertNotIn("unsafe", response.headers["content-security-policy"])
        self.assertEqual("nosniff", response.headers["x-content-type-options"])
        self.assertEqual("no-referrer", response.headers["referrer-policy"])
        self.assertEqual("no-store", response.headers["cache-control"])
        self.assertNotIn("server", response.headers)

    def test_session_secret_never_in_responses(self):
        secret = BACKEND.state.sessions.secret
        client = BACKEND.client()
        for response in (client.get("/v1/bootstrap"), client.get("/v1/ui/contributions"), client.get("/v1/projects"),
                         client.post("/v1/queries/qdemo.fails", json={}), client.get("/v1/nothing")):
            self.assertNotIn(secret, response.text)

    def test_env_secret_from_a_handler_is_redacted(self):
        response = BACKEND.client().post("/v1/queries/qdemo.secret", json={})
        self.assertEqual(200, response.status_code, response.text)
        self.assertNotIn(SECRET_VALUE, response.text)
        self.assertIn("token ", response.json()["metrics"][0]["label"])


if __name__ == "__main__":
    unittest.main()
