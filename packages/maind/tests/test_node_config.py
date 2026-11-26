"""Node config: settings in [maind], fleet registry in the state, the legacy node file until upgrade.

Covers the new places (machine config + registry.json), the legacy path on a copy of the real
file form (settings as an extra layer, registry read and written in the legacy file), the
single-writer rule (registry.json wins; the legacy file is then never changed), [maind] winning over
legacy settings, [maind.graph.links] next to the legacy graph file, the carriers of the project
provider selection, and backups under .swissknifeman/backups."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.config import ConfigError
from aicore.state import list_backups, machine_config_file

from maind import config as config_mod
from maind import derive, provider_deploy
from maind.config import (Config, load_config, merge_defaults, registry_of, settings_schema,
                          split_node_document, toml_project_providers)
from maind.graph import Graph
from maind.projects import write_registry
from tests.fixtures import make_repo

LEGACY_FORM = Path(__file__).resolve().parent / "data" / "legacy-node-config.json"


def machine_toml(env, text):
    path = machine_config_file(home=env.home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("schema_version = 1\n" + text, encoding="utf-8")
    return path


def stderr_of(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue()


class NodeConfigCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root, self.env = make_repo(self.tmp)
        # no project layer from the working directory of the test run
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.env.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        config_mod._warned_legacy.clear()
        derive._warned_graph_links.clear()
        provider_deploy._warned_legacy_providers.clear()

    def legacy_copy(self):
        path = self.root / "config.json"
        shutil.copyfile(LEGACY_FORM, path)
        return path


class TestSchemaAndExample(unittest.TestCase):
    def test_schema_defaults_equal_the_code_defaults(self):
        merged = merge_defaults({})
        schema = settings_schema()
        for key, leaf in schema.leaves.items():
            if not leaf.has_default or key[0] in ("graph",) and key[1:] == ("links",):
                continue
            node = merged
            for part in key[:-1]:
                node = node[part]
            self.assertEqual(node[key[-1]], leaf.default, ".".join(key))

    def test_registry_example_is_a_valid_registry(self):
        path = Path(__file__).resolve().parents[1] / "configs" / "registry.example.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 1)
        settings, registry = split_node_document({k: v for k, v in doc.items()
                                                  if k != "schema_version"})
        self.assertEqual(settings, {"agents": {}, "mcp": {}} if "agents" in doc else {})
        self.assertEqual(set(registry), {"agents", "mcp", "namespaces", "projects"})

    def test_registry_example_read_as_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            env.registry_file.parent.mkdir(parents=True)
            shutil.copyfile(Path(__file__).resolve().parents[1] / "configs" / "registry.example.json",
                            env.registry_file)
            with contextlib.redirect_stderr(io.StringIO()):
                cfg, source = load_config(env)
            self.assertEqual(source, "config")
            self.assertEqual([p["id"] for p in cfg["projects"]], ["brain", "swissknifeman", "maind"])
            self.assertEqual(cfg["agents"]["definitions"][0]["id"], "vault-architect")


class TestNewPlaces(NodeConfigCase):
    def test_settings_from_machine_config_registry_from_state(self):
        machine_toml(self.env, "[maind.memory]\nhttp_port = 5555\n[maind.node]\nid = \"n1\"\n")
        write_registry(self.env, Config({"projects": [{"id": "alpha", "name": "Alpha"}]}))
        cfg, err = stderr_of(Config.load, self.env)
        self.assertEqual(err, "")
        self.assertEqual(cfg.source, "config")
        self.assertEqual(cfg.path, self.env.registry_file)
        self.assertEqual(cfg["memory"]["http_port"], 5555)
        self.assertEqual(cfg["memory"]["stream_port"], 4112)     # default of the schema
        self.assertEqual(cfg["node"], {"id": "n1"})
        self.assertEqual([p["id"] for p in cfg.projects], ["alpha"])
        self.assertEqual(cfg["graph"]["adapter"], "federation")

    def test_environment_layer_wins_over_the_machine_config(self):
        machine_toml(self.env, "[maind.memory]\nhttp_port = 5555\n")
        with mock.patch.dict(os.environ, {"SKM_MAIND_MEMORY__HTTP_PORT": "5556"}):
            cfg, _ = load_config(self.env)
        self.assertEqual(cfg["memory"]["http_port"], 5556)

    def test_old_shape_of_the_loaded_dictionary(self):
        cfg, _ = load_config(self.env)
        for key in ("node", "memory", "graph", "code_graph", "agents", "projects", "namespaces",
                    "integrations", "mcp", "observability"):
            self.assertIn(key, cfg)
        self.assertEqual(cfg["agents"]["definitions"], [])
        self.assertEqual(cfg["code_graph"]["language_by_type"]["node-package"], "typescript")
        self.assertEqual(cfg["code_graph"]["engine"], "serena")
        self.assertNotIn("perplexity_web", cfg["mcp"])           # only when the section is written

    def test_perplexity_web_defaults_fill_a_written_section(self):
        machine_toml(self.env, "[maind.mcp.perplexity_web]\nenabled = true\n")
        cfg, _ = load_config(self.env)
        self.assertEqual(cfg["mcp"]["perplexity_web"],
                         {"enabled": True, "pool": "default", "bin": "", "server_name": "perplexity-web"})

    def test_invalid_setting_stops_with_file_and_key(self):
        machine_toml(self.env, "[maind.memory]\nhttp_port = \"x\"\n")
        with self.assertRaises(SystemExit):
            stderr_of(load_config, self.env)

    def test_client_role_needs_a_remote_url_from_any_source(self):
        machine_toml(self.env, "[maind.memory]\nrole = \"client\"\n")
        with self.assertRaises(SystemExit):
            stderr_of(load_config, self.env)

    def test_new_registry_file_is_private_and_written_once(self):
        cfg = Config({"projects": [{"id": "alpha", "name": "Alpha"}], "namespaces": {"n": {}}})
        written = write_registry(self.env, cfg)
        self.assertEqual(written, self.env.registry_file)
        self.assertEqual(written.stat().st_mode & 0o777, 0o600)
        doc = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(set(doc), {"schema_version", "projects", "namespaces"})
        self.assertFalse(self.env.legacy_node_config.exists())
        self.assertEqual(list_backups(None, home=self.env.home), [])

    def test_replacing_the_registry_keeps_a_backup(self):
        write_registry(self.env, Config({"projects": [{"id": "alpha", "name": "Alpha"}]}))
        first = self.env.registry_file.read_bytes()
        write_registry(self.env, Config({"projects": [{"id": "beta", "name": "Beta"}]}))
        [(_stamp, files)] = list_backups(None, home=self.env.home)
        self.assertEqual([f.read_bytes() for f in files], [first])

    def test_settings_are_never_written_to_the_registry(self):
        machine_toml(self.env, "[maind.node]\nid = \"n1\"\n")
        cfg = Config.load(self.env)
        cfg["projects"] = [{"id": "alpha", "name": "Alpha"}]
        cfg.save(self.env)
        doc = json.loads(self.env.registry_file.read_text(encoding="utf-8"))
        self.assertNotIn("node", doc)
        self.assertNotIn("memory", doc)
        self.assertEqual(registry_of(cfg)["projects"], doc["projects"])

    def test_save_validates_the_registry(self):
        cfg, _ = load_config(self.env)
        cfg["projects"] = [{"id": "bad id", "name": "x"}]
        with self.assertRaises(SystemExit):
            stderr_of(Config(cfg).save, self.env)
        self.assertFalse(self.env.registry_file.exists())


class TestLegacyNodeFile(NodeConfigCase):
    """The legacy file is a copy of the form of the real node file (the shipped example form)."""

    def test_settings_and_registry_read_with_one_warning(self):
        path = self.legacy_copy()
        before = path.read_bytes()
        (cfg, source), err = stderr_of(load_config, self.env)
        self.assertEqual(source, "legacy:config.json")
        self.assertEqual(err.count("MAIND_LEGACY_CONFIG"), 1)
        self.assertIn("reading settings and registry from", err)
        self.assertIn(str(path), err)
        # the same dictionary the legacy loader produced (shadow comparison)
        raw = json.loads(before.decode("utf-8"))
        raw = {k: v for k, v in raw.items() if not k.startswith("_")}
        raw["code_graph"].pop("embed")                    # null: no embedder
        self.assertEqual(dict(cfg), merge_defaults(raw))
        self.assertEqual(path.read_bytes(), before)
        _, again = stderr_of(load_config, self.env)
        self.assertEqual(again, "")                        # one warning per process and file

    def test_save_writes_the_legacy_document_only(self):
        path = self.legacy_copy()
        raw = json.loads(path.read_text(encoding="utf-8"))
        before = path.read_bytes()
        cfg, _ = stderr_of(Config.load, self.env)
        cfg["projects"] = cfg["projects"] + [{"id": "newp", "name": "New"}]
        cfg["namespaces"] = dict(cfg["namespaces"], extra={"name": "Extra"})
        stderr_of(cfg.save, self.env)
        self.assertFalse(self.env.registry_file.exists())
        out = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual([p["id"] for p in out["projects"]][-1], "newp")
        self.assertIn("extra", out["namespaces"])
        for key in raw:                                    # everything else is kept as it was
            if key not in ("projects", "namespaces"):
                self.assertEqual(out[key], raw[key], key)
        self.assertEqual(list(out)[0], "_version")
        [(_stamp, files)] = list_backups(None, home=self.env.home)   # the replaced file is kept
        [copy] = [f for f in files if f.name == "config.json"]
        self.assertEqual(copy.read_bytes(), before)

    def test_registry_json_wins_and_the_legacy_file_is_not_changed(self):
        path = self.legacy_copy()
        before = path.read_bytes()
        write_registry(self.env, Config({"projects": [{"id": "only", "name": "Only"}]}),
                       new_file=True)
        cfg, err = stderr_of(Config.load, self.env)
        self.assertEqual(cfg.source, "config")
        self.assertEqual([p["id"] for p in cfg.projects], ["only"])
        self.assertNotIn("registry", err)
        cfg["projects"] = cfg["projects"] + [{"id": "second", "name": "Second"}]
        stderr_of(cfg.save, self.env)
        self.assertEqual(path.read_bytes(), before)
        doc = json.loads(self.env.registry_file.read_text(encoding="utf-8"))
        self.assertEqual([p["id"] for p in doc["projects"]], ["only", "second"])
        # settings still come from the legacy file while no [maind] table exists
        self.assertEqual(cfg["node"]["id"], "hub")

    def test_maind_table_wins_over_the_legacy_settings(self):
        self.legacy_copy()
        machine_toml(self.env, "[maind.memory]\nhttp_port = 7000\n")
        (cfg, source), err = stderr_of(load_config, self.env)
        self.assertEqual(cfg["memory"]["http_port"], 7000)
        self.assertEqual(cfg["node"], {})                  # the section of the file is ignored whole
        self.assertEqual(cfg["integrations"], {})
        self.assertEqual(source, "legacy:config.json")      # the registry is still the legacy file
        self.assertIn("reading registry from", err)
        self.assertIn("settings are ignored", err)                  # and the person is told what is ignored
        self.assertEqual(len(cfg["projects"]), 3)

    def test_retired_graph_adapter_is_normalized(self):
        path = self.legacy_copy()
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["graph"]["adapter"] = "graphify"
        path.write_text(json.dumps(doc), encoding="utf-8")
        (cfg, _), err = stderr_of(load_config, self.env)
        self.assertEqual(cfg["graph"]["adapter"], "federation")
        self.assertIn("deprecated", err)

    def test_dot_maind_json_is_the_legacy_file_too(self):
        (self.root / ".maind.json").write_text(
            json.dumps({"projects": [{"id": "old", "name": "Old"}]}), encoding="utf-8")
        (cfg, source), _ = stderr_of(load_config, self.env)
        self.assertEqual(source, "legacy:.maind.json")
        self.assertEqual([p["id"] for p in cfg["projects"]], ["old"])

    def test_brain_fallback_keeps_the_maind_settings(self):
        (self.root / ".projects.json").write_text(
            json.dumps({"projects": [{"name": "Brain", "repo": "/r/brain", "vault_path": "/v"}]}),
            encoding="utf-8")
        machine_toml(self.env, "[maind.memory]\nhttp_port = 5000\n")
        (cfg, source), _ = stderr_of(load_config, self.env)
        self.assertEqual(source, "brain-fallback")
        self.assertEqual(cfg["memory"]["http_port"], 5000)
        self.assertTrue(cfg["integrations"]["brain"]["enabled"])


class TestGraphLinks(NodeConfigCase):
    def _edges(self, project_dir):
        g = Graph(self.env, path=self.tmp / "edges.db")
        project = {"id": "flexcrm", "local_path": str(project_dir)}
        config = merge_defaults({"projects": [project, {"id": "getchat", "name": "GetChat"}]})
        count = derive.derive_override(g, project, config)
        return count, sorted(
            (src, dst, data["type"], data["attrs"]) for src in g.adj for dst, data in g.adj[src].items())

    def test_toml_and_legacy_sources_give_the_same_edges(self):
        legacy, toml = self.tmp / "legacy", self.tmp / "toml"
        legacy.mkdir()
        (toml / ".swissknifeman").mkdir(parents=True)
        (legacy / ".maind.graph.json").write_text(json.dumps({"links": [
            {"to": "getchat", "type": "uses", "plane": "doc", "note": "REST"}]}), encoding="utf-8")
        (toml / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[maind.graph.links.getchat]\ntype = \"uses\"\nplane = \"doc\"\n"
            "note = \"REST\"\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            from_legacy = self._edges(legacy)
        from_toml = self._edges(toml)
        self.assertEqual(from_legacy, from_toml)
        self.assertEqual(from_toml[0], 1)

    def test_legacy_file_warns_once_per_project(self):
        legacy = self.tmp / "legacy"
        legacy.mkdir()
        (legacy / ".maind.graph.json").write_text(
            json.dumps({"links": [{"to": "getchat"}]}), encoding="utf-8")
        _, first = stderr_of(self._edges, legacy)
        self.assertEqual(first.count("MAIND_LEGACY_GRAPH_LINKS"), 1)
        _, again = stderr_of(self._edges, legacy)
        self.assertEqual(again, "")

    def test_toml_table_hides_the_legacy_file(self):
        project = self.tmp / "both"
        (project / ".swissknifeman").mkdir(parents=True)
        (project / ".maind.graph.json").write_text(
            json.dumps({"links": [{"to": "getchat", "type": "uses"}]}), encoding="utf-8")
        (project / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[maind.graph.links.getchat]\ntype = \"depends_on\"\n", encoding="utf-8")
        count, edges = self._edges(project)
        self.assertEqual(count, 1)
        self.assertEqual(edges[0][2], "depends_on")
        self.assertEqual(edges[0][3]["plane"], "runtime")   # default of the schema

    def test_links_of_the_project_do_not_reach_the_node_config(self):
        project = self.tmp / "p"
        (project / ".swissknifeman").mkdir(parents=True)
        (project / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[maind.graph.links.getchat]\ntype = \"uses\"\n", encoding="utf-8")
        legacy = self.legacy_copy()
        (cfg, _), _ = stderr_of(load_config, self.env, project=project)
        self.assertNotIn("links", cfg["graph"])
        self.assertEqual(cfg["node"]["id"], "hub")           # legacy settings still in force
        self.assertTrue(legacy.exists())


class TestProjectProviderCarriers(NodeConfigCase):
    def _project(self, name="proj"):
        root = self.tmp / name
        root.mkdir()
        return root

    def test_toml_carrier_is_read_and_resolved(self):
        root = self._project()
        (root / ".swissknifeman").mkdir()
        (root / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = true\n"
            "[aicore.providers.selection.claude-code]\nenabled = false\n", encoding="utf-8")
        providers = toml_project_providers(root)
        self.assertEqual(providers, {"contract_version": "1.0.0", "selection": {
            "codex": {"enabled": True}, "claude-code": {"enabled": False}}})
        config = merge_defaults({"projects": [{"id": "demo"}]})
        resolved = config_mod.resolve_provider_config(
            config, None, "demo", project_config=providers,
            project_carrier=config_mod.PROJECT_TOML_CARRIER)
        enabled = {x.provider_id.value: x.enabled for x in resolved.selection}
        self.assertEqual((enabled["claude-code"], enabled["codex"]), (False, True))
        sources = {item.source.carrier for item in resolved.provenance}
        self.assertIn(".swissknifeman/config.toml", sources)

    def test_deploy_loader_prefers_the_project_layer_over_the_legacy_carrier(self):
        from maind.provision.deploy import _load_project_provider_config
        root = self._project()
        legacy = {"providers": {"contract_version": "1.0.0",
                                "selection": {"claude-code": {"enabled": True}}}}
        (root / ".swissknife.json").write_text(json.dumps(legacy), encoding="utf-8")
        project = {"id": "demo", "local_path": str(root)}
        (found, carrier), err = stderr_of(_load_project_provider_config, project)
        self.assertEqual((found, carrier), (legacy["providers"], ".swissknife.json"))
        self.assertEqual(err.count("MAIND_LEGACY_PROVIDERS"), 1)
        (root / ".swissknifeman").mkdir()
        (root / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = true\n", encoding="utf-8")
        (found, carrier), err = stderr_of(_load_project_provider_config, project)
        self.assertEqual(carrier, ".swissknifeman/config.toml")
        self.assertEqual(found["selection"], {"codex": {"enabled": True}})
        self.assertEqual(err, "")
        self.assertEqual(_load_project_provider_config({"id": "x"}), (None, ".swissknife.json"))

    def test_no_table_means_no_toml_carrier(self):
        root = self._project()
        (root / ".swissknifeman").mkdir()
        (root / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[planner.bridges]\nroots = [\"b\"]\n", encoding="utf-8")
        self.assertIsNone(toml_project_providers(root))
        self.assertIsNone(toml_project_providers(self._project("empty")))

    def test_invalid_toml_carrier_is_an_error(self):
        root = self._project()
        (root / ".swissknifeman").mkdir()
        (root / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[aicore.providers.selection.codex]\nenabled = \"yes\"\n",
            encoding="utf-8")
        with self.assertRaises(ConfigError):
            toml_project_providers(root)

    def test_d108_writes_the_legacy_carrier_when_it_is_the_source(self):
        root = self._project("swissknifeman")
        carrier = root / ".swissknife.json"
        carrier.write_text(json.dumps({"custom": {"keep": True}, "providers": {
            "contract_version": "1.0.0", "selection": {"claude-code": {"enabled": True}}}}),
            encoding="utf-8")
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        plan, err = stderr_of(provider_deploy.plan_project_carrier, root, config, "swissknifeman")
        self.assertEqual(plan.carrier, ".swissknife.json")
        self.assertEqual(plan.path, carrier)
        self.assertIn("MAIND_LEGACY_PROVIDERS", err)
        expected = provider_deploy.canonical_json_bytes({"custom": {"keep": True}, "providers": {
            "contract_version": "1.0.0", "selection": {"claude-code": {"enabled": True},
                                                        "codex": {"enabled": True}}}})
        self.assertEqual(plan.after, expected)           # the bytes the legacy writer always produced
        provider_deploy.apply_project_carrier(plan)
        self.assertEqual(carrier.read_bytes(), expected)
        self.assertFalse((root / ".swissknifeman" / "config.toml").exists())

    def test_d108_writes_the_project_layer_when_it_is_the_source(self):
        root = self._project("swissknifeman")
        toml_path = root / ".swissknifeman" / "config.toml"
        toml_path.parent.mkdir()
        original = ("schema_version = 1\n\n# keep this comment\n[planner.bridges]\nroots = [\"b\"]\n\n"
                    "[aicore.providers.selection.claude-code]\nenabled = false\n")
        toml_path.write_text(original, encoding="utf-8")
        legacy = root / ".swissknife.json"
        legacy.write_text('{"providers": {"contract_version": "1.0.0", "selection": '
                          '{"claude-code": {"enabled": false}}}}\n', encoding="utf-8")
        legacy_before = legacy.read_bytes()
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        plan, err = stderr_of(provider_deploy.plan_project_carrier, root, config, "swissknifeman")
        self.assertEqual(plan.carrier, ".swissknifeman/config.toml")
        self.assertEqual(plan.path, toml_path)
        self.assertEqual(err, "")
        self.assertTrue(plan.changed)
        self.assertEqual(toml_path.read_text(encoding="utf-8"), original)   # planning writes nothing
        provider_deploy.apply_project_carrier(plan)
        text = toml_path.read_text(encoding="utf-8")
        self.assertIn("# keep this comment", text)
        self.assertEqual(toml_project_providers(root)["selection"],
                         {"claude-code": {"enabled": True}, "codex": {"enabled": True}})
        self.assertEqual(legacy.read_bytes(), legacy_before)                # never touched
        [(_stamp, files)] = list_backups(root)
        self.assertEqual(files[0].read_text(encoding="utf-8"), original)
        # a second plan finds nothing to do, and rollback restores the original bytes
        again = provider_deploy.plan_project_carrier(root, config, "swissknifeman")
        self.assertFalse(again.changed)
        provider_deploy._rollback_project_carrier(plan)
        self.assertEqual(toml_path.read_text(encoding="utf-8"), original)

    def test_d108_creates_the_project_layer_for_a_new_project_and_rollback_removes_it(self):
        root = self._project("swissknifeman")
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        plan = provider_deploy.plan_project_carrier(root, config, "swissknifeman")
        self.assertEqual(plan.carrier, ".swissknifeman/config.toml")
        self.assertIsNone(plan.before)
        provider_deploy.apply_project_carrier(plan)
        self.assertTrue((root / ".swissknifeman" / "config.toml").is_file())
        self.assertFalse((root / ".swissknife.json").exists())
        provider_deploy._rollback_project_carrier(plan)
        self.assertFalse((root / ".swissknifeman").exists())

    def test_d108_keeps_the_legacy_carrier_that_has_no_selection_yet(self):
        root = self._project("swissknifeman")
        carrier = root / ".swissknife.json"
        carrier.write_bytes(b'{"custom":{"preserve":true}}\n')
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        plan = provider_deploy.plan_project_carrier(root, config, "swissknifeman")
        self.assertEqual(plan.path, carrier)
        self.assertEqual(json.loads(plan.after)["custom"], {"preserve": True})


class TestBackups(NodeConfigCase):
    def test_hygiene_and_settings_writes_back_up_under_swissknifeman(self):
        from maind.common import save_backup
        project = self.tmp / "p"
        (project / ".git").mkdir(parents=True)
        target = project / ".claude" / "settings.json"
        target.parent.mkdir()
        target.write_text("{}", encoding="utf-8")
        copy = save_backup(target)
        self.assertEqual(copy.parent.parent.parent, project / ".swissknifeman" / "backups")
        self.assertEqual(copy.relative_to(copy.parent.parent), Path(".claude/settings.json"))
        self.assertFalse(target.with_name("settings.json.bak").exists())

    def test_no_backup_files_next_to_the_original(self):
        lib = Path(config_mod.__file__).parent
        offenders = [str(p) for p in lib.rglob("*.py") if "backup_file" in p.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
