"""The PluginHost inside the backend: wiring, the gates in front of runs, real handler outcomes, visibility of the
catalog and the structural rule that no work of a plugin bypasses ``admit`` (no Starlette needed)."""
import asyncio
import dataclasses
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from aicore.ext import settings as ext_settings
from aicore.ext.plugins import registered_plugins
from aicore.util.digest import digest_json

from gui import contracts
from gui.backend import FEATURES, BackendState, Sessions
from gui.catalog import resolve, sources
from gui.core import plugins
from gui.core.plugins import PluginError
from gui.settings import load
from gui.storage import db
from tests import plugin_support as support

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "units"
LIB = Path(__file__).resolve().parents[1] / "lib" / "gui"
ACTOR = {"kind": "user", "id": "test"}


class TestStructure(unittest.TestCase):
    def test_invoke_one_is_called_only_by_the_plugin_host(self):
        callers = sorted(str(path.relative_to(LIB)) for path in LIB.rglob("*.py")
                         if re.search(r"\binvoke_one\(", path.read_text(encoding="utf-8")))
        self.assertEqual(["core/plugins.py"], callers)

    def test_nothing_imports_invoke_one_besides_the_host(self):
        for path in LIB.rglob("*.py"):
            if path.relative_to(LIB).as_posix() != "core/plugins.py":
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"import[^\n]*\binvoke_one\b", path.name)

    def test_the_http_layer_asks_the_host_before_it_runs_anything(self):
        for name in ("routes_queries.py", "routes_runs.py"):
            text = (LIB / "http" / name).read_text(encoding="utf-8")
            self.assertIn("plugins.admit(", text, name)
        self.assertIn("ticket=ticket", (LIB / "http" / "routes_runs.py").read_text(encoding="utf-8"))

    def test_broker_submit_takes_the_ticket(self):
        import inspect

        from gui.core.broker import Broker

        self.assertIn("ticket", inspect.signature(Broker.submit).parameters)


class StateCase(unittest.IsolatedAsyncioTestCase):
    units = "exec-demo"

    async def asyncSetUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"), "PATH": os.environ["PATH"],
                    "SKM_UNITS_PATH": os.pathsep.join(str(FIXTURES / name) for name in self.units.split(",")),
                    "AICORE_ROOT": os.environ.get("AICORE_ROOT", "")}
        (self.tmp / "home").mkdir()
        self.prepare()
        self.conn = db.open_db(self.tmp / "skm" / "state" / "gui" / "gui.db")
        self.addCleanup(self.conn.close)
        base = load(self.env)
        settings = dataclasses.replace(base, runs=dataclasses.replace(base.runs, cancel_grace_s=1),
                                       plugins=dataclasses.replace(base.plugins, drain_timeout_s=0))
        self.state = BackendState(settings=settings, conn=self.conn, env=self.env, sessions=Sessions(),
                                  state_folder=self.tmp / "skm" / "state" / "gui",
                                  collect=lambda: sources.collect(None, self.env))
        self.events = []
        self.state.plugins._publish = lambda t, d, s: self.events.append((t, d, s))

    async def asyncTearDown(self):
        await self.state.broker.shutdown(timeout=10)

    def prepare(self):
        pass

    async def run_command(self, command_id, *, trusted=True, **kw):
        """What ``start_run`` does for an argv command: admit, submit with the ticket, wait for the end."""
        owner, command = self.state.catalog.commands[command_id]
        ticket = self.state.plugins.admit(owner, "command", command["effects"], None)
        try:
            run = await self.state.broker.submit(
                owner=owner, owner_root=self.state.catalog.owners[owner].source.root, trusted=trusted, command=command,
                context={}, project_root=None, values={}, dry_run=False, confirmed=False, correlation_id="c" * 32,
                actor=ACTOR, ticket=ticket, **kw)
        except BaseException:
            ticket.finish(cancelled=True)
            raise
        return run

    async def done(self, run, timeout=20):
        active = self.state.broker.active.get(run["run_id"])
        if active is not None:
            await asyncio.wait_for(active.done.wait(), timeout)
        doc = self.state.store.get(run["run_id"])
        self.assertEqual([], contracts.validate(doc, "run"))
        return doc

    def view(self, plugin):
        document = self.state.plugins.view(plugin)
        self.assertEqual([], contracts.validate(document, "trust"), document)
        return document


