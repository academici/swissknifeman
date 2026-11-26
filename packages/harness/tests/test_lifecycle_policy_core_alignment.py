"""P4.0.3 policy-core drift detectors against Claude compatibility hooks."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.lifecycle_daemon_safety_core import RULES as DAEMON_RULES
from harness.lifecycle_changelog_gate_core import RELEASE_TYPES as CHANGELOG_TYPES
from harness.lifecycle_changelog_gate_core import RULES as CHANGELOG_RULES
from harness.lifecycle_git_guardrails_core import RULES as GIT_RULES
from harness.lifecycle_policy_core import POLICY_MODES

PACKAGE = Path(__file__).resolve().parents[1]
CLAUDE_DAEMON = PACKAGE / "configs/claude-code/hooks/daemon-safety/block-daemon-ops.sh"
CLAUDE_CHANGELOG = PACKAGE / "configs/claude-code/hooks/changelog-gate/changelog-gate.py"
CLAUDE_GIT = PACKAGE / "configs/claude-code/hooks/git-guardrails/block-dangerous-git.sh"
CLAUDE_PACK_GUARD = PACKAGE / "configs/claude-code/hooks/pack-guard/pack-guard.py"


def _bash_array_patterns(text: str, name: str):
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith(f"{name}=("):
            start = index + 1
            break
    if start is None:
        raise AssertionError(f"array {name} not found")
    patterns = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped == ")":
            break
        match = re.search(r'"([^"]+)"', stripped)
        if match is not None:
            patterns.append(match.group(1))
    return tuple(patterns)


class LifecyclePolicyCoreAlignmentTests(unittest.TestCase):
    def test_daemon_safety_core_contract_shape(self):
        for rule in DAEMON_RULES:
            self.assertTrue(rule.id)
            self.assertTrue(rule.pattern)
            self.assertTrue(rule.reason)
            self.assertTrue(rule.tier)

    def test_daemon_safety_core_patterns_match_claude_hook(self):
        script = CLAUDE_DAEMON.read_text(encoding="utf-8")
        claude_patterns = (
            *_bash_array_patterns(script, "KILL_PATTERNS"),
            *_bash_array_patterns(script, "RM_PATTERNS"),
        )
        core_patterns = tuple(rule.pattern for rule in DAEMON_RULES)
        self.assertEqual(core_patterns, claude_patterns)

    def test_git_guardrails_core_contract_shape(self):
        for rule in GIT_RULES:
            self.assertTrue(rule.id)
            self.assertTrue(rule.pattern)
            self.assertTrue(rule.reason)
            self.assertTrue(rule.tier)

    def test_git_guardrails_core_patterns_match_claude_hook(self):
        script = CLAUDE_GIT.read_text(encoding="utf-8")
        claude_patterns = _bash_array_patterns(script, "DANGEROUS_PATTERNS")
        core_patterns = tuple(rule.pattern for rule in GIT_RULES)
        self.assertEqual(core_patterns, claude_patterns)

    def test_changelog_gate_core_contract_shape(self):
        for rule in CHANGELOG_RULES:
            self.assertTrue(rule.id)
            self.assertTrue(rule.pattern)
            self.assertTrue(rule.reason)
            self.assertTrue(rule.tier)

    def test_changelog_gate_core_types_match_claude_hook(self):
        script = CLAUDE_CHANGELOG.read_text(encoding="utf-8")
        match = re.search(r"_CONTENT_TYPES\s*=\s*\(([^)]*)\)", script)
        self.assertIsNotNone(match)
        claude_types = tuple(re.findall(r'"([^"]+)"', match.group(1)))
        self.assertEqual(CHANGELOG_TYPES, claude_types)

    def test_pack_guard_mode_ladder_matches_claude_hook(self):
        script = CLAUDE_PACK_GUARD.read_text(encoding="utf-8")
        match = re.search(r"_MODES\s*=\s*\(([^)]*)\)", script)
        self.assertIsNotNone(match)
        claude_modes = tuple(re.findall(r'"([^"]+)"', match.group(1)))
        self.assertEqual(POLICY_MODES, claude_modes)


if __name__ == "__main__":
    unittest.main()
