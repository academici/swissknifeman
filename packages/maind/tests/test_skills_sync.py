"""Tests derive_skills — link swissknifeman/boost to the graph from skills-lock.json.

Single derive-engine (legacy seed_skills deleted): skills-lock.json project →
project ─uses→ skill ─provided_by→ tool (via=skills, plane=meta). Without lock → 0 ribs
(rude fallback'and according to the registry swissknifeman is no more - the source of truth is only lock)."""
import json
import tempfile
import unittest
from pathlib import Path

from maind.derive import derive_skills
from maind.graph import Graph
from tests.fixtures import make_repo


def _proj_with_lock(tmp, pid, skills):
    path = Path(tmp) / "proj" / pid
    path.mkdir(parents=True)
    (path / "skills-lock.json").write_text(
        json.dumps({"version": 1, "skills": skills}), encoding="utf-8")
    return {"id": pid, "name": pid.title(), "local_path": str(path)}


class TestDeriveSkills(unittest.TestCase):
    def test_lock_materializes_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            proj = _proj_with_lock(tmp, "flexcrm", {
                "laravel-best-practices": {"source": "swissknifeman", "bucket": "php",
                                           "also_in": ["laravel-boost"]},
                "pest-testing": {"source": "laravel-boost"}})
            g = Graph(env)
            g.add_node("project:flexcrm", "project", project="flexcrm")
            edges = derive_skills(g, proj)
            self.assertEqual(edges, 5)  # 2 uses + 2 provided_by(lbp) + 1 provided_by(pest)
            uses = {n["id"] for n in g.neighbors("project:flexcrm", 1, edge_types=["uses"])}
            self.assertEqual(uses, {"skill:laravel-best-practices", "skill:pest-testing"})
            prov = {n["id"] for n in g.neighbors("skill:laravel-best-practices", 1,
                                                 edge_types=["provided_by"])}
            self.assertEqual(prov, {"tool:swissknifeman", "tool:laravel-boost"})
            prov2 = {n["id"] for n in g.neighbors("skill:pest-testing", 1,
                                                  edge_types=["provided_by"])}
            self.assertEqual(prov2, {"tool:laravel-boost"})
            self.assertEqual(g.nodes["tool:swissknifeman"]["type"], "tool")

    def test_skills_carry_owner_and_via(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            proj = _proj_with_lock(tmp, "p", {"x": {"source": "swissknifeman"}})
            g = Graph(env)
            g.add_node("project:p", "project", project="p")
            derive_skills(g, proj)
            self.assertEqual(g.nodes["skill:x"]["attrs"]["project"], "p")
            edge = g.adj["project:p"]["skill:x"]
            self.assertEqual(edge["attrs"]["via"], "skills")
            self.assertEqual(edge["attrs"]["plane"], "meta")

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            proj = _proj_with_lock(tmp, "p", {"x": {"source": "swissknifeman"}})
            g = Graph(env)
            g.add_node("project:p", "project", project="p")
            derive_skills(g, proj)
            before = (len(g.nodes), sum(len(d) for d in g.adj.values()))
            derive_skills(g, proj)
            after = (len(g.nodes), sum(len(d) for d in g.adj.values()))
            self.assertEqual(before, after)

    def test_no_lock_no_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            ppath = Path(tmp) / "proj" / "x"
            ppath.mkdir(parents=True)
            g = Graph(env)
            g.add_node("project:x", "project", project="x")
            edges = derive_skills(g, {"id": "x", "name": "X", "local_path": str(ppath)})
            self.assertEqual(edges, 0)


if __name__ == "__main__":
    unittest.main()
