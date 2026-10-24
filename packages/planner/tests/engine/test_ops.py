"""Authoring ops: numbering, new_plan, add_*, merge patch, push, batches, FIELD_OWNED, refusals."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import PlanError, check, ops, schema, store, views  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo

AUTHORING = demo.AUTHORING


def errors(plan):
    return [i for i in check.check(plan) if i.level == "error"]


class RootCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()

    def new(self, codename="DEMO", title="Demo", **kwargs):
        kwargs.setdefault("date", "2026.10.05")
        return ops.new_plan(codename, title, plans_root=self.plans, repository="demo", owner="repository owner",
                            authoring=AUTHORING, message="Make config errors aggregate.", **kwargs)


class DemoCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plans = Path(tmp.name) / "plans"
        self.plans.mkdir()
        self.root = demo.make_demo_plan(self.plans)
        self.plan = store.load_plan(self.root)

    def snapshot(self):
        # `.lock` is the empty gitignored lock file; it appears with the first mutation by design.
        return {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob("*"))
                if p.is_file() and p.name != store.LOCK}

    def complete_item_data(self):
        return {k: v for k, v in self.plan.items["P1.2"].items() if k not in ops.OWNED_FIELDS["item"]}

    def assertRefused(self, code, call, *args, **kwargs):
        before = self.snapshot()
        with self.assertRaises(PlanError) as ctx:
            call(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code, str(ctx.exception))
        self.assertEqual(self.snapshot(), before, "a refused mutation must leave every file byte-identical")
        return ctx.exception


class ReadinessOwnershipTests(DemoCase):
    def test_set_push_and_apply_cannot_write_readiness(self):
        self.assertRefused("FIELD_OWNED", ops.patch, self.root, "P1", {"readiness": None})
        self.assertRefused("FIELD_OWNED", ops.push, self.root, "P1", "readiness.findings", {})
        self.assertRefused("FIELD_OWNED", ops.apply, self.root,
                           [{"ref": "P1", "patch": {"readiness": {"status": "ready"}}}])


class NewPlanTests(RootCase):
    def test_allocates_ordinal_and_short_id(self):
        first = self.new("DEMO", "Demo")
        self.assertEqual(first.plan["id"], "2026.10.05-№1-DEMO")
        self.assertEqual(first.plan["short_id"], "PLAN1")
        self.assertEqual(first.plan["title"], "Plan №1 — Demo")
        second = self.new("OTHER", "Other")
        self.assertEqual((second.plan["id"], second.plan["short_id"]), ("2026.10.05-№2-OTHER", "PLAN2"))
        later = self.new("LATER", "Later", date="2026.10.06")
        self.assertEqual((later.plan["id"], later.plan["short_id"]), ("2026.10.06-№1-LATER", "PLAN3"))

    def test_numbering_counts_plan_json_in_live_and_archive(self):
        archived = self.plans / "archive" / "2026.09.01-№1-ARCH"
        archived.mkdir(parents=True)
        (archived / "plan.json").write_text(json.dumps({"short_id": "PLAN20"}), encoding="utf-8")
        live = self.plans / "2026.10.05-№5-OLD"
        live.mkdir()
        (live / "plan.json").write_text(json.dumps({"short_id": "PLAN9"}), encoding="utf-8")
        plan = self.new("NEXT", "Next")
        self.assertEqual((plan.plan["id"], plan.plan["short_id"]), ("2026.10.05-№6-NEXT", "PLAN21"))

    def test_creates_plan_brief_gitignore_and_log(self):
        plan = self.new(channel="chat")
        root = plan.root
        source = {".gitattributes", ".gitignore", ".lock", "brief.json", "log.jsonl", "plan.json"}
        self.assertEqual({p.name for p in root.iterdir()}, source | {"views", ".ignore", ".cursorignore"})
        self.assertEqual(views.render_all(plan, check=True), [])
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "context/\n.lock\nviews/\n")
        self.assertEqual((root / ".gitattributes").read_text(encoding="utf-8"), "log.jsonl merge=union\n")
        self.assertEqual(plan.brief["messages"], [{"id": "M1", "date": "2026-10-05",
                                                    "text": "Make config errors aggregate.", "channel": "chat"}])
        events = store.read_log(root)
        self.assertEqual([e["type"] for e in events], ["plan_created"])
        self.assertEqual(plan.plan["created"], "2026-10-05")
        self.assertEqual(plan.plan["settings"], {"design_audit": "none", "scout": "off", "context_pack": "scoped"})
        self.assertEqual((root / "plan.json").read_text(encoding="utf-8"), store.canonical_dump(plan.plan, "plan"))
        self.assertEqual(errors(plan), [])
        warnings = sorted(i.where for i in check.check(plan) if i.level == "warning")
        self.assertEqual(warnings, ["plan.json/context", "plan.json/goal"])

    def test_title_prefix_is_kept_when_already_present(self):
        plan = self.new("DEMO", "Plan №7 — Custom")
        self.assertEqual(plan.plan["title"], "Plan №7 — Custom")

    def test_first_owner_message_is_required(self):
        for message in ("", "   ", None):
            with self.assertRaises(PlanError) as ctx:
                ops.new_plan("DEMO", "Demo", plans_root=self.plans, repository="r", owner="o",
                             authoring=AUTHORING, message=message, date="2026.10.05")
            self.assertEqual(ctx.exception.code, "MESSAGE_REQUIRED")
        self.assertEqual(list(self.plans.iterdir()), [])

    def test_invalid_input_creates_nothing(self):
        for kwargs, code in (({"authoring": {"provider": "x"}}, "SCHEMA_INVALID"),
                             ({"codename": "lower"}, "PLAN_CODENAME_INVALID"),
                             ({"codename": None}, "PLAN_CODENAME_INVALID"),
                             ({"date": "05.10.2026"}, "PLAN_DATE_INVALID")):
            with self.subTest(code=code, kwargs=kwargs):
                args = {"codename": "DEMO", "title": "Demo", "plans_root": self.plans, "repository": "r",
                        "owner": "o", "authoring": AUTHORING, "message": "m", "date": "2026.10.05", **kwargs}
                with self.assertRaises(PlanError) as ctx:
                    ops.new_plan(args.pop("codename"), args.pop("title"), **args)
                self.assertEqual(ctx.exception.code, code)
                self.assertEqual(list(self.plans.iterdir()), [])

    def test_codename_is_required_and_validated(self):
        for codename in (None, "lower", "1X", ""):
            with self.subTest(codename=codename):
                with self.assertRaises(PlanError) as ctx:
                    ops.new_plan(codename, "t", plans_root=self.plans, repository="r", owner="o",
                                 authoring=AUTHORING, message="m")
                self.assertEqual(ctx.exception.code, "PLAN_CODENAME_INVALID")


class AddTests(DemoCase):
    def setUp(self):
        super().setUp()
        # These tests exercise drafting; adding placeholders to a detailed phase has its own refusal tests.
        demo.rewrite(self.root, "phases/P1/phase.json", lambda d: d.update(design="skeleton"))

    def test_add_phase_numbers_and_registers_the_phase(self):
        self.assertEqual(ops.add_phase(self.plan, "Second"), "P2")
        self.assertEqual(ops.add_phase(self.plan, "Third", data={"goal": "Third goal"}), "P3")
        self.assertEqual(self.plan.plan["phases"], ["P1", "P2", "P3"])
        doc = store.load_plan(self.root).phases["P3"]
        self.assertEqual((doc["design"], doc["goal"], doc["items"], doc["batches"]), ("skeleton", "Third goal", [], []))
        self.assertEqual(errors(store.load_plan(self.root)), [])

    def test_add_phase_refuses_owned_fields(self):
        self.assertRefused("FIELD_OWNED", ops.add_phase, self.plan, "Owned", data={"design": "detailed"})

    def test_add_item_numbers_without_reusing_ids_and_gets_a_solo_batch(self):
        (self.root / "phases" / "P1" / "P1.2.json").unlink()  # file gone, phase.items still lists it
        item_id = ops.add_item(self.plan, "P1", "Third item")
        self.assertEqual(item_id, "P1.3")
        phase = store.load_plan(self.root).phases["P1"]
        self.assertEqual(phase["items"], ["P1.1", "P1.2", "P1.3"])
        self.assertEqual(phase["batches"][-1], {"id": "BP1-3", "items": ["P1.3"], "mode": "recommended"})
        item = store.load_plan(self.root).items["P1.3"]
        self.assertEqual((item["status"], item["result"], item["route"]),
                         ("todo", None, {"class": "implementation", "effort": "high"}))

    def test_add_item_joins_an_existing_batch_or_creates_the_named_one(self):
        first = ops.add_item(self.plan, "P1", "Joins B1", batch="B1")
        second = ops.add_item(self.plan, "P1", "Own batch", batch="B9")
        phase = store.load_plan(self.root).phases["P1"]
        self.assertEqual(phase["batches"][0]["items"], ["P1.1", "P1.2", first])
        self.assertEqual(phase["batches"][-1], {"id": "B9", "items": [second], "mode": "recommended"})
        self.assertEqual([i for i in errors(store.load_plan(self.root)) if i.code.startswith("batch")], [])

    def test_add_item_takes_stable_fields_from_data(self):
        item_id = ops.add_item(self.plan, "P1", "Rich", data={"summary": "Does a thing", "route": {"class": "frontier", "effort": "xhigh"},
                                                              "rules": ["be careful"]})
        item = store.load_plan(self.root).items[item_id]
        self.assertEqual((item["summary"], item["route"]["class"], item["rules"]), ("Does a thing", "frontier", ["be careful"]))

    def test_add_item_refusals(self):
        self.assertRefused("REF_UNKNOWN", ops.add_item, self.plan, "P9", "Nowhere")
        self.assertRefused("FIELD_OWNED", ops.add_item, self.plan, "P1", "Owned", data={"status": "done"})
        self.assertRefused("FIELD_OWNED", ops.add_item, self.plan, "P1", "Owned", data={"result": None})
        self.assertRefused("SCHEMA_INVALID", ops.add_item, self.plan, "P1", "Bad", data={"route": {"class": "huge"}})

    def test_add_decision_numbers_after_the_maximum_and_defaults_to_open(self):
        self.assertEqual(ops.add_decision(self.plan, "Pick a format"), "D3")
        doc = store.load_plan(self.root).decisions["D3"]
        self.assertEqual((doc["status"], doc["question"], doc["actor"]), ("open", "Pick a format", AUTHORING))
        (self.root / "decisions" / "D2.json").unlink()
        self.assertEqual(ops.add_decision(self.plan, "Another"), "D4")  # gaps are never refilled

    def test_add_decision_can_record_an_accepted_decision(self):
        decision_id = ops.add_decision(self.plan, "Use JSON", data={"status": "accepted", "decision": "JSON only",
                                                                    "rationale": "diffable"}, actor={"provider": "codex", "model": "gpt-6-sol"})
        doc = store.load_plan(self.root).decisions[decision_id]
        self.assertEqual((doc["status"], doc["actor"]["provider"]), ("accepted", "codex"))
        self.assertNotIn("question", doc)
        self.assertEqual(errors(store.load_plan(self.root)), [])


class DetailedPhaseTests(DemoCase):
    def test_batches_refuse_new_detailed_errors_but_allow_repair(self):
        bad = [{"id": name, "items": ["P1.2"], "mode": "recommended"} for name in ("B1", "B2")]
        error = self.assertRefused("PLAN_INVALID", ops.set_batches, self.plan, "P1", bad)
        self.assertTrue(any(issue.code == "batch_coverage" for issue in error.issues))
        demo.rewrite(self.root, "phases/P1/phase.json", lambda doc: doc.update(batches=bad))
        ops.set_batches(self.plan, "P1", [{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended"}])
        self.assertEqual(errors(store.load_plan(self.root)), [])

    def test_batches_remain_editable_while_the_phase_is_a_skeleton(self):
        demo.rewrite(self.root, "phases/P1/phase.json", lambda doc: doc.update(design="skeleton"))
        bad = [{"id": name, "items": ["P1.2"], "mode": "recommended"} for name in ("B1", "B2")]
        ops.set_batches(self.plan, "P1", bad)
        self.assertTrue(any(issue.code == "batch_coverage" for issue in errors(store.load_plan(self.root))))

    def test_add_placeholder_to_detailed_phase_refuses_atomically(self):
        error = self.assertRefused("PHASE_DETAILED", ops.add_item, self.plan, "P1", "Placeholder")
        self.assertIn("--file", error.message)
        self.assertTrue(any(i.code == "incomplete" for i in error.issues))

    def test_add_complete_item_to_detailed_phase_from_file(self):
        from planner.plan import cli
        data = self.complete_item_data()
        source = self.root.parent / "item.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        with mock.patch("sys.stdout"):
            code = cli.main(["add-item", str(self.root), "P1", "--title", "Complete", "--file", str(source)])
        self.assertEqual(code, 0)
        plan = store.load_plan(self.root)
        self.assertIn("P1.3", plan.items)
        self.assertEqual(errors(plan), [])

    def test_set_cannot_remove_detailed_item_obligations(self):
        for patch in ({"validation": []}, {"validation": None}, {"deliverables": []},
                      {"deliverables": None}, {"scope": {"include": []}}):
            with self.subTest(patch=patch):
                error = self.assertRefused("PLAN_INVALID", ops.patch, self.plan, "P1.2", patch)
                self.assertTrue(any(i.code == "incomplete" for i in error.issues))

    def test_preexisting_errors_do_not_block_unrelated_edit_or_repair(self):
        demo.rewrite(self.root, "phases/P1/P1.2.json", lambda d: d.update(validation=[]))
        ops.patch(self.plan, "P1.2", {"title": "Can still repair"})
        self.assertEqual(self.plan.items["P1.2"]["validation"], [])
        ops.patch(self.plan, "P1.2", {"validation": [{"id": "V1", "cmd": "true", "expect": "OK", "kind": "acceptance"}]})
        self.assertEqual(errors(store.load_plan(self.root)), [])

    def test_push_cannot_introduce_missing_unit_in_detailed_phase(self):
        self.assertRefused("PLAN_INVALID", ops.push, self.plan, "P1.2", "units", "U9")

    def test_set_cannot_add_cycle_with_item_id_location(self):
        error = self.assertRefused("PLAN_INVALID", ops.patch, self.plan, "P1.1", {"depends_on": ["P1.2"]})
        self.assertTrue(any(i.code == "cycle" and i.where in {"P1.1", "P1.2"} for i in error.issues))

    def test_unit_edit_cannot_add_semantic_error_in_detailed_phase(self):
        doc = demo.fixture("unit-e3a-u1")
        demo.write_doc(self.root / "phases/P1/P1.1/U1.json", doc, "unit")
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(units=["U1"]))
        error = self.assertRefused("PLAN_INVALID", ops.patch, self.plan, "P1.1/U1", {"kind": "command"})
        self.assertTrue(any(i.code == "unit_command" and i.where == "P1.1/U1" for i in error.issues))


class PatchTests(DemoCase):
    def item(self, item_id="P1.2"):
        return store.load_plan(self.root).items[item_id]

    def test_merge_patch_follows_rfc_7386(self):
        self.assertEqual(ops.merge_patch({"a": {"b": 1, "c": 2}, "l": [1]}, {"a": {"b": None, "d": 3}, "l": [2]}),
                         {"a": {"c": 2, "d": 3}, "l": [2]})
        self.assertEqual(ops.merge_patch({"a": 1}, {"b": {"c": None}}), {"a": 1, "b": {}})
        self.assertEqual(ops.merge_patch({"a": 1}, [1]), [1])
        original = {"a": {"b": 1}}
        ops.merge_patch(original, {"a": {"b": 2}})
        self.assertEqual(original, {"a": {"b": 1}})

    def test_patch_merges_nested_objects_and_replaces_arrays(self):
        ops.patch(self.plan, "P1.2", {"scope": {"include": ["only this"]}, "deliverables": ["one"]})
        item = self.item()
        self.assertEqual(item["scope"], {"include": ["only this"], "exclude": ["config file format"]})
        self.assertEqual(item["deliverables"], ["one"])

    def test_null_deletes_an_optional_key_and_refuses_a_required_one(self):
        ops.patch(self.plan, "P1.2", {"guidance": None})
        self.assertNotIn("guidance", self.item())
        error = self.assertRefused("SCHEMA_INVALID", ops.patch, self.plan, "P1.2", {"why": None})
        self.assertEqual([i.code for i in error.issues], ["required"])

    def test_negative_control_unknown_field_is_refused_byte_for_byte(self):
        error = self.assertRefused("SCHEMA_INVALID", ops.patch, self.plan, "P1.2", {"bogus": 1})
        self.assertEqual([i.code for i in error.issues], ["additional"])
        self.assertIn("additional", str(error) + error.issues[0].code)

    def test_lifecycle_and_identity_fields_are_owned(self):
        for ref, field in (("P1.2", "status"), ("P1.2", "result"), ("P1.2", "id"), ("P1.2", "updated_at"),
                           ("P1", "design"), ("P1", "closed"), ("P1", "id"), ("D1", "id")):
            with self.subTest(ref=ref, field=field):
                self.assertRefused("FIELD_OWNED", ops.patch, self.plan, ref, {field: None})
        self.assertRefused("FIELD_OWNED", ops.patch, self.plan, "P1.2", {"status": "done"})

    def test_patch_reaches_phases_decisions_and_units(self):
        demo.write_doc(self.root / "phases" / "P1" / "P1.1" / "U1.json", demo.fixture("unit-e3a-u1"), "unit")
        ops.patch(self.plan, "P1", {"goal": "New goal"})
        ops.patch(self.plan, "D2", {"title": "Renamed question"})
        ops.patch(self.plan, "P1.1/U1", {"goal": "New unit goal"})
        fresh = store.load_plan(self.root)
        self.assertEqual((fresh.phases["P1"]["goal"], fresh.decisions["D2"]["title"], fresh.units["P1.1/U1"]["goal"]),
                         ("New goal", "Renamed question", "New unit goal"))
        self.assertRefused("FIELD_OWNED", ops.patch, self.plan, "P1.1/U1", {"status": "accepted"})

    def test_bad_references_and_patch_shapes(self):
        self.assertRefused("REF_UNKNOWN", ops.patch, self.plan, "P1.9", {"title": "x"})
        self.assertRefused("REF_UNKNOWN", ops.patch, self.plan, "P1.1/U9", {"title": "x"})
        self.assertRefused("REF_INVALID", ops.patch, self.plan, "nonsense", {"title": "x"})
        self.assertRefused("REF_INVALID", ops.patch, self.plan, "artifact/catalog", {"title": "x"})  # not a patchable document
        self.assertRefused("REF_QUALIFIED", ops.patch, self.plan, "PLAN3.P1.1", {"title": "x"})
        self.assertRefused("PATCH_INVALID", ops.patch, self.plan, "P1.2", ["title"])

    def test_push_appends_to_arrays_including_dotted_paths(self):
        before = len(self.item()["reads"])
        ops.push(self.plan, "P1.2", "reads", {"path": "lib/pkg/more.py", "why": "extra", "required": False})
        ops.push(self.plan, "P1.2", "scope.include", "one more thing")
        unit = demo.fixture("unit-e3a-u1")
        unit.update(item="P1.2")
        demo.write_doc(self.root / "phases/P1/P1.2/U1.json", unit, "unit")
        ops.push(self.plan, "P1.2", "units", "U1")
        item = self.item()
        self.assertEqual(len(item["reads"]), before + 1)
        self.assertEqual(item["scope"]["include"][-1], "one more thing")
        self.assertEqual(item["units"], ["U1"])

    def test_push_refusals(self):
        self.assertRefused("FIELD_NOT_ARRAY", ops.push, self.plan, "P1.2", "title", "x")
        self.assertRefused("FIELD_NOT_ARRAY", ops.push, self.plan, "P1.2", "title.sub", "x")
        self.assertRefused("FIELD_OWNED", ops.push, self.plan, "P1.2", "result.deviations", "x")
        self.assertRefused("FIELD_OWNED", ops.push, self.plan, "P1.2", "status", "x")
        self.assertRefused("SCHEMA_INVALID", ops.push, self.plan, "P1.2", "bogus", 1)
        self.assertRefused("SCHEMA_INVALID", ops.push, self.plan, "P1.2", "depends_on", "P1.1")  # already present

    def test_set_batches_replaces_the_batch_list(self):
        batches = [{"id": "B1", "items": ["P1.1"], "mode": "required"}, {"id": "B2", "items": ["P1.2"], "mode": "recommended"}]
        ops.set_batches(self.plan, "P1", batches)
        self.assertEqual(store.load_plan(self.root).phases["P1"]["batches"], batches)
        self.assertEqual(errors(store.load_plan(self.root)), [])
        self.assertRefused("REF_UNKNOWN", ops.set_batches, self.plan, "P9", [])
        self.assertRefused("SCHEMA_INVALID", ops.set_batches, self.plan, "P1", [{"id": "B1", "items": [], "mode": "required"}])

    def test_set_plan_and_set_brief(self):
        ops.set_plan(self.plan, {"goal": "Sharper goal", "rules": ["one rule"], "settings": {"scout": "auto"}})
        fresh = store.load_plan(self.root)
        self.assertEqual((fresh.plan["goal"], fresh.plan["rules"], fresh.plan["settings"]),
                         ("Sharper goal", ["one rule"], {"design_audit": "none", "scout": "auto"}))
        ops.set_brief(self.plan, {"constraints": ["no network"], "out_of_scope": None})
        self.assertEqual(store.load_plan(self.root).brief["constraints"], ["no network"])
        self.assertRefused("FIELD_OWNED", ops.set_plan, self.plan, {"status": "done"})
        self.assertRefused("FIELD_OWNED", ops.set_plan, self.plan, {"short_id": "PLAN1"})
        self.assertRefused("FIELD_OWNED", ops.set_brief, self.plan, {"$schema": "x"})
        self.assertRefused("SCHEMA_INVALID", ops.set_plan, self.plan, {"nonsense": 1})
        self.assertRefused("PATCH_INVALID", ops.set_brief, self.plan, "text")


class MutationContractTests(DemoCase):
    def test_plan_snapshot_is_refreshed_in_place(self):
        ops.add_item(self.plan, "P1", "Fresh", data=self.complete_item_data())
        self.assertIn("P1.3", self.plan.items)
        self.assertIn("P1.3", self.plan.phases["P1"]["items"])

    def test_a_directory_path_works_as_the_plan_reference(self):
        self.assertEqual(ops.add_phase(str(self.root), "By path"), "P2")
        self.assertEqual(ops.add_phase(self.root, "By Path object"), "P3")

    def test_views_hook_runs_once_per_successful_mutation_only(self):
        with mock.patch.object(ops, "_after_mutation") as hook:
            ops.add_item(self.plan, "P1", "Hooked", data=self.complete_item_data())
            self.assertEqual(hook.call_count, 1)
            with self.assertRaises(PlanError):
                ops.patch(self.plan, "P1.2", {"bogus": 1})
            self.assertEqual(hook.call_count, 1)

    def test_updated_at_comes_from_the_injectable_clock(self):
        with mock.patch.object(store, "now", return_value="2031-05-06T07:08:09Z"):
            ops.patch(self.plan, "P1.2", {"title": "Clocked"})
        self.assertEqual(store.load_plan(self.root).items["P1.2"]["updated_at"], "2031-05-06T07:08:09Z")

    def test_every_written_document_is_canonical_and_valid(self):
        ops.add_phase(self.plan, "Second")
        ops.add_item(self.plan, "P2", "Item")
        ops.add_decision(self.plan, "Q")
        ops.push(self.plan, "P1.2", "rules", "r")
        fresh = store.load_plan(self.root)
        for kind, _key, rel, doc in check._Context(fresh, []).docs():
            with self.subTest(rel):
                self.assertEqual(schema.validate(doc, kind), [])
                self.assertEqual((self.root / rel).read_text(encoding="utf-8"), store.canonical_dump(doc, kind))

    def test_mutated_plan_still_passes_check(self):
        ops.add_phase(self.plan, "Second")
        ops.add_item(self.plan, "P2", "Item")
        ops.set_batches(self.plan, "P1", [{"id": "B1", "items": ["P1.1", "P1.2"], "mode": "recommended"}])
        self.assertEqual(errors(store.load_plan(self.root)), [])


if __name__ == "__main__":
    unittest.main()
