from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from orch import contracts

ORCH = Path(__file__).resolve().parents[1]
REPO = ORCH.parents[1]
ROLES = ORCH / "roles"
ROLES_JSON = ORCH.parent / "harness/configs/common/agent-packs/roles.json"
ROLE_IDS = ("context-scout", "executor", "bounded-implementer", "reviewer", "registrar")
PACK_ROLE = {"executor": "slice-builder", "bounded-implementer": "slice-builder", "reviewer": "reviewer"}


def _manifest(role: str) -> dict:
    return json.loads((ROLES / f"{role}.json").read_text(encoding="utf-8"))


class RoleManifestTests(unittest.TestCase):
    def test_exactly_five_manifests(self):
        self.assertEqual(sorted(p.stem for p in ROLES.glob("*.json")), sorted(ROLE_IDS))

    def test_manifests_are_valid_and_named_after_role_id(self):
        for role in ROLE_IDS:
            with self.subTest(role=role):
                doc = _manifest(role)
                self.assertEqual(contracts.validate(doc, "role-manifest"), [])
                self.assertEqual(doc["role_id"], role)

    def test_instruction_files_exist_with_matching_sha256(self):
        for role in ROLE_IDS:
            for item in _manifest(role)["instructions"]:
                with self.subTest(role=role, path=item["path"]):
                    path = REPO / item["path"]
                    self.assertTrue(path.is_file())
                    self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_description_is_first_you_do_line(self):
        for role in ROLE_IDS:
            with self.subTest(role=role):
                lines = (ROLES / f"{role}.md").read_text(encoding="utf-8").splitlines()
                first = next(line for line in lines[lines.index("## You do") + 1:] if line.strip())
                self.assertEqual(_manifest(role)["description"], first.removeprefix("- "))

    @unittest.skipUnless(ROLES_JSON.is_file(), "harness agent-packs roles.json not available")
    def test_agent_pack_roles_match_harness_catalog(self):
        entries = json.loads(ROLES_JSON.read_text(encoding="utf-8"))["roles"]
        for role in ROLE_IDS:
            with self.subTest(role=role):
                expected = sorted((e["pack_id"], e["role_id"]) for e in entries
                                  if e["role_id"] == PACK_ROLE.get(role))
                actual = sorted((r["pack_id"], r["role_id"]) for r in _manifest(role).get("agent_pack_roles", []))
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
