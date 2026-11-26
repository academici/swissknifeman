"""Module discovery for the configuration CLI."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from aicore.config import units

UNITS = Path(__file__).resolve().parent / "fixtures" / "units"


class TestDiscover(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_parent_of_modules(self):
        found = units.discover({"SKM_UNITS_PATH": str(UNITS)})
        self.assertEqual(["demo"], sorted(found))  # "plain" has no provides.config
        info = found["demo"]
        self.assertEqual(UNITS / "demo", info.root)
        self.assertEqual(UNITS / "demo" / "configs" / "config.schema.json", info.schema_path)
        self.assertEqual("configs/config.schema.json", info.schema_rel)

    def test_module_folder_itself(self):
        found = units.discover({"SKM_UNITS_PATH": str(UNITS / "demo")})
        self.assertEqual(["demo"], sorted(found))

    def test_several_roots_first_wins(self):
        other = self.tmp / "demo"
        shutil.copytree(UNITS / "demo", other)
        found = units.discover({"SKM_UNITS_PATH": os.pathsep.join([str(other), str(UNITS)])})
        self.assertEqual(other, found["demo"].root)

    def test_missing_root_and_broken_manifest_are_skipped(self):
        (self.tmp / "bad").mkdir()
        (self.tmp / "bad" / "unit.json").write_text("{not json", encoding="utf-8")
        found = units.discover({"SKM_UNITS_PATH": os.pathsep.join([str(self.tmp / "nope"), str(self.tmp)])})
        self.assertEqual({}, found)

    def test_default_is_the_folder_holding_the_foundation(self):
        self.assertEqual(units.foundation_root().parent, units._roots({})[0])
        self.assertTrue((units.foundation_root() / "unit.json").is_file())

    def test_load_unit_without_config(self):
        self.assertIsNone(units.load_unit(UNITS / "plain"))
        self.assertIsNone(units.load_unit(self.tmp))
