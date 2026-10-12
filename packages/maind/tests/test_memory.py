"""Tests memory.py: HTTP-wrapper (FakeMemoryServer), ports, status, short-circuit start.

Real Node-daemon does not start: start short-circuit'appears alive FakeMemoryServer,
a status/wrapper work against it."""
import base64
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from aicore.util.http import HTTPUnauthorizedError
from maind import memory_policy as policy

from maind import memory
from tests.fixtures import FakeMemoryServer, make_repo


class TestWrapper(unittest.TestCase):
    def test_store_recall_health_and_scope(self):
        with FakeMemoryServer() as url:
            self.assertTrue(memory.health(url))
            memory.store(url, "project:brain", "context", "the sky is blue")
            memory.store(url, "project:brain", "context", "grass is green")
            texts = [r["text"] for r in memory.recall(url, "project:brain", "sky")]
            self.assertIn("the sky is blue", texts)
            self.assertNotIn("grass is green", texts)
            # insulation by scope
            self.assertEqual(memory.recall(url, "project:other", "sky"), [])

    def test_health_false_when_down(self):
        self.assertFalse(memory.health("http://127.0.0.1:1"))

    def test_active_handoff_replaces_previous_slot(self):
        with FakeMemoryServer() as url:
            memory.store_managed(url, "project:p", "active-handoff", "first")
            memory.store_managed(url, "project:p", "active-handoff", "second")
            rows = memory.recall(url, "project:p", "active-handoff")
            self.assertEqual([r["text"] for r in rows], ["[active-handoff] second"])

    def test_ephemeral_progress_key_is_rejected(self):
        with FakeMemoryServer() as url:
            with self.assertRaisesRegex(ValueError, "not durable memory"):
                memory.store_managed(url, "project:p", "checkpoint", "temporary")


class TestScopeMarker(unittest.TestCase):
    def test_roundtrip_single(self):
        marked = memory.mark_scope("project:brain", "hello")
        self.assertEqual(memory.split_scope(marked), ("project:brain", "hello"))

    def test_unmarked_is_none(self):
        self.assertEqual(memory.split_scope("plain text"), (None, "plain text"))

    def test_strips_all_leading_markers(self):
        # owner = FIRST marker; residual nested/repeated ones are removed (do not leak into the search results)
        scope, text = memory.split_scope("[[s:project:a]] [[s:project:b]] secret")
        self.assertEqual(scope, "project:a")
        self.assertNotIn("[[s:", text)
        self.assertEqual(text, "secret")

    def test_owner_is_unforgeable_first_marker(self):
        # user value contains a fake token - store writes owner FIRST
        stored = memory.mark_scope("project:a", "[[s:project:victim]] x")
        scope, text = memory.split_scope(stored)
        self.assertEqual(scope, "project:a")        # owner - real scope, not fake
        self.assertEqual(text, "x")


class TestLifecycle(unittest.TestCase):
    def test_resolve_ports_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = {"memory": {"http_port": 5111, "stream_port": 5112}}
            hp, sp, url = memory.resolve_ports(env, cfg)
            self.assertEqual((hp, sp, url), (5111, 5112, "http://127.0.0.1:5111"))
            os.environ["AGENTMEMORY_PORT"] = "6111"  # env takes precedence over the config
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
                self.assertFalse(env.memory_pidfile.exists())  # the demon is already alive

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
            env.memory_pidfile.write_text("2147483646", encoding="utf-8")  # dead pid
            st = memory.status(env, {"memory": {"url": "http://127.0.0.1:1"}})
            self.assertFalse(st["running"])
            self.assertEqual(st["pid"], 2147483646)
            self.assertTrue(st["pidfile_stale"])


def live(text):
    """Content with a valid unexpired envelope (bypasses write-time size limits)."""
    now = datetime.now(timezone.utc).timestamp()
    meta = {"key": "context", "created_at": now, "expires_at": now + 3600}
    encoded = base64.urlsafe_b64encode(json.dumps(meta).encode()).decode()
    return f"{policy.PREFIX}{encoded}] {text}"


