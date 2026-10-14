"""selection.json sidecars (skill-selection/v1): check, report, registry ingest and the real library."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import tests.fixtures as fx
from skiller import selection
from skiller.common import Env
from skiller.registry import build_registry

PKG_ROOT = Path(__file__).resolve().parents[1]


def sidecar(**fields):
    return dict({"schema": "skill-selection/v1", "kind": "domain", "decision": "KEEP"}, **fields)


class SelectionFixtureCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root, self.env = fx.make_registry(Path(self._tmp.name))

    def put(self, skill, document):
        (self.root / "skills" / skill / "selection.json").write_text(json.dumps(document), encoding="utf-8")

    def groups(self, groups):
        (self.root / "configs").mkdir(exist_ok=True)
        (self.root / "configs" / "exclusive-groups.json").write_text(
            json.dumps({"schema": "exclusive-groups/v1", "groups": groups}), encoding="utf-8")

    def test_no_sidecars_is_green(self):
        self.assertEqual(selection.check(self.root), [])

    def test_valid_sidecar_and_group_pass(self):
        self.groups({"stack": {"description": "d", "max": 1, "members": ["php/code-style", "php/laravel-conventions"]}})
        self.put("php/code-style", sidecar(exclusive_group="stack", conflicts=["devops/docker"]))
        self.assertEqual(selection.check(self.root), [])

    def test_schema_violation_names_file_and_field(self):
        self.put("php/code-style", sidecar(kind="workflow"))
        problems = selection.check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("skills/php/code-style/selection.json", problems[0])
        self.assertIn("/kind", problems[0])

    def test_unknown_field_and_broken_json_are_problems(self):
        self.put("php/code-style", sidecar(metadata={"selection": "x"}))
        (self.root / "skills/quality/test-writer/selection.json").write_text("{", encoding="utf-8")
        problems = selection.check(self.root)
        self.assertTrue(any("code-style" in p and "metadata" in p for p in problems))
        self.assertTrue(any("test-writer" in p for p in problems))

    def test_conflicts_must_name_other_existing_skills(self):
        self.put("php/code-style", sidecar(conflicts=["php/ghost", "php/code-style"]))
        problems = selection.check(self.root)
        self.assertTrue(any("php/ghost is not a skill" in p for p in problems))
        self.assertTrue(any("names the skill itself" in p for p in problems))

    def test_exclusive_group_must_exist_and_list_the_skill(self):
        self.groups({"stack": {"description": "d", "max": 1, "members": ["php/laravel-conventions"]}})
        self.put("php/code-style", sidecar(exclusive_group="stack"))
        self.put("quality/test-writer", sidecar(exclusive_group="nowhere"))
        problems = selection.check(self.root)
        self.assertTrue(any("does not list php/code-style" in p for p in problems))
        self.assertTrue(any("nowhere is not in" in p for p in problems))

    def test_group_table_is_checked(self):
        self.groups({"a": {"description": "d", "members": ["php/code-style"]},
                     "b": {"description": "d", "max": 0, "members": ["php/code-style"]},
                     "c": {"description": "d", "router": "devops/docker", "members": ["php/code-style"]},
                     "d": {"description": "d", "max": 1, "members": ["php/ghost"]}})
        problems = "\n".join(selection.check(self.root))
        self.assertIn("group a: exactly one of `max` and `router`", problems)
        self.assertIn("group b: `max` must be an integer >= 1", problems)
        self.assertIn("group c: router devops/docker must be a member", problems)
        self.assertIn("group d: member php/ghost is not a skill", problems)

    def test_registry_carries_selection_without_the_schema_marker(self):
        self.put("php/code-style", sidecar(kind="contract", decision="OVERLAY", also=["MERGE"]))
        registry, _meta, _dirs = build_registry(self.env)
        entries = {s["name"]: s for s in registry["skills"]}
        self.assertEqual(entries["code-style"]["selection"],
                         {"kind": "contract", "decision": "OVERLAY", "also": ["MERGE"]})
        self.assertNotIn("selection", entries["docker"])

    def test_sidecar_does_not_change_the_content_hash(self):
        before = {s["name"]: s["content_sha256"] for s in build_registry(self.env)[0]["skills"]}
        self.put("php/code-style", sidecar())
        after = {s["name"]: s["content_sha256"] for s in build_registry(self.env)[0]["skills"]}
        self.assertEqual(before, after)

    def test_report_counts_and_lists_differences(self):
        (self.root / "configs").mkdir(exist_ok=True)
        (self.root / "configs" / "selection-summary.json").write_text(json.dumps(
            {"source": "audit", "total": 4, "decisions": {"KEEP": 2, "ROUTER_ONLY": 1},
             "leaves_runtime": 1, "leaves_runtime_decisions": ["ROUTER_ONLY"]}), encoding="utf-8")
        self.put("php/code-style", sidecar())
        self.put("devops/docker", sidecar(kind="router", decision="ROUTER_ONLY"))
        data = selection.report(self.root)
        self.assertEqual((data["skills"], data["with_selection"]), (4, 2))
        self.assertEqual(data["decisions"], {"KEEP": 1, "ROUTER_ONLY": 1})
        self.assertEqual(data["leaves_runtime"], 1)
        self.assertEqual(data["differences"], [{"decision": "KEEP", "expected": 2, "actual": 1}])
        self.assertIn("php/laravel-conventions", data["without_selection"])

    def test_cli_report_json_and_check_exit_code(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            selection.cmd_selection(self.env, ["report", "--json"])
        self.assertEqual(json.loads(out.getvalue())["skills"], 4)
        self.put("php/code-style", sidecar(kind="workflow"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            selection.cmd_selection(self.env, ["check"])
        self.assertEqual(raised.exception.code, 1)


class SelectionLibraryCase(unittest.TestCase):
    """The real library: every skill has a valid sidecar and the decisions equal the audit summary 3.5."""

    def test_library_is_valid(self):
        self.assertEqual(selection.check(PKG_ROOT), [])

    def test_every_skill_has_a_sidecar_and_the_summary_matches(self):
        data = selection.report(PKG_ROOT)
        self.assertEqual(data["skills"], 209)
        self.assertEqual(data["without_selection"], [])
        self.assertEqual(data["differences"], [])

    def test_registry_file_is_current(self):
        registry = json.loads((PKG_ROOT / "skills.json").read_text(encoding="utf-8"))
        self.assertTrue(all("selection" in s for s in registry["skills"]))


if __name__ == "__main__":
    unittest.main()


class WaveACase(unittest.TestCase):
    """Audit 3.2, wave A, without deletion (D1): the meta-skills stay, select does not preload them."""

    WAVE_A = ("general/implement", "general/complex-task-orchestrator", "general/task-brief-template",
              "general/context-economy", "general/compact-responses", "ai/performance", "general/session-handoff",
              "general/anti-drift", "general/git-safety", "general/spec-interview", "general/grill-with-docs",
              "general/mcp-advisor")

    def sidecars(self):
        return {sid: selection.read_sidecar(path) for sid, path in selection.skill_ids(PKG_ROOT).items()}

    def test_wave_a_skills_exist_and_are_never_selected_without_an_explicit_include(self):
        found = self.sidecars()
        for sid in self.WAVE_A:
            with self.subTest(skill=sid):
                self.assertIn(sid, found)
                doc = found[sid]
                self.assertTrue(doc.get("replaced_by") or not doc.get("triggers"),
                                "needs replaced_by or no triggers, so select cannot reach it")
        self.assertTrue(found["general/implement"]["replaced_by"].endswith("roles/executor.md"))

    def test_every_replaced_by_that_is_a_repository_path_exists(self):
        repo = PKG_ROOT.parent.parent
        for sid, doc in self.sidecars().items():
            dest = doc.get("replaced_by")
            if dest and "/" in dest:
                with self.subTest(skill=sid):
                    self.assertTrue((repo / "packages" / dest).exists(), dest)

    def test_routers_and_personas_have_their_kind(self):
        for sid, doc in self.sidecars().items():
            if doc["decision"] == "ROUTER_ONLY":
                with self.subTest(skill=sid):
                    self.assertEqual(doc["kind"], "router")
            if doc["decision"] == "PERSONA" or sid.startswith("roles/"):
                with self.subTest(skill=sid):
                    self.assertEqual(doc["kind"], "persona")

    def test_deprecated_list(self):
        rows = {row["id"]: row for row in selection.deprecated(PKG_ROOT)}
        self.assertEqual(rows["php/laravel-best-practices"]["decision"], "DEPRECATE")
        self.assertEqual(rows["general/compact-responses"]["decision"], "DELETE")
        self.assertTrue(rows["general/git-safety"]["replaced_by"].endswith("hooks/git-guardrails"))
        self.assertNotIn("quality/code-review", rows)

    def test_presets_of_wave_a_hold_none_of_its_skills(self):
        for name in ("agent-context", "agent-tasks"):
            doc = json.loads((PKG_ROOT / "presets" / f"{name}.json").read_text(encoding="utf-8"))
            with self.subTest(preset=name):
                self.assertFalse(set(doc.get("include", [])) & set(self.WAVE_A))
        tasks = json.loads((PKG_ROOT / "presets" / "agent-tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(tasks["include"], ["general/cross-layer-change-checklist", "oss-dev/to-issues"])

    def test_list_deprecated_prints_json_and_text(self):
        from skiller.listing import cmd_list
        env = Env(PKG_ROOT, "list")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_list(env, ["--deprecated", "--json"])
        ids = [row["id"] for row in json.loads(out.getvalue())["deprecated"]]
        self.assertIn("general/implement", ids)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_list(env, ["--deprecated"])
        self.assertIn("general/anti-drift", out.getvalue())
