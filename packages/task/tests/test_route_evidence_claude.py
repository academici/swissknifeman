"""Claude Code session-bound route provenance."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402

from task import route_evidence, route_evidence_claude


class ClaudeRouteEvidenceTests(unittest.TestCase):
    def test_local_owner_invocation_survives_addition_but_not_revoke(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._session(Path(directory))
            options = dict(expected_invocation="/task:plan-run PLAN P0.15", expected_cwd="/workspace/repo",
                           session_id="claude-1", state_root=directory, require_current_owner_invocation=True,
                           allow_additive_owner_followup=True)
            original = route_evidence_claude.capture_current(**options)
            for message in ("Also explain the result", "revoke this grant"):
                with path.open("a") as stream:
                    stream.write(json.dumps({"type": "user", "message": {"role": "user", "content": message}}) + "\n")
                if message.startswith("revoke"):
                    with self.assertRaisesRegex(route_evidence.RouteEvidenceError, "ROUTE_LAUNCH_MISMATCH"):
                        route_evidence_claude.capture_current(**options)
                else:
                    self.assertEqual(route_evidence_claude.capture_current(**options)["owner_message_digest"], original["owner_message_digest"])

    def _session(self, root: Path, *, session_id="claude-1", invocation=None,
                 model="claude-opus-5", effort="high", cwd="/workspace/repo"):
        project = root / "-workspace-repo"
        project.mkdir(parents=True)
        invocation = invocation or "/task:plan-run PLAN P0.15"
        command, _, arguments = invocation.partition(" ")
        rows = [
            {"type": "user", "sessionId": session_id, "cwd": cwd,
             "message": {"role": "user", "content":
                         f"<command-name>{command}</command-name>\n"
                         f"<command-args>{arguments}</command-args>"}},
            {"type": "assistant", "sessionId": session_id, "cwd": cwd,
             "effort": effort, "message": {"role": "assistant", "model": model}},
        ]
        path = project / f"{session_id}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def test_exact_opus_high_is_bound_to_claude_session(self):
        with tempfile.TemporaryDirectory() as directory:
            self._session(Path(directory))
            evidence = route_evidence_claude.capture_current(
                expected_invocation="/task:plan-run PLAN P0.15",
                expected_cwd="/workspace/repo", session_id="claude-1", state_root=directory)
        self.assertEqual(evidence["model"], "claude-opus-5")
        self.assertEqual(evidence["model_class"], "frontier")
        self.assertEqual(evidence["effort"], "high")
        self.assertEqual(evidence["source"], "provider-thread-state")
        self.assertEqual(evidence["thread_id"], "claude-1")

    def test_lower_route_remains_a_real_undershoot(self):
        with tempfile.TemporaryDirectory() as directory:
            self._session(Path(directory), model="claude-haiku-5", effort="low")
            actual = route_evidence_claude.capture_current(
                expected_invocation="/task:plan-run PLAN P0.15",
                expected_cwd="/workspace/repo", session_id="claude-1", state_root=directory)
        required = {"model_class": "frontier", "effort": "high"}
        self.assertEqual(route_evidence.dispatch_guard(required, actual, ()), "ROUTE_UNDERSHOOT")

    def test_owner_grant_requires_latest_user_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._session(Path(directory))
            options = dict(expected_invocation="/task:plan-run PLAN P0.15", expected_cwd="/workspace/repo",
                           session_id="claude-1", state_root=directory, require_current_owner_invocation=True)
            self.assertIn("owner_message_digest", route_evidence_claude.capture_current(**options))
            with path.open("a") as stream:
                stream.write(json.dumps({"type": "user", "message": {"role": "user", "content": "Review only"}}) + "\n")
            with self.assertRaisesRegex(route_evidence.RouteEvidenceError, "ROUTE_LAUNCH_MISMATCH"):
                route_evidence_claude.capture_current(**options)

    def test_missing_session_record_is_unavailable_not_undershoot(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(route_evidence.RouteEvidenceError,
                                        "ROUTE_LAUNCH_UNAVAILABLE"):
                route_evidence_claude.capture_current(
                    expected_invocation="/task:plan-run PLAN P0.15",
                    expected_cwd="/workspace/repo", session_id="claude-1",
                    state_root=directory)

    def test_provider_neutral_resolver_selects_claude_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            self._session(Path(directory))
            with patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "claude-1"}, clear=True):
                evidence = route_evidence.capture_launch(
                    expected_invocation="task:plan-run PLAN P0.15",
                    expected_cwd="/workspace/repo", state_root=directory)
        self.assertEqual(evidence["source_version"], "claude-project-jsonl-v1")


if __name__ == "__main__":
    unittest.main()
