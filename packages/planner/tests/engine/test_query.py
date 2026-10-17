"""Read API acceptance: complete documents, filters, artifacts, compatibility and no writes."""
import copy
from hashlib import sha256
import json
import unittest
from unittest import mock

from planner.plan import ops, query, schema, store, units
from planner.plan.model import PlanError

try:
    from . import test_envelope, test_lifecycle
except ImportError:
    import test_envelope
    import test_lifecycle


class QueryCase(test_lifecycle.LifeCase):
    def setUp(self):
        super().setUp()
        plan = self.load()
        ops.add_document(plan, {"id": "notes", "title": "Notes", "applies_to": ["P1.1"],
                                "sections": [{"id": "a", "title": "A", "text": "я" * 100000},
                                             {"id": "b", "title": "B", "text": "second"}]})
        ops.add_decision(plan, "Pick", data={"applies_to": ["P1.1"]})
        ops.add_decision(plan, "Other", data={"applies_to": ["P2"]})
        units.add_unit(plan, "P1.1", "Piece", {"files": ["x.py"]})
        ops.patch(plan, "P1.1", {"artifacts": [
            {"id": "payload", "path": "@plan/artifacts/payload.json", "role": "output"},
            {"id": "text", "path": "@plan/artifacts/text.log", "role": "output"},
            {"id": "missing", "path": "@plan/artifacts/missing.json", "role": "output"}]})
        artifact_dir = self.root / "artifacts"
        artifact_dir.mkdir()
        (artifact_dir / "payload.json").write_text('{"value": "данные", "long": "' + 'x' * 100000 + '"}\n')
        (artifact_dir / "text.log").write_text("large text\n" * 10000)

    def error(self, code, call, *args, **kwargs):
        with self.assertRaises(PlanError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def read_cli(self, *argv):
        status, out, err = test_envelope.run(*argv)
        self.assertEqual(status, 0, err or out)
        result = json.loads(out)
        self.assertEqual(schema.validate(result, "envelope"), [])
        self.assertTrue(result["ok"])
        return result["data"]


class GetTests(QueryCase):
    def test_every_document_kind_is_readable_without_mutating_snapshot(self):
        plan = self.load()
        before = copy.deepcopy(plan.__dict__)
        for ref, kind, doc in (("plan", "plan", plan.plan), ("brief", "brief", plan.brief),
                               ("P1", "phase", plan.phases["P1"]), ("P1.1", "item", plan.items["P1.1"]),
                               ("D1", "decision", plan.decisions["D1"]),
                               ("P1.1/U1", "unit", plan.units["P1.1/U1"]),
                               ("knowledge/notes", "document", plan.documents["notes"]),
                               ("artifact/payload", "artifact", plan.items["P1.1"]["artifacts"][0])):
            with self.subTest(ref=ref):
                result = query.get(plan, ref)
                self.assertEqual(result, {"ref": ref, "kind": kind, "doc": doc, "revision": query.revision_of(doc)})
                self.assertEqual(schema.validate(result, "read-get"), [])
                result["doc"]["extra"] = "caller mutation"
        self.assertEqual(plan.__dict__, before)

    def test_sections_and_top_level_fields_keep_complete_content(self):
        plan = self.load()
        result = query.get(plan, "knowledge/notes", section="a", fields=["sections"])
        self.assertEqual(set(result["doc"]), {"sections"})
        self.assertEqual(result["doc"]["sections"], [plan.documents["notes"]["sections"][0]])
        self.assertEqual(query.get(plan, "knowledge/notes#a")["doc"]["sections"], result["doc"]["sections"])
        self.assertEqual(query.get(plan, "P1.1", fields=["title", "status"])["doc"],
                         {"title": "First", "status": "todo"})

    def test_reference_section_and_field_refusals_are_distinct(self):
        plan = self.load()
        for ref in ("P0.1", "D99", "P1.1/U99", "knowledge/missing", "artifact/absent"):
            self.error("REF_UNKNOWN", query.get, plan, ref)
        for ref in ("P1.1\n", "knowledge/../notes", "views/plan.md", "knowledge/notes#a#b"):
            self.error("REF_INVALID", query.get, plan, ref)
        self.error("SECTION_UNKNOWN", query.get, plan, "knowledge/notes", section="missing")
        self.error("SECTION_UNKNOWN", query.get, plan, "P1.1", section="a")
        self.error("SECTION_UNKNOWN", query.get, plan, "knowledge/notes#a", section="b")
        self.error("FIELD_UNKNOWN", query.get, plan, "P1.1", fields=["missing"])

    def test_qualified_refs_read_exact_documents_in_live_archive_and_other_repo(self):
        plan = self.load()
        self.assertEqual(query.get(plan, "PLAN1.knowledge/notes#a")["doc"]["sections"][0]["id"], "a")
        other = ops.new_plan("OTHER", "Other", plans_root=self.plans, repository="r", owner="o",
                             authoring=test_lifecycle.OPUS, message="m", date="2026.10.07")
        ops.add_phase(other, "Other phase")
        for archived in (False, True):
            if archived:
                archive = self.plans / "archive"
                archive.mkdir()
                other.root.rename(archive / other.root.name)
            self.assertEqual(query.get(plan, "PLAN2.P1")["doc"]["title"], "Other phase")
        remote = self.plans.parent / "remote"
        remote_plan = ops.new_plan("REMOTE", "Remote", plans_root=remote / "plans", repository="remote", owner="o",
                                  authoring=test_lifecycle.OPUS, message="m", date="2026.10.07")
        ops.add_phase(remote_plan, "Remote phase")
        result = self.read_cli("get", self.root, "remote:PLAN1.P1", "--repo", f"remote={remote}")
        self.assertEqual(result["doc"]["title"], "Remote phase")

    def test_show_delegates_get_and_preserves_legacy_document_output(self):
        plan = self.load()
        for ref, kind, doc in (("plan", "plan", plan.plan), ("P1.1", "item", plan.items["P1.1"]),
                               ("knowledge/notes.json", "document", plan.documents["notes"])):
            with self.subTest(ref=ref), mock.patch.object(query, "get", wraps=query.get) as get:
                code, out, err = test_envelope.run("show", self.root, ref)
                self.assertEqual(code, 0, err)
                self.assertEqual(out, store.canonical_dump(doc, kind))
                get.assert_called_once()
        self.assertEqual(self.read_cli("--output", "json", "show", self.root, "P1.1"), plan.items["P1.1"])


class ListTests(QueryCase):
    def test_foreign_applies_to_does_not_break_local_filters(self):
        other = ops.new_plan("OTHER", "Other", plans_root=self.plans, repository="r", owner="o",
                             authoring=test_lifecycle.OPUS, message="m", date="2026.10.07")
        ops.add_phase(other, "Other phase")
        plan = self.load()
        plan.decisions["D1"]["applies_to"].append("PLAN2.P1")
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "decisions", phase="P1")], ["D1"])
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "decisions", applies_to="PLAN2.P1")], ["D1"])

    def test_kinds_and_combined_filters(self):
        plan = self.load()
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "items")], ["P1.1", "P1.2", "P2.1"])
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "units", phase="P1")], ["P1.1/U1"])
        self.assertEqual(query.list_rows(plan, "units", phase="P2"), [])
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "items", phase="P1", status="todo")],
                         ["P1.1", "P1.2"])
        self.assertEqual(query.list_rows(plan, "items", status="in_progress"), [])
        for kind, expected in (("decisions", "D1"), ("documents", "knowledge/notes")):
            self.assertEqual([r["ref"] for r in query.list_rows(plan, kind, applies_to="PLAN1.P1.1", phase="P1")],
                             [expected])
        rows = self.read_cli("list", self.root, "documents", "--applies-to", "P1.1")
        self.assertEqual(rows, [{"ref": "knowledge/notes", "title": "Notes", "status": None}])
        self.assertEqual(schema.validate(rows, "read-list"), [])
        self.error("KIND_UNKNOWN", query.list_rows, plan, "unknown")
        self.error("REF_INVALID", query.list_rows, plan, "item", phase="P1.1")
        self.error("REF_UNKNOWN", query.list_rows, plan, "item", phase="P99")
        self.error("REF_UNKNOWN", query.list_rows, plan, "decision", applies_to="P9.1")

    def test_numeric_order_for_items_and_units(self):
        plan = self.load()
        for n in (10, 3):
            plan.items[f"P1.{n}"] = {"title": str(n), "status": "todo"}
            plan.units[f"P1.1/U{n}"] = {"title": str(n), "status": "todo"}
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "item", phase="P1")],
                         ["P1.1", "P1.2", "P1.3", "P1.10"])
        self.assertEqual([r["ref"] for r in query.list_rows(plan, "unit")], ["P1.1/U1", "P1.1/U3", "P1.1/U10"])


