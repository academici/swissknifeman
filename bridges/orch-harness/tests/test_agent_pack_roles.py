"""Conformance: ``agent_pack_roles`` of the role manifests match the partner's agent-pack role catalog."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

BRIDGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRIDGE))

import partners  # noqa: E402

ORCH = partners.find_orch_root()
ROLES = ORCH / "roles" if ORCH else None
ROLE_IDS = ("context-scout", "executor", "bounded-implementer", "reviewer", "registrar")
PACK_ROLE = {"executor": "slice-builder", "bounded-implementer": "slice-builder", "reviewer": "reviewer"}
ROLES_JSON = partners.agent_pack_roles()


class AgentPackRoles(unittest.TestCase):
    @unittest.skipUnless(ORCH and ROLES_JSON, "orch or harness agent-packs roles.json not available")
    def test_agent_pack_roles_match_harness_catalog(self):
        entries = json.loads(ROLES_JSON.read_text(encoding="utf-8"))["roles"]
        for role in ROLE_IDS:
            with self.subTest(role=role):
                expected = sorted((e["pack_id"], e["role_id"]) for e in entries
                                  if e["role_id"] == PACK_ROLE.get(role))
                actual = sorted((r["pack_id"], r["role_id"]) for r in json.loads((ROLES / f"{role}.json").read_text(encoding="utf-8")).get("agent_pack_roles", []))
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
