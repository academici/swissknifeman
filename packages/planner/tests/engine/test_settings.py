"""``[planner]`` configuration: defaults, layer order, refusals, new plan and item defaults, view templates, policies."""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_AICORE_LIB = Path(__file__).resolve().parents[3] / "aicore" / "lib"
if (_AICORE_LIB / "aicore" / "__init__.py").is_file() and str(_AICORE_LIB) not in sys.path:
    sys.path.insert(1, str(_AICORE_LIB))

from planner import integration  # noqa: E402
from planner.integration import config as integration_config  # noqa: E402
from planner.plan import budget, check, cli, context, lifecycle, ops, refs, settings, store  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

try:
    from . import test_lifecycle, test_refs
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle
    import test_refs

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "configs" / "config.schema.json").read_text())
needs_aicore = unittest.skipUnless(integration.available(), "needs the aicore foundation")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def without_aicore():
    """Pretend the foundation is absent for the duration of a test."""
    return mock.patch.dict(integration._PROBE, {"available": False, "root": None, "reason": "AICORE_NOT_FOUND"},
                           clear=True)


class ConfigCase(test_lifecycle.LifeCase):
    """Plan LIFE inside a temporary project, with a temporary machine home and no ``SKM_PLANNER_*`` variables."""

    def setUp(self):
        super().setUp()
        self.project = self.plans.parent
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.home, ignore_errors=True))
        env = {k: v for k, v in os.environ.items() if not k.startswith("SKM_")}
        env.update(HOME=str(self.home), SKM_HOME=str(self.home))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings.set_invocation(None)
        self.addCleanup(settings.set_invocation, None)

    def machine_file(self) -> Path:
        from aicore.state import machine_config_file
        return Path(machine_config_file())

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def project_file(self, text: str) -> Path:
        return self.write(self.project / ".swissknifeman" / "config.toml", text)


class DefaultsTests(ConfigCase):
    def leaves(self, node=None, prefix=()):
        node = node or SCHEMA
        for name, child in node["properties"].items():
            if child.get("type") == "object":
                yield from self.leaves(child, prefix + (name,))
            else:
                yield ".".join(prefix + (name,)), child

    def test_schema_leaves_all_carry_a_default_inside_their_bounds(self):
        for key, leaf in self.leaves():
            self.assertIn("default", leaf, key)
            self.assertTrue(leaf["description"], key)
            if "minimum" in leaf:
                self.assertGreaterEqual(leaf["default"], leaf["minimum"], key)
                self.assertLessEqual(leaf["default"], leaf["maximum"], key)
            if "enum" in leaf:
                self.assertIn(leaf["default"], leaf["enum"], key)

    def test_the_defaults_equal_the_constants_they_replaced(self):
        config = settings.for_plan(self.load())
        self.assertEqual(config.get("context.budget_kb"), 256)
        self.assertEqual(config.get("context.top_sources"), 5)
        self.assertEqual(config.get("check.heavy_text_kb"), 16)
        self.assertEqual(config.get("refs.max_chain"), 8)
        self.assertEqual(config.get("lock.timeout_seconds"), 30)
        self.assertEqual((config.get("policy.review_rounds_max"), config.get("policy.corrections_max")), (2, 1))
        self.assertEqual((config.get("new_item.route_class"), config.get("new_item.route_effort"),
                          config.get("new_item.review_mode")), ("implementation", "high", "none"))

    def test_without_aicore_the_values_are_the_schema_defaults(self):
        with without_aicore():
            settings._CACHE.clear()
            config = settings.for_plan(self.load())
            self.assertIsNone(config.resolved)
            self.assertEqual(dict(config.values), dict(self.leaves_defaults()))
            self.assertEqual(set(config.sources.values()), {"defaults"})
            self.assertEqual(config.aicore["aicore"], "unavailable")
        settings._CACHE.clear()

    def leaves_defaults(self):
        return ((key, leaf["default"]) for key, leaf in self.leaves())

    def test_without_aicore_the_plan_settings_layer_still_applies(self):
        ops.patch(self.load(), "plan", {"settings": {"context_budget_kb": 64}})
        with without_aicore():
            settings._CACHE.clear()
            config = settings.for_plan(self.load())
            self.assertEqual(config.get("context.budget_kb"), 64)
            self.assertEqual(config.explain("context.budget_kb"),
                             [{"key": "context.budget_kb", "value": 64, "layer": "plan.settings"}])
        settings._CACHE.clear()

    def test_without_aicore_a_config_file_needs_the_foundation(self):
        with without_aicore():
            with self.assertRaises(PlanError) as caught:
                integration_config.resolve(project_root=None, config_file=self.home / "x.toml")
            self.assertEqual(caught.exception.code, "AICORE_REQUIRED")
            code, _, err = run("--config", self.home / "x.toml", "config", "show")
            self.assertEqual(code, 1)
            self.assertIn("AICORE_REQUIRED", err)


