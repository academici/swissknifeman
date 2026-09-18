import io
import contextlib
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from analyst.doctor import cmd_doctor
from analyst.events import append_event, events_path, read_events
from analyst.runs import migrate_legacy, neutral_run_report, normalize

_TASK_LIB = Path(__file__).resolve().parents[2] / "task" / "lib"


class ProviderReaderTests(unittest.TestCase):
    def test_claude_rich_scalar_mapping_and_source_provenance(self):
        raw = {
            "schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z",
            "tools": {"total": 9, "by_name": {"Read": 3}},
            "reads": {"total": 7, "unique": 3, "top_rereads": []},
            "files_changed": ["a", "b"], "workflows": [{"name": "w"}],
            "retrieval": {"calls": 2}, "devloop": {"workarounds": ["w"], "deferred": ["d"]},
            "maind": {"memory_recall": {"calls": 2}, "graph_query": {"calls": 1}},
            "usage": {"totals": {"in": 13, "out": 6, "cache_read": 0, "cache_creation": 0},
                      "agents": [{"label": "main", "in": 10, "out": 4},
                                 {"label": "agent-aaa", "in": 3, "out": 2}],
                      "subagents_parsed": 1, "subagents_skipped": 0},
            "tool_failures": [{"tool": "Bash"}], "bash": {"failed": []},
        }
        source = json.dumps(raw, sort_keys=False, separators=(",", ":")).encode()
        event = normalize("claude-code", 2, raw, project_id="p", raw_ref="local:claude",
                          source_bytes=source, declared_sha256=hashlib.sha256(source).hexdigest())
        self.assertEqual(event["metrics"], {"tools": 9, "reads": 7, "files": 2, "workflows": 1,
                         "retrieval": 2, "devloop": 2, "maind": 3, "usage": 19, "errors": 1})
        self.assertEqual(event["outcome"], "ok")
        self.assertEqual(event["provenance"]["sha256"], hashlib.sha256(source).hexdigest())

    def test_claude_missing_fields_additive_and_corrupt_scalars(self):
        base = {"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z",
                "harmless_additive": {"future": True}, "bash": {}}
        event = normalize("claude-code", 2, base, project_id="p", raw_ref="local:claude")
        self.assertEqual(event["metrics"], {})
        self.assertNotIn("reads", event["metrics"])
        self.assertEqual(event["outcome"], "unknown")
        with self.assertRaisesRegex(ValueError, "ANALYTICS_UNKNOWN_SCHEMA"):
            normalize("claude-code", 3, base, project_id="p", raw_ref="local:claude")
        with self.assertRaisesRegex(ValueError, "ANALYTICS_CORRUPT_EVENT") as caught:
            normalize("claude-code", 2, dict(base, tools={"total": "bad-secret"}),
                      project_id="p", raw_ref="local:claude")
        self.assertNotIn("bad-secret", str(caught.exception))

    def test_claude_reads_total_supervisor_probe(self):
        raw = {"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z",
               "tools": {"total": 1, "by_name": {"Read": 99}},
               "reads": {"total": 7, "unique": 3, "top_rereads": []}, "bash": {}}
        event = normalize("claude-code", 2, raw, project_id="p", raw_ref="local:claude")
        self.assertEqual(event["metrics"]["reads"], 7)

    def test_explicit_reader_normalizes_distinct_provider_provenance(self):
        claude = normalize("claude-code", 2, {"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}, project_id="p", raw_ref="local:c")
        codex = normalize("codex", 1, {"schema": 1, "session_id": "s", "occurred_at": "2026-07-22T00:00:00Z", "metrics": {"usage": 1}}, project_id="p", raw_ref="local:x")
        cursor = normalize("cursor", 1, {
            "schema": 1,
            "provider_id": "cursor",
            "session_id": "conv-1",
            "conversation_id": "conv-1",
            "occurred_at": "2026-09-18T00:00:00Z",
            "event_kind": "run_summary",
            "outcome": "unknown",
            "metrics": {},
            "cursor": {"end_reason": "window_close"},
        }, project_id="p", raw_ref="local:u")
        self.assertEqual((claude["provider_id"], codex["provider_id"], cursor["provider_id"]),
                         ("claude-code", "codex", "cursor"))
        with self.assertRaisesRegex(ValueError, "ANALYTICS_UNKNOWN_PROVIDER"):
            normalize("other", 1, {}, project_id="p", raw_ref="local:z")

    def test_append_and_copy_verify_migration_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"schema": 2, "session_id": "s", "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}), encoding="utf-8")
            before = legacy.read_bytes()
            self.assertTrue(migrate_legacy(root, project_id="p", source=legacy, operation="plan")["would_copy"])
            self.assertTrue(migrate_legacy(root, project_id="p", source=legacy, operation="apply")["copied"])
            self.assertEqual(len(read_events(root)), 1)
            self.assertFalse(migrate_legacy(root, project_id="p", source=legacy, operation="apply")["would_copy"])
            self.assertEqual(legacy.read_bytes(), before)
            self.assertTrue(events_path(root).is_file())

    def test_source_bytes_hash_order_and_redaction_fail_closed(self):
        raw = {"schema": 1, "session_id": "s", "occurred_at": "2026-07-22T00:00:00Z",
               "metrics": {"usage": 1}}
        source = json.dumps(raw, separators=(",", ":"), sort_keys=False).encode()
        declared = hashlib.sha256(source).hexdigest()
        first = normalize("codex", 1, raw, project_id="p", raw_ref="local:source",
                          source_bytes=source, declared_sha256=declared)
        reordered = {"metrics": {"usage": 1}, "occurred_at": raw["occurred_at"],
                     "session_id": "s", "schema": 1}
        second = normalize("codex", 1, reordered, project_id="p", raw_ref="local:source",
                           source_bytes=source, declared_sha256=declared)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["provenance"]["sha256"], declared)
        with self.assertRaisesRegex(ValueError, "ANALYTICS_CORRUPT_EVENT"):
            normalize("codex", 1, raw, project_id="p", raw_ref="local:source",
                      source_bytes=source, declared_sha256="0" * 64)
        for invalid in (
            dict(raw, prompt="secret"),
            dict(raw, metrics={"usage": {"nested": 1}}),
            dict(raw, metrics={"unknown": 1}),
        ):
            with self.assertRaisesRegex(ValueError, "ANALYTICS_REDACTION_FAILED"):
                normalize("codex", 1, invalid, project_id="p", raw_ref="local:source")
        with self.assertRaisesRegex(ValueError, "ANALYTICS_MISSING_PROVENANCE"):
            normalize("codex", 1, raw, project_id="p", raw_ref="local:../source")

    def test_migration_modes_are_no_write_until_apply_and_conflict_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"schema": 2, "session_id": "s",
                "generated_at": "2026-07-22T00:00:00Z", "tools": {"total": 1}, "bash": {}}), encoding="utf-8")
            before = legacy.read_bytes()
            for operation in ("plan", "dry-run", "check"):
                self.assertTrue(migrate_legacy(root, project_id="p", source=legacy, operation=operation)["would_copy"])
                self.assertFalse(events_path(root).exists())
                self.assertEqual(legacy.read_bytes(), before)
            migrate_legacy(root, project_id="p", source=legacy, operation="apply")
            stored = json.loads(events_path(root).read_text(encoding="utf-8"))
            stored["provenance"]["sha256"] = "0" * 64
            events_path(root).write_text(json.dumps(stored) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ANALYTICS_MIGRATION_CONFLICT"):
                migrate_legacy(root, project_id="p", source=legacy, operation="apply")

    def test_neutral_projection_omits_missing_raw_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = normalize("codex", 1, {"schema": 1, "session_id": "s",
                "occurred_at": "2026-07-22T00:00:00Z", "metrics": {"usage": 1}},
                project_id="p", raw_ref="local:source")
            append_event(root, event)
            report = neutral_run_report(root, "s")
            self.assertEqual(report["metrics"], {"usage": 1})
            self.assertEqual(report["session_id"], "s")
            self.assertNotIn("tools", report)
            self.assertNotIn("files_changed", report)
            self.assertNotIn("bash", report)
            self.assertNotIn("workflows", report)

    def test_cursor_envelope_to_neutral_run_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "schema": 1,
                "provider_id": "cursor",
                "session_id": "conv-42",
                "conversation_id": "conv-42",
                "occurred_at": "2026-09-18T03:00:00Z",
                "event_kind": "run_summary",
                "outcome": "unknown",
                "metrics": {},
                "cursor": {
                    "end_reason": "window_close",
                    "final_status": "cancelled",
                    "native_session_id": "cursor-session-1",
                    "duration_ms": 3210,
                },
            }
            event = normalize("cursor", 1, source, project_id="p", raw_ref="local:cursor")
            append_event(root, event)
            report = neutral_run_report(root, "conv-42")
            self.assertEqual(report["session_id"], "conv-42")
            self.assertEqual(report["metrics"], {})
            self.assertEqual(len(report["provenance"]), 1)
            stored = read_events(root)[0]
            self.assertEqual(stored.provider_id, "cursor")
            self.assertEqual(stored.outcome, "unknown")

    def test_cursor_reader_rejects_output_and_bad_reason(self):
        valid = {
            "schema": 1,
            "provider_id": "cursor",
            "session_id": "conv-1",
            "conversation_id": "conv-1",
            "occurred_at": "2026-09-18T03:00:00Z",
            "event_kind": "run_summary",
            "outcome": "ok",
            "metrics": {},
            "cursor": {"end_reason": "completed"},
        }
        with self.assertRaisesRegex(ValueError, "ANALYTICS_REDACTION_FAILED"):
            normalize("cursor", 1, dict(valid, output="secret"), project_id="p", raw_ref="local:r")
        with self.assertRaisesRegex(ValueError, "ANALYTICS_REDACTION_FAILED"):
            normalize("cursor", 1, {**valid, "cursor": {"end_reason": "not-documented"}},
                      project_id="p", raw_ref="local:r")


