"""Commands, runs and the event stream over the local API (Starlette TestClient with the lifespan running)."""
import dataclasses
import json
import time
import unittest

from tests.http_support import PORT, SECRET_VALUE, Backend

from aicore.ext.events import read_events
from starlette.websockets import WebSocketDisconnect

from gui import contracts
from gui.core.runs import RunStore

ORIGIN = {"Origin": f"http://127.0.0.1:{PORT}"}
HOST = {"Host": f"127.0.0.1:{PORT}"}  # the TestClient WebSocket ignores the base URL host
RUN_API = "urn:swissknifeman:gui:run-api:v1"


def code(response):
    body = response.json()
    assert contracts.validate(body, "api-error") == [], body
    return body["error"]["code"]


def request(project_id=None, dry_run=False, **input_):
    return {"$schema": RUN_API, "kind": "run_request", "context": {"project_id": project_id} if project_id else {},
            "input": input_, "dry_run": dry_run}


class RunsCase(unittest.TestCase):
    def setUp(self):
        self.backend = Backend(units="exec-demo")
        self.addCleanup(self.backend.close)
        self.project = self.backend.project()
        self.context = self.backend.client()
        self.client = self.context.__enter__()  # runs the lifespan: mark_lost, heartbeats, journals
        self.addCleanup(self.context.__exit__, None, None, None)

    def start(self, command, body, expected=202):
        response = self.client.post(f"/v1/commands/{command}/runs", json=body)
        self.assertEqual(expected, response.status_code, response.text)
        return response.json()

    def wait(self, run_id, states=("succeeded", "failed", "cancelled", "timed_out", "denied", "failed_to_start"),
             timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            doc = self.client.get(f"/v1/runs/{run_id}").json()
            if doc["state"] in states:
                self.assertEqual([], contracts.validate(doc, "run"))
                return doc
            time.sleep(0.05)
        self.fail(f"run {run_id} did not reach {states}")


class TestCommandsAndRuns(RunsCase):
    def test_command_list_has_no_argv_or_paths(self):
        listing = self.client.get("/v1/commands").json()
        self.assertEqual([], contracts.validate(listing, "run-api"))
        self.assertIn("xdemo.echo", [entry["id"] for entry in listing["commands"]])
        self.assertNotIn("bin/", json.dumps(listing))
        fleet = self.client.get("/v1/commands?scope=fleet").json()["commands"]
        self.assertTrue(fleet and all(entry["scope"] == "fleet" for entry in fleet))
        self.assertEqual("NOT_FOUND", code(self.client.get("/v1/commands?project_id=nope-00000000")))

    def test_run_in_project_and_its_log(self):
        run = self.start("xdemo.echo", request(self.project.id, name="World"))
        self.assertEqual([], contracts.validate(run, "run"))
        done = self.wait(run["run_id"])
        self.assertEqual("succeeded", done["state"])
        page = self.client.get(f"/v1/runs/{run['run_id']}/log?stream=stdout&cursor=0").json()
        self.assertEqual([], contracts.validate(page, "run-api"))
        self.assertIn("arg:World", "".join(chunk["text"] for chunk in page["chunks"]))
        self.assertIsNone(page["next_cursor"])
        later = self.client.get(f"/v1/runs/{run['run_id']}/log?cursor=99").json()
        self.assertEqual(([], None), (later["chunks"], later["next_cursor"]))
        listing = self.client.get(f"/v1/runs?project_id={self.project.id}").json()
        self.assertEqual([], contracts.validate(listing, "run-api"))
        self.assertEqual([run["run_id"]], [entry["run_id"] for entry in listing["runs"]])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            events, _ = read_events(self.project.root, types=["gui.run.*"])
            if "gui.run.succeeded" in [event.type for event in events]:
                break
            time.sleep(0.05)
        self.assertEqual(["gui.run.started", "gui.run.succeeded"], [event.type for event in events])

    def test_risk_based_confirmation(self):
        first = self.client.post("/v1/commands/xdemo.risky/runs", json=request(self.project.id))
        self.assertEqual((428, "CONFIRMATION_REQUIRED"), (first.status_code, code(first)))
        details = first.json()["error"]["details"]
        self.assertEqual("medium", details["risk"])
        self.assertEqual([], self.client.get("/v1/runs").json()["runs"])
        other = request(self.project.id, dry_run=False)
        other["context"] = {}
        wrong = self.client.post("/v1/commands/xdemo.risky/runs", json={**other, "confirm": details["confirm"]})
        self.assertNotEqual(202, wrong.status_code)
        run = self.start("xdemo.risky", {**request(self.project.id), "confirm": details["confirm"]})
        self.assertEqual("confirmed", run["permission"]["decision"])
        dry = self.start("xdemo.risky", request(self.project.id, dry_run=True))
        self.assertEqual("allowed", dry["permission"]["decision"])
        self.assertEqual("CONFIRMATION_REQUIRED", code(self.client.post("/v1/commands/xdemo.always/runs",
                                                                        json=request(self.project.id))))
        self.wait(run["run_id"])
        self.wait(dry["run_id"])

    def test_invalid_requests(self):
        body = request(self.project.id, name="x")
        cases = [("xdemo.echo", {**body, "argv": ["sh", "-c", "id"]}, "INPUT_INVALID"),
                 ("xdemo.echo", request(self.project.id, name="-rf"), "INPUT_INVALID"),
                 ("xdemo.echo", request(self.project.id), "INPUT_INVALID"),
                 ("xdemo.echo", request(None, name="x"), "INPUT_INVALID"),
                 ("xdemo.fail", request(None, dry_run=True), "INPUT_INVALID"),
                 ("xdemo.nope", body, "NOT_FOUND"),
                 ("xdemo.echo", request("gone-00000000", name="x"), "NOT_FOUND")]
        for command, payload, expected in cases:
            with self.subTest(command=command, payload=payload):
                self.assertEqual(expected, code(self.client.post(f"/v1/commands/{command}/runs", json=payload)))
        self.assertEqual([], self.client.get("/v1/runs").json()["runs"])
        for path in ("/v1/runs/run-x", "/v1/runs/" + "run-" + "0" * 32, "/v1/runs/run-x/log"):
            self.assertEqual("NOT_FOUND", code(self.client.get(path)))

    def test_concurrency_limit_and_cancel(self):
        state = self.backend.state
        state.settings = dataclasses.replace(state.settings, runs=dataclasses.replace(state.settings.runs, max_global=1))
        run = self.start("xdemo.ticks", request())
        response = self.client.post("/v1/commands/xdemo.fail/runs", json=request())
        self.assertEqual((429, "CONCURRENCY_LIMIT"), (response.status_code, code(response)))
        self.assertTrue(response.json()["error"]["retryable"])
        cancelling = self.client.post(f"/v1/runs/{run['run_id']}:cancel", json={})
        self.assertEqual((200, "cancelling"), (cancelling.status_code, cancelling.json()["state"]))
        self.assertEqual("cancelled", self.wait(run["run_id"])["state"])
        again = self.client.post(f"/v1/runs/{run['run_id']}:cancel", json={})
        self.assertEqual((409, "RUN_NOT_CANCELLABLE"), (again.status_code, code(again)))

    def test_invoke_command_redacts_its_output(self):
        run = self.start("xdemo.hello", request(name="Ann"))
        self.assertEqual("succeeded", self.wait(run["run_id"], timeout=60)["state"])
        text = "".join(c["text"] for c in self.client.get(f"/v1/runs/{run['run_id']}/log").json()["chunks"])
        self.assertIn("hello Ann", text)
        self.assertNotIn(SECRET_VALUE, text)


class TestLost(unittest.TestCase):
    def test_runs_of_an_earlier_backend_are_lost_at_start(self):
        backend = Backend(units="exec-demo")
        self.addCleanup(backend.close)
        store = RunStore(backend.conn)
        run = store.create(command="xdemo.ticks", owner="xdemo", dry_run=False, context={}, input={},
                           actor={"kind": "user", "id": "cli"}, correlation_id="c" * 32,
                           permission={"decision": "allowed", "effects": [], "grants": []})
        for target in ("authorizing", "starting", "running"):
            store.transition(run["run_id"], target, **({"pid": 2 ** 22 + 9, "pid_start": "1"}
                                                       if target == "running" else {}))
        with backend.client() as client:
            doc = client.get(f"/v1/runs/{run['run_id']}").json()
        self.assertEqual("lost", doc["state"])


class TestEvents(RunsCase):
    def connect(self, **headers):
        return self.client.websocket_connect("/v1/events", headers={**HOST, **ORIGIN, **headers})

    def subscribe(self, ws, sub="s", cursor=None, epoch=None, **filter_):
        ws.send_text(json.dumps({"$schema": "urn:swissknifeman:gui:stream:v1", "kind": "subscribe", "id": sub,
                                 "filter": filter_, "cursor": cursor, "epoch": epoch}))

    def frames_until(self, ws, predicate, limit=200):
        found = []
        for _ in range(limit):
            frame = json.loads(ws.receive_text())
            self.assertEqual([], contracts.validate(frame, "stream"), frame)
            found.append(frame)
            if predicate(frame):
                return found
        self.fail("the expected frame did not come")

    def test_run_frames_and_replay_after_reconnect(self):
        epoch = self.client.get("/v1/bootstrap").json()["epoch"]
        with self.connect() as ws:
            self.subscribe(ws, types=["gui.run", "gui.log"])
            run = self.start("xdemo.echo", request(self.project.id, name="Ws"))
            frames = self.frames_until(ws, lambda f: f["kind"] == "run" and f["run"]["state"] == "succeeded")
        kinds = {frame["kind"] for frame in frames}
        self.assertLessEqual({"run", "log"}, kinds)
        self.assertTrue(all(frame.get("sub") == "s" for frame in frames if frame["kind"] != "heartbeat"))
        logs = "".join(frame["text"] for frame in frames if frame["kind"] == "log")
        self.assertIn("arg:Ws", logs)
        cut = frames[2]["seq"]
        with self.connect() as ws:
            self.subscribe(ws, cursor=cut, epoch=epoch, runs=[run["run_id"]])
            replay = self.frames_until(ws, lambda f: f["kind"] == "run" and f["run"]["state"] == "succeeded")
        self.assertEqual([frame["seq"] for frame in frames[3:] if frame["kind"] != "heartbeat"],
                         [frame["seq"] for frame in replay])
        with self.connect() as ws:
            self.subscribe(ws, cursor=cut, epoch="another-epoch-01")
            frame = json.loads(ws.receive_text())
            self.assertEqual(("snapshot_required", "cursor_expired"), (frame["kind"], frame["reason"]))

    def test_bad_frames(self):
        with self.connect() as ws:
            ws.send_text("not json")
            self.assertEqual("INPUT_INVALID", json.loads(ws.receive_text())["error"]["code"])
            self.subscribe(ws, cursor=3, epoch=None)
            self.assertEqual("INPUT_INVALID", json.loads(ws.receive_text())["error"]["code"])
            ws.send_text(json.dumps({"$schema": "urn:swissknifeman:gui:stream:v1", "kind": "heartbeat", "seq": 1,
                                     "at": "2026-10-16T00:00:00Z"}))
            self.assertEqual("INPUT_INVALID", json.loads(ws.receive_text())["error"]["code"])
            for index in range(16):
                self.subscribe(ws, sub=f"s{index}")
            self.subscribe(ws, sub="s16")
            frame = json.loads(ws.receive_text())
            self.assertEqual(("CONCURRENCY_LIMIT", "s16"), (frame["error"]["code"], frame["sub"]))
            ws.send_text("x" * (64 * 1024 + 1))
            with self.assertRaises(WebSocketDisconnect) as caught:
                ws.receive_text()
            self.assertEqual(1009, caught.exception.code)

    def test_cookie_websocket_needs_origin(self):
        browser = self.backend.browser()
        # The TestClient WebSocket does not send the cookie jar: the cookie goes as a header.
        cookie = {"Cookie": f"skm_gui_session={browser.cookies['skm_gui_session']}", **HOST}
        with browser.websocket_connect("/v1/events", headers=cookie) as ws:
            self.subscribe(ws)
        del browser.headers["Origin"]
        with self.assertRaises(WebSocketDisconnect) as caught:
            with browser.websocket_connect("/v1/events", headers=cookie):
                pass
        self.assertEqual(4403, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
