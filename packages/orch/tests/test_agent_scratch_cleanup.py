"""Completing an agent removes scratch while retaining its evidence and parent context."""
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor.infrastructure import roles


class AgentScratchCleanupTests(unittest.TestCase):
    def test_success_and_failure_remove_only_agent_scratch(self):
        for succeeded in (True, False):
            with self.subTest(succeeded=succeeded), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                scratch = directory / "tmp" / "nested"
                scratch.mkdir(parents=True)
                (scratch / "temporary.txt").write_text("scratch")
                evidence = directory / "result.json"
                evidence.write_text("retained evidence")
                parent = object()
                handle = {"trail": {}, "last_exit": 0, "began": time.monotonic(),
                          "stream": None, "lingered": False, "usage": {},
                          "directory": directory, "previous": parent}
                owner = SimpleNamespace(_local=SimpleNamespace(agent=handle), _agent_event=mock.Mock())
                error = None if succeeded else {"class": "provider"}
                with mock.patch.object(roles.agents, "finish"), \
                     mock.patch.object(roles.results, "denial_beacons", return_value=[]):
                    roles.agent_end(owner, handle, error=error, succeeded=succeeded)
                self.assertFalse((directory / "tmp").exists())
                self.assertEqual(evidence.read_text(), "retained evidence")
                self.assertIs(owner._local.agent, parent)
                self.assertEqual(owner._agent_event.call_args.args[0],
                                 "orch.agent.finished" if succeeded else "orch.agent.failed")