class EventsTests(QueryCase):
    def test_filters_since_and_latest_limit_keep_journal_order(self):
        self.start("P1.1")
        for item, kind, text in (("P1.1", "note", "one"), ("P1.2", "deviation", "two"),
                                 ("P1.1", "deviation", "three"), ("P1.1", "note", "four")):
            store.append_log(self.root, store.new_event(kind, text, test_lifecycle.OPUS, item=item))
        plan = self.load()
        rows = query.events(plan, item="PLAN1.P1.1", types=["note", "deviation"], limit=2)
        self.assertEqual([r["summary"] for r in rows], ["three", "four"])
        self.assertEqual(query.events(plan, since=rows[0]["ts"], limit=2), rows)
        self.assertEqual(query.events(plan, since=rows[0]["ts"].replace("Z", "+00:00")), rows)
        self.assertEqual(query.events(plan, limit=0), [])
        self.assertEqual(query.events(plan, types=["absent"]), [])
        self.assertEqual(schema.validate(rows, "read-events"), [])
        self.assertEqual(self.read_cli("events", self.root, "--item", "P1.1", "--type", "note,deviation", "--limit", "2"), rows)
        self.error("SINCE_INVALID", query.events, plan, since="2026-10-01")
        self.error("LIMIT_INVALID", query.events, plan, limit=-1)
        self.error("REF_INVALID", query.events, plan, item="P1")
        self.error("REF_INVALID", query.events, plan, item="plan")
        self.error("REF_UNKNOWN", query.events, plan, item="P1.99")

    def test_absent_log_is_empty_and_corrupt_log_is_refused(self):
        (self.root / "log.jsonl").unlink()
        self.assertEqual(query.events(self.load()), [])
        (self.root / "log.jsonl").write_text("not json\n")
        self.error("LOG_INVALID", query.events, self.load())


