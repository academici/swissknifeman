from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from artifex import security
from support import FIXTURE_PLAN as PLAN


class SecurityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = PLAN / "artifacts/P2/p3-smoke-admissions/codex.json"
        cls.admission = security.indexed_admission(PLAN, cls.path)

    def request(self) -> dict:
        task, grant = self.admission["task"], self.admission["grant"]
        return {"provider": {"id": task["provider"], "cli_version": "codex-cli 0.146.0", "mapping_state": "supported"},
                "route": {"model_class": grant["route"]["model_class"], "effort": grant["route"]["effort"], "capabilities": list(grant["capabilities"])},
                "permissions": {"approval_mode": "never", "sandbox_mode": "read_only", "network_mode": "disabled", "source": "indexed-admission"},
                "budgets": dict(task["budgets"]),
                "bundle": {"content_refs": [task["prompt"]["content_hash"], task["response_schema"]["content_hash"]]},
                "child_policy": {"mode": "forbidden", "max_children": 0, "allowed_capabilities": []}}

    def test_indexed_admission_and_exact_request_are_accepted(self) -> None:
        self.assertEqual(self.admission["task"]["provider"], security.request(self.admission, self.request())["provider"]["id"])
        self.assertEqual({}, security.environment({}))
        self.assertEqual("success", security.observation({"kind": "success", "process_count": 1, "output_hash": "a" * 64})["kind"])

    def test_grant_cross_provider_permission_child_and_content_widening_refuse(self) -> None:
        cases = (
            ("provider", lambda x: x["provider"].update(id="claude-code")),
            ("permission", lambda x: x["permissions"].update(network_mode="enabled")),
            ("child", lambda x: x["child_policy"].update(max_children=1)),
            ("content", lambda x: x["bundle"].update(content_refs=["b" * 64, "a" * 64])),
        )
        for name, mutate in cases:
            value = self.request(); mutate(value)
            with self.subTest(name=name), self.assertRaises(security.SecurityRefusal):
                security.request(self.admission, value)

    def test_foreign_path_secret_and_raw_observation_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory) / "grant.json"; foreign.write_text("{}", encoding="utf-8")
            with self.assertRaises(security.SecurityRefusal):
                security.indexed_admission(PLAN, foreign)
            canary = Path(directory) / "canary.txt"; canary.write_text("Bearer synthetic-canary", encoding="utf-8")
            with self.assertRaises(security.SecurityRefusal):
                security.bundle_lint(canary)
        with self.assertRaises(security.SecurityRefusal):
            security.observation({"kind": "success", "process_count": 1, "transcript": "raw"})
        with self.assertRaises(security.SecurityRefusal):
            security.environment({"HOME": "/unsafe"})


if __name__ == "__main__":
    unittest.main()