class TestCount(unittest.TestCase):
    def test_count_by_scope_marker(self):
        # count filters the pool by scope-TO MARKER, rather than counting the entire global daemon pool
        pool = [
            {"content": memory.mark_scope("project:brain", live("sky is blue"))},
            {"content": memory.mark_scope("project:brain", live("grass is green"))},
            {"content": memory.mark_scope("project:other", live("hidden"))},   # alien scope — do not count
            {"content": "unmarked"},                                     # without marker - do not count
        ]
        with FakeMemoryServer() as url:
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                cfg = {"memory": {"url": url}}
                orig = memory.export
                memory.export = lambda _u, _s, _h=None: pool
                try:
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        memory._cmd_count(env, cfg, ["--scope", "project:brain", "--json"])
                finally:
                    memory.export = orig
        data = json.loads(buf.getvalue())
        self.assertEqual(data["scopes"], {"project:brain": 2})
        self.assertEqual(data["total_unique"], 2)

    def test_count_dies_when_daemon_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(SystemExit):
                memory._cmd_count(env, {"memory": {"url": "http://127.0.0.1:1"}},
                                  ["--scope", "project:brain"])


class TestDigestSelection(unittest.TestCase):
    """select_digest_items — pure function (without I/O/Env), P1.1: byte-budget + shared-cap
    project-only default (D10). Testing on lists dict — form export()."""

    def _row(self, scope, text, ts):
        fresh = datetime.now(timezone.utc) - timedelta(minutes=32 - int(ts[8:10]))
        return {"content": memory.mark_scope(scope, live(text)), "timestamp": fresh.isoformat()}

    def test_real_dump_shape_sorts_by_updated_at_and_skips_superseded(self):
        # agentmemory 0.9.x export: updatedAt/createdAt, no `timestamp`; oldest-first dump order
        def rec(text, created, updated, **extra):
            return {"content": memory.mark_scope("project:p", live(text)), "createdAt": created,
                    "updatedAt": updated, **extra}
        now = datetime.now(timezone.utc)
        old, replaced, fresh = [(now - timedelta(hours=h)).isoformat() for h in (3, 2, 1)]
        raw = [rec("old fact", old, old), rec("replaced fact", replaced, replaced, isLatest=False),
               rec("fresh fact", fresh, fresh, isLatest=True)]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=8, budget_chars=4000,
            item_max_chars=500, shared_max=0)
        self.assertEqual(items, ["fresh fact", "old fact"])
        self.assertEqual(dropped, 0)

    def test_item_truncated_by_word_with_suffix(self):
        raw = [self._row("project:p", "word " * 200, "2026-01-01T00:00:00Z")]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=8, budget_chars=4000,
            item_max_chars=50, shared_max=0)
        self.assertEqual(len(items), 1)
        self.assertLessEqual(len(items[0]), 50)
        self.assertTrue(items[0].endswith("… (→ recall)"))
        self.assertNotIn("  ", items[0])            # does not cut in the middle of a word (no double space)
        self.assertEqual(dropped, 0)

    def test_budget_stop(self):
        # three DIFFERENT facts, 200 characters each (otherwise the dedup will collapse), budget - for two whole
        raw = [self._row("project:p", f"{c * 199}{i}", f"2026-01-0{i}T00:00:00Z")
               for i, c in ((3, "a"), (2, "b"), (1, "c"))]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=8, budget_chars=450,
            item_max_chars=500, shared_max=0)
        self.assertEqual(len(items), 2)             # the third does not fit entirely, the rest < 150 → drop
        self.assertEqual(dropped, 1)

    def test_default_shared_max_zero_keeps_only_private(self):
        raw = [
            self._row("project:p", "private fact", "2026-01-04T00:00:00Z"),
            self._row("ns:a", "shared fact a", "2026-01-03T00:00:00Z"),
            self._row("ns:b", "shared fact b", "2026-01-02T00:00:00Z"),
            self._row("global", "shared fact global", "2026-01-01T00:00:00Z"),
        ]
        want = {"project:p", "ns:a", "ns:b", "global"}
        items, dropped = memory.select_digest_items(
            raw, "project:p", want, limit=8, budget_chars=4000,
            item_max_chars=500, shared_max=0)
        self.assertEqual(items, ["private fact"])
        self.assertEqual(dropped, 3)

    def test_shared_max_two_takes_two_freshest_after_private(self):
        raw = [
            self._row("project:p", "private fact", "2026-01-01T00:00:00Z"),
            self._row("ns:a", "oldest shared", "2026-01-01T00:00:00Z"),
            self._row("ns:a", "middle shared", "2026-01-02T00:00:00Z"),
            self._row("global", "freshest shared", "2026-01-03T00:00:00Z"),
        ]
        want = {"project:p", "ns:a", "global"}
        items, dropped = memory.select_digest_items(
            raw, "project:p", want, limit=8, budget_chars=4000,
            item_max_chars=500, shared_max=2)
        self.assertEqual(items, ["private fact", "freshest shared", "middle shared"])
        self.assertEqual(dropped, 1)                # oldest shared remained behind cap'ohm

    def test_footer_dropped_positive_when_over_limit(self):
        raw = [self._row("project:p", f"fact {i}", f"2026-01-0{i}T00:00:00Z") for i in range(1, 4)]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=2, budget_chars=4000,
            item_max_chars=500, shared_max=0)
        self.assertEqual(len(items), 2)
        self.assertGreater(dropped, 0)

    def test_empty_pool_returns_empty(self):
        items, dropped = memory.select_digest_items(
            [], "project:p", {"project:p"}, limit=8, budget_chars=4000,
            item_max_chars=500, shared_max=0)
        self.assertEqual(items, [])
        self.assertEqual(dropped, 0)

    def test_dedup_preserved(self):
        raw = [
            self._row("project:p", "same fact", "2026-01-01T00:00:00Z"),
            self._row("project:p", "same fact", "2026-01-02T00:00:00Z"),
        ]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=8, budget_chars=4000,
            item_max_chars=500, shared_max=0)
        self.assertEqual(items, ["same fact"])
        self.assertEqual(dropped, 0)