@needs_aicore
class LayerTests(ConfigCase):
    def winner(self, key="context.budget_kb"):
        entry = settings.for_plan(self.load()).explain(key)[0]
        return entry["value"], entry["layer"], entry["file"]

    def test_order_is_machine_project_plan_settings_environment_invocation(self):
        self.assertEqual(self.winner(), (256, "defaults", None))
        machine = self.write(self.machine_file(), "[planner.context]\nbudget_kb = 100\n")
        self.assertEqual(self.winner(), (100, "machine", str(machine)))
        project = self.project_file("[planner.context]\nbudget_kb = 200\n")
        self.assertEqual(self.winner(), (200, "project", str(project)))
        ops.patch(self.load(), "plan", {"settings": {"context_budget_kb": 300}})
        self.assertEqual(self.winner(), (300, "plan.settings", None))
        with mock.patch.dict(os.environ, {"SKM_PLANNER_CONTEXT__BUDGET_KB": "400"}):
            self.assertEqual(self.winner(), (400, "env", None))
            invocation = self.write(self.home / "run.toml", "[planner.context]\nbudget_kb = 500\n")
            settings.set_invocation(invocation)
            self.assertEqual(self.winner(), (500, "invocation", str(invocation)))
        entry = settings.for_plan(self.load()).explain("context.budget_kb")[0]
        self.assertEqual([o["layer"] for o in entry["overridden"]], ["plan.settings", "project", "machine", "defaults"])

    def test_a_plan_setting_is_a_layer_of_its_own_and_the_budget_follows_it(self):
        ops.patch(self.load(), "plan", {"settings": {"context_budget_kb": 8}})
        self.assertEqual(context.budget_bytes(self.load()), 8 * 1024)
        layers = {layer["name"]: layer for layer in settings.for_plan(self.load()).layers}
        self.assertTrue(layers["plan.settings"]["present"])

    def test_a_large_plan_budget_is_lowered_to_the_bound_instead_of_refusing(self):
        ops.patch(self.load(), "plan", {"settings": {"context_budget_kb": 8192}})
        self.assertEqual(settings.for_plan(self.load()).get("context.budget_kb"), 4096)
        self.assertEqual(context.budget_bytes(self.load()), 4096 * 1024)

    def test_the_template_folder_cannot_come_from_the_machine_file(self):
        self.write(self.machine_file(), '[planner.views]\ntemplates_dir = "/tmp"\n')
        with self.assertRaises(PlanError) as caught:
            settings.for_plan(self.load())
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_a_value_outside_its_bounds_refuses_with_file_and_line(self):
        path = self.project_file("[planner.policy]\nreview_rounds_max = 0\n")
        with self.assertRaises(PlanError) as caught:
            settings.for_plan(self.load())
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        self.assertIn(str(path), caught.exception.message)
        self.assertIn("policy.review_rounds_max", caught.exception.message)
        code, _, err = run("check", self.root)
        self.assertEqual(code, 1)
        self.assertIn("CONFIG_INVALID", err)

    def test_an_unknown_key_in_a_layer_refuses(self):
        self.project_file("[planner.policy]\nsurprise = 1\n")
        with self.assertRaises(PlanError) as caught:
            settings.for_plan(self.load())
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_the_template_folder_cannot_come_from_the_environment(self):
        with mock.patch.dict(os.environ, {"SKM_PLANNER_VIEWS__TEMPLATES_DIR": "/tmp"}):
            with self.assertRaises(PlanError) as caught:
                settings.for_plan(self.load())
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_the_cache_follows_a_changed_file(self):
        self.project_file("[planner.context]\nbudget_kb = 10\n")
        self.assertEqual(self.winner()[0], 10)
        self.project_file("[planner.context]\nbudget_kb = 20\n")
        self.assertEqual(self.winner()[0], 20)


