"""Тесты memory.py: HTTP-обёртка (FakeMemoryServer), порты, статус, short-circuit start.

Настоящий Node-демон не запускается: start short-circuit'ится живым FakeMemoryServer,
а status/обёртка работают против него же."""
import os
import tempfile
import unittest

from maind import memory
from tests.fixtures import FakeMemoryServer, make_repo


class TestWrapper(unittest.TestCase):
    def test_store_recall_health_and_scope(self):
        with FakeMemoryServer() as url:
            self.assertTrue(memory.health(url))
            memory.store(url, "project:brain", "fact", "the sky is blue")
            memory.store(url, "project:brain", "fact", "grass is green")
            texts = [r["text"] for r in memory.recall(url, "project:brain", "sky")]
            self.assertIn("the sky is blue", texts)
            self.assertNotIn("grass is green", texts)
            # изоляция по scope
            self.assertEqual(memory.recall(url, "project:other", "sky"), [])

    def test_health_false_when_down(self):
        self.assertFalse(memory.health("http://127.0.0.1:1"))


class TestLifecycle(unittest.TestCase):
    def test_resolve_ports_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = {"memory": {"http_port": 5111, "stream_port": 5112}}
            hp, sp, url = memory.resolve_ports(env, cfg)
            self.assertEqual((hp, sp, url), (5111, 5112, "http://127.0.0.1:5111"))
            os.environ["AGENTMEMORY_PORT"] = "6111"  # env приоритетнее конфига
            try:
                hp, _, url = memory.resolve_ports(env, cfg)
                self.assertEqual(hp, 6111)
                self.assertEqual(url, "http://127.0.0.1:6111")
            finally:
                del os.environ["AGENTMEMORY_PORT"]

    def test_start_short_circuits_when_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                rc = memory.start(env, {"memory": {"url": url}})
                self.assertEqual(rc, 0)
                self.assertFalse(env.memory_pidfile.exists())  # демон уже жив

    def test_status_running_against_fake(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                st = memory.status(env, {"memory": {"url": url}})
                self.assertTrue(st["running"])
                self.assertTrue(all(w["state"] == "up" for w in st["workers"]))

    def test_status_down_and_stale_pidfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            env.data_dir.mkdir(parents=True, exist_ok=True)
            env.memory_pidfile.write_text("2147483646", encoding="utf-8")  # мёртвый pid
            st = memory.status(env, {"memory": {"url": "http://127.0.0.1:1"}})
            self.assertFalse(st["running"])
            self.assertEqual(st["pid"], 2147483646)
            self.assertTrue(st["pidfile_stale"])


if __name__ == "__main__":
    unittest.main()