class TestWiring(StateCase):
    async def test_state_has_a_synced_host_and_the_feature(self):
        self.assertIn("plugins", FEATURES)
        self.assertEqual(list(FEATURES), self.state.bootstrap()["features"])
        self.assertEqual("enabled", self.view("xdemo")["state"])
        self.assertEqual(["xdemo"], [v["id"] for v in self.state.plugins.views()])
        self.assertEqual({"xdemo"}, set(self.state.catalog.sources))

    async def test_refresh_catalog_syncs_the_host(self):
        self.state.collect = lambda: sources.Collected(sources=[], problems=[])
        self.state.refresh_catalog()
        self.assertEqual("discovered", self.view("xdemo")["state"])
        self.assertFalse(self.state.plugins.visible("xdemo"))
        self.state.collect = lambda: sources.collect(None, self.env)
        self.state.refresh_catalog()
        self.assertEqual("enabled", self.view("xdemo")["state"])

    async def test_visible_catalog_without_hidden_plugins_is_the_resolved_document(self):
        self.assertIs(self.state.catalog.document, self.state.visible_catalog())

    async def test_disabled_plugin_leaves_the_catalog_and_the_digest_follows(self):
        before = self.state.visible_catalog()
        self.assertEqual(["xdemo"], [entry["owner"] for entry in before["contributions"]])
        await self.state.plugins.disable("xdemo")
        after = self.state.visible_catalog()
        self.assertEqual([], after["contributions"])
        self.assertEqual(digest_json({"host": after["host"], "contributions": []}), after["digest"])
        self.assertNotEqual(before["digest"], after["digest"])
        self.assertEqual([], contracts.validate(after, "catalog"))
        self.assertEqual(self.state.catalog.document["rejected"], after["rejected"])
        self.assertEqual(1, len(self.state.catalog.document["contributions"]))  # the resolver view is untouched
        await self.state.plugins.enable("xdemo")
        self.assertEqual(before["digest"], self.state.visible_catalog()["digest"])

    async def test_hidden_plugin_filter_matches_the_resolver_algorithm(self):
        document = self.state.catalog.document
        entries = document["contributions"]
        again = resolve.resolve(sources.collect(None, self.env))
        self.assertEqual(again["digest"], digest_json({"host": document["host"], "contributions": [
            {"owner": e["owner"], "source": e["source"], "digest": e["digest"]} for e in entries]}))


class TestHubUnitRuns(StateCase):
    async def test_permission_has_grants_and_enforcement_from_the_host(self):
        run = await self.run_command("xdemo.ticks")
        self.assertEqual([], run["permission"]["grants"])
        self.assertEqual([{"effect": "process.spawn", "enforcement": "declared"}], run["permission"]["effects"])
        self.assertEqual(1, self.state.plugins._inflight["xdemo"])
        await self.state.broker.cancel(run["run_id"], system=True)
        self.assertEqual("cancelled", (await self.done(run))["state"])
        self.assertEqual(0, self.state.plugins.busy("xdemo"))
        self.assertEqual(0, self.view("xdemo")["failures"]["count"])

    async def test_a_non_zero_exit_is_the_programs_answer_not_a_plugin_failure(self):
        for _ in range(4):
            done = await self.done(await self.run_command("xdemo.fail"))
            self.assertEqual("failed", done["state"])
        view = self.view("xdemo")
        self.assertEqual((0, "healthy"), (view["failures"]["count"], view["state"]))

    async def test_timeout_and_cancel_do_not_judge_the_plugin(self):
        self.assertEqual("timed_out", (await self.done(await self.run_command("xdemo.quiet")))["state"])
        self.assertEqual(0, self.view("xdemo")["failures"]["count"])
        self.assertEqual(0, self.state.plugins.busy("xdemo"))

    async def test_denied_run_releases_the_ticket(self):
        run = await self.run_command("xdemo.fail", trusted=False)
        self.assertEqual("denied", run["state"])
        self.assertEqual(0, self.state.plugins.busy("xdemo"))

    async def test_disabled_plugin_refuses_before_a_run_exists(self):
        await self.state.plugins.disable("xdemo")
        with self.assertRaises(PluginError) as caught:
            await self.run_command("xdemo.fail")
        self.assertEqual("PLUGIN_DISABLED", caught.exception.code)
        self.assertEqual([], self.state.store.list(project_id=None, state=None, limit=10, before=None))

    async def test_refused_submit_gives_the_ticket_back(self):
        limits = dataclasses.replace(self.state.settings.runs, max_per_owner=1)
        self.state.settings = dataclasses.replace(self.state.settings, runs=limits)
        first = await self.run_command("xdemo.ticks")
        with self.assertRaises(Exception) as caught:
            await self.run_command("xdemo.quiet")
        self.assertEqual("CONCURRENCY_LIMIT", caught.exception.code)
        self.assertEqual(1, self.state.plugins._inflight["xdemo"])  # only the first run
        await self.state.broker.cancel(first["run_id"], system=True)
        await self.done(first)