@needs_aicore
class CliTests(ConfigCase):
    def test_show_lists_every_key_with_its_layer_and_the_aicore_status(self):
        self.project_file("[planner.context]\nbudget_kb = 12\n")
        code, out, _ = run("config", "show", "--plans-root", self.plans)
        self.assertEqual(code, 0)
        self.assertIn("context.budget_kb = 12  (project)", out)
        self.assertIn("policy.corrections_max = 1  (defaults)", out)
        self.assertRegex(out, r"aicore: available \S+")
        self.assertEqual(run("config", "--plans-root", self.plans)[1], out)

    def test_show_json_has_aicore_layers_and_values(self):
        code, out, _ = run("config", "show", "--json", "--plans-root", self.plans)
        document = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(document["aicore"]["aicore"], "available")
        self.assertEqual(document["values"]["context.budget_kb"], 256)
        self.assertEqual([layer["name"] for layer in document["layers"]][:3], ["defaults", "machine", "project"])

    def test_explain_json_is_the_aicore_contract(self):
        from aicore.util import schema
        registry, kind = schema.load_contract(Path(__file__).resolve().parents[3] / "aicore" / "schemas"
                                              / "config-explain" / "v1")
        code, out, _ = run("config", "explain", "context.budget_kb", "--json", "--plans-root", self.plans)
        document = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(schema.validate(document, kind, registry), [])
        self.assertEqual([e["key"] for e in document["entries"]], ["context.budget_kb"])

    def test_explain_of_a_table_and_an_unknown_key(self):
        code, out, _ = run("config", "explain", "policy", "--plans-root", self.plans)
        self.assertEqual(code, 0)
        self.assertIn("policy.review_rounds_max = 2", out)
        code, _, err = run("config", "explain", "nope", "--plans-root", self.plans)
        self.assertEqual(code, 1)
        self.assertIn("CONFIG_INVALID", err)

    def test_plan_adds_its_settings_layer(self):
        ops.patch(self.load(), "plan", {"settings": {"context_budget_kb": 33}})
        code, out, _ = run("config", "show", "--plan", self.root)
        self.assertEqual(code, 0)
        self.assertIn("context.budget_kb = 33  (plan.settings)", out)

    def test_global_config_is_the_invocation_layer(self):
        path = self.write(self.home / "run.toml", "[planner.context]\ntop_sources = 2\n")
        code, out, _ = run("--config", path, "config", "show", "--plans-root", self.plans)
        self.assertEqual(code, 0)
        self.assertIn("context.top_sources = 2  (invocation)", out)
        code, out, _ = run("--output", "json", "--config", path, "config", "show", "--json", "--plans-root", self.plans)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["values"]["context.top_sources"], 2)

    def test_a_missing_config_file_refuses(self):
        code, _, err = run("--config", self.home / "absent.toml", "config", "show", "--plans-root", self.plans)
        self.assertEqual(code, 1)
        self.assertIn("CONFIG_INVALID", err)

    def test_show_takes_no_key(self):
        self.assertEqual(run("config", "show", "context", "--plans-root", self.plans)[0], 2)


