"""Plan store: snapshot, canonical JSON, atomic validated saves, lock, event log."""
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import PlanError, schema, store  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _hold_lock(plan_dir, ready, release):
    with store.PlanLock(plan_dir):
        ready.set()
        release.wait(20)


class DemoCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()
        self.root = demo.make_demo_plan(self.plans)


class CanonicalTests(unittest.TestCase):
    def test_valid_fixtures_are_already_canonical(self):
        for path in sorted((FIXTURES / "valid").glob("*.json")):
            with self.subTest(path.name):
                kind = max((k for k in schema.KINDS if path.stem.startswith(k)), key=len)
                text = path.read_text(encoding="utf-8")
                self.assertEqual(store.canonical_dump(json.loads(text), kind), text)

    def test_key_order_follows_the_schema_not_the_input(self):
        doc = json.loads((FIXTURES / "valid" / "item-e3.json").read_text(encoding="utf-8"))
        scrambled = dict(reversed(list(doc.items())))
        scrambled["scope"] = dict(reversed(list(scrambled["scope"].items())))
        scrambled["validation"] = [dict(reversed(list(c.items()))) for c in scrambled["validation"]]
        self.assertEqual(store.canonical_dump(scrambled, "item"), store.canonical_dump(doc, "item"))
        keys = list(json.loads(store.canonical_dump(scrambled, "item")))
        self.assertEqual(keys[:3], ["$schema", "id", "title"])
        self.assertEqual(keys[-1], "updated_at")

    def test_one_of_entries_are_ordered_through_their_branch(self):
        unit = json.loads((FIXTURES / "valid" / "unit-e3a-u1.json").read_text(encoding="utf-8"))
        unit["checks"][0] = dict(reversed(list(unit["checks"][0].items())))
        text = store.canonical_dump(unit, "unit")
        self.assertEqual(list(json.loads(text)["checks"][0]), ["id", "cmd", "expect", "kind"])
        self.assertIn('"V1"', text)

    def test_non_ascii_is_kept_and_file_ends_with_newline(self):
        text = store.canonical_dump(json.loads((FIXTURES / "valid" / "plan-e1.json").read_text(encoding="utf-8")), "plan")
        self.assertIn("№", text)
        self.assertIn("…", text)
        self.assertTrue(text.endswith("}\n"))
        self.assertNotIn("\\u", text)


class SaveTests(DemoCase):
    def test_save_stamps_updated_at_and_writes_canonical_form(self):
        path = self.root / "phases" / "P1" / "P1.2.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["title"] = "Renamed"
        with mock.patch.object(store, "now", return_value="2030-01-02T03:04:05Z"):
            store.save(path, doc, "item")
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["updated_at"], "2030-01-02T03:04:05Z")
        self.assertEqual(path.read_text(encoding="utf-8"), store.canonical_dump(written, "item"))

    def test_invalid_document_is_refused_and_file_untouched(self):
        path = self.root / "phases" / "P1" / "P1.2.json"
        before = path.read_bytes()
        doc = json.loads(before)
        doc["bogus"] = 1
        with self.assertRaises(PlanError) as ctx:
            store.save(path, doc, "item")
        self.assertEqual(ctx.exception.code, "SCHEMA_INVALID")
        self.assertEqual([i.code for i in ctx.exception.issues], ["additional"])
        self.assertEqual(path.read_bytes(), before)

    def test_interrupted_write_keeps_the_old_file_and_leaves_no_temp(self):
        path = self.root / "phases" / "P1" / "P1.2.json"
        before = path.read_bytes()
        doc = json.loads(before)
        doc["title"] = "New title"
        with mock.patch("task.plan.store.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.save(path, doc, "item")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")], [])

    def test_save_many_writes_nothing_when_one_document_is_invalid(self):
        good, bad = self.root / "phases" / "P1" / "P1.1.json", self.root / "phases" / "P1" / "P1.2.json"
        before = (good.read_bytes(), bad.read_bytes())
        good_doc, bad_doc = json.loads(before[0]), json.loads(before[1])
        good_doc["title"] = "changed"
        bad_doc["status"] = "finished"
        with self.assertRaises(PlanError):
            store.save_many([(good, good_doc, "item"), (bad, bad_doc, "item")])
        self.assertEqual((good.read_bytes(), bad.read_bytes()), before)

    def test_save_creates_missing_directories(self):
        target = self.root / "decisions" / "D9.json"
        doc = json.loads((self.root / "decisions" / "D2.json").read_text(encoding="utf-8"))
        doc["id"] = "D9"
        store.save(target, doc, "decision")
        self.assertTrue(target.is_file())


