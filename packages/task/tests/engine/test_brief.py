"""plan.py brief (exec/v1 execution-input): field mapping, units, inline reads, refusals, determinism, read-only."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import brief, lifecycle, ops, units  # noqa: E402

try:
    from . import test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_lifecycle

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"


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

    def test_constraints_keep_order_and_source(self):
        self.assertEqual(self.brief()["constraints"], [
            {"text": "stdlib only", "source": "plan.rules[0]"},
            {"text": "watch the lock", "source": "phase.pitfalls[0]"},
            {"text": "no network", "source": "item.rules[0]"}])

    def test_decisions_upstream_and_lessons(self):
        ops.patch(self.root, "P1.2", {"decisions": ["PLAN3.D4"]})
        self.start("P1.1")
        self.finish("P1.1", "done", notes="shipped")
        lifecycle.log(self.root, "P1.1", "difficulty", "slow", impact="minor")
        doc = self.brief("P1.2")
        self.assertIn({"ref": "PLAN3.D4", "loaded": False}, doc["decisions"])
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
        self.assertEqual(prov["generated_by"]["tool"], "task/plan.py brief")
        self.assertEqual(prov["source_digest"],
                         hashlib.sha256(__import__("task.plan.context", fromlist=["x"]).render(
                             self.load(), "P1.1", with_scout=False).encode()).hexdigest())
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


class DigestTests(BriefCase):
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
        for phrase in ("report_api", "unit return", "plan.py start", "plan.py finish", "task:plan-run"):
            self.assertNotIn(phrase, text)
        doc = json.loads(text)
        for key in ("orchestration", "ready_units", "units", "plan", "brief"):
            self.assertNotIn(key, doc)


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
        subprocess.run([sys.executable, str(SCRIPT), "brief", str(self.root), "P1.1"],
                       capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(tree_hashes(self.root), before)
        self.assertFalse((self.root / "context").exists())


class CliTests(BriefCase):
    def run_cli(self, *args, output=None):
        head = ["--output", output] if output else []
        return subprocess.run([sys.executable, str(SCRIPT), *head, "brief", str(self.root), *args],
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

    def test_json_envelope_and_refusal_codes(self):
        ok = json.loads(self.run_cli("P1.1", output="json").stdout)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["data"]["contract_version"], "exec/v1")
        bad = self.run_cli("P2.1", output="json")
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["error"]["code"], "PHASE_NOT_DETAILED")
        text = self.run_cli("P2.1")
        self.assertEqual(text.returncode, 1)
        self.assertTrue(text.stderr.startswith("PHASE_NOT_DETAILED:"))

    def test_malformed_unit_id_is_a_usage_error(self):
        self.assertEqual(self.run_cli("P1.1", "--unit", "x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