class ExtensionCase(StateCase):
    units = "empty"

    def prepare(self):
        self.root = support.make_extension(self.tmp / "ext")
        support.register(self.tmp / "skm", self.root)

    def registration(self):
        found, _ = registered_plugins(ext_settings.load(None, env=self.env), env=self.env)
        return next(entry for entry in found if entry.id == support.EXT_ID)

    def call(self, query="xext.status", point="gui:query", effects=("read",), kind="query"):
        """What the routes do around ``ticket.invoke``: admit, call, classify, finish."""
        ticket = self.state.plugins.admit(support.EXT_ID, kind, effects, None)
        payload = {"id": query, "context": {}, "params": {}} if point == "gui:query" else \
            {"id": query, "context": {}, "input": {}}
        result = ticket.invoke(self.registration(), point, payload, env=self.env, project=None)
        ticket.finish(None if result.status == "ok" else (result.code or result.status))
        return result


class TestExtension(ExtensionCase):
    async def test_extension_waits_for_an_explicit_enable_and_a_green_check(self):
        view = self.view("xext")
        self.assertEqual(("extension", "compatible", False), (view["source"], view["state"], view["ui_enabled"]))
        self.assertEqual(["xext"], [e["owner"] for e in self.state.catalog.document["contributions"]])
        self.assertEqual([], self.state.visible_catalog()["contributions"])
        with self.assertRaises(PluginError) as caught:
            self.call()
        self.assertEqual("PLUGIN_DISABLED", caught.exception.code)
        await self.state.plugins.enable("xext")
        self.assertEqual(["xext"], [e["owner"] for e in self.state.visible_catalog()["contributions"]])
        self.assertEqual("ok", self.call().status)
        self.assertEqual("healthy", self.view("xext")["state"])

    async def test_grant_gate_for_an_extension_command(self):
        await self.state.plugins.enable("xext")
        with self.assertRaises(PluginError) as caught:
            self.call("xext.net", "gui:command", ("network",), "command")
        self.assertEqual(("PERMISSION_DENIED", {"plugin": "xext", "effect": "network", "project_id": None}),
                         (caught.exception.code, caught.exception.details))
        grant = self.state.plugins.grant("xext", "network")
        self.assertEqual("ok", self.call("xext.net", "gui:command", ("network",), "command").status)
        self.state.plugins.revoke("xext", grant["id"])
        with self.assertRaises(PluginError):
            self.call("xext.net", "gui:command", ("network",), "command")

    async def test_domain_error_is_not_a_failure(self):
        await self.state.plugins.enable("xext")
        support.set_mode(self.root, "domain")
        for _ in range(5):
            result = self.call()
            self.assertEqual(("error", "XEXT_DOMAIN"), (result.status, result.code))
        view = self.view("xext")
        self.assertEqual((0, "healthy"), (view["failures"]["count"], view["state"]))

    async def test_garbage_answers_quarantine_the_plugin_and_release_heals(self):
        await self.state.plugins.enable("xext")
        support.set_mode(self.root, "garbage")
        codes = []
        for _ in range(3):
            codes.append(self.call().code)
        self.assertTrue(set(codes) <= plugins.FAILURE_CODES, codes)
        view = self.view("xext")
        self.assertEqual(("quarantined", 3, False), (view["state"], view["failures"]["count"], view["ui_enabled"]))
        self.assertEqual([], self.state.visible_catalog()["contributions"])
        with self.assertRaises(PluginError) as caught:
            self.call()
        self.assertEqual("PLUGIN_QUARANTINED", caught.exception.code)
        support.set_mode(self.root, "ok")
        self.state.plugins.release("xext")
        self.assertEqual("ok", self.call().status)
        self.assertEqual("healthy", self.view("xext")["state"])
        states = [d["to"] for t, d, s in self.events if t == "gui.plugin.state"]
        self.assertIn("quarantined", states)

    async def test_changed_manifest_with_a_new_effect_voids_the_grant(self):
        await self.state.plugins.enable("xext")
        self.state.plugins.grant("xext", "network")
        support.make_extension(self.tmp / "ext", extra_effects=("project.write",))
        self.state.refresh_catalog()
        view = self.view("xext")
        self.assertEqual(("permission_denied", []), (view["state"], view["grants"]))
        with self.assertRaises(PluginError) as caught:
            self.call("xext.net", "gui:command", ("network",), "command")
        self.assertEqual("PERMISSION_DENIED", caught.exception.code)

    async def test_argv_run_records_the_used_grants_and_advisory_enforcement(self):
        await self.state.plugins.enable("xext")
        with self.assertRaises(PluginError) as caught:
            await self.run_command("xext.sleep")
        self.assertEqual("PERMISSION_DENIED", caught.exception.code)
        self.assertEqual(0, self.state.plugins.busy("xext"))
        grant = self.state.plugins.grant("xext", "process.spawn")
        run = await self.run_command("xext.sleep")
        self.assertEqual([grant["id"]], run["permission"]["grants"])
        self.assertEqual([{"effect": "process.spawn", "enforcement": "advisory"}], run["permission"]["effects"])
        self.assertNotIn("enforced", repr(self.state.plugins.views()))
        self.assertEqual(1, len(self.state.plugins.active_runs("xext")))
        # a revoke does not stop the running process
        self.state.plugins.revoke("xext", grant["id"])
        self.assertEqual("running", self.state.store.get(run["run_id"])["state"])
        # Disable drains: the run does not end in 0 s, so it is cancelled
        outcome = await self.state.plugins.disable("xext")
        self.assertEqual({"drained": 0, "cancelled": 1}, outcome)
        self.assertEqual("cancelled", (await self.done(run))["state"])
        self.assertEqual((0, "disabled"), (self.state.plugins.busy("xext"), self.view("xext")["state"]))
        self.assertEqual([], self.state.visible_catalog()["contributions"])

    async def test_spawn_failures_of_an_argv_command_quarantine(self):
        await self.state.plugins.enable("xext")
        self.state.plugins.grant("xext", "process.spawn")
        (self.root / "bin" / "sleeper").write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
        for _ in range(3):
            run = await self.run_command("xext.sleep")
            self.assertEqual("failed_to_start", (await self.done(run))["state"])
        self.assertEqual("quarantined", self.view("xext")["state"])
        self.assertEqual("PROCESS_SPAWN", self.view("xext")["failures"]["last_code"])

    async def test_enable_fails_the_gate_for_a_broken_handler(self):
        (self.root / "handler.py").write_text("import sys\nsys.stdout.write('nope')\n", encoding="utf-8")
        with self.assertRaises(PluginError) as caught:
            await self.state.plugins.enable("xext")
        self.assertEqual("PLUGIN_CONFORMANCE_FAILED", caught.exception.code)
        self.assertTrue(caught.exception.details["findings"])
        self.assertEqual("compatible", self.view("xext")["state"])

    async def test_aicore_trust_is_still_a_precondition(self):
        support.register(self.tmp / "skm", self.root, trusted=False)
        await self.state.plugins.enable("xext")  # the GUI layer does not touch the aicore configuration
        self.assertEqual("enabled", self.view("xext")["state"])


class TestErrorsAreRegistered(unittest.TestCase):
    def test_new_codes_build_envelopes_now(self):
        for code, status in (("PLUGIN_DISABLED", 503), ("PLUGIN_CONFORMANCE_FAILED", 422)):
            document = PluginError(code, "text", details={"findings": "a: b", "count": 1}).envelope("corr-0001")
            self.assertEqual([], contracts.validate(document, "api-error"))
            from gui.errors import http_status
            self.assertEqual(status, http_status(code))


if __name__ == "__main__":
    unittest.main()
