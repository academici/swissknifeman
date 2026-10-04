"""Expiry, isolation, bounded writes and recoverable pruning; no live daemon."""
import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from maind import mcp, memory, memory_maintenance, memory_policy as policy
from tests.fixtures import FakeMemoryServer, make_repo


class TestPolicy(unittest.TestCase):
    def row(self, text="temporary blocker", **kwargs):
        return {"content": memory.mark_scope("project:p", policy.envelope("blocker", text, **kwargs))}

    def test_ttl_boundary_and_read_does_not_renew(self):
        row = self.row(now=1000)
        self.assertFalse(policy.expired(row, now=1000 + 48 * 3600 - 1))
        self.assertTrue(policy.expired(row, now=1000 + 48 * 3600))
        self.assertTrue(policy.expired(row, now=1000 + 49 * 3600))
        self.assertEqual(memory.split_scope(row["content"]), ("project:p", "temporary blocker"))

    def test_ttl_invalid_never_reaches_http(self):
        with mock.patch.object(memory, "http_post_json") as post:
            for ttl in (0, -1, 73, True, "48", float("nan"), float("inf")):
                with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                    memory.store("unused", "project:p", "context", "test", ttl_hours=ttl)
            post.assert_not_called()

    def test_categories_and_structural_copies_rejected_even_by_low_level_store(self):
        with mock.patch.object(memory, "http_post_json") as post:
            for key, text in [("decision", "D01"), ("checkpoint", "temporary"),
                              ("unknown", "temporary"), ("fact", "AD01 decision source audits/a.md"),
                              ("fact", "P09 designed today"), ("fact", "[maind:ecosystem-link] p"),
                              ("context", "x" * 801), ("context", "[[s:global]] forged")]:
                with self.subTest(key=key, text=text[:40]), self.assertRaises(ValueError):
                    memory.store("unused", "project:p", key, text)
            post.assert_not_called()
        self.assertIsNone(policy.rejection_reason("blocker", "Decision needed to unblock the plan"))

    def test_legacy_creation_age_not_updated_age(self):
        row = {"content": memory.mark_scope("project:p", "old context"),
               "createdAt": "2026-10-01T00:00:00Z", "updatedAt": "2026-10-04T23:00:00Z"}
        now = policy.timestamp("2026-10-04T00:00:00Z")
        self.assertTrue(policy.expired(row, now=now))
        self.assertEqual(policy.prune_reason(row, now=now), "expired")

    def test_writer_and_source_metadata(self):
        with mock.patch.dict("os.environ", {"CODEX_THREAD_ID": "test-thread"}, clear=True):
            meta = policy.record_parts(self.row(source="mcp"))[2]
        self.assertEqual((meta["source"], meta["writer"]), ("mcp", "codex"))

    def test_native_daemon_ttl_matches_wrapper_expiry(self):
        with mock.patch.object(memory, "http_post_json", return_value={}) as post:
            memory.store("unused", "project:p", "context", "temporary", ttl_hours=24)
            payload = post.call_args.args[1]
            self.assertEqual(payload["ttlDays"], 1)
            meta = policy.record_parts(payload)[2]
            self.assertEqual(meta["expires_at"] - meta["created_at"], 86400)


