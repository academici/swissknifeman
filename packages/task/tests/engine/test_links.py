"""Graph read API: independent field walk, every edge kind, bounded traversal and local packs."""
import copy
import json
import unittest
from unittest import mock

from task.plan import context, edges, query, schema, store
from task.plan.model import PlanError

try:
    from . import test_edges, test_envelope
except ImportError:
    import test_edges
    import test_envelope


def independent_edges(plan):
    """Oracle walks document fields explicitly; never calls LINK_FIELDS, tagged or edges."""
    found = []

    def add(source, target, kind, relation=None, note=None):
        row = {"from": source, "to": target, "kind": kind}
        if relation is not None:
            row["relation"] = relation
        if note is not None:
            row["note"] = note
        found.append(row)

    for req in plan.brief.get("requirements", []):
        for owner in req.get("owners", []):
            add("brief/" + req["id"], owner, "applies_to")
    for name, phase in plan.phases.items():
        for dep in phase.get("depends_on", []):
            add(name, dep, "depends_on")
    for name, item in plan.items.items():
        for dep in item.get("depends_on", []):
            add(name, dep, "depends_on")
        for related in item.get("related", []):
            add(name, related["ref"], "related", related.get("relation"), related.get("note"))
        for decision in item.get("decisions", []):
            add(name, decision, "decision")
        if (item.get("result") or {}).get("decision"):
            add(name, item["result"]["decision"], "decision", "result")
        for read in item.get("reads", []):
            if "ref" in read:
                add(name, read["ref"], "consumes", "reads")
        for artifact in item.get("artifacts", []):
            if "id" in artifact:
                add(name, "artifact/" + artifact["id"], "consumes" if artifact["role"] == "input" else "produces")
    for name, decision in plan.decisions.items():
        for target in decision.get("applies_to", []):
            add(name, target, "applies_to")
        for old in decision.get("supersedes", []):
            add(name, old, "supersedes")
    for name, unit in plan.units.items():
        owner = name.split("/")[0]
        for dep in unit.get("depends_on", []):
            add(name, owner + "/" + dep, "unit_depends_on")
        if unit.get("parent"):
            add(name, owner + "/" + unit["parent"], "parent")
    for name, doc in plan.documents.items():
        for target in doc.get("applies_to", []):
            add("knowledge/" + name, target, "applies_to")
    return sorted(found, key=edge_key)


def edge_key(row):
    return row["kind"], row["from"], row["to"], row.get("relation", ""), row.get("note", "")


def independent_walk(graph, root, direction, depth, kinds=None):
    """Scan all rows once per distance; independent of the production adjacency index."""
    distances = {root: 0}
    selected = {}
    for distance in range(depth):
        frontier = {node for node, d in distances.items() if d == distance}
        for row in graph:
            if kinds is not None and row["kind"] not in kinds:
                continue
            endpoints = []
            if direction in ("out", "both") and row["from"] in frontier:
                endpoints.append(row["to"])
            if direction in ("in", "both") and row["to"] in frontier:
                endpoints.append(row["from"])
            if endpoints:
                selected[edge_key(row)] = row
            for node in endpoints:
                distances.setdefault(node, distance + 1)
    return [selected[key] for key in sorted(selected)]


class LinksCase(test_edges.EdgeCase):
    def setUp(self):
        super().setUp()
        self.rich()

    def error(self, code, call, *args, **kwargs):
        with self.assertRaises(PlanError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)


