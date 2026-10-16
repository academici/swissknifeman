"""Every default run option is written down: a key of ``options.DEFAULTS`` (and of its groups) is named in
``docs/conductor.md`` with its default, so no default hides in the code."""
from __future__ import annotations

from pathlib import Path
import unittest

from orch.conductor import options

DOC = (Path(__file__).resolve().parents[1] / "docs" / "conductor.md").read_text(encoding="utf-8")
# keys that a table row does not name by themselves (the row names the group)
GROUPED_ELSEWHERE = {"stages", "skills", "on_error", "fallback_routes", "on_blocked"}


class DefaultsDocumentedTests(unittest.TestCase):
    def test_every_top_level_option_is_named_in_the_docs(self):
        missing = [key for key in options.DEFAULTS if f"`{key}`" not in DOC]
        self.assertEqual(missing, [], "options without a row in docs/conductor.md")

    def test_every_key_of_a_group_is_named_in_the_docs(self):
        missing = []
        for group, value in options.DEFAULTS.items():
            if isinstance(value, dict) and group not in GROUPED_ELSEWHERE:
                missing += [f"{group}.{key}" for key in value if f"`{key}`" not in DOC]
        self.assertEqual(missing, [], "group keys without a mention in docs/conductor.md")

    def test_the_batch_defaults_are_written_down(self):
        for text in ("`--batch`", "`--no-batch`", "`--ready`", "`session`", "`fence`", "`extra_paths`"):
            self.assertIn(text, DOC)


if __name__ == "__main__":
    unittest.main()
