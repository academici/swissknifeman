"""The plan schema validator agrees with the aicore validator on the same plan/v1 schemas (aicore needed)."""
import json
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_AICORE_LIB = Path(__file__).resolve().parents[3] / "aicore" / "lib"
if (_AICORE_LIB / "aicore" / "__init__.py").is_file() and str(_AICORE_LIB) not in sys.path:
    sys.path.insert(1, str(_AICORE_LIB))

from planner import integration  # noqa: E402
from planner.plan import schema  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _kind(name: str, prefix_len: int = 0) -> str:
    rest = name[prefix_len:]
    return max((k for k in schema.KINDS if rest == k or rest.startswith(k + "-")), key=len)


def _documents():
    for path in sorted((FIXTURES / "valid").glob("*.json")):
        yield path.name, _kind(path.stem), json.loads(path.read_text(encoding="utf-8"))
    for path in sorted((FIXTURES / "invalid").glob("*.json")):
        code = path.stem.split("-", 1)[0]
        yield path.name, _kind(path.stem, len(code) + 1), json.loads(path.read_text(encoding="utf-8"))


@unittest.skipUnless(integration.available(), "aicore is not available")
class SchemaParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aicore.util import schema as foundation
        cls.foundation = foundation
        cls.registry = foundation.load_registry(
            schema.default_schema_dir(), urn_prefix=schema.SCHEMA_URN_PREFIX, kinds=schema.KINDS)

    def test_verdicts_and_codes_match_on_every_fixture(self):
        count = 0
        for name, kind, document in _documents():
            with self.subTest(name):
                ours = schema.validate(document, kind)
                theirs = self.foundation.validate(document, kind, self.registry)
                self.assertEqual(bool(ours), bool(theirs), (ours, theirs))
                self.assertEqual({i.code for i in ours}, {i.code for i in theirs})
                self.assertEqual([i.path for i in ours], [i.path for i in theirs])
            count += 1
        self.assertGreaterEqual(count, 20)

    def test_the_demo_plan_is_valid_for_both(self):
        plan = json.loads((FIXTURES / "demo-plan" / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(schema.validate(plan, "plan"), [])
        self.assertEqual(self.foundation.validate(plan, "plan", self.registry), [])


if __name__ == "__main__":
    unittest.main()
