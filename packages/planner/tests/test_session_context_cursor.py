import os
import unittest
from unittest.mock import patch

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from planner import session_context, session_context_cursor


class CursorSessionContextTests(unittest.TestCase):
    def test_reads_only_cursor_conversation_id(self):
        with patch.dict(os.environ, {"CURSOR_CONVERSATION_ID": "cursor-session-1"}, clear=True):
            context = session_context_cursor.current()
        self.assertEqual(context.as_dict(), {
            "provider": "cursor",
            "session_id": "cursor-session-1",
            "source": "CURSOR_CONVERSATION_ID",
        })

    def test_absent_conversation_id_is_not_an_adapter_match(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(session_context_cursor.current())

    def test_whitespace_conversation_id_fails_closed(self):
        with patch.dict(os.environ, {"CURSOR_CONVERSATION_ID": "bad id"}, clear=True):
            with self.assertRaisesRegex(session_context.SessionContextError, "is invalid"):
                session_context_cursor.current()

    def test_default_resolve_selects_cursor_when_it_is_the_only_session(self):
        with patch.dict(os.environ, {"CURSOR_CONVERSATION_ID": "cursor-session-1"}, clear=True):
            resolved = session_context.resolve()
        self.assertEqual(resolved.provider, "cursor")
        self.assertEqual(resolved.session_id, "cursor-session-1")
