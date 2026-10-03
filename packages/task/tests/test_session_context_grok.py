import os
import unittest
from unittest.mock import patch

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from task import session_context, session_context_grok


class GrokSessionContextTests(unittest.TestCase):
    def test_reads_only_grok_session_id(self):
        with patch.dict(os.environ, {"GROK_SESSION_ID": "grok-session-1"}, clear=True):
            context = session_context_grok.current()
        self.assertEqual(context.as_dict(), {
            "provider": "grok",
            "session_id": "grok-session-1",
            "source": "GROK_SESSION_ID",
        })

    def test_cursor_conversation_id_is_not_a_grok_match(self):
        with patch.dict(os.environ, {"CURSOR_CONVERSATION_ID": "cursor-session-1"}, clear=True):
            self.assertIsNone(session_context_grok.current())

    def test_absent_session_id_is_not_an_adapter_match(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(session_context_grok.current())

    def test_whitespace_session_id_fails_closed(self):
        with patch.dict(os.environ, {"GROK_SESSION_ID": "bad id"}, clear=True):
            with self.assertRaisesRegex(session_context.SessionContextError, "is invalid"):
                session_context_grok.current()

    def test_default_resolve_selects_grok_when_it_is_the_only_session(self):
        with patch.dict(os.environ, {"GROK_SESSION_ID": "grok-session-1"}, clear=True):
            resolved = session_context.resolve()
        self.assertEqual(resolved.provider, "grok")
        self.assertEqual(resolved.session_id, "grok-session-1")
