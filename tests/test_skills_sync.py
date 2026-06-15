"""Тесты skills_sync — связать swissknifeman/boost в граф из skills-lock.json (+ fallback)."""
import json
import tempfile
import unittest
from pathlib import Path

from maind.config import merge_defaults
from maind.graph import Graph, seed_skills
from tests.fixtures import make_repo


def _proj_with_lock(tmp, pid, skills):
    path = Path(tmp) / "proj" / pid
    path.mkdir(parents=True)
    (path / "skills-lock.json").write_text(
        json.dumps({"version": 1, "skills": skills}), encoding="utf-8")
    return path


def _cfg(path, pid):
    return merge_defaults({"projects": [{"id": pid, "name": pid.title(),
                                         "local_path": str(path)}]})


class TestSeedSkills(unittest.TestCase):
    def test_lock_materializes_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _proj_with_lock(tmp, "flexcrm", {
                "laravel-best-practices": {"source": "swissknifeman", "bucket": "php",
                                           "also_in": ["laravel-boost"]},
                "pest-testing": {"source": "laravel-boost"}})
            g = Graph(env)
            stats = seed_skills(g, env, _cfg(ppath, "flexcrm"))
            self.assertEqual(stats["projects"], 1)
            self.assertEqual(stats["skill_nodes"], 2)
            uses = {n["id"] for n in g.neighbors("project:flexcrm", 1, edge_types=["uses"])}
            self.assertEqual(uses, {"skill:laravel-best-practices", "skill:pest-testing"})
            prov = {n["id"] for n in g.neighbors("skill:laravel-best-practices", 1,
                                                 edge_types=["provided_by"])}
            self.assertEqual(prov, {"tool:swissknifeman", "tool:laravel-boost"})
            prov2 = {n["id"] for n in g.neighbors("skill:pest-testing", 1,
                                                  edge_types=["provided_by"])}
            self.assertEqual(prov2, {"tool:laravel-boost"})
            self.assertEqual(g.nodes["tool:swissknifeman"]["type"], "tool")

    def test_fallback_to_skm_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = Path(tmp) / "proj" / "agelto"
            ppath.mkdir(parents=True)  # без lock
            skm = env.home / ".swissknifeman"
            skm.mkdir(parents=True)
            (skm / "projects.json").write_text(json.dumps({"projects": [
                {"path": str(ppath), "channel": "vendor", "buckets": ["php"]}]}),
                encoding="utf-8")
            g = Graph(env)
            stats = seed_skills(g, env, _cfg(ppath, "agelto"))
            self.assertEqual(stats["projects"], 1)
            uses = {n["id"] for n in g.neighbors("project:agelto", 1, edge_types=["uses"])}
            self.assertIn("tool:swissknifeman", uses)

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = _proj_with_lock(tmp, "p", {"x": {"source": "swissknifeman"}})
            cfg = _cfg(ppath, "p")
            g = Graph(env)
            seed_skills(g, env, cfg)
            before = (len(g.nodes), sum(len(d) for d in g.adj.values()))
            seed_skills(g, env, cfg)
            after = (len(g.nodes), sum(len(d) for d in g.adj.values()))
            self.assertEqual(before, after)

    def test_no_lock_no_registry_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = Path(tmp) / "proj" / "x"
            ppath.mkdir(parents=True)
            g = Graph(env)
            stats = seed_skills(g, env, _cfg(ppath, "x"))
            self.assertEqual(stats["projects"], 0)


if __name__ == "__main__":
    unittest.main()
