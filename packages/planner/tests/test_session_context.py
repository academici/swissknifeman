import json
import os
import unittest
from unittest.mock import patch

try:
    from . import fixtures  # noqa: F401
except ImportError:
    import fixtures  # noqa: F401,E402
from planner import session_context


class SessionContextTests(unittest.TestCase):
    def test_resolves_the_single_applicable_adapter(self):
        adapter = lambda: session_context.SessionContext(
            provider="fixture", session_id="root-123", source="fixture-env")
        resolved = session_context.resolve(adapters=(adapter,))
        self.assertEqual(resolved.as_dict(), {
            "provider": "fixture", "session_id": "root-123", "source": "fixture-env",
        })

    def test_missing_adapter_fails_closed(self):
        with self.assertRaisesRegex(session_context.SessionContextError, "not found"):
            session_context.resolve(adapters=())

    def test_multiple_adapters_fail_closed(self):
        adapter = lambda: session_context.SessionContext(
            provider="fixture", session_id="root-123", source="fixture-env")
        with self.assertRaisesRegex(session_context.SessionContextError, "exactly one"):
            session_context.resolve(adapters=(adapter, adapter))

    def test_cli_json_and_id(self):
        env = {"CODEX_THREAD_ID": "codex-thread-1"}
        with patch.dict(os.environ, env, clear=True):
            payload = session_context.current_json()
            self.assertEqual(json.loads(payload)["session_id"], "codex-thread-1")
            self.assertEqual(session_context.current_id(), "codex-thread-1")
