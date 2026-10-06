"""check(plan): one test per error/warning code, plus 'never raises on a broken plan'."""
import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import check, store  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo

P1 = "phases/P1/"


class CheckCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()
        self.root = demo.make_demo_plan(self.plans)

    def run_check(self):
        return check.check(store.load_plan(self.root))

    def found(self, code, level="error", where=None):
        return [i for i in self.run_check() if i.code == code and i.level == level and (where is None or where in i.where)]

    def assertFound(self, code, where=None, level="error", count=None):
        hits = self.found(code, level, where)
        self.assertTrue(hits, f"no {level} {code} at {where!r}; got {self.run_check()}")
        if count is not None:
            self.assertEqual(len(hits), count, hits)
        return hits

    def edit(self, rel, change):
        demo.rewrite(self.root, rel, change)

    def add_unit(self, unit_id, **changes):
        doc = copy.deepcopy(demo.fixture("unit-e3a-u1"))
        doc.update(id=unit_id, **changes)
        demo.write_doc(self.root / P1 / "P1.1" / f"{unit_id}.json", doc, "unit")

    def list_units(self, *ids):
        self.edit(P1 + "P1.1.json", lambda d: d.update(units=list(ids)))


class BaselineTests(CheckCase):
    def test_demo_plan_has_no_errors(self):
        self.assertEqual([i for i in self.run_check() if i.level == "error"], [])

    def test_demo_plan_warnings_are_only_missing_reads_and_modify_targets(self):
        warnings = {i.code for i in self.run_check() if i.level == "warning"}
        self.assertEqual(warnings, {"read_missing", "modify_missing"})

    def test_issue_shape(self):
        self.edit(P1 + "P1.2.json", lambda d: d.pop("why"))
        issue = self.found("schema")[0]
        self.assertEqual((issue.level, issue.where.split("/")[0]), ("error", "phases"))
        self.assertIsInstance(issue.message, str)

    def test_check_never_raises_on_garbage(self):
        garbage = {"phases": "x", "items": 5, "depends_on": "x", "batches": [1, None, "a"], "units": {"a": 1},
                   "reads": [None, 3, {"path": 5}], "task_files": "x", "result": [], "scope": None, "validation": {},
                   "sections": [None, {"id": []}], "orchestration": ["bad"]}
        for rel in ("plan.json", "brief.json", P1 + "phase.json", P1 + "P1.1.json", P1 + "P1.2.json", "decisions/D1.json"):
            self.edit(rel, lambda d: d.update(copy.deepcopy(garbage)))
        self.add_unit("U1", files="x", depends_on="x", checks=[1, None], outcome=[])
        (self.root / "log.jsonl").write_text("[]\n{\n" + '{"v":1,"type":"start","item":5}\n', encoding="utf-8")
        issues = self.run_check()
        self.assertTrue(any(i.level == "error" for i in issues))


class JsonAndSchemaTests(CheckCase):
    def test_json_unreadable_file_and_missing_file(self):
        (self.root / P1 / "P1.2.json").write_text("{broken", encoding="utf-8")
        (self.root / "brief.json").unlink()
        self.assertFound("json", "phases/P1/P1.2.json")
        self.assertFound("json", "brief.json")

    def test_json_malformed_log_line(self):
        with open(self.root / "log.jsonl", "a", encoding="utf-8") as handle:
            handle.write("not json\n")
        self.assertFound("json", "log.jsonl:5")

    def test_schema_violation_points_into_the_file(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(status="finished"))
        hit = self.assertFound("schema", "phases/P1/P1.2.json/status")[0]
        self.assertIn("one of", hit.message)

    def test_schema_covers_every_document_kind_and_the_log(self):
        self.edit("plan.json", lambda d: d.update(status="x"))
        self.edit("brief.json", lambda d: d.update(messages=[]))
        self.edit(P1 + "phase.json", lambda d: d.update(design="x"))
        self.edit("decisions/D1.json", lambda d: d.update(status="x"))
        self.add_unit("U1", mode="x")
        with open(self.root / "log.jsonl", "a", encoding="utf-8") as handle:
            handle.write('{"v":1,"ts":"2026-10-05T10:00:00Z","type":"gossip","summary":"s","actor":{"provider":"p","model":"m"}}\n')
        for where in ("plan.json/status", "brief.json/messages", "phase.json/design", "D1.json/status", "U1.json/mode",
                      "log.jsonl:5/type"):
            self.assertFound("schema", where)


