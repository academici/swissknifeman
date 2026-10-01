"""Machine-readable diagnostics for transitive skill dependencies."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.common import resolve_requires_bfs


class RequiresDiagnosticsCase(unittest.TestCase):
    def _resolve(self, seed, nodes, exclude=frozenset()):
        selected = {"root"}
        diagnostics = []

        def lookup(name):
            return nodes.get(name)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            resolved = resolve_requires_bfs(
                seed, lookup, selected, set(exclude), diagnostics=diagnostics)
        return resolved, diagnostics, stderr.getvalue()

    def test_unknown_transitive_requirement_is_stable_and_emitted_once(self):
        nodes = {
            "middle": {
                "key": "middle",
                "requires": ["missing", "missing"],
                "exclude_tokens": {"middle"},
            },
        }
        _resolved, diagnostics, warning = self._resolve(
            [("middle", "root")], nodes)
        self.assertEqual(diagnostics, [{
            "code": "SKILL_REQUIRED_UNKNOWN",
            "severity": "warning",
            "required_skill": "missing",
            "affected_identities": ["middle"],
        }])
        self.assertEqual(
            warning.count("'middle' requires unknown skill 'missing' — pass"), 2)

    def test_excluded_requirement_aggregates_requesters_deterministically(self):
        nodes = {
            "blocked": {
                "key": "blocked",
                "requires": [],
                "exclude_tokens": {"blocked", "bucket/blocked"},
            },
        }
        _resolved, diagnostics, warning = self._resolve(
            [("blocked", "zeta"), ("blocked", "alpha")], nodes,
            exclude={"blocked"})
        self.assertEqual(diagnostics, [{
            "code": "SKILL_REQUIRED_EXCLUDED",
            "severity": "warning",
            "required_skill": "blocked",
            "affected_identities": ["alpha", "zeta"],
        }])
        self.assertEqual(
            warning.count("requires 'blocked', but he's in exclude — dependency missing"), 2)


if __name__ == "__main__":
    unittest.main()