class TestRoleGate(unittest.TestCase):
    """memory.role (ADR-0001): default standalone does not change behavior; client
    PROHIBITS raising the local daemon with CODE (not documentation, D27)."""

    def test_standalone_default_unaffected_start_short_circuits(self):
        # config WITHOUT memory.role behaves like today (comparison with existing
        # test_start_short_circuits_when_running — is explicit here role='standalone' nearby).
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                rc = memory.start(env, {"memory": {"url": url, "role": "standalone"}})
                self.assertEqual(rc, 0)

    def test_daemon_argv_refuses_when_role_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(SystemExit):
                memory._daemon_argv(env, {"memory": {"role": "client", "url": "http://10.0.0.1:4111"}})

    def test_start_refuses_when_role_client_and_unreachable(self):
        # health(url) gives False (dead port) → start() reaches _daemon_argv → failure
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = {"memory": {"role": "client", "url": "http://127.0.0.1:1"}}
            with self.assertRaises(SystemExit):
                memory.start(env, cfg)

    def test_start_client_short_circuits_when_host_already_up(self):
        # client, whose url is really alive (host is already up) — start() is NOT trying to raise
        # is a local daemon and does NOT refuse: there is nothing to deny, the memory is already available.
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with FakeMemoryServer() as url:
                rc = memory.start(env, {"memory": {"role": "client", "url": url}})
                self.assertEqual(rc, 0)

    def test_run_foreground_refuses_when_role_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(SystemExit):
                memory.run_foreground(env, {"memory": {"role": "client", "url": "http://10.0.0.1:4111"}})


class TestAuth(unittest.TestCase):
    """Bearer-authentication (ADR-0001 p.3/p.4): secret_file → Authorization header;
    401 differs from «not available» (findings §2: /health is always public)."""

    def test_resolve_secret_none_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            self.assertIsNone(memory.resolve_secret(env, {"memory": {}}))

    def test_resolve_secret_env_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            os.environ["AGENTMEMORY_SECRET"] = "from-env"
            try:
                self.assertEqual(memory.resolve_secret(env, {"memory": {}}), "from-env")
            finally:
                del os.environ["AGENTMEMORY_SECRET"]

    def test_resolve_secret_from_secret_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            secret_path = env.root / "memory.secret"
            secret_path.write_text("file-secret\n", encoding="utf-8")
            secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            cfg = {"memory": {"secret_file": "memory.secret"}}
            self.assertEqual(memory.resolve_secret(env, cfg), "file-secret")

    def test_auth_headers_none_without_secret(self):
        self.assertIsNone(memory.auth_headers(None))

    def test_auth_headers_bearer_with_secret(self):
        self.assertEqual(memory.auth_headers("tok"), {"Authorization": "Bearer tok"})

    def test_store_sends_authorization_header_when_secret_configured(self):
        with FakeMemoryServer(secret="good-token") as url:
            with self.assertRaises(HTTPUnauthorizedError):
                memory.store(url, "project:p", "context", "no header")
            res = memory.store(url, "project:p", "context", "with header",
                               headers=memory.auth_headers("good-token"))
            self.assertTrue(res.get("success"))

    def test_check_auth_distinguishes_401_from_unauthenticated_call(self):
        with FakeMemoryServer(secret="good-token") as url:
            self.assertIsNone(memory.check_auth(url, None))                     # secret not configured
            self.assertFalse(memory.check_auth(url, {"Authorization": "Bearer wrong"}))
            self.assertTrue(memory.check_auth(url, {"Authorization": "Bearer good-token"}))

    def test_health_stays_public_regardless_of_secret(self):
        # /agentmemory/health ALWAYS public (findings §2) — health() should not 401'
        # even without headers, with a given secret on the server.
        with FakeMemoryServer(secret="good-token") as url:
            self.assertTrue(memory.health(url))

    def test_export_raises_unauthorized_without_header_when_secret_set(self):
        with FakeMemoryServer(secret="good-token") as url:
            with self.assertRaises(HTTPUnauthorizedError):
                memory.export(url, "project:p")
            self.assertEqual(memory.export(url, "project:p",
                                           memory.auth_headers("good-token")), [])

    def test_unavailable_message_is_role_aware(self):
        # client: DO NOT prompt to raise local daemon (would create a second writer)
        msg_client = memory.unavailable_message({"memory": {"role": "client"}}, "http://10.0.0.1:4111")
        self.assertNotIn("maind start", msg_client)
        msg_standalone = memory.unavailable_message({"memory": {}}, "http://127.0.0.1:4111")
        self.assertIn("maind start", msg_standalone)