class IdentityTests(CheckCase):
    def test_id_mismatch_for_plan_item_decision_phase_and_unit(self):
        self.edit("plan.json", lambda d: d.update(id="2026.10.05-№2-OTHER"))
        self.edit(P1 + "P1.2.json", lambda d: d.update(id="P1.3"))
        self.edit("decisions/D2.json", lambda d: d.update(id="D3"))
        self.edit(P1 + "phase.json", lambda d: d.update(id="P2"))
        self.add_unit("U1", item="P1.2")
        for where in ("plan.json/id", "P1.2.json/id", "D2.json/id", "phase.json/id", "U1.json/item"):
            self.assertFound("id_mismatch", where)


class PlanStateTests(CheckCase):
    def test_paused_plan_requires_reason_and_active_plan_cannot_keep_pause(self):
        self.edit("plan.json", lambda d: d.update(status="paused"))
        self.assertFound("plan_state", "plan.json/pause", count=1)
        self.edit("plan.json", lambda d: d.update(pause={"reason": "Wait for PLAN3"}))
        self.assertEqual(self.found("plan_state"), [])
        self.edit("plan.json", lambda d: d.update(status="active"))
        self.assertFound("plan_state", "plan.json/pause", count=1)


class MembershipTests(CheckCase):
    def test_phase_list_mismatch_both_ways(self):
        demo.write_doc(self.root / "phases" / "P2" / "phase.json", {**demo.fixture("phase-e2"), "id": "P2", "items": [], "batches": []}, "phase")
        self.edit("plan.json", lambda d: d.update(phases=["P1", "P3"]))
        hits = self.assertFound("phase_list", count=2)
        self.assertEqual(sorted(re.search(r"P\d+", h.message)[0] for h in hits), ["P2", "P3"])

    def test_phase_items_listed_without_file_and_file_without_listing(self):
        self.edit(P1 + "phase.json", lambda d: d.update(items=["P1.1", "P1.9"]))
        messages = [h.message for h in self.assertFound("phase_items", count=2)]
        self.assertTrue(any("P1.9" in m and "no file" in m for m in messages))
        self.assertTrue(any("P1.2" in m and "not listed" in m for m in messages))

    def test_item_file_in_an_unknown_phase(self):
        demo.write_doc(self.root / P1 / "P7.1.json", {**demo.fixture("item-e3-skeleton"), "id": "P7.1"}, "item")
        self.assertFound("phase_items", "P7.1.json", count=1)


