"""Тесты probe — мониторинг проектов/демонов (read-only, fail-soft)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import maind.probe as probe
from maind import deploy
from maind.config import merge_defaults
from tests.fixtures import FakeMemoryServer, make_repo


def _proj(tmp, pid, *, boost=False, lock=None):
    path = Path(tmp) / "proj" / pid
    path.mkdir(parents=True)
    if boost:
        (path / "boost.json").write_text('{"skills":[]}', encoding="utf-8")
    if lock is not None:
        (path / "skills-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return path


def _cfg(path, pid, **extra):
    rec = {"id": pid, "name": pid.title(), "local_path": str(path),
           "memory_scope": f"project:{pid}"}
    rec.update(extra)
    return merge_defaults({"projects": [rec]})


class TestProbe(unittest.TestCase):
    def test_connected(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            _, env = make_repo(tmp)
            ppath = _proj(tmp, "flexcrm")
            cfg = _cfg(ppath, "flexcrm")
            cfg["memory"]["url"] = url
            deploy.deploy_project(env, cfg, cfg["projects"][0])  # пишет .mcp.json
            r = probe.probe_project(env, cfg, cfg["projects"][0], memory_reachable=True)
            self.assertEqual(r["status"], "connected")
            self.assertTrue(r["configured"]["agentmemory_mcp"])
            self.assertTrue(r["configured"]["maind_mcp"])

    def test_standalone(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = _cfg(_proj(tmp, "bare"), "bare")
            r = probe.probe_project(env, cfg, cfg["projects"][0], memory_reachable=False)
            self.assertEqual(r["status"], "standalone")

    def test_partial_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = _cfg(_proj(tmp, "drift"), "drift", deployed=True)  # флаг без сервера
            r = probe.probe_project(env, cfg, cfg["projects"][0], memory_reachable=False)
            self.assertEqual(r["status"], "partial")

    def test_skills_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            lock = {"version": 1, "skills": {
                "a": {"source": "swissknifeman"}, "b": {"source": "laravel-boost"},
                "c": {"source": "swissknifeman"}, "d": {"source": "local"}}}
            cfg = _cfg(_proj(tmp, "p", boost=True, lock=lock), "p")
            r = probe.probe_project(env, cfg, cfg["projects"][0], memory_reachable=False)
            self.assertEqual(r["skills"], {"total": 4, "swissknifeman": 2,
                                           "laravel_boost": 1, "local": 1})
            self.assertTrue(r["configured"]["boost"])
            self.assertTrue(r["configured"]["skills_lock"])

    def test_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = merge_defaults({"projects": [{"id": "x", "name": "X",
                                                "local_path": str(Path(tmp) / "nope")}]})
            r = probe.probe_project(env, cfg, cfg["projects"][0])
            self.assertEqual(r["status"], "missing-path")

    def test_docs_watcher_pidfile_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            (env.home / ".brain").mkdir(parents=True)
            (env.home / ".brain" / "docs-watcher.pid").write_text(str(os.getpid()),
                                                                  encoding="utf-8")
            dw = probe.detect_docs_watcher(env)
            self.assertTrue(dw["running"])
            self.assertEqual(dw["via"], "pidfile")

    def test_docs_watcher_stale_pid(self):
        # мёртвый pid + systemd замокан как inactive → не запущен (гермётично)
        orig = probe.subprocess.run
        probe.subprocess.run = lambda *a, **k: type("R", (), {"stdout": "inactive"})()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                (env.home / ".brain").mkdir(parents=True)
                (env.home / ".brain" / "docs-watcher.pid").write_text("2147483646",
                                                                      encoding="utf-8")
                self.assertFalse(probe.detect_docs_watcher(env)["running"])
        finally:
            probe.subprocess.run = orig


if __name__ == "__main__":
    unittest.main()
