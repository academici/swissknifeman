"""Run options ``skills: ["auto"]`` (P8.2): the conductor asks the skills bridge, as a process, for the skills of a role
from the write set of the piece, keeps the answer in the state and reads the SKILL.md files the bridge names."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from orch.conductor import engine, options as opts

BRIDGE = '''\
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
(here / "calls.jsonl").open("a").write(json.dumps(sys.argv[1:]) + "\\n")
if (here / "fail").exists():
    print("boom", file=sys.stderr)
    raise SystemExit(1)
skill = here / "SKILL.md"
print(json.dumps({"role": "executor", "provider": "claude-code",
                  "skills": [{"name": "database", "id": "php/database", "path": str(skill),
                              "reason": "trigger_path", "tokens": 12}],
                  "excluded": [{"id": "php/laravel", "reason": "kind_not_preloaded"}],
                  "discoverable": ["php/laravel"], "tokens": 12, "diagnostics": []}))
'''


class Progress:
    def __init__(self):
        self.lines = []

    def emit(self, *args, **fields):
        self.lines.append(fields)


class SkillsAutoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "bridge.py").write_text(BRIDGE, encoding="utf-8")
        (self.dir / "SKILL.md").write_text("---\nname: database\n---\n\nUse migrations carefully.\n", encoding="utf-8")
        self.eng = engine.Conductor.__new__(engine.Conductor)
        self.eng.project = self.dir
        self.eng.env = dict(os.environ)
        self.eng.progress = Progress()
        self.eng.conductor = {"provider": "claude-code", "skills_bridge": [sys.executable, str(self.dir / "bridge.py")]}
        self.item = type("I", (), {
            "ref": "W1", "state": {}, "routes": {},
            "options": {"skills": {"executor": ["auto"]}, "stages": [],
                        "instructions": {"isolate_roles": ["executor"]}},
            "input_doc": {"scope": {"write_set": ["database/migrations/**"]}}})()

    def calls(self):
        path = self.dir / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_auto_names_and_texts_come_from_the_bridge_answer(self):
        self.assertEqual(self.eng._skills(self.item, "executor"), ["database"])
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {"database": "Use migrations carefully."})

    def test_the_bridge_gets_the_role_provider_project_and_write_set_and_is_asked_once(self):
        self.eng._skills(self.item, "executor")
        self.eng._skill_texts(self.item, "executor")
        self.eng._skills(self.item, "executor")
        (call,) = self.calls()
        self.assertEqual(call[:7], ["--select", "--role", "executor", "--provider", "claude-code", "--project",
                                    str(self.dir)])
        self.assertEqual(call[7:], ["--paths", "database/migrations/**"])
        self.assertEqual(self.item.state["skills_auto"]["executor"]["discoverable"], ["php/laravel"])
        message = self.eng.progress.lines[0]["message"]
        self.assertIn("php/database", message)

    def test_no_bridge_stops_the_piece(self):
        self.eng.conductor["skills_bridge"] = []
        with self.assertRaises(engine.Stop) as raised:
            self.eng._skills(self.item, "executor")
        self.assertEqual(raised.exception.code, "SKILLS_BRIDGE_UNAVAILABLE")

    def test_a_failing_bridge_stops_the_piece_and_nothing_is_kept(self):
        (self.dir / "fail").write_text("")
        with self.assertRaises(engine.Stop) as raised:
            self.eng._skills(self.item, "executor")
        self.assertEqual(raised.exception.code, "SKILLS_SELECT_FAILED")
        self.assertNotIn("executor", self.item.state.get("skills_auto", {}))

    def test_a_list_of_names_does_not_touch_the_bridge(self):
        self.item.options["skills"]["executor"] = ["docs:notes"]
        self.assertEqual(self.eng._skills(self.item, "executor"), ["docs:notes"])
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {})
        self.assertEqual(self.calls(), [])

    def test_a_role_that_runs_with_the_project_instructions_gets_no_texts(self):
        self.item.options["instructions"]["isolate_roles"] = []
        self.assertEqual(self.eng._skill_texts(self.item, "executor"), {})
        self.assertEqual(self.calls(), [])

    def test_auto_cannot_be_listed_with_other_skills(self):
        layer = {"skills": [{"role": "executor", "names": ["auto", "docs:notes"]}]}
        self.assertEqual(len(opts.layer_problems(layer)), 1)
        self.assertEqual(opts.layer_problems({"skills": [{"role": "executor", "names": ["auto"]}]}), [])


if __name__ == "__main__":
    unittest.main()