class ReferenceTests(CheckCase):
    def test_unknown_local_refs_are_errors_qualified_refs_are_not(self):
        def change(doc):
            doc.update(depends_on=["P1.9"], decisions=["D9"],
                       related=[{"ref": "P7.1", "relation": "informs"}, {"ref": "PLAN3.P2.1", "relation": "informs"},
                                {"ref": "repo:PLAN3.D4", "relation": "consumes"}])
        self.edit(P1 + "P1.2.json", change)
        wheres = sorted(h.where for h in self.assertFound("ref_unknown", count=3))
        self.assertEqual(wheres, [P1 + "P1.2.json/decisions/0", P1 + "P1.2.json/depends_on/0",
                                  P1 + "P1.2.json/related/0/ref"])

    def test_unknown_phase_dependency_decision_links_and_requirement_owners(self):
        self.edit(P1 + "phase.json", lambda d: d.update(depends_on=["P9"]))
        self.edit("decisions/D1.json", lambda d: d.update(applies_to=["P1.9"], supersedes=["D8"], superseded_by="D7"))
        self.edit("brief.json", lambda d: d["requirements"][0].update(owners=["P4.4"]))
        for where in ("phase.json/depends_on/0", "D1.json/applies_to/0", "D1.json/supersedes/0", "D1.json/superseded_by",
                      "brief.json/requirements/0/owners/0"):
            self.assertFound("ref_unknown", where)

    def test_result_decision_must_exist(self):
        self.edit(P1 + "P1.1.json", lambda d: d["result"].update(decision="D9"))
        self.assertFound("ref_unknown", "P1.1.json/result/decision")

    def test_unit_dependency_and_check_references(self):
        self.list_units("U1")
        self.add_unit("U1", depends_on=["U5"], checks=["V1", "V9"])
        self.assertFound("ref_unknown", "U1.json/depends_on/0")
        self.assertFound("ref_unknown", "U1.json/checks/1", count=1)

    def test_new_ref_kinds_must_resolve(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            related=[{"ref": "knowledge/none", "relation": "informs"}, {"ref": "knowledge/none#s", "relation": "informs"},
                     {"ref": "artifact/none", "relation": "informs"}, {"ref": "P1.1/U9", "relation": "informs"}]))
        self.assertFound("ref_unknown", "P1.2.json/related/0/ref")
        self.assertFound("ref_unknown", "P1.2.json/related/1/ref")
        self.assertFound("ref_unknown", "P1.2.json/related/2/ref")
        self.assertFound("ref_unknown", "P1.2.json/related/3/ref")

    def test_ref_to_an_existing_knowledge_section_unit_and_artifact_is_fine(self):
        self.list_units("U1")
        self.add_unit("U1")
        demo.write_doc(self.root / "knowledge" / "design.json",
                       {"$schema": "urn:swissknifeman:task:plan:document:v1", "id": "design", "title": "D",
                        "sections": [{"id": "validation", "title": "V", "text": "t"}]}, "document")
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            related=[{"ref": "knowledge/design#validation", "relation": "informs"},
                     {"ref": "P1.1/U1", "relation": "informs"}, {"ref": "artifact/catalog", "relation": "consumes"}]))
        self.edit(P1 + "P1.1.json", lambda d: d.update(artifacts=[{"id": "catalog", "path": "a.json", "role": "output"}]))
        self.assertEqual(self.found("ref_unknown"), [])
        self.assertEqual(self.found("ref_kind"), [])

    def test_a_field_takes_only_its_ref_kinds(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(decisions=["P1.1"]))
        self.edit("decisions/D1.json", lambda d: d.update(applies_to=["D2"]))
        self.edit(P1 + "P1.1.json", lambda d: d["result"].update(decision="P1.2"))
        for where in ("P1.2.json/decisions/0", "D1.json/applies_to/0", "P1.1.json/result/decision"):
            self.assertFound("ref_kind", where, count=1)

    def test_qualified_refs_of_the_wrong_kind_are_still_refused(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(decisions=["PLAN3.P2.1"]))
        self.assertFound("ref_kind", "P1.2.json/decisions/0")

    def test_supersede_pointers_must_match_both_ways(self):
        self.edit("decisions/D1.json", lambda d: d.update(superseded_by="D2"))  # D2 does not list D1
        self.assertFound("backlink_mismatch", "D1.json/superseded_by", count=1)
        self.edit("decisions/D1.json", lambda d: d.update(superseded_by=None))
        self.edit("decisions/D2.json", lambda d: d.update(supersedes=["D1"]))  # D1 does not name D2
        self.assertFound("backlink_mismatch", "D2.json/supersedes/0", count=1)
        self.edit("decisions/D1.json", lambda d: d.update(superseded_by="D2"))
        self.assertEqual(self.found("backlink_mismatch"), [])

    def test_unit_parent_is_reported_once_as_unit_parent(self):
        self.list_units("U1")
        self.add_unit("U1", parent="U7")
        self.assertFound("unit_parent", count=1)
        self.assertEqual(self.found("ref_unknown", where="U1.json/parent"), [])

    def test_artifact_ids_are_declared_once_and_inputs_name_the_declared_path(self):
        out = {"id": "catalog", "path": "a.json", "role": "output"}
        self.edit(P1 + "P1.1.json", lambda d: d.update(artifacts=[out]))
        self.edit(P1 + "P1.2.json", lambda d: d.update(artifacts=[{**out, "path": "b.json"}]))
        self.assertFound("artifact_duplicate", "P1.2.json/artifacts/0/id", count=1)
        self.edit(P1 + "P1.2.json", lambda d: d.update(artifacts=[{**out, "path": "b.json", "role": "input"}]))
        self.assertEqual(self.found("artifact_duplicate"), [])
        self.assertFound("artifact_path", "P1.2.json/artifacts/0/id", count=1)
        self.edit(P1 + "P1.2.json", lambda d: d.update(artifacts=[{**out, "role": "input"}]))
        self.assertEqual(self.found("artifact_path") + self.found("ref_unknown"), [])

    def test_an_input_artifact_without_an_output_is_unknown(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(artifacts=[{"id": "ghost", "path": "a.json", "role": "input"}]))
        self.assertFound("ref_unknown", "P1.2.json/artifacts/0/id", count=1)

    def test_read_refs_resolve_and_stay_local_with_one_section(self):
        reads = [{"ref": "knowledge/none", "why": "w", "required": False},
                 {"ref": "PLAN3.D1", "why": "w", "required": False}]
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=reads))
        self.assertFound("ref_unknown", "P1.2.json/reads/0/ref", count=1)
        self.assertFound("reads_ref", "P1.2.json/reads/1/ref", count=1)
        demo.write_doc(self.root / "knowledge" / "design.json",
                       {"$schema": "urn:swissknifeman:task:plan:document:v1", "id": "design", "title": "D",
                        "sections": [{"id": "validation", "title": "V", "text": "t"}]}, "document")
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            reads=[{"ref": "knowledge/design#validation", "section": "validation", "why": "w", "required": True}]))
        self.assertFound("reads_ref", "P1.2.json/reads/0/section", count=1)

    def test_read_ref_section_key_must_name_an_existing_id_or_title(self):
        demo.write_doc(self.root / "knowledge" / "design.json",
                       {"$schema": "urn:swissknifeman:task:plan:document:v1", "id": "design", "title": "D",
                        "sections": [{"id": "validation", "title": "Validation", "text": "t"}]}, "document")
        for section in ("validation", "Validation", "missing"):
            with self.subTest(section=section):
                self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[
                    {"ref": "knowledge/design", "section": section, "why": "w", "required": True}]))
                if section == "missing":
                    self.assertFound("ref_unknown", "P1.2.json/reads/0/section", count=1)
                else:
                    self.assertEqual(self.found("ref_unknown"), [])

    def test_log_events_must_point_at_existing_items_and_phases(self):
        with open(self.root / "log.jsonl", "a", encoding="utf-8") as handle:
            handle.write('{"v":1,"ts":"2026-10-05T10:00:00Z","type":"note","item":"P1.7","phase":"P5","actor":{"provider":"p","model":"m"},"summary":"s"}\n')
        self.assertFound("ref_unknown", "log.jsonl:5/item")
        self.assertFound("ref_unknown", "log.jsonl:5/phase")


