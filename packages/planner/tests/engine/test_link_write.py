"""Link and artifact writes (D11): one checked transaction, idempotent repeats, refusals that write nothing."""
import copy
import json
import unittest

from planner.plan import check, ops, query, units
from planner.plan.model import PlanError

try:
    from . import test_envelope, test_lifecycle
except ImportError:
    import test_envelope
    import test_lifecycle

UNIT = {"goal": "g", "mode": "self"}


class LinkCase(test_lifecycle.LifeCase):
    """LIFE plus a decision D1, a knowledge document `notes`, and (after ``units``) P1.1/U1..U3."""

    def setUp(self):
        super().setUp()
        ops.add_decision(self.root, "Pick")
        ops.add_document(self.root, {"id": "notes", "title": "Notes",
                                     "sections": [{"id": "a", "title": "A", "text": "t"}]})

    def units(self):
        self.start("P1.1")
        return [units.add_unit(self.root, "P1.1", f"u{n}", {**UNIT, "files": [f"lib/u{n}.py"]})
                for n in (1, 2, 3)]

    def errors(self):
        return [i for i in check.check(self.load()) if i.level == "error"]


class LinkTests(LinkCase):
    def test_every_kind_is_written_in_its_stored_form(self):
        self.assertTrue(ops.link(self.root, "P2.1", "P1.2", kind="depends_on"))
        self.assertTrue(ops.link(self.root, "P2", "P1", kind="depends_on"))
        self.assertTrue(ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs", note="why"))
        self.assertTrue(ops.link(self.root, "P1.1", "D1", kind="decision"))
        self.assertTrue(ops.link(self.root, "D1", "P1.1", kind="applies_to"))
        self.assertTrue(ops.link(self.root, "knowledge/notes", "P2", kind="applies_to"))
        self.units()
        self.assertTrue(ops.link(self.root, "P1.1/U2", "P1.1/U1", kind="unit_depends_on"))
        plan = self.load()
        self.assertEqual(plan.items["P2.1"]["depends_on"], ["P1.2"])
        self.assertEqual(plan.phases["P2"]["depends_on"], ["P1"])
        self.assertEqual(plan.items["P1.1"]["related"], [{"ref": "P2.1", "relation": "informs", "note": "why"}])
        self.assertEqual(plan.items["P1.1"]["decisions"], ["D1"])
        self.assertEqual(plan.decisions["D1"]["applies_to"], ["P1.1"])
        self.assertEqual(plan.documents["notes"]["applies_to"], ["P2"])
        self.assertEqual(plan.units["P1.1/U2"]["depends_on"], ["U1"])
        self.assertEqual(self.errors(), [])
        edges = query.links(plan, "P1.1/U2", direction="out")
        self.assertIn("P1.1/U1", json.dumps(edges))

    def test_a_repeat_is_not_an_error_and_not_a_duplicate(self):
        ops.link(self.root, "P2.1", "P1.2", kind="depends_on")
        ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs")
        before = self.tree()
        self.assertFalse(ops.link(self.root, "P2.1", "P1.2", kind="depends_on"))
        self.assertFalse(ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs"))
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.load().items["P2.1"]["depends_on"], ["P1.2"])

    def test_a_related_repeat_refreshes_the_note_and_another_relation_is_another_edge(self):
        ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs", note="a")
        self.assertTrue(ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs", note="b"))
        self.assertFalse(ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs"))
        self.assertTrue(ops.link(self.root, "P1.1", "P2.1", kind="related", relation="conflicts"))
        related = self.load().items["P1.1"]["related"]
        self.assertEqual([(r["relation"], r.get("note")) for r in related], [("informs", "b"), ("conflicts", None)])

    def test_links_never_touch_status_or_result(self):
        self.start("P1.1")
        self.finish("P1.1")
        before = {k: copy.deepcopy(v) for k, v in self.load().items.items()}
        ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs")
        ops.link(self.root, "P1.1", "D1", kind="decision")
        after = self.load().items
        for key, doc in before.items():
            for field in ("status", "result"):
                self.assertEqual(after[key].get(field), doc.get(field), f"{key}.{field}")

    def test_set_and_push_refuse_a_dangling_link_and_write_nothing(self):
        before = check.check(ops.store.load_plan(self.root))
        for call in (lambda: ops.patch(self.root, "P1.1", {"depends_on": ["P9.9"]}),
                     lambda: ops.push(self.root, "P1.1", "depends_on", "P9.9"),
                     lambda: ops.push(self.root, "P1.1", "related", {"ref": "D404", "relation": "informs"}),
                     lambda: ops.patch(self.root, "D1", {"applies_to": ["P9"]})):
            with self.assertRaises(PlanError) as caught:
                call()
            self.assertEqual(caught.exception.code, "PLAN_INVALID")
        after = ops.store.load_plan(self.root)
        self.assertEqual(after.items["P1.1"].get("depends_on", []), [])
        self.assertEqual(check.check(after), before)
        ops.push(self.root, "P1.1", "related", {"ref": "D1", "relation": "informs"})  # a resolvable link is fine

    def test_refusals_write_nothing(self):
        self.units()
        cases = [
            ("PLAN_INVALID", ("P1.1", "P9.9"), {"kind": "depends_on"}),  # unknown target
            ("PLAN_INVALID", ("P1.1", "P1.1"), {"kind": "depends_on"}),  # self cycle
            ("PLAN_INVALID", ("P1.1", "P1.2"), {"kind": "depends_on"}),  # P1.2 already depends on P1.1
            ("PLAN_INVALID", ("P1.1", "D9"), {"kind": "decision"}),
            ("PLAN_INVALID", ("P1.1", "D9"), {"kind": "related", "relation": "informs"}),
            ("PLAN_INVALID", ("D1", "P9.9"), {"kind": "applies_to"}),
            ("PLAN_INVALID", ("P1.1/U1", "P1.1/U1"), {"kind": "unit_depends_on"}),
            ("PLAN_INVALID", ("P1.1/U1", "P1.1/U9"), {"kind": "unit_depends_on"}),
            ("SCHEMA_INVALID", ("P1.1", "P2.1"), {"kind": "related", "relation": "nonsense"}),
            ("LINK_INVALID", ("P1.1", "P2"), {"kind": "depends_on"}),  # item -> phase
            ("LINK_INVALID", ("P1.1", "P2.1"), {"kind": "decision"}),
            ("LINK_INVALID", ("P2", "P1.1"), {"kind": "related", "relation": "informs"}),  # phase has no related
            ("LINK_INVALID", ("P1.1", "P2.1"), {"kind": "related"}),  # relation required
            ("LINK_INVALID", ("P1.1", "P2.1"), {"kind": "depends_on", "relation": "informs"}),
            ("LINK_INVALID", ("P1.1", "P2.1"), {"kind": "applies_to"}),
            ("LINK_INVALID", ("P1.1/U1", "P1.2/U1"), {"kind": "unit_depends_on"}),  # across items
            ("KIND_UNKNOWN", ("P1.1", "P2.1"), {"kind": "owns"}),
            ("REF_UNKNOWN", ("P9.9", "P1.1"), {"kind": "depends_on"}),
            ("REF_INVALID", ("P1.1", "bogus"), {"kind": "depends_on"}),
            ("REF_INVALID", ("artifact/x", "P1.1"), {"kind": "depends_on"}),
            ("REF_QUALIFIED", ("P1.1", "PLAN7.P1.2"), {"kind": "depends_on"}),
        ]
        for code, (source, target), kwargs in cases:
            with self.subTest(code=code, source=source, target=target, **kwargs):
                self.refused(code, ops.link, source, target, **kwargs)

    def test_a_cycle_through_two_items_is_refused(self):
        ops.link(self.root, "P2.1", "P1.1", kind="depends_on")
        error = self.refused("PLAN_INVALID", ops.link, "P1.1", "P2.1", kind="depends_on")
        self.assertTrue(any(i.code == "cycle" for i in error.issues), error.issues)

    def test_a_unit_cycle_is_refused(self):
        self.units()
        ops.link(self.root, "P1.1/U2", "P1.1/U1", kind="unit_depends_on")
        self.refused("PLAN_INVALID", ops.link, "P1.1/U1", "P1.1/U2", kind="unit_depends_on")


class UnlinkTests(LinkCase):
    def test_unlink_removes_the_edge_and_a_repeat_is_a_no_op(self):
        ops.link(self.root, "P1.1", "P2.1", kind="related", relation="informs")
        ops.link(self.root, "P1.1", "P2.1", kind="related", relation="conflicts")
        ops.link(self.root, "P1.1", "D1", kind="decision")
        self.assertTrue(ops.unlink(self.root, "P1.1", "P2.1", kind="related", relation="informs"))
        self.assertEqual([r["relation"] for r in self.load().items["P1.1"]["related"]], ["conflicts"])
        self.assertTrue(ops.unlink(self.root, "P1.1", "D1", kind="decision"))
        before = self.tree()
        self.assertFalse(ops.unlink(self.root, "P1.1", "D1", kind="decision"))
        self.assertFalse(ops.unlink(self.root, "P1.1", "P2.1", kind="related", relation="informs"))
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.errors(), [])

    def test_unlink_removes_a_unit_dependency(self):
        self.units()
        ops.link(self.root, "P1.1/U2", "P1.1/U1", kind="unit_depends_on")
        self.assertTrue(ops.unlink(self.root, "P1.1/U2", "P1.1/U1", kind="unit_depends_on"))
        self.assertEqual(self.load().units["P1.1/U2"]["depends_on"], [])

    def test_a_dangling_link_can_be_removed_through_the_api(self):
        path = self.root / "phases" / "P2" / "P2.1.json"
        doc = json.loads(path.read_text())
        doc["depends_on"] = ["P9.9"]
        path.write_text(json.dumps(doc))
        self.assertTrue(self.errors())
        self.assertTrue(ops.unlink(self.root, "P2.1", "P9.9", kind="depends_on"))
        self.assertEqual(self.errors(), [])

    def test_unlink_refusals_write_nothing(self):
        for code, args, kwargs in (("REF_UNKNOWN", ("P9.9", "P1.1"), {"kind": "depends_on"}),
                                   ("KIND_UNKNOWN", ("P1.1", "P2.1"), {"kind": "owns"}),
                                   ("LINK_INVALID", ("P1.1", "P2.1"), {"kind": "related"}),
                                   ("LINK_INVALID", ("P1.1", "P2"), {"kind": "depends_on"}),
                                   ("REF_QUALIFIED", ("P1.1", "PLAN7.P1.2"), {"kind": "depends_on"})):
            with self.subTest(code=code, args=args):
                self.refused(code, ops.unlink, *args, **kwargs)


class ArtifactTests(LinkCase):
    def test_add_artifact_declares_outputs_and_inputs(self):
        self.assertTrue(ops.add_artifact(self.root, "P1.1", "out/a.json", "output", artifact_id="a"))
        self.assertTrue(ops.add_artifact(self.root, "P1.2", "out/a.json", "input", artifact_id="a"))
        self.assertTrue(ops.add_artifact(self.root, "P1.2", "out/b.json", "output"))
        plan = self.load()
        self.assertEqual(plan.items["P1.1"]["artifacts"], [{"path": "out/a.json", "role": "output", "id": "a"}])
        self.assertEqual(plan.items["P1.2"]["artifacts"][1], {"path": "out/b.json", "role": "output"})
        self.assertEqual(self.errors(), [])

    def test_a_repeat_is_a_no_op(self):
        ops.add_artifact(self.root, "P1.1", "out/a.json", "output", artifact_id="a")
        before = self.tree()
        self.assertFalse(ops.add_artifact(self.root, "P1.1", "out/a.json", "output", artifact_id="a"))
        self.assertFalse(ops.add_artifact(self.root, "P1.1", "out/a.json", "output"))
        self.assertEqual(self.tree(), before)

    def test_an_id_can_be_added_to_an_artifact_that_had_none_but_not_changed(self):
        ops.add_artifact(self.root, "P1.1", "out/a.json", "output")
        self.assertTrue(ops.add_artifact(self.root, "P1.1", "out/a.json", "output", artifact_id="a"))
        self.assertEqual(len(self.load().items["P1.1"]["artifacts"]), 1)
        self.refused("LINK_INVALID", ops.add_artifact, "P1.1", "out/a.json", "output", artifact_id="other")

    def test_refusals_write_nothing(self):
        ops.add_artifact(self.root, "P1.1", "out/a.json", "output", artifact_id="a")
        for code, args, kwargs in (
                ("PLAN_INVALID", ("P1.2", "out/z.json", "output"), {"artifact_id": "a"}),  # id declared twice
                ("PLAN_INVALID", ("P1.2", "elsewhere.json", "input"), {"artifact_id": "a"}),  # path differs
                ("PLAN_INVALID", ("P1.2", "x.json", "input"), {"artifact_id": "ghost"}),  # no such output
                ("PLAN_INVALID", ("P1.2", "../x.json", "output"), {}),
                ("SCHEMA_INVALID", ("P1.2", "x.json", "sideways"), {}),
                ("SCHEMA_INVALID", ("P1.2", "x.json", "output"), {"artifact_id": "bad id"}),
                ("REF_UNKNOWN", ("P9.9", "x.json", "output"), {}),
                ("LINK_INVALID", ("P1", "x.json", "output"), {})):
            with self.subTest(code=code, args=args, kwargs=kwargs):
                self.refused(code, ops.add_artifact, *args, **kwargs)


class LinkCliTests(test_envelope.EnvelopeCase):
    def test_the_verbs_answer_with_the_envelope_and_are_idempotent(self):
        link = ("link", self.root, "P1.2", "P1.1", "--kind", "related", "--relation", "informs")
        first = self.envelope(*link, code=0)
        self.assertEqual(first["data"]["changed"], True)
        self.assertEqual(self.envelope(*link, code=0)["data"]["changed"], False)
        gone = ("unlink", self.root, "P1.2", "P1.1", "--kind", "related", "--relation", "informs")
        self.assertEqual(self.envelope(*gone, code=0)["data"]["changed"], True)
        self.assertEqual(self.envelope(*gone, code=0)["data"]["changed"], False)
        art = ("add-artifact", self.root, "P1.1", "--path", "out/a.json", "--role", "output", "--id", "a")
        self.assertEqual(self.envelope(*art, code=0)["data"]["changed"], True)
        self.assertEqual(self.envelope(*art, code=0)["data"]["changed"], False)

    def test_refusals_carry_codes_and_issues(self):
        document = self.envelope("link", self.root, "P1.1", "P9.9", "--kind", "depends_on", code=1)
        self.assertEqual(document["error"]["code"], "PLAN_INVALID")
        self.assertTrue(document["error"]["issues"])
        self.assertEqual(self.envelope("link", self.root, "P1.1", "P2", "--kind", "depends_on", code=1)["error"]["code"],
                         "LINK_INVALID")
        self.envelope("link", self.root, "P1.1", "P2.1", "--kind", "owns", code=2)  # closed enum is a usage error
        self.assertEqual(self.envelope("add-artifact", self.root, "P9.9", "--path", "x", "--role", "output",
                                       code=1)["error"]["code"], "REF_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
