"""``/v1/config*`` over the local API: modules, effective view, preview and commit (Starlette TestClient)."""
import time
import unittest
from pathlib import Path

from tests.http_support import SECRET_VALUE, Backend

from aicore.ext.events import read_events
from aicore.state import machine_config_file, project_config_file
from aicore.util.digest import sha256_tagged

from gui import contracts

MUTATION = "urn:swissknifeman:gui:config-mutation:v1"
EMPTY = sha256_tagged(b"")


def code(response):
    body = response.json()
    assert contracts.validate(body, "api-error") == [], body
    return body["error"]["code"]


def preview_request(layer, patch, revision=EMPTY, module="config-demo"):
    return {"$schema": MUTATION, "kind": "preview_request", "module": module, "layer": layer,
            "expected_revision": revision, "patch": patch}


def commit_request(preview, confirmed=False, revision=None):
    return {"$schema": MUTATION, "kind": "commit_request", "preview_id": preview["preview_id"],
            "expected_revision": revision or preview["revision"], "confirmed": confirmed}


class ConfigApiCase(unittest.TestCase):
    def setUp(self):
        self.backend = Backend(units="config-demo")
        self.addCleanup(self.backend.close)
        self.project = self.backend.project()
        self.context = self.backend.client()
        self.client = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.machine = Path(machine_config_file(env=self.backend.env))
        self.project_file = Path(project_config_file(self.project.root))
        self.bodies = []

    def call(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.bodies.append(response.text)
        return response

    def preview(self, layer, patch, revision=EMPTY, expected=200):
        response = self.call("POST", f"/v1/config/config-demo/preview?project_id={self.project.id}",
                             json=preview_request(layer, patch, revision))
        self.assertEqual(expected, response.status_code, response.text)
        body = response.json()
        if expected == 200:
            self.assertEqual([], contracts.validate(body, "config-mutation"))
        return body

    def commit(self, layer, body, expected=200):
        response = self.call("PATCH", f"/v1/config/config-demo/layers/{layer}?project_id={self.project.id}",
                             json=body)
        self.assertEqual(expected, response.status_code, response.text)
        return response.json()

    def tearDown(self):
        # No response of the test carried the value of the secret in the environment.
        for body in self.bodies:
            self.assertNotIn(SECRET_VALUE, body)


class TestRead(ConfigApiCase):
    def test_modules(self):
        body = self.call("GET", "/v1/config").json()
        self.assertEqual([], contracts.validate(body, "config-view"))
        self.assertEqual(["config-demo"], [module["id"] for module in body["modules"]])

    def test_effective_without_and_with_a_project(self):
        body = self.call("GET", "/v1/config/config-demo/effective").json()
        self.assertEqual([], contracts.validate(body, "config-view"))
        layers = {layer["name"]: layer for layer in body["layers"]}
        self.assertFalse(layers["project"]["writable"])
        self.assertTrue(layers["machine"]["writable"])
        body = self.call("GET", f"/v1/config/config-demo/effective?project_id={self.project.id}").json()
        self.assertEqual([], contracts.validate(body, "config-view"))
        self.assertEqual(self.project.id, body["project_id"])
        self.assertTrue(next(layer for layer in body["layers"] if layer["name"] == "project")["writable"])

    def test_raw_of_a_layer_redacts_the_secret_of_the_environment(self):
        self.machine.parent.mkdir(parents=True, exist_ok=True)
        self.machine.write_text(f"# {SECRET_VALUE}\nschema_version = 1\n", encoding="utf-8")
        body = self.call("GET", "/v1/config/config-demo/effective").json()
        raw = next(layer for layer in body["layers"] if layer["name"] == "machine")["raw"]
        self.assertNotIn(SECRET_VALUE, raw)
        self.assertIn("schema_version", raw)

    def test_unknown_module_and_project(self):
        self.assertEqual("NOT_FOUND", code(self.call("GET", "/v1/config/nothing/effective")))
        self.assertEqual("NOT_FOUND", code(self.call("GET", "/v1/config/Bad_Id/effective")))
        self.assertEqual("NOT_FOUND", code(self.call("GET", "/v1/config/config-demo/effective?project_id=nope-0000")))

    def test_the_session_is_required(self):
        anonymous = self.backend.client(bearer=False)
        self.assertEqual(401, anonymous.get("/v1/config").status_code)


class TestWrite(ConfigApiCase):
    def test_preview_then_commit_in_the_project_layer(self):
        preview = self.preview("project", [{"op": "set", "key": "limits.max", "value": 6}])
        self.assertEqual({"confirm_required": False, "confirm_reasons": []},
                         {key: preview[key] for key in ("confirm_required", "confirm_reasons")})
        self.assertFalse(self.project_file.exists())
        result = self.commit("project", commit_request(preview))
        self.assertEqual([], contracts.validate(result, "config-mutation"))
        self.assertIn("max = 6", self.project_file.read_text(encoding="utf-8"))
        self.assertEqual(sha256_tagged(self.project_file.read_bytes()), result["revision"])
        view = self.call("GET", f"/v1/config/config-demo/effective?project_id={self.project.id}").json()
        maximum = next(entry for entry in view["entries"] if entry["key"] == "limits.max")
        self.assertEqual(6, maximum["effective"]["value"])
        self.assertEqual(str(self.project_file), maximum["effective"]["file"])
        rows = [(row["action"], row["target"], row["decision"])
                for row in self.backend.conn.execute("SELECT * FROM audit ORDER BY id")]
        self.assertIn(("config.commit", "config-demo:project", "applied"), rows)
        deadline = time.monotonic() + 5
        events = []
        while time.monotonic() < deadline and not events:
            events, _ = read_events(self.project.root, types=["gui.config.changed"])
            time.sleep(0.05)
        self.assertEqual({"module": "config-demo", "layer": "project", "keys": ["limits.max"],
                          "revision": result["revision"]}, events[0].data)

    def test_machine_layer_needs_a_confirmation_and_publishes_a_frame(self):
        subscription = self.backend.state.hub.subscribe("s1", {}, None, None)
        preview = self.preview("machine", [{"op": "set", "key": "mode", "value": "fast"}])
        self.assertEqual(["machine_layer"], preview["confirm_reasons"])
        refused = self.call("PATCH", f"/v1/config/config-demo/layers/machine?project_id={self.project.id}",
                            json=commit_request(preview))
        self.assertEqual("CONFIRMATION_REQUIRED", code(refused))
        self.assertEqual(428, refused.status_code)
        self.assertFalse(self.machine.exists())
        result = self.call("PATCH", f"/v1/config/config-demo/layers/machine?project_id={self.project.id}",
                           json=commit_request(preview, confirmed=True))
        self.assertEqual(200, result.status_code, result.text)
        self.assertIn('mode = "fast"', self.machine.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        frame = None
        while time.monotonic() < deadline and frame is None:
            frame = subscription.get_nowait()
            time.sleep(0.02)
        self.assertEqual("event", frame["kind"])
        self.assertEqual("gui.config.changed", frame["event"]["type"])
        self.assertEqual("machine", frame["event"]["data"]["layer"])

    def test_stale_revision_is_409_with_the_current_revision(self):
        self.project_file.parent.mkdir(parents=True, exist_ok=True)
        self.project_file.write_text("schema_version = 1\n", encoding="utf-8")
        response = self.call("POST", f"/v1/config/config-demo/preview?project_id={self.project.id}",
                             json=preview_request("project", [{"op": "set", "key": "verbose", "value": True}]))
        self.assertEqual(409, response.status_code)
        self.assertEqual("CONFIG_REVISION_CONFLICT", code(response))
        self.assertEqual(sha256_tagged(self.project_file.read_bytes()),
                         response.json()["error"]["details"]["current_revision"])
        preview = self.preview("project", [{"op": "set", "key": "verbose", "value": True}],
                               revision=sha256_tagged(self.project_file.read_bytes()))
        self.project_file.write_text("schema_version = 1\n# changed\n", encoding="utf-8")
        edited = self.project_file.read_bytes()
        conflict = self.call("PATCH", f"/v1/config/config-demo/layers/project?project_id={self.project.id}",
                             json=commit_request(preview))
        self.assertEqual(409, conflict.status_code)
        self.assertEqual("CONFIG_REVISION_CONFLICT", code(conflict))
        self.assertEqual(sha256_tagged(edited), conflict.json()["error"]["details"]["current_revision"])
        self.assertEqual(edited, self.project_file.read_bytes())

    def test_env_layer_is_forbidden(self):
        response = self.call("PATCH", "/v1/config/config-demo/layers/env", json={})
        self.assertEqual(403, response.status_code)
        self.assertEqual("CONFIG_LAYER_FORBIDDEN", code(response))
        self.assertEqual("CONFIG_LAYER_FORBIDDEN", code(self.call("PATCH", "/v1/config/config-demo/layers/flags",
                                                                 json={})))

    def test_unknown_preview_is_stale_and_a_commit_cannot_carry_a_patch(self):
        stale = self.call("PATCH", f"/v1/config/config-demo/layers/project?project_id={self.project.id}",
                          json={"$schema": MUTATION, "kind": "commit_request", "preview_id": "sha256:" + "0" * 64,
                                "expected_revision": EMPTY, "confirmed": True})
        self.assertEqual(409, stale.status_code)
        self.assertEqual("PREVIEW_STALE", code(stale))
        preview = self.preview("project", [{"op": "set", "key": "limits.max", "value": 6}])
        smuggled = {**commit_request(preview), "patch": [{"op": "set", "key": "limits.max", "value": 99}]}
        rejected = self.call("PATCH", f"/v1/config/config-demo/layers/project?project_id={self.project.id}",
                             json=smuggled)
        self.assertEqual("INPUT_INVALID", code(rejected))
        self.assertFalse(self.project_file.exists())

    def test_input_errors(self):
        url = f"/v1/config/config-demo/preview?project_id={self.project.id}"
        self.assertEqual("INPUT_INVALID", code(self.call("POST", url, json={"kind": "preview_request"})))
        self.assertEqual("INPUT_INVALID", code(self.call("POST", url, content=b"not json")))
        self.assertEqual("INPUT_INVALID", code(self.call(
            "POST", url, json=preview_request("project", [{"op": "set", "key": "verbose", "value": True}],
                                              module="other"))))
        no_project = self.call("POST", "/v1/config/config-demo/preview",
                               json=preview_request("project", [{"op": "set", "key": "verbose", "value": True}]))
        self.assertEqual("INPUT_INVALID", code(no_project))
        self.assertEqual("NOT_FOUND", code(self.call(
            "POST", "/v1/config/nothing/preview", json=preview_request(
                "machine", [{"op": "set", "key": "verbose", "value": True}], module="nothing"))))
        self.assertEqual("NOT_FOUND", code(self.call(
            "POST", "/v1/config/config-demo/preview?project_id=nope-0000",
            json=preview_request("project", [{"op": "set", "key": "verbose", "value": True}]))))

    def test_a_secret_value_is_refused_and_never_echoed(self):
        preview = self.preview("machine", [{"op": "set", "key": "token", "value": SECRET_VALUE}])
        self.assertEqual(["SECRET_REF_INVALID"], [issue["code"] for issue in preview["issues"]])
        refused = self.call("PATCH", f"/v1/config/config-demo/layers/machine?project_id={self.project.id}",
                            json=commit_request(preview, confirmed=True))
        self.assertEqual("INPUT_INVALID", code(refused))
        self.assertFalse(self.machine.exists())
        good = self.preview("machine", [{"op": "set", "key": "token", "value": "env://SKM_TEST_SECRET"}])
        self.assertEqual(["machine_layer", "secret_key"], good["confirm_reasons"])
        self.call("PATCH", f"/v1/config/config-demo/layers/machine?project_id={self.project.id}",
                  json=commit_request(good, confirmed=True))
        self.assertNotIn(SECRET_VALUE, self.machine.read_text(encoding="utf-8"))
        self.call("GET", f"/v1/config/config-demo/effective?project_id={self.project.id}")

    def test_the_browser_session_can_write(self):
        browser = self.backend.browser()
        response = browser.post(f"/v1/config/config-demo/preview?project_id={self.project.id}",
                                json=preview_request("project", [{"op": "set", "key": "verbose", "value": True}]))
        self.assertEqual(200, response.status_code, response.text)


if __name__ == "__main__":
    unittest.main()
