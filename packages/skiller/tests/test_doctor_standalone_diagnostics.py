"""Effective-source diagnostics read no plan files: unmeasured items are a named `unknown`."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller.common import Env
from skiller.host import clear_host_cache

from skiller.doctor import (
    _capability_gap_diagnostic,
    _effective_carrier_set_document,
    _trace_quality_diagnostic,
)


class StandaloneDiagnosticsCase(unittest.TestCase):
    def test_capability_gap_is_unknown_without_any_repo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = _capability_gap_diagnostic(Path(tmp))
        self.assertEqual(diagnostic["status"], "unknown")
        self.assertEqual(diagnostic["next_command"], "skiller doctor --provider-distribution")
        self.assertNotIn("plans/", diagnostic["source"])

    def _host(self, tmp, config):
        path = Path(tmp) / "host.json"
        path.write_text(json.dumps({"schema_version": 1, **config}), encoding="utf-8")
        clear_host_cache()
        self.addCleanup(clear_host_cache)
        return mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(path)})

    def test_trace_quality_is_unknown_and_cites_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / "bin" / "trace-tool"
            tool.parent.mkdir()
            tool.write_text("#!/bin/sh\n", encoding="utf-8")
            with self._host(tmp, {"commands": {"trace_doctor": {"argv": ["bin/trace-tool", "doctor"]}}}):
                diagnostic = _trace_quality_diagnostic(Env(Path(tmp)))
        self.assertEqual(diagnostic["status"], "unknown")
        self.assertEqual(diagnostic["source"], "host trace doctor")
        self.assertNotIn("plans/", diagnostic["source"])
        # Suggested from the config text, never executed or resolved to an absolute path.
        self.assertEqual(diagnostic["next_command"], "bin/trace-tool doctor")

    def test_trace_quality_without_host_trace_doctor_names_the_gap(self):
        with tempfile.TemporaryDirectory() as tmp, self._host(tmp, {}):
            diagnostic = _trace_quality_diagnostic(Env(Path(tmp)))
        self.assertEqual(diagnostic["status"], "unknown")
        self.assertEqual(diagnostic["evidence"], {"gap": "no trace doctor configured"})
        self.assertIsNone(diagnostic["next_command"])

    def test_carrier_set_names_the_fixture_without_a_plan_path(self):
        doc = _effective_carrier_set_document({"positive_maps": {"codex": {"a": ["root:codex"]}}},
                                              commit_sha="deadbeef")
        self.assertEqual(doc["providers"]["codex"]["fixture_unit_set"], "fixture-unit-set.json")
        self.assertEqual(doc["providers"]["codex"]["identities"],
                         [{"identity": "a", "carriers": ["root:codex"]}])


if __name__ == "__main__":
    unittest.main()
