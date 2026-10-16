import os
import unittest
from unittest.mock import patch

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from planner import session_context, session_context_codex


class CodexSessionContextTests(unittest.TestCase):
    def test_reads_only_codex_thread_id(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": "codex-thread-1"}, clear=True):
            context = session_context_codex.current()
        self.assertEqual(context.as_dict(), {
            "provider": "codex", "session_id": "codex-thread-1", "source": "CODEX_THREAD_ID",
        })

    def test_absent_thread_id_is_not_an_adapter_match(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(session_context_codex.current())

    def test_empty_or_whitespace_thread_id_fails_closed(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": " invalid id "}, clear=True):
            with self.assertRaisesRegex(session_context.SessionContextError, "is invalid"):
                session_context_codex.current()
