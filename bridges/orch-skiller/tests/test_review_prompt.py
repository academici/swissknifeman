"""The reviewer prompt names the review skills that this bridge declares for the role."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import unittest

BRIDGE = Path(__file__).resolve().parents[1]
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

import partners  # noqa: E402

ORCH = partners.find_orch_root()


@unittest.skipUnless(ORCH, "orch partner not found (set SKM_ORCH_ROOT)")
class ReviewPrompt(unittest.TestCase):
    def test_reviewer_prompt_lists_code_review_skill(self):
        partners.use_aicore()  # orch imports the foundation
        lib = str(ORCH / "lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        adhoc, render = importlib.import_module("orch.adhoc"), importlib.import_module("orch.render")
        skills = json.loads((BRIDGE / "role-skills.json").read_text(encoding="utf-8"))["roles"]["reviewer"]
        manifest, text = render.load_role("reviewer")
        doc = adhoc.build_adhoc_input(None, [], review="main..feature/x")
        out = render.render_prompt(doc, {**manifest, "skills": skills}, text)
        head = out.partition("\n---\n")[0]
        self.assertIn("- `quality:code-review` (required)", head)
        self.assertIn("**Read only**: yes", out)


if __name__ == "__main__":
    unittest.main()
