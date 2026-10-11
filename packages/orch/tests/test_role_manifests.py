from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from orch import contracts

ORCH = Path(__file__).resolve().parents[1]
ROLES = ORCH / "roles"
ROLE_IDS = ("context-scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar")


def _manifest(role: str) -> dict:
    return json.loads((ROLES / f"{role}.json").read_text(encoding="utf-8"))


class RoleManifestTests(unittest.TestCase):
    def test_exactly_the_known_manifests(self):
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
                    self.assertTrue(item["path"].startswith("roles/"))
                    path = ORCH / item["path"]
                    self.assertTrue(path.is_file())
                    self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_description_is_first_you_do_line(self):
        for role in ROLE_IDS:
            with self.subTest(role=role):
                lines = (ROLES / f"{role}.md").read_text(encoding="utf-8").splitlines()
                first = next(line for line in lines[lines.index("## You do") + 1:] if line.strip())
                self.assertEqual(_manifest(role)["description"], first.removeprefix("- "))


if __name__ == "__main__":
    unittest.main()
