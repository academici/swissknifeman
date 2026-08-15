"""P4.2 regression tests for the provider-neutral Skill Core template."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = PACKAGE_ROOT / "SKILL_TEMPLATE.md"
GENERATED = PACKAGE_ROOT / "generate-skill" / "generate-skill" / "snippets" / "SKILL_TEMPLATE.md"
GENERATOR = PACKAGE_ROOT / "scripts" / "generate-skill-template.py"


class SkillTemplateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CANONICAL.read_text(encoding="utf-8")
        self.frontmatter = self.text.split("---", 2)[1]

    def test_generated_copy_is_byte_stable(self) -> None:
        result = subprocess.run(["python3", str(GENERATOR), "--check"], capture_output=True,
                                text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(CANONICAL.read_bytes(), GENERATED.read_bytes())

    def test_minimum_core_has_early_trigger_contract_and_progressive_links(self) -> None:
        required = ("# Skill purpose", "## Trigger checks", "## Inputs and outputs",
                    "## Invariants and risk", "## Workflow", "## Resources", "## Optional failure modes",
                    "## Provenance")
        positions = [self.text.index(heading) for heading in required]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(self.text.index("## Trigger checks"), 900)
        for label in ("Positive:", "Negative:", "Boundary:"):
            self.assertIn(label, self.text)
        self.assertTrue("references/" in self.text or "snippets/" in self.text)
        self.assertIn("linked observed failure or ablation record", self.text)

    def test_shared_frontmatter_has_no_provider_controls_and_risk_matches_intent(self) -> None:
        for field in ("name:", "description:", "risk:", "invocation_intent:", "capabilities:",
                      "inputs:", "outputs:", "resources:", "provenance:"):
            self.assertIn(field, self.frontmatter)
        for forbidden in ("adapters:", "provider:", "claude:", "codex:", "cursor:", "fable:",
                          "model:", "effort:", "approval:", "sandbox:"):
            self.assertNotIn(forbidden, self.frontmatter)
        self.assertIn("for `write` and `external` risk", self.text)


if __name__ == "__main__":
    unittest.main()
