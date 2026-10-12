"""State places: no .bak or env.ini writers, lock paths come from constants, example config is current."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.artifacts.lock import LOCK_RELATIVE_PATH
from harness import agentpacks, hooks

PKG = Path(__file__).resolve().parents[1]
LIB = PKG / "lib" / "harness"


def sources():
    return {path: path.read_text(encoding="utf-8") for path in sorted(LIB.rglob("*.py"))}


class ConstantsCase(unittest.TestCase):
    def test_the_provider_lock_path_is_a_constant_not_a_literal(self):
        self.assertEqual(LOCK_RELATIVE_PATH, ".swissknifeman/provider-artifacts.lock.json")
        offenders = [str(path) for path, text in sources().items() if "provider-artifacts.lock.json" in text]
        self.assertEqual(offenders, [])
        self.assertIs(hooks.LOCK_RELATIVE_PATH, LOCK_RELATIVE_PATH)

    def test_the_agent_pack_lock_path_stays_a_constant(self):
        self.assertEqual(agentpacks.LOCK_REL, ".claude/agent-pack.lock.json")

    def test_no_bak_writer_and_no_ini_writer_in_the_library(self):
        for path, text in sources().items():
            with self.subTest(path=path.name):
                self.assertNotIn("backup_file", text)
                self.assertIsNone(re.search(r"write_text\(.*\.env\.ini", text))



if __name__ == "__main__":
    unittest.main()