class CycleTests(CheckCase):
    def test_item_cycle(self):
        self.edit(P1 + "P1.1.json", lambda d: d.update(depends_on=["P1.2"]))
        hit = self.assertFound("cycle", count=1)[0]
        self.assertIn("P1.1", hit.message)
        self.assertIn("P1.2", hit.message)

    def test_item_self_dependency_is_a_cycle(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(depends_on=["P1.2"]))
        self.assertFound("cycle")

    def test_multi_item_import_cycle_is_reported_once(self):
        third = copy.deepcopy(demo.fixture("item-e3"))
        third.update(id="P1.3", title="Third", status="todo", depends_on=["P1.1"], result=None)
        demo.write_doc(self.root / P1 / "P1.3.json", third, "item")
        self.edit(P1 + "phase.json", lambda d: (d["items"].append("P1.3"), d["batches"].append(
            {"id": "B3", "items": ["P1.3"], "mode": "recommended"})))
        self.edit(P1 + "P1.1.json", lambda d: d.update(depends_on=["P1.2"]))
        self.edit(P1 + "P1.2.json", lambda d: d.update(depends_on=["P1.3"]))
        hit = self.assertFound("cycle", count=1)[0]
        self.assertIn("P1.1 -> P1.2 -> P1.3 -> P1.1", hit.message)

    def test_phase_cycle_through_the_default_previous_phase_edge(self):
        demo.write_doc(self.root / "phases" / "P2" / "phase.json", {**demo.fixture("phase-e2"), "id": "P2", "items": [], "batches": []}, "phase")
        self.edit("plan.json", lambda d: d.update(phases=["P1", "P2"]))
        self.assertEqual(self.found("cycle"), [])
        self.edit(P1 + "phase.json", lambda d: d.update(depends_on=["P2"]))  # P2 defaults to depend on P1
        hit = self.assertFound("cycle", count=1)[0]
        self.assertIn("phase dependency cycle", hit.message)

    def test_unit_cycle(self):
        self.list_units("U1", "U2")
        self.add_unit("U1", depends_on=["U2"], files=["a.py"])
        self.add_unit("U2", depends_on=["U1"], files=["b.py"])
        hit = self.assertFound("cycle", count=1)[0]
        self.assertIn("unit dependency cycle", hit.message)


