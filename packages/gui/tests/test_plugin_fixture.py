"""The sample external extension ``tests/fixtures/extensions/ext-demo`` end to end below the browser: ``gui check``, the
catalog of a throwaway HOME whose ``[aicore.plugins]`` names it, Enable with the conformance gate, a grant, a command,
Disable during a run, quarantine and Release. The same scenarios as ``e2e/plugins.spec.ts``, at the level of the plugin
host (no Starlette) and of the ASGI application (``TestFixtureApi``)."""
import asyncio
import dataclasses
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from aicore.ext import settings as ext_settings
from aicore.ext.plugins import registered_plugins

from gui import contracts
from gui.backend import BackendState, Sessions
from gui.catalog import resolve, sources
from gui.core.plugins import PluginError
from gui.settings import load
from gui.storage import db

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXTENSION = FIXTURES / "extensions" / "ext-demo"
UNITS = FIXTURES / "units" / "empty"  # a hub registry without the extension: it is found only through [aicore.plugins]
ACTOR = {"kind": "user", "id": "test"}
API = "urn:swissknifeman:gui:plugin-api:v1"


def write_config(skm_home: Path) -> None:
    config = skm_home / "config" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(f'schema_version = 1\n\n[aicore.plugins.ext-demo]\nmanifest = "{EXTENSION / "extension.json"}"\n'
                      'enabled = true\ntrusted = true\n', encoding="utf-8")


class TestCheck(unittest.TestCase):
    def test_gui_check_has_no_failure(self):
        results = resolve.check(EXTENSION, env={"PATH": os.environ["PATH"], "HOME": tempfile.gettempdir()}, conformance=True)
        self.assertEqual([], [item for item in results if item["status"] == "fail"], results)
        self.assertTrue(any(item["check_id"].startswith("ext.conformance.") and item["status"] == "ok" for item in results))

    def test_the_sample_is_not_in_the_hub_registry_folder(self):
        self.assertFalse((FIXTURES / "units" / "ext-demo").exists())
        self.assertNotIn("extensions", {path.name for path in (FIXTURES / "units").iterdir()})

    def test_the_handler_and_the_script_write_nothing_and_are_executable(self):
        self.assertTrue(os.access(EXTENSION / "bin" / "slow", os.X_OK))
        text = (EXTENSION / "handler" / "handler.py").read_text(encoding="utf-8")
        for needle in ("open(", "write_text", "write_bytes", "os.remove", "shutil"):
            self.assertNotIn(needle, text)

    def test_contribution_declares_what_the_scenarios_need(self):
        gui = json.loads((EXTENSION / "gui.json").read_text(encoding="utf-8"))
        commands = {command["id"]: command for command in gui["commands"]}
        self.assertEqual(["process.spawn"], commands["ext-demo.slow"]["effects"])
        self.assertEqual({"cancel", "stream"}, set(commands["ext-demo.slow"]["supports"]))
        self.assertEqual("argv", commands["ext-demo.slow"]["exec"]["kind"])
        self.assertEqual((["project.write"], "invoke"), (commands["ext-demo.note"]["effects"],
                                                         commands["ext-demo.note"]["exec"]["kind"]))
        self.assertEqual({"ext-demo.items", "ext-demo.flaky"}, {query["id"] for query in gui["queries"]})
        self.assertIn("home", [route["path"] for route in gui["routes"]])


class StateCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"), "PATH": os.environ["PATH"],
                    "SKM_UNITS_PATH": str(UNITS), "AICORE_ROOT": os.environ.get("AICORE_ROOT", "")}
        (self.tmp / "home").mkdir()
        write_config(self.tmp / "skm")
        self.conn = db.open_db(self.tmp / "skm" / "state" / "gui" / "gui.db")
        self.addCleanup(self.conn.close)
        base = load(self.env)
        settings = dataclasses.replace(base, runs=dataclasses.replace(base.runs, cancel_grace_s=2),
                                       plugins=dataclasses.replace(base.plugins, drain_timeout_s=1))
        self.state = BackendState(settings=settings, conn=self.conn, env=self.env, sessions=Sessions(),
                                  state_folder=self.tmp / "skm" / "state" / "gui",
                                  collect=lambda: sources.collect(None, self.env))
        self.host = self.state.plugins

    async def asyncTearDown(self):
        await self.state.broker.shutdown(timeout=10)

    def registration(self):
        found, _ = registered_plugins(ext_settings.load(None, env=self.env), env=self.env)
        return next(entry for entry in found if entry.id == "ext-demo")

    def call(self, query_id="ext-demo.items", point="gui:query", effects=("read",)):
        ticket = self.host.admit("ext-demo", "query" if point == "gui:query" else "command", effects, None)
        payload = {"id": query_id, "context": {}, "params": {}} if point == "gui:query" else \
            {"id": query_id, "context": {}, "input": {}}
        result = ticket.invoke(self.registration(), point, payload, env=self.env, project=None)
        ticket.finish(None if result.status == "ok" else (result.code or result.status))
        return result

    async def run_slow(self):
        owner, command = self.state.catalog.commands["ext-demo.slow"]
        ticket = self.host.admit(owner, "command", command["effects"], None)
        try:
            return await self.state.broker.submit(
                owner=owner, owner_root=self.state.catalog.owners[owner].source.root, trusted=True, command=command,
                context={}, project_root=None, values={}, dry_run=False, confirmed=False, correlation_id="c" * 32,
                actor=ACTOR, ticket=ticket)
        except BaseException:
            ticket.finish(cancelled=True)
            raise

    def view(self):
        document = self.host.view("ext-demo")
        self.assertEqual([], contracts.validate(document, "trust"), document)
        return document


