"""Тесты memory.py: HTTP-обёртка (FakeMemoryServer), порты, статус, short-circuit start.

Настоящий Node-демон не запускается: start short-circuit'ится живым FakeMemoryServer,
а status/обёртка работают против него же."""
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest

from core.http import HTTPUnauthorizedError

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


class TestScopeMarker(unittest.TestCase):
    def test_roundtrip_single(self):
        marked = memory.mark_scope("project:brain", "hello")
        self.assertEqual(memory.split_scope(marked), ("project:brain", "hello"))

    def test_unmarked_is_none(self):
        self.assertEqual(memory.split_scope("plain text"), (None, "plain text"))

    def test_strips_all_leading_markers(self):
        # владелец = ПЕРВЫЙ маркер; остаточные вложенные/повторные снимаются (не утекают в выдачу)
        scope, text = memory.split_scope("[[s:project:a]] [[s:project:b]] secret")
        self.assertEqual(scope, "project:a")
        self.assertNotIn("[[s:", text)
        self.assertEqual(text, "secret")

    def test_owner_is_unforgeable_first_marker(self):
        # значение пользователя содержит фейковый маркер — store пишет владельца ПЕРВЫМ
        stored = memory.mark_scope("project:a", "[[s:project:victim]] x")
        scope, text = memory.split_scope(stored)
        self.assertEqual(scope, "project:a")        # владелец — реальный scope, не фейк
        self.assertEqual(text, "x")


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


class TestCount(unittest.TestCase):
    def test_count_by_scope_marker(self):
        # count фильтрует пул по scope-МАРКЕРУ, а не считает весь глобальный пул демона
        pool = [
            {"content": memory.mark_scope("project:brain", "sky is blue")},
            {"content": memory.mark_scope("project:brain", "grass is green")},
            {"content": memory.mark_scope("project:other", "hidden")},   # чужой scope — не считать
            {"content": "unmarked legacy"},                              # без маркера — не считать
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
    """select_digest_items — чистая функция (без I/O/Env), P1.1: байт-бюджет + shared-cap
    project-only по умолчанию (D10). Тестируем на списках dict — форма export()."""

    def _row(self, scope, text, ts):
        return {"content": memory.mark_scope(scope, text), "timestamp": ts}

    def test_item_truncated_by_word_with_suffix(self):
        raw = [self._row("project:p", "слово " * 200, "2026-01-01T00:00:00Z")]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=8, budget_chars=4000,
            item_max_chars=50, shared_max=0)
        self.assertEqual(len(items), 1)
        self.assertLessEqual(len(items[0]), 50)
        self.assertTrue(items[0].endswith("… (→ recall)"))
        self.assertNotIn("  ", items[0])            # не режет посреди слова (нет двойного пробела)
        self.assertEqual(dropped, 0)

    def test_budget_stop(self):
        # три РАЗНЫХ факта по 200 симв каждый (иначе дедуп схлопнет), бюджет — на два целиком
        raw = [self._row("project:p", f"{c * 199}{i}", f"2026-01-0{i}T00:00:00Z")
               for i, c in ((3, "a"), (2, "b"), (1, "c"))]
        items, dropped = memory.select_digest_items(
            raw, "project:p", {"project:p"}, limit=8, budget_chars=450,
            item_max_chars=500, shared_max=0)
        self.assertEqual(len(items), 2)             # третий не влезает целиком, остаток < 150 → drop
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
        self.assertEqual(dropped, 1)                # oldest shared остался за cap'ом

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
    """memory.role (ADR-0001): дефолт standalone не меняет поведение; client
    ЗАПРЕЩАЕТ поднимать локальный демон КОДОМ (не документацией, D27)."""

    def test_standalone_default_unaffected_start_short_circuits(self):
        # конфиг БЕЗ memory.role ведёт себя как сегодня (сравнение с уже существующим
        # test_start_short_circuits_when_running — тут явный role='standalone' рядом).
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
        # health(url) даёт False (мёртвый порт) → start() доходит до _daemon_argv → отказ
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            cfg = {"memory": {"role": "client", "url": "http://127.0.0.1:1"}}
            with self.assertRaises(SystemExit):
                memory.start(env, cfg)

    def test_start_client_short_circuits_when_host_already_up(self):
        # client, чей url реально жив (хост уже поднят) — start() НЕ пытается поднять
        # локальный демон и НЕ отказывает: нечего запрещать, память уже доступна.
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
    """Bearer-аутентификация (ADR-0001 п.3/п.4): secret_file → Authorization header;
    401 различается от «недоступен» (findings §2: /health всегда публичен)."""

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
                memory.store(url, "project:p", "fact", "no header")
            res = memory.store(url, "project:p", "fact", "with header",
                               headers=memory.auth_headers("good-token"))
            self.assertTrue(res.get("success"))

    def test_check_auth_distinguishes_401_from_unauthenticated_call(self):
        with FakeMemoryServer(secret="good-token") as url:
            self.assertIsNone(memory.check_auth(url, None))                     # секрет не настроен
            self.assertFalse(memory.check_auth(url, {"Authorization": "Bearer wrong"}))
            self.assertTrue(memory.check_auth(url, {"Authorization": "Bearer good-token"}))

    def test_health_stays_public_regardless_of_secret(self):
        # /agentmemory/health ВСЕГДА публичен (findings §2) — health() не должен 401'ить
        # даже без заголовков, при заданном секрете на сервере.
        with FakeMemoryServer(secret="good-token") as url:
            self.assertTrue(memory.health(url))

    def test_export_raises_unauthorized_without_header_when_secret_set(self):
        with FakeMemoryServer(secret="good-token") as url:
            with self.assertRaises(HTTPUnauthorizedError):
                memory.export(url, "project:p")
            self.assertEqual(memory.export(url, "project:p",
                                           memory.auth_headers("good-token")), [])

    def test_unavailable_message_is_role_aware(self):
        # client: НЕ подсказывать поднять локальный демон (создало бы второго писателя)
        msg_client = memory.unavailable_message({"memory": {"role": "client"}}, "http://10.0.0.1:4111")
        self.assertNotIn("maind start", msg_client)
        msg_standalone = memory.unavailable_message({"memory": {}}, "http://127.0.0.1:4111")
        self.assertIn("maind start", msg_standalone)


if __name__ == "__main__":
    unittest.main()