class DoctorRouteEvidenceTests(unittest.TestCase):
    """P2.4 (plans/2026.07.24-AGENT-RELIABILITY): `analyst doctor` optionally reports
    whether `task.route_evidence` is importable — analyst does not depend on `task`
    hard, mirroring the existing optional `maind` check."""

    def _run_doctor(self):
        from analyst.common import Env
        env = Env("/tmp/analyst-root", "doctor", home="/tmp/fakehome")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_doctor(env, [])
        return out.getvalue()

    def test_reports_available_when_task_lib_is_on_sys_path(self):
        sys.path.insert(0, str(_TASK_LIB))
        sys.modules.pop("task.route_evidence", None)
        sys.modules.pop("task", None)
        try:
            text = self._run_doctor()
        finally:
            sys.path.remove(str(_TASK_LIB))
            sys.modules.pop("task.route_evidence", None)
            sys.modules.pop("task", None)
        self.assertIn("✓ task.route_evidence", text)

    def test_reports_optional_and_does_not_fail_the_verdict_when_absent(self):
        sys.modules.pop("task.route_evidence", None)
        sys.modules.pop("task", None)
        blocked = [p for p in sys.path if p.endswith("task/lib") or p == str(_TASK_LIB)]
        for p in blocked:
            sys.path.remove(p)
        try:
            text = self._run_doctor()
        finally:
            for p in blocked:
                sys.path.insert(0, p)
        self.assertIn("· task.route_evidence", text)
        self.assertIn("Окружение готово.", text)


if __name__ == "__main__":
    unittest.main()
