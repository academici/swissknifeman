"""Тесты config.py: валидация схемы, дефолты, приоритет, brain-маппинг."""
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skiller" / "lib"))

from maind.config import (load_config, map_brain_project, merge_defaults,
                          provider_config_layers, resolve_provider_config,
                          validate_config)
from core.tests.test_provider_config import catalog, config
from core import effective_projection
from skiller.config import resolve_provider_config as resolve_skiller_provider_config
from tests.fixtures import make_repo, write_brain_projects, write_maind_config


class TestValidate(unittest.TestCase):
    def test_valid_passes(self):
        validate_config({"node": {"role": "primary"},
                         "graph": {"adapter": "federation"}}, "x")

    def test_legacy_adapter_accepted_with_warning(self):
        # memory/graphify/networkx устарели → принимаются (нормализуются в federation),
        # не падают
        validate_config({"graph": {"adapter": "memory"}}, "x")
        self.assertEqual(merge_defaults({"graph": {"adapter": "memory"}})["graph"]["adapter"],
                         "federation")

    def test_unknown_top_key_dies(self):
        with self.assertRaises(SystemExit):
            validate_config({"grph": {}}, "x")  # опечатка

    def test_wrong_type_dies(self):
        with self.assertRaises(SystemExit):
            validate_config({"projects": {}}, "x")  # должно быть списком

    def test_bad_adapter_enum_dies(self):
        with self.assertRaises(SystemExit):
            validate_config({"graph": {"adapter": "neo4j"}}, "x")

    def test_bad_status_dies(self):
        with self.assertRaises(SystemExit):
            validate_config({"projects": [{"id": "a", "status": "wat"}]}, "x")

    def test_bad_role_dies(self):
        with self.assertRaises(SystemExit):
            validate_config({"node": {"role": "boss"}}, "x")

    def test_bad_memory_role_dies(self):
        with self.assertRaises(SystemExit):
            validate_config({"memory": {"role": "boss"}}, "x")

    def test_memory_role_client_requires_url(self):
        with self.assertRaises(SystemExit):
            validate_config({"memory": {"role": "client"}}, "x")

    def test_memory_role_client_rejects_loopback_url(self):
        with self.assertRaises(SystemExit):
            validate_config({"memory": {"role": "client", "url": "http://127.0.0.1:4111"}}, "x")

    def test_memory_role_client_rejects_wildcard_url(self):
        with self.assertRaises(SystemExit):
            validate_config({"memory": {"role": "client", "url": "http://0.0.0.0:4111"}}, "x")

    def test_memory_role_client_with_lan_url_passes(self):
        validate_config({"memory": {"role": "client", "url": "http://192.168.1.5:4111"}}, "x")

    def test_memory_role_host_needs_no_url(self):
        validate_config({"memory": {"role": "host"}}, "x")   # host не обязан задавать url


class TestDefaults(unittest.TestCase):
    def test_merge_fills(self):
        m = merge_defaults({})
        self.assertEqual(m["memory"]["http_port"], 4111)
        self.assertEqual(m["memory"]["stream_port"], 4112)
        self.assertEqual(m["graph"]["adapter"], "federation")
        self.assertEqual(m["observability"]["service_name"], "maind")
        self.assertEqual(m["agents"]["heartbeat_interval_ms"], 30000)
        self.assertEqual(m["projects"], [])

    def test_merge_no_mutate(self):
        src = {"memory": {"http_port": 9}}
        merge_defaults(src)
        self.assertEqual(src, {"memory": {"http_port": 9}})

    def test_digest_defaults(self):
        # P1.1 (D10): дайджест project-only по умолчанию — shared_max=0
        m = merge_defaults({})
        self.assertEqual(m["memory"]["digest"]["budget_chars"], 4000)
        self.assertEqual(m["memory"]["digest"]["item_max_chars"], 500)
        self.assertEqual(m["memory"]["digest"]["shared_max"], 0)

    def test_digest_overrides_preserved(self):
        m = merge_defaults({"memory": {"digest": {"shared_max": 3}}})
        self.assertEqual(m["memory"]["digest"]["shared_max"], 3)
        self.assertEqual(m["memory"]["digest"]["budget_chars"], 4000)  # остальные — дефолт

    def test_memory_role_defaults_to_standalone(self):
        # back-compat (D80/P4.2): конфиг без memory.role — существующие 17 узлов не
        # меняют поведение после апгрейда.
        m = merge_defaults({})
        self.assertEqual(m["memory"]["role"], "standalone")

    def test_memory_role_explicit_preserved(self):
        m = merge_defaults({"memory": {"role": "host"}})
        self.assertEqual(m["memory"]["role"], "host")