@needs_aicore
class ConsumerTests(ConfigCase):
    def test_new_plan_takes_its_settings_from_the_project_configuration(self):
        self.project_file('[planner.new_plan]\nscout = "auto"\ncontext_pack = "legacy"\nevidence = "required"\n'
                          'language = "ru"\ncommit_scope = "demo"\ndesign_audit = "required"\n')
        plan = ops.new_plan("CONF", "Conf", plans_root=self.plans, repository="r", owner="o",
                            authoring=test_lifecycle.OPUS, message="m", date="2026.10.08")
        self.assertEqual(plan.plan["settings"], {
            "design_audit": "required", "scout": "auto", "context_pack": "legacy", "evidence": "required",
            "language": "ru", "commit": {"scope": "demo"}})
        self.assertEqual([i for i in check.check(store.load_plan(plan.root)) if i.level == "error"], [])

    def test_new_plan_writes_the_old_settings_without_configuration(self):
        plan = ops.new_plan("CONF", "Conf", plans_root=self.plans, repository="r", owner="o",
                            authoring=test_lifecycle.OPUS, message="m", date="2026.10.08")
        self.assertEqual(plan.plan["settings"], {"design_audit": "none", "scout": "off", "context_pack": "scoped"})

    def test_add_item_takes_route_and_review_from_configuration_but_data_wins(self):
        self.project_file('[planner.new_item]\nroute_class = "economy"\nroute_effort = "low"\n'
                          'review_mode = "requested"\n')
        item = ops.add_item(self.load(), "P1", "Third")
        doc = self.load().items[item]
        self.assertEqual((doc["route"], doc["review"]), ({"class": "economy", "effort": "low"}, {"mode": "requested"}))
        other = ops.add_item(self.load(), "P1", "Fourth", data={"route": {"class": "frontier", "effort": "max"}})
        self.assertEqual(self.load().items[other]["route"], {"class": "frontier", "effort": "max"})

    def test_budget_report_lists_the_configured_number_of_sources(self):
        for name in ("one", "two"):
            ops.add_document(self.root, {"id": name, "title": name, "global": True,
                                         "sections": [{"id": "s", "title": "S", "text": name * 800}]})
        self.project_file("[planner.context]\ntop_sources = 1\nbudget_kb = 1\n")
        report = budget.measure(self.load(), "P1.1")
        self.assertEqual((report["top_sources"], report["budget_bytes"], report["over_budget"]), (1, 1024, True))
        text = budget.text(report)
        self.assertIn("budget 1 KB; OVER", text)
        self.assertEqual(text.split("  top: ")[1].count(" KB"), 1)  # one listed source

    def test_check_warns_about_text_above_the_configured_size(self):
        self.project_file("[planner.check]\nheavy_text_kb = 1\n")
        ops.patch(self.load(), "brief", {"requirements": [], "messages": [
            {"id": "M1", "date": "2026-10-07", "text": "x" * 2048}]})
        codes = [issue.code for issue in check.check(self.load())]
        self.assertIn("context_heavy", codes)
        os.remove(self.project / ".swissknifeman" / "config.toml")
        self.assertNotIn("context_heavy", [issue.code for issue in check.check(self.load())])

    def test_lock_wait_follows_the_configuration(self):
        self.project_file("[planner.lock]\ntimeout_seconds = 1\n")
        with store.PlanLock(self.root):
            started = time.monotonic()
            with self.assertRaises(PlanError) as caught:
                ops.add_item(self.load(), "P1", "Blocked")
            self.assertEqual(caught.exception.code, "PLAN_LOCKED")
            self.assertLess(time.monotonic() - started, 10)

    def test_the_pack_carries_the_loop_policies(self):
        self.assertEqual(context.collect(self.load(), "P1.1")["policy"],
                         {"review_rounds_max": 2, "corrections_max": 1})
        self.project_file("[planner.policy]\nreview_rounds_max = 3\ncorrections_max = 2\n")
        self.assertEqual(context.collect(self.load(), "P1.1")["policy"],
                         {"review_rounds_max": 3, "corrections_max": 2})

    def test_the_supersede_chain_limit_comes_from_configuration(self):
        other = test_refs.new_plan(self.plans, "OTHER", "r")
        keys = [test_refs.accepted(other, f"v{n}") for n in range(1, 5)]
        for old, new in zip(keys, keys[1:]):
            lifecycle.supersede(other, old, new, test_lifecycle.OPUS)
        short = store.load_plan(other).plan["short_id"]
        self.assertTrue(refs.resolve(self.load(), f"{short}.D1")["loaded"])
        self.project_file("[planner.refs]\nmax_chain = 3\n")
        entry = refs.resolve(self.load(), f"{short}.D1")
        self.assertEqual((entry["loaded"], entry["reason"].split(":")[0]), (False, "CYCLE"))


