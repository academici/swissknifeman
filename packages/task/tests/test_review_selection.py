"""Storage-independent reviewer options preserve exact routes and remain opt-in."""
import unittest

from task import review_selection as selection


class ReviewSelectionTests(unittest.TestCase):
    def test_absent_options_do_not_request_review(self):
        for command in ("task:dev goal", "task:plan-run PLAN P1.1", "task:make-workflow dev"):
            self.assertIsNone(selection.invocation_selection(command))
            self.assertIsNone(selection.invocation_selection(command + " --review-effort high"))

    def test_context_effort_and_trailing_slash(self):
        self.assertEqual(selection.reviewer("grok/grok-4.7/500k/hight/"),
                         {"provider": "grok", "model": "grok-4.7", "context_tokens": 500000, "effort": "high"})
        self.assertEqual(selection.canonical_selector("grok/grok-4.7/500k/high/"), "grok/grok-4.7/500000")

    def test_command_effort_defaults_and_explicit_flags(self):
        selected = selection.invocation_selection("$ task:plan-run PLAN P1.1 --reviewer codex/gpt-6 --review-effort xhigh")
        self.assertEqual(selected, {"provider": "codex", "model": "gpt-6", "effort": "xhigh"})
        self.assertEqual(selection.invocation_selection("/task:plan-audit PLAN design --reviewer=codex/gpt-6")["effort"], "xhigh")
        self.assertEqual(selection.invocation_selection("task:review diff --reviewer codex/gpt-6")["effort"], "high")

    def test_conflicts_duplicates_unknown_provider_and_capacity_refuse(self):
        for invocation in (
                "task:review diff --reviewer codex/gpt-6/low --effort high",
                "task:review diff --reviewer codex/gpt-6 --reviewer grok/grok-4.7",
                "task:review diff --reviewer codex/gpt-6 --effort high --review-effort low",
                "task:review diff --reviewer unknown/model",
                "task:review diff --reviewer codex/gpt-6/0k",
                "task:review diff --reviewer codex/gpt-6/low/high",
                "task:review diff --reviewer",
                "task:review diff --reviewer codex/gpt-6 --effort nonsense"):
            with self.subTest(invocation=invocation), self.assertRaises(selection.ReviewError):
                selection.invocation_selection(invocation)
