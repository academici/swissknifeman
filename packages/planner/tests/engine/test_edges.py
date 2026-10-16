"""Link table and edge list (D11): one table of link fields, deterministic typed edges, local ref lookup."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import edges, store  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo

P1 = "phases/P1/"
SCHEMAS = Path(__file__).resolve().parents[2] / "schemas" / "plan" / "v1"
REF_DEFS = ("defs.schema.json#/$defs/ref",)


class EdgeCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()
        self.root = demo.make_demo_plan(self.plans)

    def plan(self):
        return store.load_plan(self.root)

    def edit(self, rel, change):
        demo.rewrite(self.root, rel, change)

    def find(self, **want):
        return [e for e in edges.edges(self.plan()) if all(getattr(e, k) == v for k, v in want.items())]

    def rich(self):
        """Demo plan plus one link of every kind."""
        self.edit(P1 + "P1.1.json", lambda d: d.update(
            artifacts=[{"id": "catalog", "path": "@plan/artifacts/P1/error-catalog.json", "role": "output"}],
            reads=[{"ref": "knowledge/design#validation", "why": "w", "required": True}], units=["U1", "U2"]))
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            artifacts=[{"id": "catalog", "path": "@plan/artifacts/P1/error-catalog.json", "role": "input"}]))
        self.edit("brief.json", lambda d: d["requirements"][0].update(owners=["P1", "D1"]))
        self.edit("decisions/D1.json", lambda d: d.update(status="superseded", superseded_by="D2"))
        self.edit("decisions/D2.json", lambda d: d.update(supersedes=["D1"]))
        for unit_id, extra in (("U1", {}), ("U2", {"depends_on": ["U1"], "parent": "U1"})):
            doc = copy.deepcopy(demo.fixture("unit-e3a-u1"))
            doc.update(id=unit_id, **extra)
            demo.write_doc(self.root / P1 / "P1.1" / f"{unit_id}.json", doc, "unit")
        demo.write_doc(self.root / "knowledge" / "design.json",
                       {"$schema": "urn:swissknifeman:task:plan:document:v1", "id": "design", "title": "Design",
                        "applies_to": ["P1.2"], "sections": [{"id": "validation", "title": "V", "text": "t"}]}, "document")


class TableTests(unittest.TestCase):
    def test_every_row_uses_a_closed_edge_kind_and_every_kind_has_a_row(self):
        self.assertEqual({f.kind for f in edges.LINK_FIELDS}, set(edges.EDGE_KINDS))

    def test_rows_are_unique(self):
        keys = [(f.doc, f.path, f.kind, f.when) for f in edges.LINK_FIELDS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_ref_typed_schema_field_is_in_the_table(self):
        """The table is the only place that knows link fields: a new ref-typed field must be added to it."""
        declared = {(f.doc, f.path) for f in edges.LINK_FIELDS}
        wanted = set()

        def walk(kind, node, path):
            ref = node.get("$ref", "")
            if ref.endswith("$defs/ref") or ref.endswith("$defs/decisionId") and path[-1] in ("supersedes", "superseded_by"):
                wanted.add((kind, tuple(path)))
            for name, child in node.get("properties", {}).items():
                walk(kind, child, [*path, name])
            if isinstance(node.get("items"), dict):
                walk(kind, node["items"], [*path, "*"])

        for kind in ("brief", "phase", "item", "decision", "document"):
            schema = json.loads((SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))
            walk(kind, schema, [])
        wanted = {(k, p) for k, p in wanted if p[-1] != "superseded_by"}  # the back-pointer, see BACKLINKS
        self.assertEqual(wanted - declared, set())

    def test_backlinks_name_table_fields(self):
        for (kind, _field), (fwd_kind, fwd_field) in edges.BACKLINKS.items():
            self.assertEqual(kind, fwd_kind)
            self.assertIn((kind, (fwd_field, "*")), {(f.doc, f.path) for f in edges.LINK_FIELDS})


class EdgeListTests(EdgeCase):
    def test_demo_plan_edges(self):
        self.assertEqual(self.find(source="P1.1", kind="decision"),
                         [edges.Edge("P1.1", "D1", "decision", None, None, P1 + "P1.1.json/decisions/0")])
        related, = self.find(kind="related")
        self.assertEqual((related.source, related.target, related.relation), ("P1.1", "P1.2", "informs"))
        self.assertEqual(related.note, "P1.2 reuses the error collector")
        self.assertEqual(related.where, P1 + "P1.1.json/related/0/ref")
        self.assertEqual([(e.source, e.target) for e in self.find(kind="depends_on")], [("P1.2", "P1.1")])

    def test_order_is_deterministic_and_complete(self):
        self.rich()
        first = edges.edges(self.plan())
        self.assertEqual(first, edges.edges(self.plan()))
        self.assertEqual({e.kind for e in first}, set(edges.EDGE_KINDS))
        sources = [e.source for e in first]
        self.assertEqual(sources[0].split("/")[0], "brief")  # documents come in a fixed order: brief, phases, items, ...

    def test_each_kind_carries_its_endpoints(self):
        self.rich()
        got = {(e.kind, e.source, e.target, e.relation) for e in edges.edges(self.plan())}
        for expected in (("unit_depends_on", "P1.1/U2", "P1.1/U1", None), ("parent", "P1.1/U2", "P1.1/U1", None),
                         ("produces", "P1.1", "artifact/catalog", None), ("consumes", "P1.2", "artifact/catalog", None),
                         ("consumes", "P1.1", "knowledge/design#validation", "reads"),
                         ("applies_to", "brief/B1", "D1", None), ("applies_to", "knowledge/design", "P1.2", None),
                         ("supersedes", "D2", "D1", None), ("decision", "P1.1", "D1", None)):
            self.assertIn(expected, got)

    def test_superseded_by_is_not_a_forward_edge(self):
        self.rich()
        self.assertEqual(self.find(source="D1", kind="supersedes"), [])

    def test_as_dict_uses_json_names(self):
        edge = edges.Edge("P1.1", "D1", "decision", None, None, "x")
        self.assertEqual(edge.as_dict(), {"from": "P1.1", "to": "D1", "kind": "decision", "relation": None,
                                          "note": None, "where": "x"})

    def test_broken_documents_yield_fewer_edges_and_never_raise(self):
        self.edit(P1 + "P1.1.json", lambda d: d.update(depends_on="P1.2", related=[5, {"ref": 3}, {"ref": "D1"}],
                                                       decisions={"a": 1}, artifacts=[None, {"id": 3, "role": "input"}]))
        self.edit("decisions/D1.json", lambda d: d.update(supersedes="D2", applies_to=[1, "P1"]))
        self.assertEqual([e.target for e in self.find(source="P1.1", kind="related")], ["D1"])
        self.assertEqual(self.find(source="D1", kind="applies_to")[0].where, "decisions/D1.json/applies_to/1")


class LocateTests(EdgeCase):
    def test_local_refs_resolve_to_their_documents(self):
        self.rich()
        plan = self.plan()
        self.assertEqual(edges.locate(plan, "P1")["id"], "P1")
        self.assertEqual(edges.locate(plan, "P1.1")["id"], "P1.1")
        self.assertEqual(edges.locate(plan, "D2")["id"], "D2")
        self.assertEqual(edges.locate(plan, "P1.1/U2")["id"], "U2")
        self.assertEqual(edges.locate(plan, "knowledge/design")["id"], "design")
        self.assertEqual(edges.locate(plan, "knowledge/design#validation")["id"], "validation")
        self.assertEqual(edges.locate(plan, "artifact/catalog")["role"], "output")

    def test_unknown_targets_are_none(self):
        self.rich()
        plan = self.plan()
        for ref in ("P9", "P1.9", "D9", "P1.1/U9", "knowledge/none", "knowledge/design#none", "artifact/none"):
            with self.subTest(ref):
                self.assertIsNone(edges.locate(plan, ref))

    def test_an_input_alone_does_not_declare_an_artifact(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(artifacts=[{"id": "only-in", "path": "x.json", "role": "input"}]))
        self.assertIsNone(edges.locate(self.plan(), "artifact/only-in"))

    def test_qualified_and_malformed_refs_raise(self):
        plan = self.plan()
        for ref in ("PLAN3.P2.1", "repo:PLAN3.D4", "knowledge/", "X1", ""):
            with self.subTest(ref), self.assertRaises(ValueError):
                edges.locate(plan, ref)


if __name__ == "__main__":
    unittest.main()
