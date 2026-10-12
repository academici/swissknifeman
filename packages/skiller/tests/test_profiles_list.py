"""skiller profiles --json: output validates against profiles-list/v1 and mirrors profiles/*.json."""
import contextlib
import io
import json
import unittest
from pathlib import Path

import aicore
from aicore.util.schema import load_contract, validate
from skiller.cli import main

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = Path(aicore.__file__).resolve().parents[2] / "schemas"


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main([str(ROOT), "profiles", *args])
    return out.getvalue()


class TestProfilesList(unittest.TestCase):
    def test_json_validates_and_mirrors_files(self):
        doc = json.loads(run("--json"))
        registry, kind = load_contract(ROOT / "schemas" / "profiles-list" / "v1",
                                       urn_prefix="urn:swissknifeman:skiller:", foundation=FOUNDATION)
        self.assertEqual(list(validate(doc, kind, registry)), [])
        files = sorted(p.stem for p in (ROOT / "profiles").glob("*.json"))
        self.assertEqual(sorted(doc["profiles"]), files)
        for name in files:
            expected = json.loads((ROOT / "profiles" / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["profiles"][name], expected)

    def test_text_lists_every_profile(self):
        text = run()
        for path in (ROOT / "profiles").glob("*.json"):
            self.assertIn(path.stem, text)


if __name__ == "__main__":
    unittest.main()
