"""Context pack (dossier §7): golden pack, section extraction, reads, lessons, decisions, start integration."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import context, lifecycle, ops  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

try:
    from . import test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
DOC = """# Title

## 1. Overview

Intro.

## 2. Validation

Body line.

```text
## fenced, not a heading
```

### 2.1 Error format

Nested body.

## 3. `Out` of scope

Last.

## Empty

## Tail
tail text
"""


class SectionTests(unittest.TestCase):
    def test_numbered_and_named_headings(self):
        self.assertEqual(context.extract_section(DOC, "§1"), "Intro.")
        self.assertEqual(context.extract_section(DOC, "§2.1"), "Nested body.")
        self.assertEqual(context.extract_section(DOC, "§2 Validation").splitlines()[0], "Body line.")  # N alone decides
        self.assertEqual(context.extract_section(DOC, "validation").splitlines()[0], "Body line.")  # case-insensitive
        self.assertEqual(context.extract_section(DOC, "Error format"), "Nested body.")  # substring tier
        self.assertEqual(context.extract_section(DOC, "out of scope"), "Last.")  # markup ignored in headings

    def test_a_section_runs_to_the_next_heading_of_the_same_or_higher_level(self):
        body = context.extract_section(DOC, "§2")
        self.assertIn("### 2.1 Error format", body)  # a deeper heading stays inside
        self.assertIn("Nested body.", body)
        self.assertNotIn("Last.", body)
        self.assertIn("## fenced, not a heading", body)  # fenced lines are never headings

    def test_missing_empty_and_last_sections(self):
        self.assertIsNone(context.extract_section(DOC, "§9"))
        self.assertIsNone(context.extract_section(DOC, "Nonexistent"))
        self.assertEqual(context.extract_section(DOC, "Empty"), "")
        self.assertEqual(context.extract_section(DOC, "Tail"), "tail text")


def force_patch(root, ref, patch):
    """Plant data that ``ops.patch`` would refuse (dangling links): these tests probe how readers treat it."""
    with ops._mutation(root) as p:
        kind, key, doc = ops.resolve_target(p, ref)
        ops._commit(p, [(kind, key, ops.merge_patch(doc, patch))])


class JsonContextTests(test_lifecycle.LifeCase):
    """Legacy pack semantics: the plan from ``new_plan`` is scoped, so these tests pin ``context_pack: legacy``."""

    def setUp(self):
        super().setUp()
        ops.patch(self.load(), "plan", {"settings": {"context_pack": "legacy"}})

    def test_complete_context_is_json_and_deterministic(self):
        text = context.render(self.load(), "P1.1")
        value = json.loads(text)
        self.assertEqual(value["item"]["id"], "P1.1")
        self.assertEqual(value["brief"]["messages"][0]["text"], "m")
        path = context.build(self.load(), "P1.1")
        self.assertEqual(path.name, "P1.1.json")
        self.assertEqual(path.read_text(), text)
        self.assertEqual(context.render(self.load(), "P1.1"), text)

    def test_all_lessons_survive_without_a_read_budget(self):
        for n in range(12):
            lifecycle.log(self.root, "P1.1", "difficulty", f"problem {n}")
        lessons = context.collect(self.load(), "P1.1")["lessons"]
        self.assertEqual([e["summary"] for e in lessons], [f"problem {n}" for n in range(12)])

    def test_long_supporting_sections_are_not_truncated(self):
        text = "\n".join(f"line {n}" for n in range(501))
        (self.root.parent.parent / "runbook.md").write_text("## Runbook\n" + text)
        force_patch(self.root, "P1.1", {"reads": [{"path": "runbook.md", "section": "Runbook", "why": "steps", "required": True}]})
        self.assertEqual(context.collect(self.load(), "P1.1")["reads"][0]["content"], text)

    def test_knowledge_sections_and_provenance_are_preserved(self):
        ops.add_document(self.root, {"id": "design", "title": "Design", "applies_to": ["P1.1"],
            "sections": [{"id": "steps", "title": "Steps", "text": "do everything\n" * 400}]})
        force_patch(self.root, "P1.1", {"reads": [{"path": "@plan/knowledge/design.json", "section": "steps", "why": "steps", "required": True}]})
        value = context.collect(self.load(), "P1.1")
        self.assertEqual(value["reads"][0]["content"]["sections"], value["documents"][0]["sections"])
        self.assertEqual(context.collect(self.load(), "P1.2")["documents"], [])

    def add_design(self):
        ops.add_document(self.root, {"id": "design", "title": "Design", "applies_to": ["P1.1"],
            "sections": [{"id": "steps", "title": "Steps", "text": "do everything"},
                         {"id": "other", "title": "Other", "text": "else"}]})

    def test_a_read_by_ref_is_inlined_like_the_read_by_path(self):
        self.add_design()
        force_patch(self.root, "P1.1", {"reads": [{"ref": "knowledge/design#steps", "why": "steps", "required": True},
                                                 {"path": "@plan/knowledge/design.json", "section": "steps", "why": "same", "required": True}]})
        by_ref, by_path = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual(by_ref["ref"], "knowledge/design#steps")
        self.assertEqual((by_ref["path"], by_ref["section"]), ("@plan/knowledge/design.json", "steps"))
        self.assertEqual(by_ref["content"], by_path["content"])
        self.assertEqual([s["id"] for s in by_ref["content"]["sections"]], ["steps"])

    def test_the_section_key_selects_when_the_ref_names_a_whole_document(self):
        self.add_design()
        force_patch(self.root, "P1.1", {"reads": [{"ref": "knowledge/design", "section": "other", "why": "w", "required": True}]})
        entry, = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual([s["id"] for s in entry["content"]["sections"]], ["other"])

    def test_plan_documents_of_every_local_kind_are_readable_by_ref(self):
        decision = ops.add_decision(self.root, "Question")
        force_patch(self.root, "P1.1", {"reads": [{"ref": ref, "why": "w", "required": True}
                                                 for ref in ("P1", "P1.2", decision)]})
        entries = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual([e["content"]["id"] for e in entries], ["P1", "P1.2", decision])

    def test_an_artifact_ref_reads_the_path_of_its_output(self):
        (self.root / "artifacts").mkdir()
        (self.root / "artifacts" / "catalog.json").write_text(json.dumps({"errors": 3}))
        force_patch(self.root, "P1.2", {"artifacts": [{"id": "catalog", "path": "@plan/artifacts/catalog.json", "role": "output"}]})
        force_patch(self.root, "P1.1", {"reads": [{"ref": "artifact/catalog", "why": "w", "required": True}]})
        entry, = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual((entry["path"], entry["exists"], entry["content"]), ("@plan/artifacts/catalog.json", True, {"errors": 3}))

    def test_a_required_ref_that_names_nothing_is_missing(self):
        force_patch(self.root, "P1.1", {"reads": [{"ref": "knowledge/gone", "why": "w", "required": True},
                                                 {"ref": "artifact/gone", "why": "w", "required": True},
                                                 {"ref": "knowledge/gone", "why": "w", "required": False}]})
        self.assertEqual(context.missing_reads(self.load(), "P1.1"), ["@plan/knowledge/gone.json", "artifact/gone"])
        self.refused("READ_MISSING", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))

    def test_a_ref_to_another_plan_is_not_readable(self):
        force_patch(self.root, "P1.1", {"reads": [{"ref": "PLAN3.D1", "why": "w", "required": False}]})
        entry, = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual((entry["ref"], entry["exists"], "path" in entry), ("PLAN3.D1", False, False))

    def test_an_unreadable_section_of_a_ref_reports_the_same_error_as_a_path_read(self):
        self.add_design()
        force_patch(self.root, "P1.1", {"reads": [{"ref": "knowledge/design#nope", "why": "w", "required": False}]})
        entry, = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual(entry["error"], "section not found")

    def test_required_ref_sections_refuse_start_without_mutation(self):
        self.add_design()
        for extra in ({"ref": "knowledge/design#missing"},
                      {"ref": "knowledge/design", "section": "missing"},
                      {"ref": "knowledge/design#Steps"}):  # fragments name ids, not titles
            with self.subTest(extra=extra):
                force_patch(self.root, "P1.1", {"reads": [{**extra, "why": "needed", "required": True}]})
                self.assertTrue(context.missing_reads(self.load(), "P1.1"))
                self.refused("READ_MISSING", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))

    def test_required_ref_section_titles_remain_readable_via_section_key(self):
        self.add_design()
        force_patch(self.root, "P1.1", {"reads": [
            {"ref": "knowledge/design", "section": "Steps", "why": "needed", "required": True}]})
        self.assertEqual(context.missing_reads(self.load(), "P1.1"), [])
        self.assertEqual(context.collect(self.load(), "P1.1")["reads"][0]["content"]["sections"][0]["id"], "steps")

    def test_views_never_supply_agent_input(self):
        force_patch(self.root, "P1.1", {"reads": [{"path": "@plan/views/plan.md", "section": "Goal", "why": "bad", "required": False}]})
        self.refused("HUMAN_VIEW", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))
        self.assertEqual(self.load().items["P1.1"]["status"], "todo")

    def test_an_item_in_progress_may_start_again_after_its_own_work_moved_a_read(self):
        (self.root / "artifacts").mkdir()
        path = self.root / "artifacts" / "input.json"
        path.write_text("{}")
        force_patch(self.root, "P1.1", {"reads": [{"path": "@plan/artifacts/input.json", "why": "needed", "required": True}]})
        lifecycle.start(self.root, ["P1.1"], test_lifecycle.OPUS)
        path.unlink()
        lifecycle.start(self.root, ["P1.1"], test_lifecycle.OPUS)  # a repeated claim of the same run
        self.assertEqual(self.load().items["P1.1"]["status"], "in_progress")

    def test_missing_required_input_is_refused_without_mutation(self):
        force_patch(self.root, "P1.1", {"reads": [{"path": "gone.py", "why": "needed", "required": True}]})
        self.refused("READ_MISSING", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))

    def test_authored_plan_markdown_is_not_an_execution_source(self):
        (self.root / "notes.md").write_text("Private old plan notes")
        force_patch(self.root, "P1.1", {"reads": [{"path": "@plan/notes.md", "why": "bad", "required": True}]})
        self.refused("HUMAN_VIEW", lambda root: lifecycle.start(root, ["P1.1"], test_lifecycle.OPUS))

    def test_upstream_results_and_foreign_decisions_remain_structured(self):
        self.start("P1.1")
        self.finish("P1.1", "done_with_deviations", notes="result", deviations=["slow"], pending=["docs"])
        force_patch(self.root, "P1.2", {"decisions": ["PLAN3.D4"]})
        value = context.collect(self.load(), "P1.2")
        self.assertEqual(value["upstream"][0]["result"]["deviations"], ["slow"])
        entry, = value["decisions"]  # superset of the former {"ref", "loaded": False}; the resolver adds a reason
        self.assertEqual((entry["ref"], entry["loaded"]), ("PLAN3.D4", False))
        self.assertTrue(entry["reason"].startswith("PLAN_NOT_FOUND: "))

    def test_start_and_resume_build_json_inputs(self):
        started = self.start("P1.1", "P1.2")
        self.assertEqual([p.name for p in started.packs], ["P1.1.json", "P1.2.json"])
        started.packs[0].write_text("stale")
        self.start("P1.1")
        self.assertEqual(json.loads(started.packs[0].read_text())["item"]["status"], "in_progress")

    def test_cli_stdout_is_json_and_does_not_write_a_pack(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "context", str(self.root), "P1.1", "--stdout"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["item"]["id"], "P1.1")
        self.assertFalse((self.root / "context").exists())


DECISION = {"status": "accepted", "decision": "rule", "rationale": "why"}


class ScopeTests(test_lifecycle.LifeCase):
    """``settings.context_pack``: legacy sends unbound content everywhere, scoped only bound, global or explicit."""

    def add_content(self):
        ops.add_document(self.root, {"id": "loose", "title": "Loose", "sections": [{"id": "s", "title": "S", "text": "t"}]})
        ops.add_document(self.root, {"id": "everywhere", "title": "All", "global": True,
                                     "sections": [{"id": "s", "title": "S", "text": "t"}]})
        ops.add_document(self.root, {"id": "bound", "title": "Bound", "applies_to": ["P1.1"],
                                     "sections": [{"id": "s", "title": "S", "text": "t"}]})
        self.loose = ops.add_decision(self.root, "Loose", data=DECISION)
        self.pinned = ops.add_decision(self.root, "Pinned", data=DECISION)
        self.phase = ops.add_decision(self.root, "Phase", data={**DECISION, "applies_to": ["P1"]})
        self.world = ops.add_decision(self.root, "World", data={**DECISION, "global": True})
        force_patch(self.root, "P1.1", {"decisions": [self.pinned]})

    def set_mode(self, mode):
        ops.patch(self.load(), "plan", {"settings": {"context_pack": mode}})

    def ids(self, value, key):
        return [d["id"] for d in value[key]]

    def test_new_plans_are_scoped_and_a_missing_setting_is_legacy(self):
        self.assertEqual(context.pack_mode(self.load()), "scoped")
        plan = self.load()
        del plan.plan["settings"]["context_pack"]
        self.assertEqual(context.pack_mode(plan), "legacy")
        self.assertEqual(context.budget_bytes(plan), 256 * 1024)
        plan.plan["settings"]["context_budget_kb"] = 8
        self.assertEqual(context.budget_bytes(plan), 8 * 1024)
        plan.plan["settings"]["context_budget_kb"] = 0
        self.assertEqual(context.budget_bytes(plan), 256 * 1024)

    def test_scope_reason_priority_and_modes(self):
        reason = context.scope_reason
        self.assertEqual(reason({"applies_to": ["P1.1"]}, "P1.1", "P1", "scoped"), "item")
        self.assertEqual(reason({"applies_to": ["P1"], "global": True}, "P1.1", "P1", "scoped"), "phase")
        self.assertEqual(reason({"global": True}, "P1.1", "P1", "scoped"), "global")
        self.assertEqual(reason({}, "P1.1", "P1", "legacy"), "unbound")
        self.assertIsNone(reason({}, "P1.1", "P1", "scoped"))
        self.assertIsNone(reason({"applies_to": ["P2"]}, "P1.1", "P1", "legacy"))

    def test_legacy_pack_keeps_unbound_content_and_full_upstream(self):
        self.add_content()
        self.set_mode("legacy")
        self.start("P1.1")
        self.finish("P1.1", notes="result")
        ops.add_document(self.root, {"id": "second", "title": "Second", "applies_to": ["P1.2"],
                                     "sections": [{"id": "s", "title": "S", "text": "t"}]})
        force_patch(self.root, "P1.2", {"reads": [{"path": "@plan/knowledge/second.json", "why": "w", "required": True}]})
        value = context.collect(self.load(), "P1.2")
        self.assertNotIn("projection", value)
        self.assertEqual(self.ids(value, "documents"), ["everywhere", "loose", "second"])
        self.assertEqual(self.ids(value, "decisions"), [self.loose, self.pinned, self.phase, self.world])
        self.assertEqual(value["reads"][-1]["content"]["id"], "second")
        self.assertEqual(value["upstream"], [self.load().items["P1.1"]])
        self.assertEqual(value["phase_dependencies"], [])

    def test_scoped_pack_drops_unbound_content_and_keeps_global_and_explicit(self):
        self.add_content()
        value = context.collect(self.load(), "P1.1")
        self.assertEqual(self.ids(value, "documents"), ["bound", "everywhere"])
        self.assertEqual(self.ids(value, "decisions"), [self.pinned, self.phase, self.world])
        self.assertEqual(context.collect(self.load(), "P1.2")["documents"][0]["id"], "everywhere")
        self.assertEqual(self.ids(context.collect(self.load(), "P1.2"), "decisions"), [self.phase, self.world])

    def test_scoped_reads_name_the_key_that_already_holds_the_source(self):
        self.add_content()
        reads = [{"path": "@plan/knowledge/bound.json", "section": "s", "why": "w", "required": True},
                 {"path": "@plan/knowledge/bound.json", "section": "s", "why": "again", "required": True},
                 {"ref": self.phase, "why": "w", "required": True},
                 {"path": "@plan/plan.json", "why": "w", "required": True},
                 {"path": "@plan/brief.json", "why": "w", "required": True},
                 {"path": "@plan/phases/P1/phase.json", "why": "w", "required": True},
                 {"path": "@plan/phases/P1/P1.1.json", "why": "w", "required": True},
                 {"path": "@plan/knowledge/loose.json", "why": "unbound but asked for", "required": True}]
        force_patch(self.root, "P1.1", {"reads": reads})
        value = context.collect(self.load(), "P1.1")
        self.assertEqual([r.get("included") for r in value["reads"]],
                         ["documents", "documents", "decisions", "plan", "brief", "phase", "item", None])
        self.assertTrue(all("content" not in r for r in value["reads"][:-1]))
        self.assertEqual(value["reads"][-1]["content"]["id"], "loose")  # not in the pack: the read supplies it
        self.assertEqual(value["reads"][0]["why"], "w")
        self.assertTrue(value["reads"][0]["exists"])

    def test_a_repeated_read_points_at_its_first_occurrence(self):
        read = {"path": "@plan/knowledge/loose.json", "why": "w", "required": True}
        ops.add_document(self.root, {"id": "loose", "title": "Loose", "sections": [{"id": "s", "title": "S", "text": "t"}]})
        force_patch(self.root, "P1.1", {"reads": [read, {**read, "why": "twice"}, {**read, "section": "s"}]})
        entries = context.collect(self.load(), "P1.1")["reads"]
        self.assertEqual([e.get("included") for e in entries], [None, "reads/0", None])
        self.assertIn("content", entries[0])
        self.assertEqual(context.duplicate_target(self.load(), "P1.1", {"documents": [], "decisions": [],
                                                                         "reads": entries}, 1), "reads/0")

    def test_scoped_upstream_and_phase_dependencies_are_summaries(self):
        self.start("P1.1")
        self.finish("P1.1", notes="result")
        value = context.collect(self.load(), "P1.2")
        entry, = value["upstream"]
        self.assertLessEqual(set(entry), set(context.UPSTREAM_KEYS) | {"result"})
        self.assertEqual((entry["id"], entry["status"], entry["result"]["notes"]), ("P1.1", "done", "result"))
        self.assertNotIn("validation", entry)
        self.assertNotIn("reads", entry)
        self.assertEqual(value["projection"]["mode"], "scoped")
        self.assertIn("summaries", value["projection"]["note"])
        deps = context.collect(self.load(), "P2.1")["phase_dependencies"]
        self.assertTrue(all(set(d) <= set(context.PHASE_KEYS) for d in deps))


class SchemaScopeTests(test_lifecycle.LifeCase):
    def test_schema_accepts_global_and_the_new_settings(self):
        ops.add_document(self.root, {"id": "g", "title": "G", "global": True, "sections": []})
        ops.add_decision(self.root, "G", data={**DECISION, "global": True})
        ops.patch(self.load(), "plan", {"settings": {"context_pack": "legacy", "context_budget_kb": 64}})
        self.assertEqual(self.load().plan["settings"]["context_budget_kb"], 64)

    def test_schema_rejects_an_unknown_pack_mode_and_a_non_boolean_global(self):
        with self.assertRaises(PlanError):
            ops.patch(self.load(), "plan", {"settings": {"context_pack": "x"}})
        with self.assertRaises(PlanError):
            ops.add_document(self.root, {"id": "g", "title": "G", "global": "yes", "sections": []})


if __name__ == "__main__":
    unittest.main()