@needs_aicore
class WorkspaceProjectTests(ConfigCase):
    """Plans in the portable workspace take the project configuration of the checkout bound to them."""

    PID = "billium"

    def setUp(self):
        super().setUp()
        self.project = Path(os.path.realpath(self.project))
        self.ws = self.home / "wss" / "axioma"
        patcher = mock.patch.dict(os.environ, {"SKM_WORKSPACES_ROOT": str(self.ws.parent)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ws_plans = self.ws / "projects" / self.PID / "plans"
        self.ws_plans.mkdir(parents=True)

    def bind(self):
        marker = self.project / ".swissknifeman" / "project.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1",
                                      "workspace": "axioma", "project_id": self.PID, "plans_store": "workspace"}), encoding="utf-8")
        bindings = self.home / "state" / "workspaces" / "axioma" / "bindings.json"
        bindings.parent.mkdir(parents=True, exist_ok=True)
        bindings.write_text(json.dumps({
            "$schema": "urn:swissknifeman:aicore:workspace-bindings:v1",
            "projects": {self.PID: {"paths": [str(self.project)], "primary": str(self.project),
                                    "bound_at": "2026-10-17T09:30:00Z"}}}), encoding="utf-8")

    def new(self):
        return ops.new_plan("WSP", "Wsp", plans_root=self.ws_plans, repository=ops.default_repository(self.ws_plans),
                            owner="o", authoring=test_lifecycle.OPUS, message="m", date="2026.10.08")

    def test_the_project_root_of_the_workspace_plans_is_the_bound_checkout(self):
        self.assertIsNone(settings.project_root_of(self.ws_plans))
        self.bind()
        self.assertEqual(settings.project_root_of(self.ws_plans), self.project)
        self.assertEqual(settings.project_root_of(self.plans), self.project)  # a legacy folder: as before

    def local_file(self, text: str) -> Path:
        """The project layer of a project bound to the workspace: ``local/config.toml`` of the workspace project."""
        return self.write(self.ws / "projects" / self.PID / "local" / "config.toml", text)

    def test_new_plan_takes_the_configuration_and_the_name_of_the_bound_checkout(self):
        self.local_file('[planner.new_plan]\nscout = "auto"\n')
        before = self.new()
        self.assertEqual((before.plan["settings"]["scout"], before.plan["repository"]), ("off", self.PID))
        self.bind()
        after = self.new()
        self.assertEqual((after.plan["settings"]["scout"], after.plan["repository"]), ("auto", self.project.name))
        self.assertEqual(settings.for_plan(store.load_plan(after.root)).get("new_plan.scout"), "auto")

    def test_the_project_layer_of_a_marked_project_is_the_local_folder_not_the_checkout(self):
        self.project_file('[planner.new_plan]\nscout = "auto"\n')
        self.bind()
        self.assertEqual(self.new().plan["settings"]["scout"], "off")
        self.local_file('[planner.new_plan]\nscout = "auto"\n')
        self.assertEqual(self.new().plan["settings"]["scout"], "auto")
        entry = settings.for_root(self.ws_plans).explain("new_plan.scout")[0]
        self.assertEqual(entry["layer"], "project")
        self.assertEqual(Path(entry["file"]), self.ws / "projects" / self.PID / "local" / "config.toml")


@needs_aicore
class TemplateTests(ConfigCase):
    def folder(self, name="own"):
        path = self.project / ".swissknifeman" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_a_template_of_the_same_name_replaces_the_built_in_one(self):
        folder = self.folder()
        (folder / "open-questions.md").write_text("custom {{short_id}}\n", encoding="utf-8")
        self.project_file('[planner.views]\ntemplates_dir = "own"\n')  # relative to the folder of the file
        ops.patch(self.load(), "plan", {"goal": "changed"})
        plan = self.load()
        self.assertEqual((plan.root / "views" / "open-questions.md").read_text(), f"custom {plan.plan['short_id']}\n")
        self.assertTrue((plan.root / "views" / "status.md").read_text().startswith("<!-- generated"))

    def test_an_unknown_template_name_warns_once(self):
        folder = self.folder("odd")
        (folder / "surprise.md").write_text("x\n", encoding="utf-8")
        self.project_file(f'[planner.views]\ntemplates_dir = "{folder}"\n')
        from planner.plan import views
        views._WARNED.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            views.render_all(self.load(), check=True)
            views.render_all(self.load(), check=True)
        self.assertEqual(err.getvalue().count("VIEW_TEMPLATE_UNKNOWN"), 1)

    def test_a_missing_folder_warns_and_keeps_the_built_in_templates(self):
        self.project_file(f'[planner.views]\ntemplates_dir = "{self.home / "nowhere"}"\n')
        from planner.plan import views
        views._WARNED.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            changed = views.render_all(self.load(), check=True)
        self.assertEqual(changed, [])
        self.assertIn("VIEW_TEMPLATES_MISSING", err.getvalue())


if __name__ == "__main__":
    unittest.main()