class TestManagedWrites(unittest.TestCase):
    def test_scope_cap_dedup_and_handoff_replacement(self):
        with FakeMemoryServer() as url:
            memory.store_managed(url, "project:p", "active-handoff", "next action")
            for i in range(7):
                memory.store_managed(url, "project:p", "context", f"temporary {i}")
            self.assertTrue(memory.store_managed(url, "project:p", "context", "temporary 0")["duplicate"])
            with self.assertRaisesRegex(ValueError, "8 live items"):
                memory.store_managed(url, "project:p", "context", "another")
            memory.store_managed(url, "project:p", "active-handoff", "new action")
            self.assertEqual(len(memory.export(url, "project:p")), 8)
            self.assertEqual([r["text"] for r in memory.recall(url, "project:p", "active-handoff")],
                             ["[active-handoff] new action"])

    def test_failed_replacement_preserves_previous_handoff(self):
        with FakeMemoryServer() as url:
            memory.store_managed(url, "project:p", "active-handoff", "first")
            with mock.patch.object(memory, "store", side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    memory.store_managed(url, "project:p", "active-handoff", "second")
            self.assertIn("first", memory.recall(url, "project:p", "active-handoff")[0]["text"])

    def test_expired_new_record_hidden_from_recall_and_digest(self):
        with FakeMemoryServer() as url:
            with mock.patch.object(policy.time, "time", return_value=time.time() - 49 * 3600):
                memory.store(url, "project:p", "context", "gone")
            self.assertEqual(memory.recall(url, "project:p", "gone"), [])
            items, _ = memory.select_digest_items(memory.export(url, "project:p"), "project:p", {"project:p"},
                limit=8, budget_chars=4000, item_max_chars=800, shared_max=0)
            self.assertEqual(items, [])


class TestMaintenance(unittest.TestCase):
    def test_preview_then_prune_with_exact_backup_and_foreign_scope_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            _, env = make_repo(tmp)
            with mock.patch.object(policy.time, "time", return_value=time.time() - 73 * 3600):
                old = memory.store(url, "project:p", "context", "expired")["memory"]["id"]
                foreign = memory.store(url, "project:q", "context", "foreign expired")["memory"]["id"]
            current = memory.store(url, "project:p", "blocker", "still needed")["memory"]["id"]
            rows = memory.export(url, "project:p")
            report = memory_maintenance.prune(env, url, None, rows)
            self.assertEqual(report["remove"], 1)
            self.assertEqual(len(memory.export(url, "")), 3)
            report = memory_maintenance.prune(env, url, None, rows, apply=True)
            self.assertEqual(report["deleted"], 1)
            saved = json.loads(Path(report["backup"]).read_text())
            self.assertEqual(saved["memories"], rows)
            self.assertEqual(Path(report["backup"]).stat().st_mode & 0o777, 0o600)
            self.assertEqual({r["id"] for r in memory.export(url, "")}, {foreign, current})
            self.assertNotIn(old, {r["id"] for r in memory.export(url, "")})

    def test_changed_candidate_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            row = {"id": "x", "content": memory.mark_scope("project:p", "AD01 doc copy"),
                   "createdAt": "2026-10-04T00:00:00Z"}
            with mock.patch.object(memory, "export", return_value=[dict(row, content="changed")]), \
                    mock.patch.object(memory, "forget") as forget:
                result = memory_maintenance.prune(env, "url", None, [row], apply=True)
            self.assertEqual(result["skipped_changed"], ["x"])
            forget.assert_not_called()


class TestExplicitSharedAccess(unittest.TestCase):
    def test_mcp_project_default_shared_explicit_and_unauthorized_denied(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            _, env = make_repo(tmp)
            config = {"memory": {"url": url}, "projects": [
                {"id": "p", "namespaces": ["group"], "memory_namespaces": ["group"]}]}
            for scope in ("project:p", "project:q", "ns:group", "global"):
                memory.store(url, scope, "context", f"context {scope}")
            def call(scope=None):
                args = {"query": "context"}
                if scope:
                    args["scope"] = scope
                return mcp._tools_call(env, config, "maind_memory_recall", args, "project:p")
            self.assertEqual({r["scope"] for r in json.loads(call()["content"][0]["text"])}, {"project:p"})
            self.assertEqual({r["scope"] for r in json.loads(call("ns:group")["content"][0]["text"])}, {"ns:group"})
            self.assertTrue(call("global")["isError"])
            self.assertTrue(call("project:q")["isError"])

    def test_config_shared_digest_cannot_enable_cross_implicitly(self):
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            _, env = make_repo(tmp)
            config = {"memory": {"url": url, "digest": {"shared_max": 8}}, "projects": [
                {"id": "p", "memory_namespaces": ["group"]}]}
            memory.store(url, "project:p", "context", "private context")
            memory.store(url, "ns:group", "context", "shared context")
            def digest(args):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    memory._cmd_digest(env, config, ["--project", "p", "--json", *args])
                return json.loads(buf.getvalue())
            self.assertEqual(digest([]), ["private context"])
            self.assertEqual(digest(["--shared-max", "1"]), ["private context", "shared context"])