class LoadAndOpenTests(DemoCase):
    def test_load_plan_reads_every_document(self):
        plan = store.load_plan(self.root)
        self.assertEqual(plan.problems, [])
        self.assertEqual(plan.plan["short_id"], "PLAN7")
        self.assertEqual(list(plan.phases), ["P1"])
        self.assertEqual(list(plan.items), ["P1.1", "P1.2"])
        self.assertEqual(list(plan.decisions), ["D1", "D2"])
        self.assertEqual(plan.units, {})
        self.assertEqual(plan.rel(plan.path("item", "P1.1")), "phases/P1/P1.1.json")

    def test_units_are_loaded_from_the_item_workspace(self):
        demo.write_doc(self.root / "phases" / "P1" / "P1.1" / "U1.json", demo.fixture("unit-e3a-u1"), "unit")
        plan = store.load_plan(self.root)
        self.assertEqual(list(plan.units), ["P1.1/U1"])
        self.assertEqual(plan.path("unit", "P1.1/U1"), self.root / "phases" / "P1" / "P1.1" / "U1.json")

    def test_natural_order_puts_p1_10_after_p1_9(self):
        for number in (10, 9, 2):
            demo.write_doc(self.root / "phases" / "P1" / f"P1.{number}.json",
                           {**demo.fixture("item-e3-skeleton"), "id": f"P1.{number}"}, "item")
        self.assertEqual(list(store.load_plan(self.root).items), ["P1.1", "P1.2", "P1.9", "P1.10"])

    def test_unreadable_documents_become_problems_not_exceptions(self):
        (self.root / "phases" / "P1" / "P1.2.json").write_text("{not json", encoding="utf-8")
        (self.root / "brief.json").unlink()
        (self.root / "decisions" / "D2.json").write_text("[1]", encoding="utf-8")
        plan = store.load_plan(self.root)
        self.assertEqual(sorted(rel for rel, _ in plan.problems),
                         ["brief.json", "decisions/D2.json", "phases/P1/P1.2.json"])
        self.assertEqual(plan.items["P1.2"], {})

    def test_directory_without_plan_json_is_not_found(self):
        empty = self.plans / "2026.01.01-№1-EMPTY"
        empty.mkdir()
        with self.assertRaises(PlanError) as ctx:
            store.load_plan(empty)
        self.assertEqual(ctx.exception.code, "PLAN_NOT_FOUND")
        self.assertIn("has no plan.json", str(ctx.exception))
        with self.assertRaises(PlanError) as ctx:
            store.open_plan("2026.01.01-№1-EMPTY", self.plans)
        self.assertEqual(ctx.exception.code, "PLAN_NOT_FOUND")

    def test_open_plan_by_id_path_and_short_id(self):
        for ref in (demo.PLAN_ID, str(self.root), "PLAN7"):
            with self.subTest(ref):
                self.assertEqual(store.open_plan(ref, self.plans).root.name, demo.PLAN_ID)

    def test_open_plan_finds_archived_plans(self):
        archive = self.plans / "archive"
        archive.mkdir()
        self.root.rename(archive / demo.PLAN_ID)
        for ref in (demo.PLAN_ID, "PLAN7"):
            plan = store.open_plan(ref, self.plans)
            self.assertEqual(plan.root, archive / demo.PLAN_ID)
        self.assertEqual(plan.repo_root, self.plans.parent)

    def test_repo_root_of_a_live_plan(self):
        self.assertEqual(store.load_plan(self.root).repo_root, self.plans.parent)

    def test_unknown_and_ambiguous_references(self):
        with self.assertRaises(PlanError) as ctx:
            store.open_plan("PLAN99", self.plans)
        self.assertEqual(ctx.exception.code, "PLAN_NOT_FOUND")
        with self.assertRaises(PlanError):
            store.open_plan("", self.plans)
        twin = self.plans / "2026.10.05-№2-TWIN"
        demo.write_doc(twin / "plan.json", {**demo.fixture("plan-e1"), "id": twin.name}, "plan")
        with self.assertRaises(PlanError) as ctx:
            store.open_plan("PLAN7", self.plans)
        self.assertEqual(ctx.exception.code, "PLAN_AMBIGUOUS")