class BatchTests(CheckCase):
    def test_item_in_no_batch_or_in_two_batches(self):
        self.edit(P1 + "phase.json", lambda d: d.update(batches=[{"id": "B1", "items": ["P1.1"], "mode": "recommended"},
                                                                 {"id": "B2", "items": ["P1.1"], "mode": "recommended"}]))
        messages = sorted(h.message for h in self.assertFound("batch_coverage", count=2))
        self.assertTrue(any("P1.1 is in 2 batches (B1, B2)" in m for m in messages))
        self.assertTrue(any("P1.2 is in 0 batches" in m for m in messages))

    def test_batch_item_from_another_phase_or_not_in_the_phase(self):
        self.edit(P1 + "phase.json", lambda d: d["batches"][0].update(items=["P1.1", "P1.2", "P2.1", "P1.8"]))
        self.assertFound("batch_foreign", count=2)

    def test_duplicate_batch_id(self):
        self.edit(P1 + "phase.json", lambda d: d.update(batches=[{"id": "B1", "items": ["P1.1"], "mode": "recommended"},
                                                                 {"id": "B1", "items": ["P1.2"], "mode": "recommended"}]))
        self.assertFound("batch_id", "phase.json/batches/1/id")
        self.assertEqual(self.found("batch_coverage"), [])


class CompletenessTests(CheckCase):
    def test_detailed_phase_requires_the_listed_fields(self):
        def strip(doc):
            for field in ("deliverables", "reads", "task_files", "validation", "guidance", "sections"):
                doc.pop(field, None)
            doc["scope"]["include"] = []
        self.edit(P1 + "P1.2.json", strip)
        wheres = {h.where.split("P1.2.json/")[1] for h in self.found("incomplete")}
        self.assertEqual(wheres, {"scope/include", "validation", "deliverables", "reads"})

    def test_validation_needs_an_acceptance_check(self):
        self.edit(P1 + "P1.2.json", lambda d: d["validation"][0].update(kind="impact"))
        self.assertFound("incomplete", "P1.2.json/validation", count=1)

    def test_reads_or_task_files_is_enough(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[]))
        self.assertEqual(self.found("incomplete"), [])

    def test_skeleton_phase_may_hold_placeholder_items(self):
        self.edit(P1 + "phase.json", lambda d: d.update(design="skeleton"))
        self.edit(P1 + "P1.2.json", lambda d: d.update(summary="Outcome placeholder", validation=[], deliverables=[], reads=[], task_files=[]))
        self.assertEqual(self.found("incomplete"), [])

    def test_validation_has_exactly_one_command_or_procedure(self):
        self.edit(P1 + "P1.2.json", lambda d: d["validation"][0].update(procedure="Inspect the owner packet"))
        self.assertFound("validation_carrier", "P1.2.json/validation/0", count=1)
        self.edit(P1 + "P1.2.json", lambda d: (d["validation"][0].pop("cmd"),
                                                d["validation"][0].pop("procedure")))
        self.assertFound("validation_carrier", "P1.2.json/validation/0", count=1)


class AuthorityTests(CheckCase):
    def test_source_label_is_a_gate_identity_and_scope_is_required(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            authority={"kind": "owner_gate", "label": "Запускай P1.2", "scope": "Exact source instruction"}))
        self.assertEqual(self.found("authority_identity"), [])
        self.assertEqual(self.found("authority_scope"), [])
        self.edit(P1 + "P1.2.json", lambda d: d.update(authority={"kind": "owner_gate"}))
        self.assertFound("authority_identity", "P1.2.json/authority", count=1)
        self.assertFound("authority_scope", "P1.2.json/authority/scope", count=1)

    def test_external_gate_needs_a_traceable_identity_and_scope(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            authority={"kind": "external_gate", "label": "owning package receipt",
                       "scope": "The owning repository must publish the immutable receipt."}))
        self.assertEqual(self.found("authority_identity"), [])
        self.assertEqual(self.found("authority_scope"), [])
        self.edit(P1 + "P1.2.json", lambda d: d.update(authority={"kind": "external_gate"}))
        self.assertFound("authority_identity", "P1.2.json/authority", count=1)
        self.assertFound("authority_scope", "P1.2.json/authority/scope", count=1)


