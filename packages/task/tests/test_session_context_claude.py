import os
import unittest
from unittest.mock import patch

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from task import session_context, session_context_claude


class ClaudeSessionContextTests(unittest.TestCase):
    def test_reads_only_claude_session_id(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "claude-session-1"}, clear=True):
            context = session_context_claude.current()
        self.assertEqual(context.as_dict(), {
            "provider": "claude-code",
            "session_id": "claude-session-1",
            "source": "CLAUDE_CODE_SESSION_ID",
        })

    def test_absent_session_id_is_not_an_adapter_match(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(session_context_claude.current())

    def test_whitespace_session_id_fails_closed(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "bad id"}, clear=True):
            with self.assertRaisesRegex(session_context.SessionContextError, "is invalid"):
                session_context_claude.current()
