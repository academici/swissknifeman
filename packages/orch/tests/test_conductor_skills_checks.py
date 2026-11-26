"""The checks of the skills of a role before its prompt is built (P9.2): what a skill declares in its ``selection.json``
(``replaced_by``, ``requires_tools``, ``kind``, ``conflicts``, ``exclusive_group``, ``max_tokens``) and the route tools of
the role decide, deterministically, which skills enter the prompt; nothing is guessed from the text and nothing is cut.
Design: knowledge ``p9-prompt#dedupe``. ``--tools`` of the route is the launch-catalog argument of a Claude Code role
(``configs/launch-catalog.json``: ``"--tools", "Read,Grep,Glob"``; ``--tools ""`` is a role with no tools)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from orch.conductor import contract, engine, options as opts, prompts

INPUT = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "exec" / "v1" / "valid" / "execution-input"
                    / "adhoc.json").read_text(encoding="utf-8"))
ROUTE = {"provider": "claude-code", "model": "m", "argv": ["claude", "-p", "--tools", "Read,Grep,Glob"]}


class Progress:
    def __init__(self):
        self.lines = []

    def emit(self, *args, **fields):
        self.lines.append(fields)


class SkillChecksTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.eng = engine.Conductor.__new__(engine.Conductor)
        self.eng.project = self.dir
        self.eng.env = dict(os.environ)
        self.eng.progress = Progress()
        self.eng.conductor = {"provider": "claude-code"}
        self.item = type("I", (), {
            "ref": "W1", "state": {}, "routes": {"executor": dict(ROUTE)},
            "options": {"skills": {"executor": []}, "stages": [], "limits": dict(opts.DEFAULT_LIMITS),
                        "instructions": {"isolate_roles": ["executor"]}},
            "input_doc": {}})()

    def skill(self, name, body="Do the thing.", **selection):
        folder = self.dir / ".claude" / "skills" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {name}\n---\n\n{body}\n", encoding="utf-8")
        if selection:
            (folder / "selection.json").write_text(json.dumps({"schema": "skill-selection/v1", "kind": "domain",
                                                              "decision": "KEEP", **selection}), encoding="utf-8")
        return name

    def use(self, *names):
        self.item.options["skills"]["executor"] = list(names)

    def excluded(self):
        self.eng._skills(self.item, "executor")
        return {row["id"]: row["reason"] for row in self.eng._skills_excluded(self.item, "executor")}

    # --- every outcome ---------------------------------------------------------------------------------------------

    def test_skills_without_a_sidecar_are_all_kept(self):
        self.use(self.skill("a"), self.skill("b"))
        self.assertEqual(self.eng._skills(self.item, "executor"), ["a", "b"])
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"a": "Do the thing.", "b": "Do the thing."})
        self.assertEqual(self.eng._skills_excluded(self.item, "executor"), [])
        self.assertEqual(self.eng.progress.lines, [])

    def test_a_skill_replaced_by_a_role_contract_or_a_schema_is_excluded(self):
        self.use(self.skill("contract", replaced_by="orch/roles/executor.md"),
                 self.skill("shape", replaced_by="orch/schemas/conductor/v1/stage-report.schema.json"),
                 self.skill("kept"))
        self.assertEqual(self.excluded(), {"contract": "duplicated_by_role_contract", "shape": "duplicated_by_role_contract"})
        self.assertEqual(self.eng._skills(self.item, "executor"), ["kept"])
        self.assertEqual(list(self.eng._skill_texts(self.item, "executor")), ["kept"])

    def test_a_skill_replaced_by_a_script_or_a_hook_stays(self):
        self.use(self.skill("script", replaced_by="orch/lib/orch/conductor/progress.py"),
                 self.skill("hook", replaced_by="configs/claude-code/hooks/git-guardrails"))
        self.assertEqual(self.excluded(), {})
        self.assertEqual(self.eng._skills(self.item, "executor"), ["script", "hook"])

    def test_a_tool_the_route_lacks_excludes_the_skill(self):
        self.use(self.skill("shell", requires_tools=["Bash"]), self.skill("reader", requires_tools=["Read", "Grep"]))
        self.assertEqual(self.excluded(), {"shell": "tool_missing"})

    def test_a_route_with_no_tools_list_does_not_exclude_by_tools(self):
        self.item.routes["executor"] = {"provider": "codex", "argv": ["codex", "exec"]}
        self.use(self.skill("shell", requires_tools=["Bash"]))
        self.assertEqual(self.excluded(), {})

    def test_an_empty_tools_list_is_a_role_with_no_tools(self):
        self.item.routes["executor"] = {"provider": "claude-code", "argv": ["claude", "-p", "--tools", ""]}
        self.use(self.skill("shell", requires_tools=["Bash"]), self.skill("plain"))
        self.assertEqual(self.excluded(), {"shell": "tool_missing"})

    def test_an_interactive_skill_is_excluded_for_a_headless_role_even_when_the_tool_is_listed(self):
        self.item.routes["executor"] = {"provider": "claude-code", "argv": ["claude", "-p", "--tools", "Read,AskUserQuestion"]}
        self.use(self.skill("ask", requires_tools=["AskUserQuestion"]))
        self.assertEqual(self.excluded(), {"ask": "interactive_in_headless"})

    def test_the_second_persona_is_excluded(self):
        self.use(self.skill("first", kind="persona"), self.skill("second", kind="persona"), self.skill("other", kind="domain"))
        self.assertEqual(self.excluded(), {"second": "persona_duplicate"})
        self.assertEqual(self.eng._skills(self.item, "executor"), ["first", "other"])

    def test_a_persona_that_another_check_excluded_does_not_count(self):
        self.use(self.skill("first", kind="persona", requires_tools=["Bash"]), self.skill("second", kind="persona"))
        self.assertEqual(self.excluded(), {"first": "tool_missing"})

    def test_a_declared_conflict_of_two_included_skills_stops_the_role(self):
        self.use(self.skill("a", conflicts=["bucket/b"]), self.skill("b"))
        with self.assertRaises(engine.Stop) as raised:
            self.eng._skills(self.item, "executor")
        self.assertEqual(raised.exception.code, "PROMPT_CONFLICT")
        self.assertIn("a", raised.exception.message)
        self.assertIn("b", raised.exception.message)

    def test_a_conflict_with_an_excluded_or_absent_skill_is_no_conflict(self):
        self.use(self.skill("a", conflicts=["bucket/b", "bucket/gone"]),
                 self.skill("b", requires_tools=["Bash"]))
        self.assertEqual(self.excluded(), {"b": "tool_missing"})
        self.assertEqual(self.eng._skills(self.item, "executor"), ["a"])

    def test_a_conflict_matches_the_bridge_id_of_an_auto_skill(self):
        bridge = [{"name": "a", "id": "bucket/a", "path": str(self.dir / ".claude/skills/a/SKILL.md")},
                  {"name": "b", "id": "bucket/b", "path": str(self.dir / ".claude/skills/b/SKILL.md")}]
        self.skill("a", conflicts=["bucket/b"])
        self.skill("b")
        for row in bridge:
            row["skill_md_sha256"] = hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest()
        self.item.options["skills"]["executor"] = [opts.AUTO_SKILLS]
        self.item.state["skills_auto"] = {"executor": {"skills": bridge, "excluded": [], "discoverable": [], "tokens": 0}}
        with self.assertRaises(engine.Stop) as raised:
            self.eng._skills(self.item, "executor")
        self.assertEqual(raised.exception.code, "PROMPT_CONFLICT")
        self.assertIn("bucket/a", raised.exception.message)

    def test_an_exclusive_group_keeps_one_and_the_extra_are_excluded(self):
        self.use(self.skill("a", exclusive_group="docker"), self.skill("b", exclusive_group="docker"),
                 self.skill("c", exclusive_group="docker"), self.skill("d", exclusive_group="pinia"))
        self.assertEqual(self.excluded(), {"b": "exclusive_group", "c": "exclusive_group"})
        self.assertEqual(self.eng._skills(self.item, "executor"), ["a", "d"])

    def test_the_group_php_architecture_allows_two(self):
        self.use(*[self.skill(name, exclusive_group="php-architecture") for name in ("a", "b", "c")])
        self.assertEqual(self.excluded(), {"c": "exclusive_group"})

    def test_a_text_over_the_skill_budget_is_excluded_not_cut_and_gives_a_beacon(self):
        self.item.options["limits"]["skill_tokens_max"] = 50
        self.use(self.skill("big", body="word " * 400), self.skill("small", body="short"))
        self.assertEqual(self.excluded(), {"big": "over_budget"})
        self.assertEqual(list(self.eng._skill_texts(self.item, "executor")), ["small"])
        beacons = [line for line in self.eng.progress.lines if line.get("reason_code") == "SKILL_EXCLUDED"]
        self.assertEqual(len(beacons), 1)
        self.assertIn("big", beacons[0]["message"])
        self.assertIn("over_budget", beacons[0]["message"])

    def test_the_default_skill_budget_is_5000_tokens_and_a_long_text_is_never_cut(self):
        self.assertEqual(opts.DEFAULT_LIMITS["skill_tokens_max"], 5000)
        body = "word " * 3000  # 15000 characters: above the old 12000-character cut, below 5000 tokens
        self.use(self.skill("long", body=body))
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"long": body.strip()})

    def test_the_budget_zero_switches_the_limit_off(self):
        self.item.options["limits"]["skill_tokens_max"] = 0
        self.use(self.skill("big", body="word " * 4000))
        self.assertEqual(self.excluded(), {})

    def test_max_tokens_of_the_sidecar_is_a_budget_of_its_own(self):
        self.use(self.skill("tight", body="word " * 400, max_tokens=20))
        self.assertEqual(self.excluded(), {"tight": "over_budget"})

    def test_a_role_that_loads_skills_itself_has_no_text_to_weigh(self):
        self.item.options["instructions"]["isolate_roles"] = []
        self.item.options["limits"]["skill_tokens_max"] = 10
        self.use(self.skill("big", body="word " * 400), self.skill("shell", requires_tools=["Bash"]))
        self.assertEqual(self.excluded(), {"shell": "tool_missing"})
        self.assertEqual(self.eng._skills(self.item, "executor"), ["big"])

    # --- state, beacons, manifest ----------------------------------------------------------------------------------

    def test_every_exclusion_gives_a_beacon_once_and_the_verdict_is_kept_in_the_state(self):
        self.use(self.skill("shell", requires_tools=["Bash"]))
        self.eng._skills(self.item, "executor")
        self.eng._skill_texts(self.item, "executor")
        self.eng._skills(self.item, "executor")
        beacons = [line for line in self.eng.progress.lines if line.get("reason_code") == "SKILL_EXCLUDED"]
        self.assertEqual(len(beacons), 1)
        self.assertIn("tool_missing", beacons[0]["message"])
        self.assertEqual(self.item.state["skills_checked"]["executor"]["excluded"],
                         [{"id": "shell", "reason": "tool_missing"}])

    def test_an_excluded_skill_is_not_named_in_the_prompt_and_the_manifest_lists_it(self):
        self.use(self.skill("shell", requires_tools=["Bash"]), self.skill("plain", body="Plain rules."))
        names = self.eng._skills(self.item, "executor")
        texts = self.eng._skill_texts(self.item, "executor")
        blocks = prompts.scout(INPUT, item="W1", step="scout.1", skills=names, skill_texts=texts)
        text = prompts.render(blocks)
        self.assertIn("## Skill `plain`", text)
        self.assertNotIn("shell", text)
        doc = prompts.manifest(blocks, step="scout.1", role="executor", route=ROUTE,
                               excluded=self.eng._skills_excluded(self.item, "executor"))
        self.assertEqual(doc["excluded"], [{"id": "shell", "reason": "tool_missing"}])

    def test_a_skill_without_a_file_is_left_to_the_provider(self):
        self.use("missing")
        self.assertEqual(self.eng._skills(self.item, "executor"), ["missing"])
        self.assertEqual(self.excluded(), {})

    def test_the_budget_limit_is_a_run_option_with_bounds(self):
        self.assertEqual(opts.layer_problems({"limits": {"skill_tokens_max": 0}}), [])
        self.assertEqual(opts.layer_problems({"limits": {"skill_tokens_max": 8000}}), [])
        self.assertEqual(len(opts.layer_problems({"limits": {"skill_tokens_max": -1}})), 1)

    def test_the_schema_of_run_options_knows_the_limit_and_stays_closed(self):
        # valid/invalid fixtures of run-options live outside the write set of P9.2; the cases are checked here
        self.assertEqual(contract.problems({"limits": {"skill_tokens_max": 3000}}, "run-options"), [])
        self.assertTrue(contract.problems({"limits": {"skill_tokens_max": "3000"}}, "run-options"))
        self.assertTrue(contract.problems({"limits": {"skill_token_max": 3000}}, "run-options"))


if __name__ == "__main__":
    unittest.main()