class TestProviderConfig(unittest.TestCase):
    def test_fleet_and_project_layers_use_shared_resolver(self):
        cfg = {"providers": {"defaults": config({"codex": {"enabled": False}})},
               "projects": [{"id": "demo", "providers": config({"codex": {"enabled": True}})}]}
        validate_config(cfg, "x")
        result = resolve_provider_config(cfg, catalog(), "demo")
        self.assertTrue(dict((x.provider_id.value, x.enabled) for x in result.effective)["codex"])

    def test_skiller_and_maind_adapters_match_on_identical_layers(self):
        providers = config({"codex": {"enabled": True}})
        fleet = {"providers": {"defaults": config({"codex": {"enabled": False}})},
                 "projects": [{"id": "demo"}]}
        maind_result = resolve_provider_config(fleet, catalog(), "demo", project_config=providers)
        skiller_result = resolve_skiller_provider_config(
            {"providers": providers}, catalog(), project_id="demo",
            fleet_defaults=provider_config_layers(fleet, "demo")[0])
        self.assertEqual(effective_projection(maind_result), effective_projection(skiller_result))
        self.assertEqual(maind_result.diagnostics, skiller_result.diagnostics)

    def test_legacy_carriers_load_and_resolve_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            path = write_maind_config(root)
            before = path.read_bytes()
            loaded, source = load_config(env)
            result = resolve_provider_config(loaded, catalog(), "alpha")
            self.assertEqual(source, "config.json")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([item.code for item in result.diagnostics], ["PCFG_LEGACY_DEFAULT_APPLIED"])

    def test_synthetic_protected_carriers_remain_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            repository_config = write_maind_config(root)
            sentinels = {
                repository_config: repository_config.read_bytes(),
                root / "protected-plan" / "sentinel.txt": b"protected plan sentinel\n",
                root / "external-fleet" / "config.json": b"external fleet sentinel\n",
            }
            for path, content in sentinels.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            before = {path: path.read_bytes() for path in sentinels}

            loaded, source = load_config(env)
            result = resolve_provider_config(loaded, catalog(), "alpha")

            self.assertEqual(source, "config.json")
            self.assertEqual([item.code for item in result.diagnostics], ["PCFG_LEGACY_DEFAULT_APPLIED"])
            self.assertEqual({path: path.read_bytes() for path in sentinels}, before)

    def test_duplicate_fleet_project_is_fail_closed_without_mutation(self):
        providers = config({"codex": {"enabled": True}})
        fleet = {"projects": [{"id": "demo", "providers": providers}, {"id": "demo", "providers": providers}]}
        before = repr(fleet)
        result = resolve_provider_config(fleet, catalog(), "demo")
        self.assertIsNone(result.effective)
        self.assertEqual(result.diagnostics[0].code, "PCFG_DUPLICATE_FLEET_PROJECT")
        self.assertEqual(repr(fleet), before)


class TestPrecedence(unittest.TestCase):
    def test_maind_json_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root)
            write_brain_projects(root)  # присутствует, но .maind.json приоритетнее
            cfg, source = load_config(env)
            self.assertEqual(source, "config.json")
            self.assertEqual(cfg["projects"][0]["id"], "alpha")

    def test_brain_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_brain_projects(root)
            cfg, source = load_config(env)
            self.assertEqual(source, "brain-fallback")
            ids = [p["id"] for p in cfg["projects"]]
            self.assertIn("brain", ids)
            self.assertIn("swiss-knife-man", ids)  # slug из "Swiss Knife Man"

    def test_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            cfg, source = load_config(env)
            self.assertEqual(source, "empty")
            self.assertEqual(cfg["projects"], [])


class TestBrainMapping(unittest.TestCase):
    def test_field_mapping(self):
        bp = {"name": "My Proj", "enabled": False, "vault_path": "/v/x",
              "repo": "/r/x", "folders": ["docs"]}
        m = map_brain_project(bp)
        self.assertEqual(m["id"], "my-proj")
        self.assertEqual(m["name"], "My Proj")
        self.assertEqual(m["local_path"], "/r/x")        # repo → local_path
        self.assertEqual(m["vault_path"], "/v/x")
        # folders → docs_folders, нормализованы в объектную модель (standalone → private)
        self.assertEqual(m["docs_folders"], [
            {"id": "docs", "vault": "docs", "repo": "docs", "visibility": "private"}])
        self.assertFalse(m["enabled"])
        self.assertEqual(m["memory_scope"], "project:my-proj")


class TestNormalizeDocsFolders(unittest.TestCase):
    def test_flat_back_compat(self):
        from maind.config import normalize_docs_folders
        out = normalize_docs_folders(["docs", "docs-public"])
        self.assertEqual(out, [
            {"id": "docs", "vault": "docs", "repo": "docs", "visibility": "private"},
            {"id": "docs-public", "vault": "docs-public", "repo": "docs-public",
             "visibility": "public"}])

    def test_empty_uses_default_visibility(self):
        from maind.config import normalize_docs_folders
        out = normalize_docs_folders(None, default_visibility="public")
        self.assertEqual(out[0]["visibility"], "public")   # docs → дефолт по типу
        self.assertEqual(out[1]["visibility"], "public")   # docs-public всегда public

    def test_object_different_names(self):
        from maind.config import normalize_docs_folders
        out = normalize_docs_folders(
            [{"vault": "docs-public", "repo": "docs", "visibility": "public"}])
        self.assertEqual(out, [{"id": "docs-public", "vault": "docs-public",
                                "repo": "docs", "visibility": "public"}])

    def test_bad_visibility_falls_back(self):
        from maind.config import normalize_docs_folders
        out = normalize_docs_folders([{"vault": "docs", "visibility": "weird"}],
                                     default_visibility="private")
        self.assertEqual(out[0]["visibility"], "private")


if __name__ == "__main__":
    unittest.main()
