from __future__ import annotations

from pathlib import Path
import re
import unittest

from orch.contracts import LIFECYCLE_PHRASES

ROLES = Path(__file__).resolve().parents[1] / "roles"
ROLE_IDS = ("context-scout", "executor", "bounded-implementer", "reviewer", "registrar")
WORKER_ROLES = ("context-scout", "executor", "bounded-implementer", "reviewer")
SECTIONS = ("## You receive", "## You do", "## You never", "## You return")
EXPORT = re.compile(r"<!-- export:(begin|end) ([\w-]+) -->")


def _text(role: str) -> str:
    return (ROLES / f"{role}.md").read_text(encoding="utf-8")


def _exports(text: str) -> dict[str, str]:
    """Exported fragments by name; raises ``ValueError`` on unpaired or nested markers."""
    found: dict[str, str] = {}
    open_name, start = None, 0
    for match in EXPORT.finditer(text):
        kind, name = match.groups()
        if kind == "begin":
            if open_name is not None or name in found:
                raise ValueError(f"unexpected begin {name}")
            open_name, start = name, match.end()
        else:
            if open_name != name:
                raise ValueError(f"unexpected end {name}")
            found[name], open_name = text[start:match.start()], None
    if open_name is not None:
        raise ValueError(f"unclosed {open_name}")
    return found


class RolesTextTests(unittest.TestCase):
    def test_every_role_exists_with_four_sections_in_order(self):
        for role in ROLE_IDS:
            with self.subTest(role=role):
                text = _text(role)
                self.assertTrue(text.startswith("# "))
                positions = [text.find(f"\n{heading}\n") for heading in SECTIONS]
                self.assertNotIn(-1, positions)
                self.assertEqual(positions, sorted(positions))

    def test_worker_roles_carry_no_lifecycle_instruction(self):
        for role in WORKER_ROLES:
            text = _text(role)
            for phrase in (*LIFECYCLE_PHRASES, "plan.py"):
                with self.subTest(role=role, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_export_markers_are_paired(self):
        for role in ROLE_IDS:
            with self.subTest(role=role):
                _exports(_text(role))

    def test_executor_exports_a_clean_handoff(self):
        handoff = _exports(_text("executor")).get("handoff")
        self.assertTrue(handoff and handoff.strip())
        for phrase in (*LIFECYCLE_PHRASES, "plan.py"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, handoff)
        for field in ("summary", "changed_paths", "checks_run", "evidence", "open_issues"):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", handoff)

    def test_reviewer_references_the_review_skills(self):
        text = _text("reviewer")
        self.assertIn("quality:code-review", text)
        self.assertIn("quality:artifact-review", text)

    def test_marker_parser_rejects_unpaired_markers(self):
        for text in ("<!-- export:begin a -->", "<!-- export:end a -->",
                     "<!-- export:begin a --><!-- export:begin b --><!-- export:end b --><!-- export:end a -->"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                _exports(text)


if __name__ == "__main__":
    unittest.main()
