"""Tests agents.py: upsert, heartbeat, state derivation, kill, reap."""
import tempfile
import unittest

import maind.agents as agents_mod
from maind.agents import heartbeat, kill, listing, load, reap, register
from tests.fixtures import make_repo

CFG = {"agents": {"heartbeat_interval_ms": 1000}}  # 1s → threshold stale = 3s


class TestAgents(unittest.TestCase):
    def test_register_upsert_preserves_registered_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            register(env, "a1", now="2026-01-01T00:00:00Z", project="p")
            register(env, "a1", now="2026-01-01T00:05:00Z", kind="worker")
            agents = load(env)["agents"]
            self.assertEqual(len(agents), 1)
            self.assertEqual(agents[0]["registered_at"], "2026-01-01T00:00:00Z")
            self.assertEqual(agents[0]["last_heartbeat"], "2026-01-01T00:05:00Z")
            self.assertEqual(agents[0]["kind"], "worker")

    def test_heartbeat_unknown_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(SystemExit):
                heartbeat(env, "ghost")

    def test_state_alive_then_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            register(env, "a", now="2026-01-01T00:00:00Z")
            s2 = listing(env, CFG, now="2026-01-01T00:00:02Z")[0]["state"]
            self.assertEqual(s2, "alive")    # 2s < 3s
            s10 = listing(env, CFG, now="2026-01-01T00:00:10Z")[0]["state"]
            self.assertEqual(s10, "stale")   # 10s > 3s

    def test_kill_removes_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            register(env, "a")               # without pid → kill simply removes the entry
            self.assertTrue(kill(env, "a"))
            self.assertEqual(load(env)["agents"], [])

    def test_kill_unknown_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(SystemExit):
                kill(env, "ghost")

    def test_kill_signals_pid(self):
        calls = []
        orig = agents_mod.os.kill
        agents_mod.os.kill = lambda pid, sig: calls.append((pid, sig))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                register(env, "a", pid=99999)
                kill(env, "a")
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0], 99999)
        finally:
            agents_mod.os.kill = orig

    def test_reap_drops_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            register(env, "a", now="2026-01-01T00:00:00Z")
            self.assertEqual(reap(env, CFG, now="2026-01-01T00:00:10Z"), 1)
            self.assertEqual(load(env)["agents"], [])


if __name__ == "__main__":
    unittest.main()