class TestScenarios(StateCase):
    async def test_the_catalog_accepts_the_sample_as_compatible_and_hides_it(self):
        view = self.view()
        self.assertEqual(("extension", "compatible", False), (view["source"], view["state"], view["ui_enabled"]))
        self.assertEqual(["ext-demo"], [entry["owner"] for entry in self.state.catalog.document["contributions"]])
        self.assertEqual([], self.state.visible_catalog()["contributions"])
        effects = {entry["effect"]: entry for entry in view["permissions"] if entry["declared"]}
        self.assertEqual({"read", "project.write", "process.spawn"}, set(effects))
        self.assertEqual("advisory", effects["project.write"]["enforcement"])

    async def test_enable_then_grant_then_note(self):
        await self.host.enable("ext-demo")
        self.assertEqual(["ext-demo"], [entry["owner"] for entry in self.state.visible_catalog()["contributions"]])
        self.assertEqual("ok", self.call().status)
        with self.assertRaises(PluginError) as caught:
            self.call("ext-demo.note", "gui:command", ("project.write",))
        self.assertEqual("PERMISSION_DENIED", caught.exception.code)
        grant = self.host.grant("ext-demo", "project.write", None, None, granted_by="cli")
        result = self.call("ext-demo.note", "gui:command", ("project.write",))
        self.assertEqual(("ok", {"ok": True}), (result.status, result.output))
        self.assertEqual([grant["id"]], [item["id"] for item in self.view()["grants"]])

    async def test_disable_during_a_slow_run_cancels_it(self):
        await self.host.enable("ext-demo")
        self.host.grant("ext-demo", "process.spawn", None, None, granted_by="cli")
        run = await self.run_slow()
        self.assertEqual("running", run["state"])
        self.assertEqual([run["run_id"]], self.host.active_runs("ext-demo"))
        outcome = await self.host.disable("ext-demo")
        self.assertEqual({"drained": 0, "cancelled": 1}, outcome)
        active = self.state.broker.active.get(run["run_id"])
        if active is not None:
            await asyncio.wait_for(active.done.wait(), 10)
        self.assertEqual("cancelled", self.state.store.get(run["run_id"])["state"])
        self.assertEqual("disabled", self.view()["state"])
        self.assertEqual([], self.state.visible_catalog()["contributions"])
        with self.assertRaises(PluginError) as caught:
            self.call()
        self.assertEqual("PLUGIN_DISABLED", caught.exception.code)

    async def test_the_run_prints_ticks_and_stops_on_sigterm(self):
        await self.host.enable("ext-demo")
        self.host.grant("ext-demo", "process.spawn", None, None, granted_by="cli")
        run = await self.run_slow()
        folder = self.state.runs_dir / run["run_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and "tick 1" not in "".join(
                (folder / "stdout.jsonl").read_text() if (folder / "stdout.jsonl").exists() else ""):
            await asyncio.sleep(0.1)
        await self.state.broker.cancel(run["run_id"], system=True)
        await asyncio.wait_for(self.state.broker.active[run["run_id"]].done.wait(), 10) \
            if run["run_id"] in self.state.broker.active else None
        text = (folder / "stdout.jsonl").read_text()
        self.assertIn("tick 1", text)
        self.assertEqual("cancelled", self.state.store.get(run["run_id"])["state"])

    async def test_three_flaky_calls_quarantine_and_release_heals(self):
        await self.host.enable("ext-demo")
        for _ in range(3):
            result = self.call("ext-demo.flaky")
            self.assertEqual("error", result.status)
        view = self.view()
        self.assertEqual(("quarantined", 3, False), (view["state"], view["failures"]["count"], view["ui_enabled"]))
        with self.assertRaises(PluginError) as caught:
            self.call()
        self.assertEqual("PLUGIN_QUARANTINED", caught.exception.code)
        self.assertEqual("enabled", self.host.release("ext-demo")["state"])
        self.assertEqual("ok", self.call().status)

    async def test_the_items_query_answers_a_valid_list(self):
        await self.host.enable("ext-demo")
        result = self.call()
        self.assertEqual([], contracts.validate(result.output, "view-data"))
        self.assertEqual(["alpha", "beta"], [row["id"] for row in result.output["rows"]])


