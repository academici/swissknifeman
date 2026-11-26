"""``/v1/plugins*`` and the plugin gates of queries, commands and the catalog over the local API (ASGI TestClient).

A hub unit (``xdemo``, source ``unit``) and a throwaway external extension (``xext``, source ``extension``, enabled and
trusted in the machine layer of ``[aicore.plugins]``) run behind the backend of a temporary SKM_HOME.
"""
import dataclasses
import json
import time
import unittest

from tests import plugin_support as support
from tests.http_support import PORT, Backend

from gui import contracts

ORIGIN = {"Origin": f"http://127.0.0.1:{PORT}"}
HOST = {"Host": f"127.0.0.1:{PORT}"}
API = "urn:swissknifeman:gui:plugin-api:v1"
RUN_API = "urn:swissknifeman:gui:run-api:v1"
TERMINAL = ("succeeded", "failed", "cancelled", "timed_out", "denied", "failed_to_start")


def no_float(value):
    raise AssertionError(f"a float in a response: {value}")


class PluginsCase(unittest.TestCase):
    def setUp(self):
        self.backend = Backend(units="exec-demo")
        self.addCleanup(self.backend.close)
        self.root = support.make_extension(self.backend.tmp / "ext")
        support.register(self.backend.tmp / "skm", self.root)
        settings = self.backend.state.settings
        self.backend.state.settings = dataclasses.replace(
            settings, runs=dataclasses.replace(settings.runs, cancel_grace_s=1),
            plugins=dataclasses.replace(settings.plugins, drain_timeout_s=0))
        self.backend.state.refresh_catalog()
        self.project = self.backend.project()
        self.bodies = []
        self.context = self.backend.client()
        self.client = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    # --- helpers ---

    def send(self, method, path, body=None, expected=None):
        response = self.client.request(method, path, json=body) if body is not None else \
            self.client.request(method, path)
        self.bodies.append(response.text)
        json.loads(response.text, parse_float=no_float)  # no float anywhere (the canonical JSON refuses it)
        self.assertNotIn("enforced", response.text)
        if expected is not None:
            self.assertEqual(expected, response.status_code, response.text)
        return response

    def code(self, response):
        body = response.json()
        self.assertEqual([], contracts.validate(body, "api-error"), body)
        return body["error"]["code"]

    def action(self, plugin, verb, confirm=None, expected=200):
        body = {"$schema": API, "kind": "action_request"}
        if confirm:
            body["confirm"] = confirm
        response = self.send("POST", f"/v1/plugins/{plugin}:{verb}", body, expected)
        if expected == 200:
            document = response.json()
            self.assertEqual([], contracts.validate(document, "plugin-api"), document)
            self.assertEqual([], contracts.validate(document["plugin"], "trust"))
        return response

    def view(self, plugin, query=""):
        response = self.send("GET", f"/v1/plugins/{plugin}{query}", expected=200)
        self.assertEqual([], contracts.validate(response.json(), "trust"), response.json())
        return response.json()

    def grant_body(self, capability="network", project_id=None, expires_at=None, confirm=None):
        body = {"$schema": API, "kind": "grant_request", "capability": capability, "project_id": project_id,
                "expires_at": expires_at}
        if confirm:
            body["confirm"] = confirm
        return body

    def grant(self, plugin="xext", **kw):
        first = self.send("POST", f"/v1/plugins/{plugin}/grants", self.grant_body(**kw), 428)
        self.assertEqual("CONFIRMATION_REQUIRED", self.code(first))
        token = first.json()["error"]["details"]["confirm"]
        response = self.send("POST", f"/v1/plugins/{plugin}/grants", self.grant_body(confirm=token, **kw), 201)
        document = response.json()
        self.assertEqual([], contracts.validate(document, "plugin-api"), document)
        return document["grant"]

    def query(self, query="xext.status"):
        return self.send("POST", f"/v1/queries/{query}", {"context": {}, "params": {}})

    def command_body(self, project_id=None):
        return {"$schema": RUN_API, "kind": "run_request", "context": {"project_id": project_id} if project_id else {},
                "input": {}, "dry_run": False}

    def start(self, command, expected=202):
        return self.send("POST", f"/v1/commands/{command}/runs", self.command_body(), expected)

    def wait(self, run_id, states=TERMINAL, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            document = self.client.get(f"/v1/runs/{run_id}").json()
            if document["state"] in states:
                self.assertEqual([], contracts.validate(document, "run"))
                return document
            time.sleep(0.05)
        self.fail(f"run {run_id} did not reach {states}")

    def owners(self):
        return [entry["owner"] for entry in self.send("GET", "/v1/ui/contributions", expected=200).json()["contributions"]]

    def enable(self, plugin="xext"):
        return self.action(plugin, "enable").json()


class TestListAndHistory(PluginsCase):
    def test_list_and_detail_are_trust_documents(self):
        listing = self.send("GET", "/v1/plugins", expected=200).json()
        self.assertEqual([], contracts.validate(listing, "plugin-api"), listing)
        self.assertEqual(["xdemo", "xext"], [entry["id"] for entry in listing["plugins"]])
        states = {entry["id"]: (entry["source"], entry["state"], entry["ui_enabled"]) for entry in listing["plugins"]}
        self.assertEqual({"xdemo": ("unit", "enabled", True), "xext": ("extension", "compatible", False)}, states)
        detail = self.view("xext")
        self.assertEqual(listing["plugins"][1], detail)
        effects = {entry["effect"]: entry for entry in detail["permissions"]}
        self.assertEqual(("advisory", True), (effects["network"]["enforcement"], effects["network"]["declared"]))
        self.assertEqual("declared", effects["read"]["enforcement"])
        self.view("xext", f"?project_id={self.project.id}")

    def test_unknown_plugin_project_and_ids(self):
        self.assertEqual("NOT_FOUND", self.code(self.send("GET", "/v1/plugins/nobody", expected=404)))
        self.assertEqual("NOT_FOUND", self.code(self.send("GET", "/v1/plugins/Bad_Id", expected=404)))
        self.assertEqual("NOT_FOUND", self.code(self.send("GET", "/v1/plugins/xext?project_id=gone-00000000")))
        self.assertEqual("NOT_FOUND", self.code(self.send("GET", "/v1/plugins?project_id=gone-00000000")))
        self.assertEqual("NOT_FOUND", self.code(self.send("GET", "/v1/plugins/nobody/history")))
        self.assertEqual("NOT_FOUND", self.code(self.action("nobody", "enable", expected=404)))

    def test_history_is_newest_first_and_bounded(self):
        self.enable()
        self.action("xext", "disable")
        document = self.send("GET", "/v1/plugins/xext/history", expected=200).json()
        self.assertEqual([], contracts.validate(document, "plugin-api"), document)
        self.assertEqual("xext", document["plugin"])
        ids = [entry["id"] for entry in document["entries"]]
        self.assertEqual(sorted(ids, reverse=True), ids)
        self.assertEqual(("state", "disabled"), (document["entries"][0]["kind"], document["entries"][0]["code"]))
        self.assertIn(("admin", "disable"), [(e["kind"], e.get("code")) for e in document["entries"]])
        self.assertEqual(2, len(self.send("GET", "/v1/plugins/xext/history?limit=2", expected=200).json()["entries"]))
        for bad in ("0", "201", "abc", "-1"):
            self.assertEqual("INPUT_INVALID", self.code(self.send("GET", f"/v1/plugins/xext/history?limit={bad}")), bad)


class TestEnableAndQueries(PluginsCase):
    def test_extension_is_off_until_enabled_and_the_catalog_follows(self):
        self.assertEqual(["xdemo"], self.owners())
        self.assertEqual("PLUGIN_DISABLED", self.code(self.query()))
        self.assertEqual(503, self.query().status_code)
        document = self.enable()
        self.assertEqual((0, 0, "enabled"), (document["drained"], document["cancelled"], document["plugin"]["state"]))
        self.assertEqual(["xdemo", "xext"], self.owners())
        answer = self.query()
        self.assertEqual(200, answer.status_code, answer.text)
        self.assertEqual("metric-group", answer.json()["view"])
        self.assertEqual("healthy", self.view("xext")["state"])
        self.assertEqual(["xdemo", "xext"], [e["owner"] for e in self.send(
            "GET", "/v1/ui/contributions?refresh=1", expected=200).json()["contributions"]])

    def test_catalog_digest_is_recomputed_without_hidden_plugins(self):
        full = self.send("GET", "/v1/ui/contributions", expected=200).json()
        self.enable()
        both = self.send("GET", "/v1/ui/contributions", expected=200).json()
        self.assertNotEqual(full["digest"], both["digest"])
        self.action("xext", "disable")
        again = self.send("GET", "/v1/ui/contributions", expected=200).json()
        self.assertEqual(full["digest"], again["digest"])
        self.assertEqual([], contracts.validate(again, "catalog"))
        self.assertEqual("xext", self.view("xext")["id"])  # still listed under /v1/plugins

    def test_cached_answer_of_a_disabled_plugin_is_not_served(self):
        owner, query = self.backend.state.catalog.queries["xext.status"]
        self.backend.state.catalog.queries["xext.status"] = (owner, {**query, "cache_s": 60})
        self.enable()
        self.assertEqual(200, self.query().status_code)
        self.assertEqual(200, self.query().status_code)  # from the cache
        self.action("xext", "disable")
        self.assertEqual("PLUGIN_DISABLED", self.code(self.query()))

    def test_conformance_gate_refuses_a_broken_handler(self):
        (self.root / "handler.py").write_text("import sys\nsys.stdout.write('nope')\n", encoding="utf-8")
        response = self.action("xext", "enable", expected=422)
        self.assertEqual("PLUGIN_CONFORMANCE_FAILED", self.code(response))
        details = response.json()["error"]["details"]
        self.assertGreaterEqual(details["count"], 1)
        self.assertTrue(details["findings"])
        self.assertEqual("compatible", self.view("xext")["state"])

    def test_hub_unit_enable_disable_roundtrip(self):
        self.action("xdemo", "disable")
        self.assertEqual("disabled", self.view("xdemo")["state"])
        self.assertNotIn("xdemo", self.owners())
        self.assertEqual("PLUGIN_DISABLED", self.code(self.start("xdemo.ticks", expected=503)))
        self.action("xdemo", "enable")
        self.assertIn("xdemo", self.owners())

    def test_action_bodies_are_checked(self):
        bad = {"$schema": API, "kind": "action_request", "force": True}
        self.assertEqual("INPUT_INVALID", self.code(self.send("POST", "/v1/plugins/xext:enable", bad, 422)))
        wrong_kind = {"$schema": API, "kind": "grant_request"}
        self.assertEqual("INPUT_INVALID", self.code(self.send("POST", "/v1/plugins/xext:release", wrong_kind, 422)))
        self.send("POST", "/v1/plugins/xdemo:release", {}, 200)  # an empty object is an action without confirm


class TestQuarantine(PluginsCase):
    def test_failures_quarantine_and_release_heals(self):
        self.enable()
        support.set_mode(self.root, "garbage")
        for _ in range(3):
            self.assertEqual("HANDLER_FAILED", self.code(self.query()))
        view = self.view("xext")
        self.assertEqual(("quarantined", 3, False), (view["state"], view["failures"]["count"], view["ui_enabled"]))
        self.assertEqual("PLUGIN_QUARANTINED", self.code(self.query()))
        self.assertEqual(503, self.query().status_code)
        self.assertEqual("PLUGIN_QUARANTINED", self.code(self.action("xext", "enable", expected=503)))
        self.assertNotIn("xext", self.owners())
        support.set_mode(self.root, "ok")
        released = self.action("xext", "release").json()["plugin"]
        self.assertEqual(("enabled", 0), (released["state"], released["failures"]["count"]))
        self.assertEqual(200, self.query().status_code)
        kinds = [entry["kind"] for entry in self.send("GET", "/v1/plugins/xext/history?limit=50").json()["entries"]]
        self.assertIn("failure", kinds)

    def test_domain_errors_are_not_failures(self):
        self.enable()
        support.set_mode(self.root, "domain")
        for _ in range(5):
            self.assertEqual("HANDLER_FAILED", self.code(self.query()))
        view = self.view("xext")
        self.assertEqual((0, "healthy"), (view["failures"]["count"], view["state"]))

    def test_an_invalid_view_counts_as_output_invalid(self):
        self.enable()
        support.set_mode(self.root, "badview")
        for _ in range(3):
            self.assertEqual("OUTPUT_INVALID", self.code(self.query()))
        self.assertEqual("quarantined", self.view("xext")["state"])
        self.assertEqual("OUTPUT_INVALID", self.view("xext")["failures"]["last_code"])


class TestGrants(PluginsCase):
    def test_command_without_a_grant_is_denied_with_one_it_runs_and_a_revoke_denies_again(self):
        self.enable()
        denied = self.start("xext.net", expected=403)
        self.assertEqual("PERMISSION_DENIED", self.code(denied))
        self.assertEqual({"plugin": "xext", "effect": "network", "project_id": None},
                         denied.json()["error"]["details"])
        self.assertEqual([], self.client.get("/v1/runs").json()["runs"])
        grant = self.grant()
        self.assertEqual(["xext", "network", None], [grant["plugin"], grant["capability"], grant["project_id"]])
        self.assertEqual("cli", grant["granted_by"])  # a bearer client
        run = self.start("xext.net").json()
        self.assertEqual([grant["id"]], run["permission"]["grants"])
        done = self.wait(run["run_id"])
        self.assertEqual("succeeded", done["state"])
        self.assertEqual([grant["id"]], done["permission"]["grants"])
        self.assertEqual([grant["id"]], [g["id"] for g in self.view("xext")["grants"]])
        revoked = self.send("POST", f"/v1/plugins/xext/grants/{grant['id']}:revoke",
                            {"$schema": API, "kind": "action_request"}, 200).json()
        self.assertEqual([], revoked["plugin"]["grants"])
        self.assertEqual("PERMISSION_DENIED", self.code(self.start("xext.net", expected=403)))

    def test_grant_is_always_confirmed_and_the_token_fits_only_that_request(self):
        self.enable()
        first = self.send("POST", "/v1/plugins/xext/grants", self.grant_body(), 428)
        details = first.json()["error"]["details"]
        self.assertEqual("high", details["risk"])  # every project
        self.assertIn("network", details["summary"])
        project = self.send("POST", "/v1/plugins/xext/grants", self.grant_body(project_id=self.project.id), 428)
        self.assertEqual("medium", project.json()["error"]["details"]["risk"])
        # a token of another request does not pass
        for other in (self.grant_body(project_id=self.project.id, confirm=details["confirm"]),
                      self.grant_body(capability="process.spawn", confirm=details["confirm"]),
                      self.grant_body(expires_at="2999-01-01T00:00:00Z", confirm=details["confirm"]),
                      self.grant_body(confirm="0" * 64)):
            self.assertEqual("CONFIRMATION_REQUIRED", self.code(self.send("POST", "/v1/plugins/xext/grants", other, 428)))
        self.assertEqual([], self.view("xext")["grants"])

    def test_grant_requests_are_validated(self):
        self.enable()
        for body in (self.grant_body("read"), self.grant_body("terminal"), self.grant_body("secrets.read")):
            self.assertEqual("INPUT_INVALID", self.code(self.send("POST", "/v1/plugins/xext/grants", body, 422)))
        unknown_project = self.grant_body(project_id="gone-00000000")
        first = self.send("POST", "/v1/plugins/xext/grants", unknown_project)
        self.assertEqual("INPUT_INVALID", self.code(first))
        for body in ({**self.grant_body(), "extra": 1}, {"kind": "grant_request"}, self.grant_body(expires_at="soon")):
            self.assertEqual("INPUT_INVALID", self.code(self.send("POST", "/v1/plugins/xext/grants", body, 422)))
        past = self.send("POST", "/v1/plugins/xext/grants", self.grant_body(expires_at="2001-01-01T00:00:00Z"), 428)
        confirmed = self.send("POST", "/v1/plugins/xext/grants", self.grant_body(
            expires_at="2001-01-01T00:00:00Z", confirm=past.json()["error"]["details"]["confirm"]), 422)
        self.assertEqual("INPUT_INVALID", self.code(confirmed))  # an expiry in the past
        self.assertEqual("INPUT_INVALID", self.code(self.send("POST", "/v1/plugins/xdemo/grants", self.grant_body())))
        self.assertEqual([], self.view("xext")["grants"])

    def test_grant_for_a_project_applies_to_that_project_only(self):
        self.enable()
        grant = self.grant(project_id=self.project.id)
        self.assertEqual(self.project.id, grant["project_id"])
        self.assertEqual([], self.view("xext")["grants"])  # no project chosen: only every-project grants
        self.assertEqual([grant["id"]], [g["id"] for g in self.view("xext", f"?project_id={self.project.id}")["grants"]])
        self.assertEqual("PERMISSION_DENIED", self.code(self.start("xext.net", expected=403)))  # the run has no project

    def test_revoke_errors(self):
        self.enable()
        body = {"$schema": API, "kind": "action_request"}
        self.assertEqual("NOT_FOUND", self.code(self.send(
            "POST", "/v1/plugins/xext/grants/grant-" + "0" * 32 + ":revoke", body, 404)))
        self.assertEqual("NOT_FOUND", self.code(self.send("POST", "/v1/plugins/xext/grants/bogus:revoke", body, 404)))

    def test_hub_unit_run_needs_no_grant_and_records_none(self):
        run = self.start("xdemo.ticks").json()
        self.assertEqual([], run["permission"]["grants"])
        self.assertEqual([{"effect": "process.spawn", "enforcement": "declared"}], run["permission"]["effects"])
        self.send("POST", f"/v1/runs/{run['run_id']}:cancel", {}, 200)
        self.wait(run["run_id"])

    def test_a_changed_manifest_with_a_wider_effect_voids_the_grant(self):
        self.enable()
        self.grant()
        support.make_extension(self.backend.tmp / "ext", extra_effects=("project.write",))
        self.send("GET", "/v1/ui/contributions?refresh=1", expected=200)
        view = self.view("xext")
        self.assertEqual(("permission_denied", []), (view["state"], view["grants"]))
        self.assertEqual("PERMISSION_DENIED", self.code(self.start("xext.net", expected=403)))
        self.assertEqual(200, self.query().status_code)  # queries (read) and routes stay
        self.grant()  # a new grant lifts the re-approval
        self.assertIn(self.view("xext")["state"], ("enabled", "healthy"))


class TestDisable(PluginsCase):
    def start_sleep(self):
        self.enable()
        self.grant(capability="process.spawn")
        run = self.start("xext.sleep").json()
        self.assertEqual("running", run["state"])
        return run

    def test_disable_with_an_active_run_asks_then_cancels_it(self):
        run = self.start_sleep()
        first = self.action("xext", "disable", expected=428)
        self.assertEqual("CONFIRMATION_REQUIRED", self.code(first))
        details = first.json()["error"]["details"]
        self.assertEqual("medium", details["risk"])
        self.assertIn("1 active", details["summary"])
        self.assertEqual("running", self.client.get(f"/v1/runs/{run['run_id']}").json()["state"])
        self.assertEqual("CONFIRMATION_REQUIRED", self.code(self.action("xext", "disable", "0" * 64, expected=428)))
        self.assertTrue(self.view("xext")["ui_enabled"])
        result = self.action("xext", "disable", details["confirm"]).json()
        self.assertEqual((0, 1, "disabled"), (result["drained"], result["cancelled"], result["plugin"]["state"]))
        self.assertEqual("cancelled", self.wait(run["run_id"])["state"])
        self.assertNotIn("xext", self.owners())
        self.assertEqual("PLUGIN_DISABLED", self.code(self.query()))
        self.assertEqual("PLUGIN_DISABLED", self.code(self.start("xext.sleep", expected=503)))
        self.assertEqual("xext", self.view("xext")["id"])
        self.enable()
        self.assertIn("xext", self.owners())

    def test_disable_without_runs_needs_no_confirmation(self):
        self.enable()
        result = self.action("xext", "disable").json()
        self.assertEqual((0, 0, "disabled"), (result["drained"], result["cancelled"], result["plugin"]["state"]))


class TestEvents(PluginsCase):
    def connect(self):
        return self.client.websocket_connect("/v1/events", headers={**HOST, **ORIGIN})

    def test_state_and_grant_events_reach_a_subscriber(self):
        with self.connect() as ws:
            ws.send_text(json.dumps({"$schema": "urn:swissknifeman:gui:stream:v1", "kind": "subscribe", "id": "p",
                                     "filter": {"types": ["gui.plugin.*"]}, "cursor": None, "epoch": None}))
            self.enable()
            self.grant()
            self.action("xext", "disable")
            seen = []
            for _ in range(100):
                frame = json.loads(ws.receive_text())
                self.assertEqual([], contracts.validate(frame, "stream"), frame)
                if frame["kind"] == "event":
                    seen.append((frame["event"]["type"], frame["event"]["data"]))
                if ("gui.plugin.state", "disabled") in [(t, d.get("to")) for t, d in seen]:
                    break
        self.assertIn(("gui.plugin.state", ("compatible", "enabled")),
                      [(t, (d["from"], d["to"])) for t, d in seen if t == "gui.plugin.state"])
        self.assertIn(("gui.plugin.grant", "granted"), [(t, d["action"]) for t, d in seen if t == "gui.plugin.grant"])
        self.assertIn(("enabled", "disabled"), [(d["from"], d["to"]) for t, d in seen if t == "gui.plugin.state"])


class TestBootstrapAndHistory(PluginsCase):
    def test_feature_and_contract_are_advertised(self):
        body = self.send("GET", "/v1/bootstrap", expected=200).json()
        self.assertIn("plugins", body["features"])
        self.assertIn({"id": API.rpartition(":")[0], "version": "v1"}, body["contracts"])
        schema = self.send("GET", "/v1/schemas/plugin-api/v1", expected=200).json()
        self.assertEqual(API, schema["$id"])

    def test_no_response_so_far_claims_enforced(self):
        self.enable()
        self.grant()
        self.send("GET", "/v1/plugins", expected=200)
        self.assertFalse([text for text in self.bodies if "enforced" in text])


if __name__ == "__main__":
    unittest.main()
