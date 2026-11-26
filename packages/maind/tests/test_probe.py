import unittest
from unittest import mock

from maind import probe


class ProviderHealthProbeTests(unittest.TestCase):
    def test_projects_axes_are_redacted_owner_states(self):
        with mock.patch.object(probe, "probe_hub", return_value={
            "memory": {"running": True}, "graph": {}, "docs_watcher": {},
        }), mock.patch.object(probe, "probe_project", return_value={
            "status": "connected",
            "configured": {"maind_mcp": True, "code_mcp": False},
            "path": "/home/alice/private-project",
        }):
            result = probe.provider_health_probe(None, {}, {"id": "alpha"})

        self.assertEqual({
            "maind.memory": "pass",
            "maind.mcp": "pass",
            "maind.code-graph": "unresolved",
        }, result)
        self.assertNotIn("/home", repr(result))

    def test_missing_project_path_marks_every_axis_unavailable(self):
        with mock.patch.object(probe, "probe_hub", return_value={
            "memory": {"running": False}, "graph": {}, "docs_watcher": {},
        }), mock.patch.object(probe, "probe_project", return_value={
            "status": "missing-path", "configured": {},
        }):
            result = probe.provider_health_probe(None, {}, {"id": "alpha"})

        self.assertEqual({"unavailable"}, set(result.values()))


if __name__ == "__main__":
    unittest.main()