class DecisionTests(CheckCase):
    def test_open_needs_question_accepted_and_proposed_need_decision_and_rationale(self):
        self.edit("decisions/D2.json", lambda d: d.pop("question"))
        self.edit("decisions/D1.json", lambda d: (d.pop("decision"), d.pop("rationale")))
        self.assertFound("decision_fields", "D2.json/question", count=1)
        self.assertFound("decision_fields", "D1.json/decision", count=1)
        self.assertFound("decision_fields", "D1.json/rationale", count=1)
        self.edit("decisions/D1.json", lambda d: d.update(status="proposed"))
        self.assertFound("decision_fields", "D1.json/decision", count=1)
        self.assertFound("decision_fields", "D1.json/rationale", count=1)

    def test_rejected_and_superseded_need_nothing_extra(self):
        self.edit("decisions/D2.json", lambda d: (d.pop("question"), d.update(status="rejected")))
        self.assertEqual(self.found("decision_fields"), [])


class PathTests(CheckCase):
    def test_parent_segments_absolute_drive_and_home_paths_are_errors(self):
        def change(doc):
            doc["reads"] = [{"path": "../outside.py", "why": "w", "required": False},
                            {"path": "lib/../../x", "why": "w", "required": False},
                            {"path": "C:\\Users\\x", "why": "w", "required": False},
                            {"path": "~/secret", "why": "w", "required": False},
                            {"path": "@plan/../x", "why": "w", "required": False}]
            doc["task_files"] = [{"path": "a/../b", "change": "any"}]
        self.edit(P1 + "P1.2.json", change)
        self.assertEqual(len(self.found("path", where="P1.2.json/reads")), 5)
        self.assertFound("path", "P1.2.json/task_files/0/path", count=1)

    def test_unit_and_phase_paths_are_checked_too(self):
        self.list_units("U1")
        self.add_unit("U1", files=["ok.py", "../bad.py"])
        self.edit(P1 + "phase.json", lambda d: d.update(supporting=["../dossier.md"], validation=[
            {"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance", "cwd": "../x"}]))
        self.assertFound("path", "U1.json/files/1", count=1)
        self.assertFound("path", "phase.json/supporting/0", count=1)
        self.assertFound("path", "phase.json/validation/0/cwd", count=1)

    def test_globs_and_plan_relative_paths_are_fine(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(task_files=[{"path": "lib/**/*.py", "change": "any"},
                                                                    {"path": "@plan/research/x.md", "change": "create"}]))
        self.assertEqual(self.found("path"), [])


class ResultStatusTests(CheckCase):
    def test_done_needs_finished_at_in_progress_needs_started_at_skipped_needs_decision(self):
        self.edit(P1 + "P1.1.json", lambda d: d["result"].pop("finished_at"))
        self.edit(P1 + "P1.2.json", lambda d: d.update(status="in_progress", result=None))
        self.assertFound("result_status", "P1.1.json/result")
        self.assertFound("result_status", "P1.2.json/result")
        self.edit(P1 + "P1.2.json", lambda d: d.update(status="skipped", result={"notes": "n"}))
        hit = self.assertFound("result_status", "P1.2.json/result", count=1)[0]
        self.assertIn("result.decision", hit.message)

    def test_done_with_deviations_and_consistent_results_pass(self):
        self.edit(P1 + "P1.1.json", lambda d: d.update(status="done_with_deviations"))
        self.edit(P1 + "P1.2.json", lambda d: d.update(status="in_progress", result={"started_at": "2026-10-05T11:00:00Z"}))
        self.assertEqual(self.found("result_status"), [])
        self.edit(P1 + "P1.1.json", lambda d: d["result"].pop("finished_at"))
        self.assertFound("result_status", "P1.1.json/result")

    def test_skipped_with_decision_passes(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(status="skipped", result={"decision": "D1"}))
        self.assertEqual(self.found("result_status"), [])