class TestFixtureApi(unittest.TestCase):
    """The scenarios of the E2E over the ASGI application (needs the locked backend packages)."""

    def setUp(self):
        from tests.http_support import Backend

        self.backend = Backend(units="empty")
        self.addCleanup(self.backend.close)
        write_config(self.backend.tmp / "skm")
        state = self.backend.state
        state.settings = dataclasses.replace(
            state.settings, runs=dataclasses.replace(state.settings.runs, cancel_grace_s=2),
            plugins=dataclasses.replace(state.settings.plugins, drain_timeout_s=1))
        state.refresh_catalog()
        self.context = self.backend.client()
        self.client = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def post(self, path, body, expected):
        response = self.client.post(path, json=body)
        self.assertEqual(expected, response.status_code, response.text)
        return response.json()

    def action(self, verb, confirm=None, expected=200):
        body = {"$schema": API, "kind": "action_request", **({"confirm": confirm} if confirm else {})}
        return self.post(f"/v1/plugins/ext-demo:{verb}", body, expected)

    def grant(self, capability):
        body = {"$schema": API, "kind": "grant_request", "capability": capability, "project_id": None,
                "expires_at": None}
        first = self.post("/v1/plugins/ext-demo/grants", body, 428)
        return self.post("/v1/plugins/ext-demo/grants", {**body, "confirm": first["error"]["details"]["confirm"]}, 201)

    def start(self, command, expected=202):
        body = {"$schema": "urn:swissknifeman:gui:run-api:v1", "kind": "run_request", "context": {}, "input": {},
                "dry_run": False}
        return self.post(f"/v1/commands/{command}/runs", body, expected)

    def owners(self):
        return [entry["owner"] for entry in self.client.get("/v1/ui/contributions").json()["contributions"]]

    def wait(self, run_id, states, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            document = self.client.get(f"/v1/runs/{run_id}").json()
            if document["state"] in states:
                return document
            time.sleep(0.05)
        self.fail(f"run {run_id} did not reach {states}")

    def test_enable_grant_note_slow_disable_flaky_release(self):
        listing = self.client.get("/v1/plugins").json()
        self.assertEqual([], contracts.validate(listing, "plugin-api"))
        self.assertEqual("compatible", listing["plugins"][0]["state"])
        self.assertEqual([], self.owners())
        # enable: the route appears in the catalog
        self.assertEqual("enabled", self.action("enable")["plugin"]["state"])
        self.assertEqual(["ext-demo"], self.owners())
        # a note without a grant is refused, with one it runs
        denied = self.start("ext-demo.note", 403)
        self.assertEqual("PERMISSION_DENIED", denied["error"]["code"])
        grant = self.grant("project.write")["grant"]
        run = self.start("ext-demo.note")
        self.assertEqual([grant["id"]], run["permission"]["grants"])
        self.assertEqual("succeeded", self.wait(run["run_id"], ("succeeded", "failed"))["state"])
        # disable during a slow run
        self.grant("process.spawn")
        slow = self.start("ext-demo.slow")
        first = self.client.post("/v1/plugins/ext-demo:disable", json={"$schema": API, "kind": "action_request"})
        self.assertEqual(428, first.status_code)
        self.assertIn("1 active", first.json()["error"]["details"]["summary"])
        result = self.action("disable", first.json()["error"]["details"]["confirm"])
        self.assertEqual((0, 1, "disabled"), (result["drained"], result["cancelled"], result["plugin"]["state"]))
        self.assertEqual("cancelled", self.wait(slow["run_id"], ("cancelled", "failed", "succeeded"))["state"])
        self.assertEqual([], self.owners())
        # quarantine and release
        self.action("enable")
        for _ in range(3):
            response = self.client.post("/v1/queries/ext-demo.flaky", json={"context": {}, "params": {}})
            self.assertEqual("HANDLER_FAILED", response.json()["error"]["code"])
        self.assertEqual("quarantined", self.client.get("/v1/plugins/ext-demo").json()["state"])
        self.assertEqual("enabled", self.action("release")["plugin"]["state"])
        self.assertEqual(200, self.client.post("/v1/queries/ext-demo.items", json={"context": {}, "params": {}}).status_code)


if __name__ == "__main__":
    unittest.main()
