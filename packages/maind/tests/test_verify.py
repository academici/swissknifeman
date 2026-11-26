"""Tests verify.py: memory classification (seed vs real), graph coverage, presence .serena.
Network part (living demon) do not touch - we check pure logic and file measurements in tmp."""
import json
import tempfile
import unittest
from pathlib import Path

from maind.config import load_config
from maind.federation import store_path
from maind.verify import classify_memories, graph_report, memory_viewer_url, serena_report
from tests.fixtures import make_repo, write_maind_config

TWO = [
    {"id": "alpha", "name": "Alpha", "type": "node-package", "status": "active"},
    {"id": "beta", "name": "Beta", "type": "php-package", "status": "active"},
]


class TestVerify(unittest.TestCase):
    def test_memory_viewer_follows_configured_rest_port(self):
        self.assertEqual(memory_viewer_url(4111), "http://127.0.0.1:4113")
        self.assertEqual(memory_viewer_url(5311), "http://127.0.0.1:5313")

    def test_classify_seed_vs_real(self):
        mems = [
            {"content": "[maind:ecosystem-link] alpha — node", "createdAt": "2026-06-20T10:00:00Z"},
            {"content": "[maind:ecosystem-link] beta", "createdAt": "2026-06-21T10:00:00Z"},
            {"content": "decided to use JWT for authorization", "createdAt": "2026-06-22T10:00:00Z"},
        ]
        r = classify_memories(mems)
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["seed"], 2)
        self.assertEqual(r["real"], 1)
        self.assertTrue(r["last"].startswith("2026-06-22"))   # the latest

    def test_classify_empty(self):
        r = classify_memories([])
        self.assertEqual((r["total"], r["seed"], r["real"], r["last"]), (0, 0, 0, None))

    def test_graph_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root, projects=TWO)
            config, _ = load_config(env)
            sp = Path(store_path(env, config, config["projects"][0]))   # side only alpha
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(json.dumps({"version": 1, "directed": True,
                                      "nodes": [{"id": "project:alpha", "type": "project"}],
                                      "edges": []}))
            rep = graph_report(env, config)
            self.assertEqual(rep["total"], 2)
            self.assertEqual([b["id"] for b in rep["built"]], ["alpha"])
            self.assertEqual(rep["built"][0]["nodes"], 1)
            self.assertEqual(rep["missing"], ["beta"])

    def test_serena_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_alpha"
            (projdir / ".serena" / "cache").mkdir(parents=True)
            projects = [dict(TWO[0], local_path=str(projdir)), TWO[1]]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            rep = serena_report(config)
            self.assertEqual([s["id"] for s in rep["deployed"]], ["alpha"])
            self.assertTrue(rep["deployed"][0]["cache"])


if __name__ == "__main__":
    unittest.main()
