#!/usr/bin/env python3
"""Tests scripts/workflow-policy.py — synthetic workflows, then the real tree of the repository."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "workflow_policy", os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow-policy.py"))
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)

SHA = "11d5960a326750d5838078e36cf38b85af677262"
HEAD = "name: x\non: push\npermissions:\n  contents: read\njobs:\n  a:\n    steps:\n"


class WorkflowPolicyTests(unittest.TestCase):
    def test_pinned_with_comment_passes(self):
        self.assertEqual(policy.check_text("w.yml", HEAD + f"      - uses: actions/checkout@{SHA}  # v4.4.0\n"), [])

    def test_major_tag_is_unpinned(self):
        self.assertIn("ACTION_UNPINNED", " ".join(policy.check_text("w.yml", HEAD + "      - uses: actions/checkout@v4\n")))

    def test_short_sha_is_unpinned(self):
        self.assertIn("ACTION_UNPINNED", " ".join(policy.check_text("w.yml", HEAD + "      uses: a/b@11d5960  # v1\n")))

    def test_sha_without_version_comment(self):
        errors = policy.check_text("w.yml", HEAD + f"      - uses: actions/checkout@{SHA}\n")
        self.assertIn("ACTION_VERSION_COMMENT_MISSING", " ".join(errors))

    def test_local_action_allowed(self):
        self.assertEqual(policy.check_text("w.yml", HEAD + "      - uses: ./.github/actions/setup\n"), [])

    def test_missing_top_permissions(self):
        text = HEAD.replace("permissions:\n  contents: read\n", "") + "    permissions:\n      contents: read\n"
        self.assertIn("WORKFLOW_PERMISSIONS_MISSING", " ".join(policy.check_text("w.yml", text)))

    def test_or_true_is_fail_open(self):
        self.assertIn("STEP_FAIL_OPEN", " ".join(policy.check_text("w.yml", HEAD + "        run: ./scan.sh || true\n")))

    def test_comments_are_not_checked(self):
        self.assertEqual(policy.check_text("w.yml", HEAD + "      # it used to end in `|| true`, uses: a/b@v1\n"), [])

    def test_repository_workflows_follow_the_policy(self):
        self.assertEqual(policy.check(Path(__file__).resolve().parent.parent), [])


if __name__ == "__main__":
    sys.exit(unittest.main())
