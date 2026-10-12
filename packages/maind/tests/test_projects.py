"""Tests projects.py: sync from brain (mapping, idempotency, field saving)."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import aicore
from aicore.util.partners import PartnerUnavailable
from aicore.util.schema import load_contract, validate
from maind.config import load_config
from maind.projects import brain_path, cmd_projects, get, listing, sync_from_brain, write_config
from tests.fixtures import capture, make_repo, write_brain_projects, write_maind_config


class TestSync(unittest.TestCase):
    def test_adds_and_preserves_maind_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, projects=[
                {"id": "brain", "name": "OldName", "skills": ["arch"],
                 "dependencies": ["maind"], "type": "obsidian-vault"}])
            bpath = write_brain_projects(root)
            cfg, source = load_config(env)
            self.assertEqual(source, "config.json")
            cfg, stats = sync_from_brain(env, cfg, bpath)
            self.assertEqual(stats["added"], 1)    # swiss-knife-man — new
            self.assertEqual(stats["updated"], 1)  # brain — updated
            brain = get(cfg, "brain")
            self.assertEqual(brain["name"], "Brain")       # updated from brain
            self.assertEqual(brain["skills"], ["arch"])    # maind-only saved
            self.assertEqual(brain["dependencies"], ["maind"])
            # idempotency: second sync adds nothing
            cfg, stats2 = sync_from_brain(env, cfg, bpath)
            self.assertEqual(stats2["added"], 0)

    def test_brain_visibility_wins_and_warns(self):
        """visibility — from frontmatter Brain → .projects.json; sync updates it (brain
        «wins», owner-of-fact) and warns about the change (protection against bad cache)."""
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, projects=[
                {"id": "botkit", "name": "Botkit", "type": "php-package", "status": "active",
                 "docs_folders": [{"id": "docs", "vault": "docs", "repo": "docs",
                                   "visibility": "public"}]}])
            cfg, _ = load_config(env)
            bpath = write_brain_projects(root, projects=[
                {"name": "Botkit", "enabled": True, "vault_path": "/v/Botkit",
                 "repo": "/r/botkit", "folders": [{"vault": "docs", "visibility": "private"}]}])
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                cfg, _ = sync_from_brain(env, cfg, bpath)
            docs = next(f for f in get(cfg, "botkit")["docs_folders"] if f["id"] == "docs")
            self.assertEqual(docs["visibility"], "private")   # brain won (owner-of-fact)
            self.assertIn("public→private", buf.getvalue())   # warning was

    def test_write_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            cfg, source = load_config(env)        # empty
            self.assertEqual(source, "empty")
            cfg, _ = sync_from_brain(env, cfg, write_brain_projects(root))
            write_config(env, cfg)
            cfg2, source2 = load_config(env)
            self.assertEqual(source2, "config.json")  # .maind.json takes priority
            self.assertTrue(get(cfg2, "brain"))
            self.assertEqual(len(listing(env, cfg2)), 2)


class TestBrainPath(unittest.TestCase):
    def test_config_path_wins_over_partner(self):
        cfg = {"integrations": {"brain": {"path": "/cfg/vault"}}}
        with mock.patch("maind.projects.run_partner_json") as run:
            self.assertEqual(brain_path(cfg), "/cfg/vault")
        run.assert_not_called()

    def test_project_vault_path_before_partner(self):
        cfg = {"projects": [{"id": "brain", "vault_path": "/proj/vault"}]}
        with mock.patch("maind.projects.run_partner_json") as run:
            self.assertEqual(brain_path(cfg), "/proj/vault")
        run.assert_not_called()

    def test_vault_comes_from_brain_vault_json(self):
        with mock.patch("maind.projects.run_partner_json",
                        return_value={"path": "/partner/vault", "source": "config"}) as run:
            self.assertEqual(brain_path({}), "/partner/vault")
        self.assertEqual(run.call_args[0][:2], ("brain", ["vault", "--json"]))

    def test_old_vault_variable_is_not_read(self):
        with mock.patch.dict(os.environ, {"MAIND_BRAIN_VAULT": "/env/vault"}), \
                mock.patch("maind.projects.run_partner_json",
                           return_value={"path": "/partner/vault"}):
            self.assertEqual(brain_path({}), "/partner/vault")

    def test_missing_partner_gives_none_with_message(self):
        err = PartnerUnavailable("PARTNER_UNAVAILABLE: brain not found "
                                 "(set SKM_BRAIN_ROOT or put brain on PATH)")
        with mock.patch("maind.projects.run_partner_json", side_effect=err), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertIsNone(brain_path({}))
        self.assertIn("PARTNER_UNAVAILABLE", stderr.getvalue())

    def test_partner_without_path_gives_none(self):
        with mock.patch("maind.projects.run_partner_json", return_value={"path": None}), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertIsNone(brain_path({}))
        self.assertIn("PARTNER_BAD_OUTPUT", stderr.getvalue())


class TestProjectsHealth(unittest.TestCase):
    def test_routes_exact_project_and_evidence_set_to_public_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root)
            expected = {"aggregate": "non-green", "projects": [],
                        "evidence_set_id": "set:alpha"}
            with mock.patch("maind.provider_health.load_evidence_set",
                            return_value=object()) as load, \
                    mock.patch("maind.provider_health.evaluate",
                               return_value=expected) as evaluate:
                _, out = capture(cmd_projects, env, [
                    "health", "--project", "alpha", "--evidence-set", "sealed.json",
                    "--json",
                ])
            self.assertEqual(expected, __import__("json").loads(out))
            load.assert_called_once_with("sealed.json")
            self.assertEqual(["alpha"],
                             [item["id"] for item in evaluate.call_args.args[2]])

    def test_rejects_ambiguous_or_missing_scope_before_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root)
            for argv in (
                    ["health", "--evidence-set", "sealed.json", "--json"],
                    ["health", "--project", "alpha", "--all",
                     "--evidence-set", "sealed.json", "--json"]):
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    cmd_projects(env, argv)


class TestListContract(unittest.TestCase):
    def test_list_json_matches_projects_list_schema(self):
        schemas = Path(__file__).resolve().parents[1] / "schemas"
        foundation = Path(aicore.__file__).resolve().parents[2] / "schemas"
        registry, kind = load_contract(schemas / "projects-list" / "v1",
                                       urn_prefix="urn:swissknifeman:maind:", foundation=foundation)
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, projects=[
                {"id": "alpha", "name": "Alpha", "local_path": "~/a", "namespaces": ["*"],
                 "enabled": True, "status": "active", "dependencies": ["maind"], "extra": {"k": 1}},
                {"id": "beta", "local_path": "/b", "enabled": False}])
            _, out = capture(cmd_projects, env, ["list", "--json"])
            doc = json.loads(out)
            self.assertEqual([p["id"] for p in doc], ["alpha", "beta"])
            self.assertEqual(validate(doc, kind, registry), [])
            self.assertTrue(validate([{"name": "no id"}], kind, registry))
            # records mapped from the brain fallback may carry null paths
            self.assertEqual(validate([{"id": "c", "local_path": None, "vault_path": None}], kind, registry), [])


if __name__ == "__main__":
    unittest.main()