class LockTests(DemoCase):
    def test_second_process_gets_plan_locked_then_succeeds_after_release(self):
        ctx = multiprocessing.get_context("spawn")
        ready, release = ctx.Event(), ctx.Event()
        proc = ctx.Process(target=_hold_lock, args=(str(self.root), ready, release))
        proc.start()
        try:
            self.assertTrue(ready.wait(30), "child never took the lock")
            with self.assertRaises(PlanError) as err:
                with store.PlanLock(self.root, timeout=0.3):
                    self.fail("lock must not be granted while another process holds it")
            self.assertEqual(err.exception.code, "PLAN_LOCKED")
        finally:
            release.set()
            proc.join(30)
        with store.PlanLock(self.root, timeout=2):
            pass

    def test_lock_is_released_on_exception(self):
        with self.assertRaises(RuntimeError):
            with store.PlanLock(self.root):
                raise RuntimeError("boom")
        with store.PlanLock(self.root, timeout=0.2):
            pass


class LogTests(DemoCase):
    def event(self, **extra):
        return store.new_event("note", "something happened", demo.AUTHORING, **extra)

    def test_append_validates_and_writes_one_compact_line(self):
        before = len(store.read_log(self.root))
        store.append_log(self.root, self.event(item="P1.2", refs=["a.py"]))
        events = store.read_log(self.root)
        self.assertEqual(len(events), before + 1)
        self.assertEqual(events[-1]["item"], "P1.2")
        last_line = (self.root / "log.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        self.assertNotIn(": ", last_line)
        self.assertEqual(list(json.loads(last_line))[:3], ["v", "ts", "type"])

    def test_invalid_event_is_refused_and_log_unchanged(self):
        before = (self.root / "log.jsonl").read_bytes()
        bad = self.event()
        bad["type"] = "gossip"
        with self.assertRaises(PlanError) as ctx:
            store.append_log(self.root, bad)
        self.assertEqual(ctx.exception.code, "SCHEMA_INVALID")
        self.assertEqual((self.root / "log.jsonl").read_bytes(), before)

    def test_append_with_held_lock_does_not_deadlock(self):
        with store.PlanLock(self.root) as lock:
            store.append_log(self.root, self.event(), lock=lock)

    def test_append_creates_the_log_file(self):
        (self.root / "log.jsonl").unlink()
        store.append_log(self.root, self.event())
        self.assertEqual(len(store.read_log(self.root)), 1)

    def test_malformed_line_is_reported_by_log_lines_and_rejected_by_read_log(self):
        with open(self.root / "log.jsonl", "a", encoding="utf-8") as handle:
            handle.write("not json\n[1]\n\n")
        rows = store.log_lines(self.root)
        self.assertEqual([(n, e is None) for n, e, _ in rows[-2:]], [(5, True), (6, True)])
        with self.assertRaises(PlanError) as ctx:
            store.read_log(self.root)
        self.assertEqual(ctx.exception.code, "LOG_INVALID")
        self.assertIn("log.jsonl:5", str(ctx.exception))

    def test_missing_log_is_empty(self):
        (self.root / "log.jsonl").unlink()
        self.assertEqual(store.read_log(self.root), [])

    def test_new_event_omits_unset_optionals(self):
        event = store.new_event("start", "go", demo.AUTHORING, item="P1.1")
        self.assertEqual(sorted(event), ["actor", "item", "summary", "ts", "type", "v"])
        self.assertEqual(schema.validate(event, "log-event"), [])


if __name__ == "__main__":
    unittest.main()
