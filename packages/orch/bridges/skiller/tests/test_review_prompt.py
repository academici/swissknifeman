"""The reviewer prompt names the review skills that this bridge declares for the role."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

BRIDGE = Path(__file__).resolve().parents[1]
ORCH = BRIDGE.parents[1]
if str(ORCH / "lib") not in sys.path:
    sys.path.insert(0, str(ORCH / "lib"))

from orch import adhoc, render  # noqa: E402


class ReviewPrompt(unittest.TestCase):
    def test_reviewer_prompt_lists_code_review_skill(self):
        skills = json.loads((BRIDGE / "role-skills.json").read_text(encoding="utf-8"))["roles"]["reviewer"]
        manifest, text = render.load_role("reviewer")
        doc = adhoc.build_adhoc_input(None, [], review="main..feature/x")
        out = render.render_prompt(doc, {**manifest, "skills": skills}, text)
        head = out.partition("\n---\n")[0]
        self.assertIn("- `quality:code-review` (required)", head)
        self.assertIn("**Read only**: yes", out)


if __name__ == "__main__":
    unittest.main()
