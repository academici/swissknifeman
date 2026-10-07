from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from orch import render
from orch.contracts import LIFECYCLE_PHRASES

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input"
GOLDEN = Path(__file__).resolve().parent / "golden"
WORKER_ROLES = ("context-scout", "executor", "bounded-implementer", "reviewer")


def fixture(name: str) -> dict:
    return json.loads((INPUTS / f"{name}.json").read_text(encoding="utf-8"))


def prompt(name: str, role: str) -> str:
    manifest, text = render.load_role(role)
    return render.render_prompt(fixture(name), manifest, text)


class RenderTests(unittest.TestCase):
    def test_plan_bound_executor_prompt_matches_golden(self):
        expected = (GOLDEN / "prompt-executor-plan-bound.md").read_text(encoding="utf-8")
        self.assertEqual(prompt("plan-bound", "executor"), expected)

    def test_render_is_deterministic(self):
        for name in ("plan-bound", "adhoc", "review-only"):
            with self.subTest(name=name):
                self.assertEqual(render.render_task_block(fixture(name)), render.render_task_block(fixture(name)))
                self.assertEqual(prompt(name, "executor"), prompt(name, "executor"))

    def test_sections_follow_the_fixed_order(self):
        block = render.render_task_block(fixture("plan-bound"))
        headings = [line[3:] for line in block.splitlines() if line.startswith("## ")]
        order = [title for title, _ in render.SECTIONS]
        self.assertEqual(headings, [title for title in order if title in headings])
        self.assertEqual(headings[0], "Goal")
        self.assertEqual(headings[-1], "Result contract")

    def test_empty_sections_are_omitted(self):
        block = render.render_task_block(fixture("adhoc"))
        headings = [line[3:] for line in block.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["Goal", "Scope", "Acceptance", "Result contract"])
        self.assertNotIn("**Exclude**", block)

    def test_goal_and_checks_are_verbatim(self):
        doc = fixture("plan-bound")
        doc["goal"] = "Keep `ticks`, *stars* and # signs as written"
        doc["acceptance"]["checks"][0]["cmd"] = "echo '```' && python3 -c \"print('x')\"  # tail"
        block = render.render_task_block(doc)
        self.assertIn(doc["goal"], block)
        self.assertIn("````bash\n" + doc["acceptance"]["checks"][0]["cmd"] + "\n````", block)

    def test_procedure_check_is_fenced_text(self):
        block = render.render_task_block(fixture("review-only"))
        self.assertIn("procedure:\n```text\nEvery finding has severity, file:line, failure scenario\n```", block)

    def test_reads_content_is_fenced_json(self):
        doc = fixture("plan-bound")
        doc["reads"][0]["content"] = {"a": [1, "дом"]}
        block = render.render_task_block(doc)
        self.assertIn('```json\n{\n  "a": [\n    1,\n    "дом"\n  ]\n}\n```', block)

    def test_section_helper_matches_block(self):
        doc = fixture("plan-bound")
        block = render.render_task_block(doc)
        for title in ("Goal", "Acceptance"):
            self.assertIn(render.render_section(doc, title), block)
        self.assertEqual(render.render_section(fixture("adhoc"), "Why"), "")
        with self.assertRaises(render.RenderError):
            render.render_section(doc, "Nope")

    def test_read_only_review_prompt_is_read_only(self):
        text = prompt("review-only", "reviewer")
        self.assertIn("**Read only**: yes", text)
        self.assertIn("write_authority: `none`", text)
        self.assertIn("Independent read-only review of diff main..feature/x", text)

    def test_manifest_skills_are_listed_before_the_task_block(self):
        manifest, text = render.load_role("reviewer")
        manifest = {**manifest, "skills": [{"name": "demo:review-method", "required": True, "why": "method"},
                                           {"name": "demo:doc-review", "required": False, "why": "docs"}]}
        out = render.render_prompt(fixture("review-only"), manifest, text)
        head, _, _ = out.partition("\n---\n")
        self.assertIn("- `demo:review-method` (required) — method", head)
        self.assertIn("- `demo:doc-review` (optional) — docs", head)
        self.assertNotIn("## Skills", prompt("review-only", "reviewer"))

    def test_instructions_drift_is_refused(self):
        manifest, text = render.load_role("executor")
        with self.assertRaises(render.RenderError) as caught:
            render.render_prompt(fixture("adhoc"), manifest, text + "\nextra\n")
        self.assertEqual(caught.exception.code, "INSTRUCTIONS_DRIFT")

    def test_worker_prompts_carry_no_lifecycle_phrase(self):
        for role in WORKER_ROLES:
            for name in ("plan-bound", "adhoc", "review-only"):
                for phrase in LIFECYCLE_PHRASES:
                    with self.subTest(role=role, input=name, phrase=phrase):
                        self.assertNotIn(phrase, prompt(name, role))

    def test_unknown_role_is_reported(self):
        with self.assertRaises(render.RenderError) as caught:
            render.load_role("no-such-role")
        self.assertEqual(caught.exception.code, "ROLE_UNREADABLE")

    def test_roles_dir_resolves_instructions_by_name(self):
        manifest, text = render.load_role("executor", ROOT / "roles")
        copy_of = copy.deepcopy(manifest)
        self.assertEqual(render.render_prompt(fixture("adhoc"), copy_of, text), prompt("adhoc", "executor"))


if __name__ == "__main__":
    unittest.main()