class TraversalTests(LinksCase):
    def test_links_equal_independent_field_walk_for_every_kind_and_direction(self):
        plan = self.plan()
        phase = copy.deepcopy(plan.phases["P1"])
        phase.update(id="P2", title="Second phase", depends_on=["P1"])
        plan.phases["P2"] = phase
        plan.items["P1.1"]["result"]["decision"] = "D2"
        expected = independent_edges(plan)
        self.assertEqual({e["kind"] for e in expected}, set(edges.EDGE_KINDS))
        roots = {e[end] for e in expected for end in ("from", "to") if not e[end].startswith("brief/")}
        seen = set()
        for root in sorted(roots):
            for direction in ("out", "in", "both"):
                for depth in (1, 2, 10):
                    with self.subTest(root=root, direction=direction, depth=depth):
                        result = query.links(plan, root, direction=direction, depth=depth)
                        wanted = independent_walk(expected, root, direction, depth)
                        self.assertEqual(result["edges"], wanted)
                        self.assertEqual(schema.validate(result, "read-links"), [])
                        node_refs = {root} | {e[end] for e in wanted for end in ("from", "to")}
                        self.assertEqual([n["ref"] for n in result["nodes"]], sorted(node_refs))
                        seen.update(edge_key(e) for e in result["edges"])
        self.assertEqual(seen, {edge_key(e) for e in expected})

    def test_incoming_dependencies_and_kind_filters_preserve_edge_direction(self):
        plan = self.plan()
        result = query.links(plan, "P1.1", direction="in", kinds=["depends_on"])
        self.assertEqual(result["edges"], [{"from": "P1.2", "to": "P1.1", "kind": "depends_on"}])
        kinds = ["decision", "consumes"]
        result = query.links(plan, "P1.1", direction="both", kinds=kinds, depth=3)
        self.assertEqual(result["edges"], independent_walk(independent_edges(plan), "P1.1", "both", 3, kinds))
        for kind in edges.EDGE_KINDS:
            root = next(e["from"] for e in independent_edges(plan) if e["kind"] == kind and not e["from"].startswith("brief/"))
            self.assertTrue(query.links(plan, root, direction="out", kinds=[kind])["edges"])

    def test_cycles_duplicates_and_huge_depth_terminate_deterministically(self):
        plan = self.plan()
        plan.items["P1.1"]["depends_on"] = ["P1.2", "P1.2"]
        first = query.links(plan, "P1.1", kinds=["depends_on"], depth=10**9)
        self.assertEqual(first["edges"], [{"from": "P1.1", "to": "P1.2", "kind": "depends_on"},
                                          {"from": "P1.2", "to": "P1.1", "kind": "depends_on"}])
        plan.items = dict(reversed(list(plan.items.items())))
        self.assertEqual(query.links(plan, "P1.1", kinds=["depends_on"], depth=10**9), first)

    def test_self_qualified_refs_normalize_but_foreign_nodes_never_load(self):
        plan = self.plan()
        qualified = plan.plan["short_id"] + ".P1.1"
        plan.items["P1.2"]["depends_on"] = [qualified]
        plan.items["P1.1"]["related"].append({"ref": "remote:PLAN99.P1.2", "relation": "consumes"})
        with mock.patch.object(store, "load_plan", side_effect=AssertionError("loaded foreign plan")), \
                mock.patch.object(query.refs, "resolve", side_effect=AssertionError("resolved foreign plan")):
            result = query.links(plan, qualified, depth=2)
            incoming = query.links(plan, "remote:PLAN99.P1.2", direction="in")
            pack = query.neighborhood(plan, qualified)
        self.assertEqual(result["ref"], qualified)
        self.assertIn({"from": "P1.2", "to": "P1.1", "kind": "depends_on"}, result["edges"])
        self.assertIn({"ref": "remote:PLAN99.P1.2", "title": None, "status": None}, result["nodes"])
        self.assertEqual(incoming["edges"], [{"from": "P1.1", "to": "remote:PLAN99.P1.2", "kind": "related", "relation": "consumes"}])
        self.assertEqual(pack["item"], plan.items["P1.1"])

    def test_node_metadata_covers_sections_units_artifacts_and_requirements(self):
        plan = self.plan()
        nodes = {n["ref"]: n for n in query.links(plan, "P1.1", depth=3)["nodes"]}
        self.assertEqual(nodes["artifact/catalog"], {"ref": "artifact/catalog", "title": None, "status": None})
        self.assertEqual(nodes["knowledge/design#validation"]["title"], "V")
        self.assertEqual(nodes["brief/B1"]["title"], plan.brief["requirements"][0]["text"])
        units = query.links(plan, "P1.1/U1")["nodes"]
        self.assertEqual({n["title"] for n in units}, {d["title"] for d in plan.units.values()})

    def test_invalid_roots_and_options_have_stable_refusals(self):
        plan = self.plan()
        self.error("REF_INVALID", query.links, plan, "P1.1\n")
        self.error("REF_UNKNOWN", query.links, plan, "P9.9")
        self.error("SECTION_UNKNOWN", query.links, plan, "knowledge/design#missing")
        self.error("DIRECTION_INVALID", query.links, plan, "P1.1", direction="sideways")
        for depth in (0, -1, 1.5, True):
            self.error("DEPTH_INVALID", query.links, plan, "P1.1", depth=depth)
        for kinds in (["unknown"], []):
            self.error("KIND_UNKNOWN", query.links, plan, "P1.1", kinds=kinds)
        self.assertEqual(query.links(plan, "plan")["edges"], [])
        self.assertEqual(query.links(plan, "PLAN999.P9.9")["nodes"],
                         [{"ref": "PLAN999.P9.9", "title": None, "status": None}])


