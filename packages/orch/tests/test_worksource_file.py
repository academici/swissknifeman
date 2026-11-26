"""Acceptance evidence gates of the file work source."""
import json
from pathlib import Path
import tempfile
import unittest

from orch import adhoc
from orch.worksource_file import FileWorkSource


class FileWorkSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        source = self.project / "input.json"
        source.write_text(json.dumps(adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE",
                                                            checks=["V1=true"])))
        self.source = FileWorkSource(source, project=self.project)
        self.request = {"status": "done", "evidence": {}, "report": {"summary": "review complete"},
                        "run_id": "run-1", "attempt_id": "attempt-1"}

    def test_missing_and_red_evidence_are_refused(self):
        result = self.source._register(self.request)
        self.assertEqual(result["reason_code"], "REGISTER_EVIDENCE_MISSING")
        evidence = self.project / "check.json"
        evidence.write_text(json.dumps({"check_id": "V1", "exit": 1}))
        self.request["evidence"] = {"V1": "check.json"}
        result = self.source._register(self.request)
        self.assertEqual(result["reason_code"], "REGISTER_EVIDENCE_RED")

    def test_green_evidence_is_recorded(self):
        evidence = self.project / "check.json"
        evidence.write_text(json.dumps({"check_id": "V1", "exit": 0}))
        self.request["evidence"] = {"V1": "check.json"}
        result = self.source._register(self.request)
        self.assertEqual(result["outcome"], "recorded")
        self.assertEqual(result["gate"], {"verdict": "pass", "checks": {"V1": 0}})
        self.assertEqual(result["receipt"]["evidence_copied"], ["V1"])