class UnitTests(CheckCase):
    def test_units_list_mismatch_both_ways_and_orphan_workspace(self):
        self.list_units("U1", "U2")
        self.add_unit("U1")
        self.add_unit("U3", files=["c.py"])
        orphan = copy.deepcopy(demo.fixture("unit-e3a-u1"))
        orphan.update(item="P1.2")
        demo.write_doc(self.root / P1 / "P1.7" / "U1.json", orphan, "unit")
        messages = [h.message for h in self.assertFound("units_list", count=3)]
        self.assertTrue(any("U2 is listed but has no file" in m for m in messages))
        self.assertTrue(any("P1.1/U3 is not listed" in m for m in messages))
        self.assertTrue(any("P1.7 has no item file" in m for m in messages))

    def test_independent_units_must_own_disjoint_files(self):
        self.list_units("U1", "U2")
        self.add_unit("U1", files=["lib/pkg/a.py"])
        self.add_unit("U2", files=["lib/pkg/*.py"])
        self.assertFound("unit_overlap", count=1)

    def test_directory_prefix_counts_as_overlap(self):
        self.list_units("U1", "U2")
        self.add_unit("U1", files=["lib/pkg"])
        self.add_unit("U2", files=["lib/pkg/deep/x.py"])
        self.assertFound("unit_overlap", count=1)

    def test_dependent_or_disjoint_units_may_share_nothing_to_report(self):
        self.list_units("U1", "U2", "U3")
        self.add_unit("U1", files=["lib/a.py"])
        self.add_unit("U2", files=["lib/a.py"], depends_on=["U1"])        # ordered: may touch the same file
        self.add_unit("U3", files=["docs/guide.md"])                     # disjoint from both
        self.assertEqual(self.found("unit_overlap"), [])

    def test_transitive_dependency_orders_units(self):
        self.list_units("U1", "U2", "U3")
        self.add_unit("U1", files=["lib/a.py"])
        self.add_unit("U2", files=["lib/b.py"], depends_on=["U1"])
        self.add_unit("U3", files=["lib/a.py"], depends_on=["U2"])
        self.assertEqual(self.found("unit_overlap"), [])

    def test_unit_files_outside_task_files_warn(self):
        self.list_units("U1")
        self.add_unit("U1", files=["lib/pkg/config.py", "somewhere/else.py"])
        self.assertFound("unit_files_uncovered", "U1.json/files/1", level="warning", count=1)

    def test_item_without_task_files_has_no_coverage_to_warn_about(self):
        self.edit(P1 + "P1.1.json", lambda d: d.pop("task_files"))
        self.list_units("U1")
        self.add_unit("U1", files=["anything.py"])
        self.assertEqual(self.found("unit_files_uncovered", level="warning"), [])


class GlobOverlapTests(unittest.TestCase):
    def test_table(self):
        cases = [("a.py", "a.py", True), ("a.py", "b.py", False), ("lib/*.py", "lib/a.py", True),
                 ("lib/a.py", "docs/a.py", False), ("lib", "lib/x/y.py", True), ("lib/**", "lib/x/y.py", True),
                 ("lib/a/*.py", "lib/b/*.py", False), ("*.md", "*.py", False), ("*", "x", True),
                 ("lib/[ab].py", "lib/a.py", True), ("src/x", "tests/x", False)]
        for a, b, expected in cases:
            with self.subTest(a=a, b=b):
                self.assertIs(check.globs_overlap(a, b), expected)
                self.assertIs(check.globs_overlap(b, a), expected)


class LogTargetTests(CheckCase):
    def test_lifecycle_and_friction_events_need_item_or_phase(self):
        actor = '{"provider":"p","model":"m"}'
        with open(self.root / "log.jsonl", "a", encoding="utf-8") as handle:
            handle.write(f'{{"v":1,"ts":"2026-10-05T10:00:00Z","type":"start","actor":{actor},"summary":"s"}}\n')
            handle.write(f'{{"v":1,"ts":"2026-10-05T10:00:00Z","type":"note","actor":{actor},"summary":"plan-level note ok"}}\n')
            handle.write(f'{{"v":1,"ts":"2026-10-05T10:00:00Z","type":"blocker","phase":"P1","actor":{actor},"summary":"s"}}\n')
        self.assertFound("log_target", "log.jsonl:5", count=1)
        self.assertEqual(self.found("ref_unknown"), [])