class NeighborhoodTests(LinksCase):
    def test_pack_matches_local_context_applicability_and_depth_one_links(self):
        plan = self.plan()
        baseline = context.collect(plan, "P1.2", with_scout=False)
        result = query.neighborhood(plan, "P1.2")
        self.assertEqual(result["item"], baseline["item"])
        self.assertEqual(result["decisions"], baseline["decisions"])
        self.assertEqual(result["documents"], baseline["documents"])
        graph = query.links(plan, "P1.2", depth=1)
        self.assertEqual({k: result[k] for k in graph}, graph)
        self.assertEqual(schema.validate(result, "read-neighborhood"), [])

    def test_global_phase_explicit_and_consumed_docs_are_full_and_ordered(self):
        plan = self.plan()
        accepted = copy.deepcopy(plan.decisions["D1"])
        for ident, scope, status in (("D3", [], "accepted"), ("D4", ["P1"], "accepted"),
                                     ("D5", ["P1.1"], "accepted"), ("D6", ["P1.2"], "accepted"),
                                     ("D7", [], "open")):
            doc = copy.deepcopy(accepted)
            doc.update(id=ident, status=status, applies_to=scope)
            doc.pop("superseded_by", None)
            plan.decisions[ident] = doc
        plan.items["P1.1"]["decisions"] += ["D7", "remote:PLAN99.D1"]
        design = copy.deepcopy(plan.documents["design"])
        design["sections"][0]["text"] = "я" * 100000
        plan.documents["design"] = design  # explicitly consumed despite applying to the other item
        for name, scope in (("global", []), ("phase", ["P1"]), ("own", ["P1.1"]), ("other", ["P1.2"])):
            doc = copy.deepcopy(design)
            doc.update(id=name, applies_to=scope)
            plan.documents[name] = doc
        before = copy.deepcopy(plan.__dict__)
        with mock.patch.object(store, "load_plan", side_effect=AssertionError("foreign plan loaded")):
            result = query.neighborhood(plan, "P1.1")
        self.assertEqual([d["id"] for d in result["decisions"]], ["D1", "D3", "D4", "D5", "D7"])
        self.assertEqual([d["id"] for d in result["documents"]], ["design", "global", "own", "phase"])
        self.assertEqual(result["documents"][0]["sections"][0]["text"], "я" * 100000)
        result["item"]["title"] = "changed"
        result["decisions"][0]["title"] = "changed"
        result["documents"][0]["sections"][0]["text"] = "changed"
        self.assertEqual(plan.__dict__, before)

    def test_neighborhood_rejects_non_item_and_foreign_roots(self):
        for ref in ("P1", "D1", "knowledge/design", "plan"):
            self.error("REF_INVALID", query.neighborhood, self.plan(), ref)
        self.error("REF_UNKNOWN", query.neighborhood, self.plan(), "P9.9")
        plan = self.plan()
        with mock.patch.object(store, "load_plan", side_effect=AssertionError("foreign plan loaded")):
            self.error("REF_QUALIFIED", query.neighborhood, plan, "PLAN99.P1.1")


class CliAndSchemaTests(LinksCase):
    def test_cli_data_schema_and_no_writes_under_held_lock(self):
        with store.PlanLock(self.root):
            before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
            with mock.patch.object(store.PlanLock, "__enter__", side_effect=AssertionError("read acquired lock")), \
                    mock.patch.object(store, "atomic_write", side_effect=AssertionError("read wrote")):
                for verb, extra, kind in (("links", ["--kind", "decision,consumes", "--direction", "out", "--depth", "2"], "read-links"),
                                          ("neighborhood", [], "read-neighborhood")):
                    code, out, err = test_envelope.run(verb, self.root, "P1.1", *extra)
                    self.assertEqual(code, 0, err or out)
                    result = json.loads(out)
                    self.assertEqual(schema.validate(result, "envelope"), [])
                    self.assertEqual(schema.validate(result["data"], kind), [])
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_cli_refusals_and_usage_errors_are_enveloped(self):
        for argv, code, reason in ((("links", self.root, "P1.1", "--depth", "0"), 1, "DEPTH_INVALID"),
                                   (("links", self.root, "P1.1", "--kind", "wrong"), 1, "KIND_UNKNOWN"),
                                   (("links", self.root, "P99.1"), 1, "REF_UNKNOWN"),
                                   (("neighborhood", self.root, "P1"), 1, "REF_INVALID"),
                                   (("links", self.root, "P1.1", "--direction", "wrong"), 2, "USAGE"),
                                   (("links", self.root, "P1.1", "--depth", "text"), 2, "USAGE"),
                                   (("neighborhood", self.root), 2, "USAGE")):
            with self.subTest(argv=argv):
                status, out, err = test_envelope.run(*argv)
                self.assertEqual(status, code)
                result = json.loads(out)
                self.assertEqual(schema.validate(result, "envelope"), [])
                self.assertEqual(result["error"]["code"], reason)
                self.assertEqual(err, "")

    def test_schemas_reject_unknown_edge_kinds_and_unexpected_fields(self):
        result = query.links(self.plan(), "P1.1")
        result["edges"][0]["kind"] = "not-an-edge"
        self.assertTrue(schema.validate(result, "read-links"))
        result = query.neighborhood(self.plan(), "P1.1")
        result["nodes"][0]["unexpected"] = True
        self.assertTrue(schema.validate(result, "read-neighborhood"))


if __name__ == "__main__":
    unittest.main()
