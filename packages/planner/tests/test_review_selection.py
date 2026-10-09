"""Storage-independent reviewer options preserve exact routes and remain opt-in."""
import unittest

from planner import review_selection as selection


class ReviewSelectionTests(unittest.TestCase):
    def test_absent_options_do_not_request_review(self):
        for command in ("planner:dev goal", "planner:plan-run PLAN P1.1", "planner:make-workflow dev"):
            self.assertIsNone(selection.invocation_selection(command))
            self.assertIsNone(selection.invocation_selection(command + " --review-effort high"))

    def test_context_effort_and_trailing_slash(self):
        self.assertEqual(selection.reviewer("grok/grok-4.7/500k/hight/"),
                         {"provider": "grok", "model": "grok-4.7", "context_tokens": 500000, "effort": "high"})
        self.assertEqual(selection.canonical_selector("grok/grok-4.7/500k/high/"), "grok/grok-4.7/500000")

    def test_command_effort_defaults_and_explicit_flags(self):
        selected = selection.invocation_selection("$ planner:plan-run PLAN P1.1 --reviewer codex/gpt-6 --review-effort xhigh")
        self.assertEqual(selected, {"provider": "codex", "model": "gpt-6", "effort": "xhigh"})
        self.assertEqual(selection.invocation_selection("/planner:plan-audit PLAN design --reviewer=codex/gpt-6")["effort"], "xhigh")
        self.assertEqual(selection.invocation_selection("planner:review diff --reviewer codex/gpt-6")["effort"], "high")

    def test_conflicts_duplicates_unknown_provider_and_capacity_refuse(self):
        for invocation in (
                "planner:review diff --reviewer codex/gpt-6/low --effort high",
                "planner:review diff --reviewer codex/gpt-6 --reviewer grok/grok-4.7",
                "planner:review diff --reviewer codex/gpt-6 --effort high --review-effort low",
                "planner:review diff --reviewer unknown/model",
                "planner:review diff --reviewer codex/gpt-6/0k",
                "planner:review diff --reviewer codex/gpt-6/low/high",
                "planner:review diff --reviewer",
                "planner:review diff --reviewer codex/gpt-6 --effort nonsense"):
            with self.subTest(invocation=invocation), self.assertRaises(selection.ReviewError):
                selection.invocation_selection(invocation)