if __name__ == "__main__":
    unittest.main()


class TestBindHost(unittest.TestCase):
    """memory.bind_host: machine address - in the node config/env, not in tracked iii-config."""

    TEMPLATE = ("workers:\n  - name: iii-http\n    config:\n      port: 4111\n"
                "      host: 127.0.0.1\n  - name: iii-stream\n    config:\n      port: 4112\n"
                "      host: 127.0.0.1\n")

    def _env(self, tmp):
        _, env = make_repo(tmp)
        env.memory_config.parent.mkdir(parents=True, exist_ok=True)
        env.memory_config.write_text(self.TEMPLATE, encoding="utf-8")
        return env

    def test_without_bind_host_the_tracked_template_is_used_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp)
            self.assertEqual(memory.effective_memory_config(env, {}), env.memory_config)

    def test_host_role_renders_runtime_copy_only_for_iii_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp)
            path = memory.effective_memory_config(
                env, {"memory": {"role": "host", "bind_host": "192.0.2.10"}})
            self.assertNotEqual(path, env.memory_config)
            text = path.read_text(encoding="utf-8")
            self.assertIn("host: 192.0.2.10", text)
            self.assertEqual(text.count("host: 127.0.0.1"), 1)  # iii-stream stays loopback
            self.assertEqual(env.memory_config.read_text(encoding="utf-8"), self.TEMPLATE)

    def test_auto_uses_this_machines_lan_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp)
            with mock.patch.object(memory, "lan_address", return_value="192.0.2.77"):
                path = memory.effective_memory_config(
                    env, {"memory": {"role": "host", "bind_host": "auto"}})
            self.assertIn("host: 192.0.2.77", path.read_text(encoding="utf-8"))

    def test_env_overrides_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp)
            with mock.patch.dict(os.environ, {"AGENTMEMORY_BIND_HOST": "192.0.2.5"}):
                path = memory.effective_memory_config(env, {"memory": {"role": "host"}})
            self.assertIn("host: 192.0.2.5", path.read_text(encoding="utf-8"))

    def test_unsafe_or_misplaced_bind_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp)
            for cfg in ({"memory": {"role": "host", "bind_host": "0.0.0.0"}},
                        {"memory": {"role": "host", "bind_host": "::"}},
                        {"memory": {"role": "host", "bind_host": "not-an-ip"}},
                        {"memory": {"role": "standalone", "bind_host": "192.0.2.10"}},
                        {"memory": {"role": "client", "bind_host": "192.0.2.10"}}):
                with self.subTest(cfg=cfg), self.assertRaises(SystemExit):
                    memory.effective_memory_config(env, cfg)

    def test_daemon_gets_the_runtime_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp)
            with mock.patch.object(memory.shutil, "which", return_value="/usr/bin/node"):
                bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
                bin_path.parent.mkdir(parents=True, exist_ok=True)
                bin_path.write_text("")
                _, child_env, _ = memory._daemon_argv(
                    env, {"memory": {"role": "host", "bind_host": "192.0.2.10"}})
            self.assertTrue(child_env["AGENTMEMORY_III_CONFIG"].endswith("iii-config.runtime.yaml"))