class AdvisoryTests(CheckCase):
    def test_context_equal_to_title_warns(self):
        self.edit("plan.json", lambda d: d.update(context=d["title"], goal=d["title"]))
        self.assertFound("context_default", "plan.json/context", level="warning", count=1)
        self.assertFound("context_default", "plan.json/goal", level="warning", count=1)

    def test_required_read_missing_warns_until_it_exists_or_a_dependency_produces_it(self):
        warn = lambda: [h.where for h in self.found("read_missing", level="warning") if "P1.2" in h.where]  # noqa: E731
        self.assertEqual(len(warn()), 1)  # config.py is a dependency task_file; knowledge is not produced yet
        (self.root.parents[1] / "lib" / "pkg").mkdir(parents=True)
        (self.root.parents[1] / "lib" / "pkg" / "config.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(len(warn()), 1)
        self.edit(P1 + "P1.1.json", lambda d: d["artifacts"].append(
            {"path": "@plan/knowledge/design.json", "role": "output"}))
        self.assertEqual(warn(), [])  # produced by a dependency (P1.1) even though not on disk yet
        (self.root / "research").mkdir()
        (self.root / "research" / "00-design.md").write_text("# d\n", encoding="utf-8")
        self.assertEqual(warn(), [])

    def test_dependency_task_files_and_output_directories_satisfy_future_reads(self):
        self.edit(P1 + "P1.1.json", lambda d: d.update(task_files=[
            {"path": "@plan/artifacts/future/", "change": "create"}]))
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[
            {"path": "@plan/artifacts/future/manifest.json", "why": "producer output", "required": True}]))
        self.assertEqual([h for h in self.found("read_missing", level="warning") if "P1.2" in h.where], [])

    def test_missing_required_read_waits_until_item_dependencies_are_terminal(self):
        self.edit(P1 + "P1.1.json", lambda d: d.update(status="todo", result=None))
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[
            {"path": "future/input.json", "why": "needed after the producer is complete", "required": True}]))
        self.assertEqual([h for h in self.found("read_missing", level="warning") if "P1.2" in h.where], [])
        self.edit(P1 + "P1.1.json", lambda d: d.update(
            status="done", result={"started_at": "2026-10-05T10:00:00Z",
                                   "finished_at": "2026-10-05T10:01:00Z",
                                   "executor": {"provider": "p", "model": "m"},
                                   "notes": "done", "checks": [], "deviations": [], "pending": []}))
        self.assertEqual(len([h for h in self.found("read_missing", level="warning") if "P1.2" in h.where]), 1)

    def test_brace_expansion_read_is_treated_as_a_pattern(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[
            {"path": "app/{main,config}.py", "why": "two source inputs", "required": True}]))
        self.assertEqual([h for h in self.found("read_missing", level="warning") if "P1.2" in h.where], [])

    def test_terminal_item_does_not_warn_about_a_retired_historical_read(self):
        self.edit(P1 + "P1.1.json", lambda d: d.update(reads=[
            {"path": "retired/source.py", "why": "historical execution input", "required": True}]))
        self.assertEqual([h for h in self.found("read_missing", level="warning") if "P1.1" in h.where], [])

    def test_external_gate_does_not_warn_about_reads_owned_outside_the_plan(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(
            authority={"kind": "external_gate", "label": "owning repository receipt",
                       "scope": "The owning repository controls these inputs."},
            reads=[{"path": "other-project/receipt.json", "why": "external evidence", "required": True}]))
        self.assertEqual([h for h in self.found("read_missing", level="warning") if "P1.2" in h.where], [])

    def test_optional_reads_and_globs_do_not_warn(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[
            {"path": "nowhere/optional.py", "why": "w", "required": False},
            {"path": "nowhere/**/*.py", "why": "w", "required": True}], task_files=[]))
        self.assertEqual([h for h in self.found("read_missing", level="warning") if "P1.2" in h.where], [])

    def test_modify_target_missing_warns_create_and_globs_do_not(self):
        self.edit(P1 + "P1.2.json", lambda d: d.update(reads=[], task_files=[
            {"path": "lib/pkg/gone.py", "change": "modify"}, {"path": "lib/pkg/new.py", "change": "create"},
            {"path": "lib/**/*.py", "change": "modify"}]))
        hits = [h for h in self.found("modify_missing", level="warning") if "P1.2" in h.where]
        self.assertEqual([h.where.rsplit("/", 2)[-2] for h in hits], ["0"])


if __name__ == "__main__":
    unittest.main()
