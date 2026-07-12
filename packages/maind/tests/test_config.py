"""Тесты config.py: валидация схемы, дефолты, приоритет, brain-маппинг."""
import tempfile
import unittest

from maind.config import (load_config, map_brain_project, merge_defaults,
                          validate_config)
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