class ArtifactTests(QueryCase):
    def test_metadata_digest_full_json_and_text_content(self):
        plan = self.load()
        raw = (self.root / "artifacts/payload.json").read_bytes()
        result = query.artifact(plan, "artifact/payload")
        self.assertNotIn("content", result)
        self.assertEqual(result["sha256"], sha256(raw).hexdigest())
        self.assertEqual(query.artifact(plan, "artifact/payload", inline=True)["content"], json.loads(raw))
        text = (self.root / "artifacts/text.log").read_text()
        self.assertEqual(query.artifact(plan, "artifact/text", inline=True)["content"], text)
        self.assertEqual(schema.validate(result, "read-artifact"), [])
        self.assertEqual(self.read_cli("artifact", self.root, "artifact/payload", "--inline")["content"], json.loads(raw))

    def test_missing_file_and_ref_are_distinct(self):
        result = query.artifact(self.load(), "artifact/missing", inline=True)
        self.assertEqual(result, {"ref": "artifact/missing", "path": "@plan/artifacts/missing.json",
                                  "role": "output", "exists": False, "sha256": None})
        self.error("REF_UNKNOWN", query.artifact, self.load(), "artifact/unknown")
        self.error("REF_INVALID", query.artifact, self.load(), "P1.1")

    def test_path_escape_symlink_and_human_views_are_refused(self):
        plan = self.load()
        entry = plan.items["P1.1"]["artifacts"][0]
        for path in ("@plan/../secret.json", "/etc/passwd", "@plan/views/data.json", "@plan/artifacts/page.md"):
            entry["path"] = path
            self.error("HUMAN_VIEW" if "/views/" in path or path.endswith(".md") else "PATH_INVALID",
                       query.artifact, plan, "artifact/payload", inline=True)
        target = self.root / "artifacts/escape.json"
        target.symlink_to(self.root.parent / "outside.json")
        entry["path"] = "@plan/artifacts/escape.json"
        self.error("PATH_INVALID", query.artifact, plan, "artifact/payload")

    def test_bad_content_is_refused_only_when_requested_inline(self):
        target = self.root / "artifacts/payload.json"
        for raw in (b"\xff", b"{bad json"):
            target.write_bytes(raw)
            self.assertTrue(query.artifact(self.load(), "artifact/payload")["exists"])
            self.error("CONTENT_INVALID", query.artifact, self.load(), "artifact/payload", inline=True)


class ReadOnlyTests(QueryCase):
    def test_usage_errors_of_read_verbs_also_return_envelopes(self):
        for argv in (("get", self.root), ("get", self.root, "P1.1", "--fields", "title,,status"),
                     ("list", self.root), ("events", self.root, "--limit", "invalid"),
                     ("artifact", self.root), ("get", self.root, "P1.1", "--unknown")):
            with self.subTest(argv=argv):
                status, out, err = test_envelope.run(*argv)
                self.assertEqual(status, 2)
                doc = json.loads(out)
                self.assertEqual(schema.validate(doc, "envelope"), [])
                self.assertEqual(doc["error"]["code"], "USAGE")
                self.assertEqual(err, "")

    def test_reads_never_lock_or_write_even_when_the_plan_lock_is_held(self):
        before = self.tree()
        calls = (("get", self.root, "P1.1"), ("get", self.root, "knowledge/notes#a", "--fields", "sections"),
                 ("list", self.root, "items", "--phase", "P1"), ("events", self.root, "--limit", "1"),
                 ("artifact", self.root, "artifact/payload", "--inline"), ("show", self.root, "P1.1"))
        with store.PlanLock(self.root):
            with mock.patch.object(store.PlanLock, "__enter__", side_effect=AssertionError("read took lock")), \
                    mock.patch.object(store, "atomic_write", side_effect=AssertionError("read wrote a file")):
                for call in calls:
                    status, out, err = test_envelope.run(*call)
                    self.assertEqual(status, 0, err or out)
        self.assertEqual(self.tree(), before)


if __name__ == "__main__":
    unittest.main()
