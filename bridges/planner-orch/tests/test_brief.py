"""plan.py bridge planner-orch brief (exec/v1 execution-input): field mapping, units, inline reads, refusals, determinism,
read-only, ``--out``, and the core no longer knowing the verb."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

_BRIDGE = Path(__file__).resolve().parents[1]
for _path in (_BRIDGE, _BRIDGE / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import bridge_fixture  # noqa: E402  (skips the module without a planner)
import partners  # noqa: E402

_PLANNER = bridge_fixture.PLANNER
_ENGINE_TESTS = str(_PLANNER / "tests" / "engine")
if _ENGINE_TESTS not in sys.path:
    sys.path.insert(0, _ENGINE_TESTS)

import brief  # noqa: E402
context, lifecycle, ops, store, units, model = partners.planner_engine(
    "plan.context", "plan.lifecycle", "plan.ops", "plan.store", "plan.units", "plan.model")
PlanError = model.PlanError
import test_context  # noqa: E402
import test_lifecycle  # noqa: E402
import test_refs  # noqa: E402

SCRIPT = _PLANNER / "scripts" / "plan.py"
BRIDGE = ("bridge", "planner-orch", "brief")


def tree_hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class BriefCase(test_lifecycle.LifeCase):
    def setUp(self):
        super().setUp()
        self.repo = self.plans.parent
        (self.repo / "lib").mkdir()
        (self.repo / "lib" / "x.py").write_text("print('x')\n", encoding="utf-8")
        (self.repo / "data.bin").write_bytes(b"\xff\xfe\x00binary")
        ops.patch(self.root, "P1", {"pitfalls": ["watch the lock"]})
        ops.patch(self.root, "P1.1", {
            "rules": ["no network"], "guidance": "do it", "sections": [{"id": "s1", "title": "T", "text": "body"}],
            "reads": [{"path": "lib/x.py", "why": "source", "required": True},
                      {"path": "data.bin", "why": "blob", "required": False}]})
        ops.patch(self.root, "P1.1", {"scope": {"include": ["a", "b"], "exclude": ["c"]}})
        ops.set_plan(self.root, {"rules": ["stdlib only"]})

    def brief(self, item="P1.1", **kwargs):
        return brief.build(self.load(), item, **kwargs)


class FloatContentTests(unittest.TestCase):
    def test_a_read_with_float_content_becomes_json_text_so_the_digest_can_be_computed(self):
        entry = {"path": "schema.json", "why": "w", "required": True, "exists": False,
                 "content": {"b": {"default": 0.6}, "a": [1, 0.95]}}
        read = brief._read(None, entry, False)
        self.assertEqual(read["content"], '{"a":[1,0.95],"b":{"default":0.6}}')
        brief.canonical_digest({"reads": [read]})  # no floats left
        plain = {"path": "x", "exists": False, "content": {"n": 1}}
        self.assertEqual(brief._read(None, plain, False)["content"], {"n": 1})


class MappingTests(BriefCase):
    def test_item_fields_follow_the_mapping_table(self):
        doc = self.brief()
        item = self.load().items["P1.1"]
        self.assertEqual(doc["$schema"], "urn:swissknifeman:orch:exec:execution-input:v1")
        self.assertEqual(doc["contract_version"], "exec/v1")
        self.assertEqual(doc["goal"], f"{item['title']}: {item['summary']}")
        self.assertEqual(doc["why"], item["why"])
        self.assertEqual(doc["scope"], {"include": ["a", "b"], "exclude": ["c"], "write_set": ["lib/x.py"],
                                        "read_only": False})
        self.assertEqual(doc["guidance"], "do it")
        self.assertEqual(doc["sections"], [{"id": "s1", "title": "T", "text": "body"}])
        self.assertEqual(doc["acceptance"], {"checks": item["validation"], "deliverables": ["d"]})
        self.assertEqual(doc["route"], {"minimum": item["route"]})
        self.assertEqual(doc["result_contract"], {"report": brief.REPORT, "write_authority": "code_scope",
                                                  "commit_owner": "coordinator", "plan_mutation": "forbidden"})
        self.assertEqual(doc["escalation"], brief.ESCALATION)

    def test_the_research_need_of_the_item_is_carried_with_its_notes(self):
        self.assertEqual(self.brief()["research"], {"need": "none"})  # the planner default: no research
        ops.patch(self.root, "P1.1", {"rag": {"need": "required", "status": "pending", "notes": "check the flags"}})
        doc = self.brief()
        self.assertEqual(doc["research"], {"need": "required", "notes": "check the flags"})
        self.assertEqual(doc["digest"], brief.canonical_digest(doc))
        ops.patch(self.root, "P1.1", {"rag": {"need": "optional", "status": "pending"}})
        self.assertEqual(self.brief()["research"], {"need": "optional", "notes": "check the flags"})

    def test_an_item_without_rag_gets_no_research_field(self):
        plan = self.load()
        plan.items["P1.1"].pop("rag")
        self.assertNotIn("research", brief.build(plan, "P1.1"))

    def test_constraints_keep_order_and_source(self):
        self.assertEqual(self.brief()["constraints"], [
            {"text": "stdlib only", "source": "plan.rules[0]"},
            {"text": "watch the lock", "source": "phase.pitfalls[0]"},
            {"text": "no network", "source": "item.rules[0]"}])

    def test_decisions_upstream_and_lessons(self):
        other = ops.new_plan("OTHER", "Other", plans_root=self.plans, repository="r", owner="o",
                             authoring=test_lifecycle.OPUS, message="m", date="2026.10.08").root
        ops.add_decision(other, "Elsewhere", data={"options": [{"id": "A", "text": "yes"}]})
        lifecycle.decide(other, "D1", "A", "why", by="owner", actor=test_lifecycle.OPUS)
        ops.patch(self.root, "P1.2", {"decisions": ["PLAN2.D1"]})
        self.start("P1.1")
        self.finish("P1.1", "done", notes="shipped")
        lifecycle.log(self.root, "P1.1", "difficulty", "slow", impact="minor")
        doc = self.brief("P1.2")
        foreign = doc["decisions"][0]
        self.assertEqual((foreign["ref"], foreign["loaded"], foreign["status"], foreign["title"]),
                         ("PLAN2.D1", True, "accepted", "Elsewhere"))
        self.assertEqual(doc["upstream"][0]["ref"], "P1.1")
        self.assertEqual(doc["upstream"][0]["status"], "done")
        self.assertEqual(doc["upstream"][0]["notes"], "shipped")
        lesson = doc["lessons"][0]
        self.assertEqual((lesson["type"], lesson["summary"], lesson["impact"]), ("difficulty", "slow", "minor"))
        self.assertNotIn("actor", lesson)

    def test_local_decisions_are_loaded_with_their_text(self):
        ops.add_decision(self.root, "Format", data={"options": [{"id": "A", "text": "English"}]})  # D1, open
        lifecycle.decide(self.root, "D1", "A", "simple", by="owner", actor=test_lifecycle.OPUS)
        ops.patch(self.root, "P1.1", {"decisions": ["D1"]})
        entry = self.brief()["decisions"][0]
        self.assertEqual((entry["ref"], entry["loaded"], entry["status"], entry["title"]),
                         ("D1", True, "accepted", "Format"))
        self.assertEqual(entry["rationale"], "simple")
        self.assertIn("decision", entry)

    def test_provenance_context_refs_and_hints(self):
        ops.add_document(self.root, {"id": "design", "title": "Design", "applies_to": ["P1.1"],
                                     "sections": [{"id": "a", "title": "A", "text": "t"}]})
        (self.root / "context").mkdir()
        (self.root / "context" / "P1.1.scout.json").write_text(json.dumps({"entries": ["lib/x.py — entry"]}))
        doc = self.brief()
        prov = doc["provenance"]
        self.assertEqual((prov["kind"], prov["plan"], prov["item"]), ("plan", "PLAN1", "P1.1"))
        self.assertEqual(prov["plan_dir"], f"plans/{self.root.name}")
        self.assertNotIn("unit", prov)
        self.assertEqual(prov["generated_by"]["tool"], "planner-orch brief")
        self.assertEqual(prov["source_digest"],
                         hashlib.sha256(context.render(self.load(), "P1.1", with_scout=False).encode()).hexdigest())
        pack, document = doc["context_refs"]
        self.assertEqual(pack["kind"], "pack")
        self.assertEqual(pack["path"], f"plans/{self.root.name}/context/P1.1.json")
        self.assertEqual((document["kind"], document["ref"]), ("document", "knowledge/design"))
        self.assertEqual(document["sha256"], hashlib.sha256((self.root / "knowledge" / "design.json").read_bytes()).hexdigest())
        self.assertEqual(doc["hints"], [{"text": "lib/x.py — entry", "source": "scout"}])

    def test_owner_gate_adds_an_escalation_line(self):
        ops.patch(self.root, "P1.1", {"authority": {"kind": "owner_gate", "gate": "RELEASE", "scope": "tag"}})
        self.assertEqual(self.brief()["escalation"][-1], "Owner gate RELEASE: tag")

    def test_route_minimum_is_the_item_route(self):
        ops.patch(self.root, "P1.1", {"route": {"class": "frontier", "effort": "max"}})
        self.assertEqual(self.brief()["route"]["minimum"], {"class": "frontier", "effort": "max"})


class PhaseChecksTests(BriefCase):
    FULL = {"id": "V9", "cmd": "python3 scripts/affected-tests.py --tier all --run", "expect": "exit 0", "kind": "acceptance"}

    def test_only_the_item_that_closes_the_phase_gets_the_phase_checks(self):
        ops.patch(self.root, "P1", {"validation": [dict(self.FULL)]})
        ids = [check["id"] for check in self.brief()["acceptance"]["checks"]]
        self.assertNotIn("V9", ids)  # P1.2 is still open
        self.start("P1.1")
        self.finish("P1.1")
        self.start("P1.2")
        checks = self.brief("P1.2")["acceptance"]["checks"]
        self.assertEqual(checks[-1], dict(self.FULL, cadence="phase"))
        self.assertEqual(brief.verify(self.load(), "P1.2", self.brief("P1.2")), [])

class ReadsTests(BriefCase):
    def test_existing_files_carry_sha256_and_missing_ones_do_not(self):
        ops.patch(self.root, "P1.1", {"reads": [
            {"path": "lib/x.py", "why": "source", "required": True},
            {"path": "gone.py", "why": "optional", "required": False}]})
        by_path = {r["path"]: r for r in self.brief()["reads"]}
        self.assertEqual(by_path["lib/x.py"]["sha256"], hashlib.sha256(b"print('x')\n").hexdigest())
        self.assertNotIn("content", by_path["lib/x.py"])
        self.assertFalse(by_path["gone.py"]["exists"])
        self.assertNotIn("sha256", by_path["gone.py"])

    def test_inline_reads_embed_full_text_and_flag_binary(self):
        text = "\n".join(f"line {n}" for n in range(800)) + "\n"
        (self.repo / "lib" / "x.py").write_text(text, encoding="utf-8")
        by_path = {r["path"]: r for r in self.brief(inline_reads=True)["reads"]}
        self.assertEqual(by_path["lib/x.py"]["content"], text)
        self.assertEqual(by_path["data.bin"]["error"], "binary or non-utf8")
        self.assertNotIn("content", by_path["data.bin"])

    def test_inline_reads_keep_section_content_of_json_sources(self):
        ops.patch(self.load(), "plan", {"settings": {"context_pack": "legacy"}})  # scoped drops reads held by documents
        ops.add_document(self.root, {"id": "design", "title": "Design", "applies_to": ["P1.1"],
                                     "sections": [{"id": "a", "title": "A", "text": "t"}, {"id": "b", "title": "B", "text": "u"}]})
        ops.patch(self.root, "P1.1", {"reads": [
            {"path": "@plan/knowledge/design.json", "section": "a", "why": "w", "required": True}]})
        for flag in (False, True):
            read = self.brief(inline_reads=flag)["reads"][0]
            self.assertEqual([s["id"] for s in read["content"]["sections"]], ["a"])
            self.assertEqual(len(read["sha256"]), 64)


class UnitTests(BriefCase):
    def test_unit_brief_uses_unit_goal_files_and_checks(self):
        unit_id = units.add_unit(self.root, "P1.1", "Part", {
            "goal": "do the part", "files": ["lib/x.py"], "instructions": "careful", "checks": ["V2"],
            "reads": [{"path": "data.bin", "why": "blob"}],
            "route": {"class": "economy", "effort": "low"}})
        doc = self.brief(unit_id=unit_id)
        self.assertEqual(doc["goal"], "do the part")
        self.assertEqual(doc["scope"]["write_set"], ["lib/x.py"])
        self.assertFalse(doc["scope"]["read_only"])
        self.assertEqual([c["id"] for c in doc["acceptance"]["checks"]], ["V2"])
        self.assertEqual(doc["constraints"][-1], {"text": "careful", "source": "unit.instructions"})
        self.assertEqual(doc["route"]["minimum"], {"class": "economy", "effort": "low"})
        self.assertEqual(doc["provenance"]["unit"], unit_id)
        self.assertTrue(doc["input_id"].startswith(f"PLAN1.P1.1/{unit_id}@"))
        self.assertIn("data.bin", [r["path"] for r in doc["reads"]])

    def test_unit_without_files_is_read_only_with_no_write_authority(self):
        unit_id = units.add_unit(self.root, "P1.1", "Review", {"goal": "look", "files": [], "checks": ["V1"]})
        doc = self.brief(unit_id=unit_id)
        self.assertEqual(doc["scope"]["write_set"], [])
        self.assertTrue(doc["scope"]["read_only"])
        self.assertEqual(doc["result_contract"]["write_authority"], "none")


class InputDigestTests(BriefCase):
    def test_digest_and_input_id_follow_the_convention(self):
        doc = self.brief()
        self.assertEqual(doc["digest"], brief.canonical_digest(doc))
        self.assertTrue(doc["input_id"].endswith("@" + doc["digest"][:12]))
        self.assertTrue(doc["input_id"].startswith("PLAN1.P1.1@"))
        tampered = {**doc, "goal": "other"}
        self.assertNotEqual(brief.canonical_digest(tampered), doc["digest"])

    def test_two_calls_give_the_same_document(self):
        self.assertEqual(brief.render(self.load(), "P1.1"), brief.render(self.load(), "P1.1"))
        self.assertEqual(self.brief()["digest"], self.brief()["digest"])

    def test_no_lifecycle_or_report_api_content(self):
        text = brief.render(self.load(), "P1.1")
        for phrase in ("report_api", "unit return", "plan.py start", "plan.py finish", "planner:plan-run"):
            self.assertNotIn(phrase, text)
        doc = json.loads(text)
        for key in ("orchestration", "ready_units", "units", "plan", "brief"):
            self.assertNotIn(key, doc)


class CompletenessTests(BriefCase):
    def verify(self, doc, item="P1.1", **kwargs):
        return brief.verify(self.load(), item, doc, **kwargs)

    def test_a_read_that_names_forbidden_inputs_is_not_lifecycle_content(self):
        doc = self.brief()
        doc["reads"] = list(doc["reads"]) + [{"path": "roles/x.json", "content": {"forbidden_inputs": ["report_api"]}}]
        self.assertFalse([line for line in self.verify(doc) if "lifecycle" in line])
        doc["reads"][-1]["content"]["forbidden_inputs"] = ["run plan.py start and go on"]  # a sentence is not a denied token
        self.assertTrue([line for line in self.verify(doc) if "lifecycle phrase" in line])
        doc["reads"][-1]["content"]["forbidden_inputs"] = ["report_api"]
        doc["reads"][-1]["content"]["note"] = "call report_api"
        self.assertTrue([line for line in self.verify(doc) if "lifecycle phrase 'report_api'" in line])

    def test_complete_document_has_no_omissions(self):
        self.assertEqual(self.verify(self.brief()), [])

    def test_removed_check_is_reported_once(self):
        doc = self.brief()
        removed = doc["acceptance"]["checks"].pop()
        self.assertEqual(self.verify(doc), [f"acceptance.checks: missing {removed['id']}"])

    def test_removed_rule_is_reported_once(self):
        doc = self.brief()
        doc["constraints"] = [c for c in doc["constraints"] if c["source"] != "item.rules[0]"]
        self.assertEqual(self.verify(doc), ["constraints: missing item.rules[0]"])

    def test_removed_required_read_is_reported_once(self):
        doc = self.brief()
        doc["reads"] = [r for r in doc["reads"] if r["path"] != "lib/x.py"]
        self.assertEqual(self.verify(doc), ["reads: missing lib/x.py"])

    def test_removed_decision_is_reported_once(self):
        ops.add_decision(self.root, "Format", data={"options": [{"id": "A", "text": "English"}]})
        lifecycle.decide(self.root, "D1", "A", "simple", by="owner", actor=test_lifecycle.OPUS)
        ops.patch(self.root, "P1.1", {"decisions": ["D1"]})
        doc = self.brief()
        doc["decisions"] = [d for d in doc["decisions"] if d["ref"] != "D1"]
        self.assertEqual(self.verify(doc), ["decisions: missing D1"])

    def test_scope_goal_route_and_deliverables_must_match(self):
        doc = self.brief()
        doc["scope"]["include"] = ["other"]
        doc["goal"] = " "
        doc["route"] = {}
        doc["acceptance"]["deliverables"] = []
        self.assertEqual(self.verify(doc), [
            "scope.include: differs from the item", "goal: empty", "route.minimum: missing",
            "deliverables: differ from the item"])

    def test_lifecycle_phrase_in_guidance_is_refused(self):
        ops.patch(self.root, "P1.1", {"guidance": "then run plan.py finish P1.1"})
        with self.assertRaises(Exception) as ctx:
            self.brief()
        self.assertEqual(ctx.exception.code, "BRIEF_INCOMPLETE")
        self.assertIn("/guidance: lifecycle phrase 'plan.py finish'", str(ctx.exception))

    def test_lifecycle_phrase_in_plan_rules_is_data(self):
        ops.set_plan(self.root, {"rules": ["never call plan.py finish by hand"]})
        self.assertEqual(self.verify(self.brief()), [])

    def test_large_item_is_not_truncated(self):
        reads = [{"path": f"absent/{i}.py", "why": "optional", "required": False} for i in range(200)]
        ops.patch(self.root, "P1.1", {"reads": reads + [{"path": "lib/x.py", "why": "source", "required": True}],
                                      "rules": [f"rule {i}" for i in range(50)]})
        doc = self.brief()
        self.assertEqual(self.verify(doc), [])
        self.assertEqual(len(doc["constraints"]), 50 + 1 + 1)  # item rules + plan rule + phase pitfall
        self.assertEqual(len(doc["reads"]), 201)


class RefusalTests(BriefCase):
    def test_unknown_item_and_unit(self):
        with self.assertRaises(Exception) as ctx:
            self.brief("P9.9")
        self.assertEqual(ctx.exception.code, "REF_UNKNOWN")
        with self.assertRaises(Exception) as ctx:
            self.brief(unit_id="U7")
        self.assertEqual(ctx.exception.code, "REF_UNKNOWN")

    def test_skeleton_phase_is_refused(self):
        with self.assertRaises(Exception) as ctx:
            self.brief("P2.1")
        self.assertEqual(ctx.exception.code, "PHASE_NOT_DETAILED")

    def test_missing_required_read_is_refused(self):
        ops.patch(self.root, "P1.1", {"reads": [{"path": "gone.py", "why": "needed", "required": True}]})
        with self.assertRaises(Exception) as ctx:
            self.brief()
        self.assertEqual(ctx.exception.code, "READ_MISSING")

    def test_required_read_the_item_deleted_does_not_refuse_the_brief_of_an_item_in_progress(self):
        self.start("P1.1")
        (self.repo / "lib" / "x.py").unlink()  # the item retires its own read; the claim after a stop builds the brief again
        doc = self.brief()
        self.assertEqual(doc["reads"][0]["path"], "lib/x.py")
        self.assertFalse(doc["reads"][0]["exists"])

    def test_human_views_never_supply_input(self):
        ops.patch(self.root, "P1.1", {"reads": [{"path": "@plan/views/plan.md", "section": "Goal", "why": "bad",
                                                 "required": False}]})
        with self.assertRaises(Exception) as ctx:
            self.brief()
        self.assertEqual(ctx.exception.code, "HUMAN_VIEW")


class ReadOnlyTests(BriefCase):
    def test_build_and_cli_leave_every_plan_file_untouched(self):
        before = tree_hashes(self.root)
        self.brief()
        subprocess.run([sys.executable, str(SCRIPT), *BRIDGE, str(self.root), "P1.1"],
                       capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(tree_hashes(self.root), before)
        self.assertFalse((self.root / "context").exists())


class CliTests(BriefCase):
    def run_cli(self, *args, output=None):
        head = ["--output", output] if output else []
        return subprocess.run([sys.executable, str(SCRIPT), *head, *BRIDGE, str(self.root), *args],
                              capture_output=True, text=True, timeout=30)

    def test_stdout_is_the_document(self):
        result = self.run_cli("P1.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("}\n"))
        self.assertEqual(json.loads(result.stdout), self.brief())

    def test_out_writes_the_file_and_prints_its_path(self):
        target = self.repo / "out" / "brief.json"
        result = self.run_cli("P1.1", "--out", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(target))
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.brief())

    def test_unit_and_inline_flags(self):
        unit_id = units.add_unit(self.root, "P1.1", "Part", {"goal": "g", "files": ["lib/x.py"], "checks": ["V1"]})
        result = self.run_cli("P1.1", "--unit", unit_id, "--inline-reads")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["provenance"]["unit"], unit_id)
        self.assertEqual(doc["reads"][0]["content"], "print('x')\n")

    def test_bridge_owns_its_output_and_refusal_codes(self):
        ok = self.run_cli("P1.1", output="json")  # the dispatcher passes bridge output through, no envelope
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["contract_version"], "exec/v1")
        for output in (None, "json"):
            bad = self.run_cli("P2.1", output=output)
            self.assertEqual(bad.returncode, 1)
            self.assertTrue(bad.stderr.startswith("PHASE_NOT_DETAILED:"), bad.stderr)

    def test_main_takes_the_plan_reference_and_plans_root(self):
        result = subprocess.run([sys.executable, str(SCRIPT), *BRIDGE, self.root.name, "P1.1", "--plans-root",
                                 str(self.plans)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.brief())
        missing = subprocess.run([sys.executable, str(SCRIPT), *BRIDGE, "absent", "P1.1", "--plans-root",
                                  str(self.plans)], capture_output=True, text=True, timeout=30)
        self.assertEqual(missing.returncode, 1)
        self.assertTrue(missing.stderr.startswith("PLAN_NOT_FOUND:"), missing.stderr)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("P1.1", "--repo", "bad").returncode, 2)

    def test_malformed_unit_id_is_refused_by_the_api(self):
        result = self.run_cli("P1.1", "--unit", "x")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("REF_INVALID:"))


class OutTests(BriefCase):
    """``--out`` (formerly in the core envelope tests)."""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *BRIDGE, str(self.root), *args],
                              capture_output=True, text=True, timeout=30)

    def test_out_must_be_a_file_outside_the_plan(self):
        plan = store.load_plan(self.root)
        for bad in ("", str(self.root / "brief-copy.json"), str(self.root / "phases" / "P1" / "P1.1.json"),
                    str(self.root), str(self.plans)):
            with self.subTest(out=bad):
                with self.assertRaises(PlanError) as ctx:
                    brief.write(plan, "P1.1", bad)
                self.assertEqual(ctx.exception.code, "OUT_INVALID")
        self.assertFalse((self.root / "brief-copy.json").exists())

    def test_a_refused_out_leaves_the_plan_untouched(self):
        before = (self.root / "phases" / "P1" / "P1.1.json").read_bytes()
        result = self.run_cli("P1.1", "--out", str(self.root / "phases" / "P1" / "P1.1.json"))
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("OUT_INVALID:"), result.stderr)
        self.assertEqual((self.root / "phases" / "P1" / "P1.1.json").read_bytes(), before)

    def test_malformed_ids_are_refused_by_the_api_not_the_parser(self):
        for argv, code in ((("P1.1", "--unit", "x"), "REF_INVALID"), (("P1", ), "REF_INVALID"),
                           (("P1.1", "--unit", "U9"), "REF_UNKNOWN")):
            with self.subTest(argv=argv):
                result = self.run_cli(*argv)
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stderr.startswith(f"{code}:"), result.stderr)

    def test_out_writes_a_new_file_and_reports_its_path(self):
        target = self.plans.parent / "briefs" / "p1.json"
        result = self.run_cli("P1.1", "--out", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{target.resolve()}\n")
        self.assertEqual(json.loads(target.read_text())["input_id"].split("@")[0], "PLAN1.P1.1")


class RefReadTests(test_lifecycle.LifeCase):
    """Reads by reference (formerly in the core context tests): exec/v1 reads stay path-based."""

    add_design = test_context.JsonContextTests.add_design

    def test_the_brief_keeps_exec_reads_path_based(self):
        self.add_design()
        test_context.force_patch(self.root, "P1.1", {"reads": [
            {"ref": "knowledge/design#steps", "why": "steps", "required": True}]})
        read, = brief.build(self.load(), "P1.1")["reads"]
        self.assertNotIn("ref", read)
        self.assertEqual((read["path"], read["section"]), ("@plan/knowledge/design.json", "steps"))

    def test_required_ref_sections_refuse_the_brief_without_mutation(self):
        self.add_design()
        for extra in ({"ref": "knowledge/design#missing"},
                      {"ref": "knowledge/design", "section": "missing"},
                      {"ref": "knowledge/design#Steps"}):  # fragments name ids, not titles
            with self.subTest(extra=extra):
                test_context.force_patch(self.root, "P1.1", {"reads": [{**extra, "why": "needed", "required": True}]})
                self.refused("READ_MISSING", lambda root: brief.build(self.load(), "P1.1"))

    def test_required_ref_section_titles_remain_readable_via_section_key(self):
        self.add_design()
        ops.patch(self.load(), "plan", {"settings": {"context_pack": "legacy"}})  # scoped drops reads held by documents
        test_context.force_patch(self.root, "P1.1", {"reads": [
            {"ref": "knowledge/design", "section": "Steps", "why": "needed", "required": True}]})
        self.assertEqual(brief.build(self.load(), "P1.1")["reads"][0]["content"]["sections"][0]["id"], "steps")

    def test_unresolved_optional_ref_refuses_brief_but_declared_missing_file_is_allowed(self):
        test_context.force_patch(self.root, "P1.1", {"reads": [
            {"ref": "artifact/catalog", "why": "optional", "required": False}]})
        self.refused("REF_UNRESOLVED", lambda root: brief.build(self.load(), "P1.1"))
        test_context.force_patch(self.root, "P1.2", {"artifacts": [
            {"id": "catalog", "path": "catalog.json", "role": "output"}]})
        read, = brief.build(self.load(), "P1.1")["reads"]
        self.assertEqual((read["path"], read["exists"]), ("catalog.json", False))
        self.assertNotIn("ref", read)


class CrossPlanTests(test_refs.RefsCase):
    """Decisions of other plans (formerly in the core refs tests): resolved, refused, foreign repositories."""

    def setUp(self):
        super().setUp()
        (self.plans.parent / "lib").mkdir()
        (self.plans.parent / "lib" / "x.py").write_text("x\n", encoding="utf-8")

    def brief(self, **kwargs):
        return brief.build(self.load(), "P1.1", **kwargs)

    def test_resolved_decision_is_in_the_brief_within_the_closed_schema(self):
        ops.patch(self.root, "P1.1", {"decisions": ["PLAN2.D1"]})
        entry = self.brief()["decisions"][0]
        self.assertEqual(set(entry), {"ref", "loaded", "title", "status", "decision", "rationale", "source"})
        self.assertEqual(entry["source"]["sha256"],
                         hashlib.sha256((self.other / "decisions" / "D1.json").read_bytes()).hexdigest())

    def test_unresolved_required_decision_refuses(self):
        ops.patch(self.root, "P1.1", {"decisions": ["PLAN2.D1", "PLAN8.D3"]})
        with self.assertRaises(PlanError) as ctx:
            self.brief()
        self.assertEqual(ctx.exception.code, "REF_UNRESOLVED")
        self.assertIn("PLAN8.D3", ctx.exception.message)
        self.assertNotIn("PLAN2.D1", ctx.exception.message)

    def test_not_accepted_required_decision_refuses(self):
        key = ops.add_decision(self.other, "Open question", data={"options": [{"id": "A", "text": "x"}]})
        ops.patch(self.root, "P1.1", {"decisions": [f"PLAN2.{key}"]})
        with self.assertRaises(PlanError) as ctx:
            self.brief()
        self.assertEqual(ctx.exception.code, "REF_UNRESOLVED")

    def test_foreign_repository_via_repos(self):
        repo, _ = self.foreign_repo()
        ops.patch(self.root, "P1.1", {"decisions": ["ext:PLAN1.D1"]})
        with self.assertRaises(PlanError) as ctx:
            self.brief()
        self.assertEqual(ctx.exception.code, "REF_UNRESOLVED")
        self.assertTrue(self.brief(repos={"ext": str(repo)})["decisions"][0]["loaded"])

    def test_cli_brief_refuses_and_accepts_repo(self):
        repo, _ = self.foreign_repo()
        ops.patch(self.root, "P1.1", {"decisions": ["ext:PLAN1.D1"]})
        base = [sys.executable, str(SCRIPT), *BRIDGE, str(self.root), "P1.1"]
        refused = subprocess.run(base, capture_output=True, text=True, timeout=30)
        self.assertEqual(refused.returncode, 1)
        self.assertTrue(refused.stderr.startswith("REF_UNRESOLVED: "), refused.stderr)
        ok = subprocess.run([*base, "--repo", f"ext={repo}"], capture_output=True, text=True, timeout=30)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["decisions"][0]["loaded"])

    def test_local_decisions_are_untouched(self):
        key = test_refs.accepted(self.root, "Local")
        ops.patch(self.root, "P1.1", {"decisions": [key]})
        self.assertTrue(self.brief()["decisions"][0]["loaded"])


def legacy_digest(doc: dict) -> str:
    """The formula the bridge used before it took the canonical form from the foundation."""
    payload = {key: value for key, value in doc.items() if key != "digest"}
    if isinstance(payload.get("input_id"), str):
        payload["input_id"] = payload["input_id"].rsplit("@", 1)[0]
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class DigestTests(unittest.TestCase):
    def test_digest_equals_the_legacy_formula_on_a_crafted_document(self):
        doc = {"b": 1, "a": ["ф", {"z": None, "y": True}], "input_id": "PLAN@abcdef012345", "digest": "0" * 64}
        self.assertEqual(brief.canonical_digest(doc), legacy_digest(doc))
        self.assertEqual(brief.canonical_digest({**doc, "input_id": "PLAN@other"}), brief.canonical_digest(doc))
        self.assertNotEqual(brief.canonical_digest({**doc, "b": 2}), brief.canonical_digest(doc))

    def test_digest_equals_the_legacy_formula_on_the_demo_plan(self):
        import tempfile
        for item in ("P1.1", "P1.2"):
            with self.subTest(item=item), tempfile.TemporaryDirectory() as tmp:
                doc = bridge_fixture.brief_of_demo_plan(tmp, item)
                self.assertEqual(doc["digest"], legacy_digest(doc))
                self.assertEqual(doc["digest"], brief.canonical_digest(doc))


class CoreVerbTests(unittest.TestCase):
    def test_brief_is_no_longer_a_core_verb(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "brief", "PLAN1", "P1.1"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice: 'brief'", result.stderr)

    def test_bridge_list_names_the_brief_verb(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--output", "json", "bridge", "list"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        row, = [r for r in json.loads(result.stdout)["data"]["bridges"] if r["name"] == "planner-orch"]
        self.assertIn("brief", row["verbs"])
        self.assertEqual(row["contract"], "exec/v1")


if __name__ == "__main__":
    unittest.main()
