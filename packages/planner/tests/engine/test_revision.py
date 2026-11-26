"""Document revision in ``get``, ``--expected-revision`` of set/push under the plan lock, and the ``plans`` verb."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from planner.plan import ops, query, schema
from planner.plan.model import PlanError

try:
    from . import test_envelope
except ImportError:
    import test_envelope

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"


class RevisionTests(test_envelope.EnvelopeCase):
    def revision(self, ref="P1.1"):
        return self.envelope("get", self.root, ref, code=0)["data"]["revision"]

    def test_get_reports_a_stable_revision_that_set_changes(self):
        first = self.revision()
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(first, self.revision())
        self.assertEqual(first, query.revision_of(self.load().items["P1.1"]))
        self.assertEqual(first, self.envelope("get", self.root, "P1.1", "--fields", "title", code=0)["data"]["revision"])
        ops.patch(self.root, "P1.1", {"summary": "changed"})
        self.assertNotEqual(first, self.revision())

    def test_get_data_validates_and_has_only_the_revision_added(self):
        data = self.envelope("get", self.root, "P1.1", code=0)["data"]
        self.assertEqual(set(data), {"ref", "kind", "doc", "revision"})
        self.assertEqual(schema.validate(data, "read-get"), [])
        data.pop("revision")
        self.assertEqual(schema.validate(data, "read-get"), [])

    def test_set_with_the_current_revision_passes_and_a_stale_one_changes_nothing(self):
        rev = self.revision()
        self.envelope("set", self.root, "P1.1", "--json", '{"summary": "one"}', "--expected-revision", rev, code=0)
        before = self.tree()
        document = self.envelope("set", self.root, "P1.1", "--json", '{"summary": "two"}',
                                 "--expected-revision", rev, code=1)
        self.assertEqual(document["error"]["code"], "PLAN_REVISION_CONFLICT")
        self.assertEqual(before, self.tree())

    def test_plan_brief_and_push_check_the_revision(self):
        for ref in ("plan", "brief"):
            with self.subTest(ref=ref):
                stale = self.revision(ref)
                self.envelope("set", self.root, ref, "--json", '{"out_of_scope": ["x"]}' if ref == "brief" else '{"goal": "g2"}', code=0)
                before = self.tree()
                doc = self.envelope("set", self.root, ref, "--json", "{}", "--expected-revision", stale, code=1)
                self.assertEqual(doc["error"]["code"], "PLAN_REVISION_CONFLICT")
                self.assertEqual(before, self.tree())
        rev = self.revision()
        self.envelope("push", self.root, "P1.1", "scope.include", "--json", '"a.py"', "--expected-revision", rev, code=0)
        before = self.tree()
        doc = self.envelope("push", self.root, "P1.1", "scope.include", "--json", '"b.py"',
                            "--expected-revision", rev, code=1)
        self.assertEqual(doc["error"]["code"], "PLAN_REVISION_CONFLICT")
        self.assertEqual(before, self.tree())

    def test_a_malformed_revision_is_a_usage_error_and_the_revision_comes_before_the_ownership_guard(self):
        for bad in ("abc", "sha256:ABC", "sha256:" + "0" * 63):
            with self.subTest(bad=bad):
                before = self.tree()
                doc = self.envelope("set", self.root, "P1.1", "--json", "{}", "--expected-revision", bad, code=2)
                self.assertEqual(doc["error"]["code"], "USAGE")
                self.assertEqual(before, self.tree())
        doc = self.envelope("set", self.root, "P1.1", "--json", '{"status": "done"}',
                            "--expected-revision", "sha256:" + "0" * 64, code=1)
        self.assertEqual(doc["error"]["code"], "PLAN_REVISION_CONFLICT")

    def test_ops_refuse_a_stale_revision(self):
        with self.assertRaises(PlanError) as ctx:
            ops.patch(self.root, "P1.1", {"summary": "x"}, expected_revision="sha256:" + "1" * 64)
        self.assertEqual(ctx.exception.code, "PLAN_REVISION_CONFLICT")

    def test_two_processes_on_one_revision_yield_exactly_one_success(self):
        rev = self.revision()
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "set", str(self.root), "P1.1", "--json",
                                   json.dumps({"summary": f"writer {n}"}), "--expected-revision", rev],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in range(2)]
        results = [(p.wait(timeout=60), p.stderr.read()) for p in procs]
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(sorted(code for code, _ in results), [0, 1], results)
        self.assertIn("PLAN_REVISION_CONFLICT", next(err for code, err in results if code))


class PlansTests(test_envelope.EnvelopeCase):
    def test_plans_lists_live_plans_with_progress_and_skips_archive_and_foreign_folders(self):
        ops.new_plan("ZETA", "Zeta", plans_root=self.plans, repository="r", owner="o", authoring=test_envelope.test_lifecycle.OPUS,
                     message="m", date="2026.10.08")
        (self.plans / "archive" / "2026.01.01-№1-OLD").mkdir(parents=True)
        (self.plans / "archive" / "2026.01.01-№1-OLD" / "plan.json").write_text("{}")
        (self.plans / "notes").mkdir()
        data = self.envelope("plans", "--plans-root", self.plans, code=0)["data"]
        self.assertEqual(schema.validate(data, "read-plans"), [])
        rows = data["plans"]
        self.assertEqual([r["id"] for r in rows], sorted(r["id"] for r in rows))
        self.assertEqual([r["short_id"] for r in rows], ["PLAN1", "PLAN2"])
        life = rows[0]
        self.assertEqual((life["title"], life["status"]), ("Plan №1 — Life", "active"))
        self.assertEqual(life["progress"], {"phases": 2, "phases_closed": 0, "items": 3, "items_done": 0})
        self.assertEqual(rows[1]["progress"], {"phases": 0, "phases_closed": 0, "items": 0, "items_done": 0})

    def test_items_done_counts_done_deviations_and_skipped(self):
        plan = self.load()
        for item, status in (("P1.1", "done"), ("P1.2", "skipped"), ("P2.1", "blocked")):
            plan.items[item]["status"] = status
        self.assertEqual(sum(1 for i in plan.items.values() if i["status"] in query._DONE_ITEM), 2)
        self.start("P1.1")
        self.finish("P1.1")
        row = self.envelope("plans", "--plans-root", self.plans, code=0)["data"]["plans"][0]
        self.assertEqual(row["progress"]["items_done"], 1)

    def test_a_broken_plan_is_listed_with_an_error_and_does_not_fail_the_list(self):
        ops.new_plan("OTHER", "Other", plans_root=self.plans, repository="r", owner="o", authoring=test_envelope.test_lifecycle.OPUS,
                     message="m", date="2026.10.08")
        broken = self.plans / "2026.10.09-№1-BROKEN"
        broken.mkdir()
        (broken / "plan.json").write_text("{not json")
        rows = self.envelope("plans", "--plans-root", self.plans, code=0)["data"]["plans"]
        self.assertEqual([r["id"] for r in rows][-1], broken.name)
        self.assertEqual(rows[-1], {"id": broken.name, "error": "PLAN_INVALID"})
        self.assertEqual(sum(1 for r in rows if "error" not in r), 2)

    def test_an_absent_plans_folder_is_an_empty_list(self):
        self.assertEqual(query.plans_overview(self.plans / "absent"), {"plans": []})


if __name__ == "__main__":
    unittest.main()
