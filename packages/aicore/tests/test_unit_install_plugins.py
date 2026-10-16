"""unit/v1 minor: provides.install and plugins[].source|catalog are additive; the old plugin form stays valid."""
import copy
import json
import unittest
from pathlib import Path

from aicore.util import schema
from aicore.util.schemacompat import compare

UNIT_DIR = Path(__file__).resolve().parent.parent / "schemas" / "unit" / "v1"


def base_unit():
    return {
        "$schema": "urn:swissknifeman:aicore:unit:v1", "id": "sample", "title": "Sample", "kind": "capability",
        "version": "0.1.0", "stability": "alpha", "destination": "hub", "requires": [],
        "provides": {"cli": ["bin/sample"]},
    }


class TestInstallAndPlugins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.kind = schema.load_contract(UNIT_DIR)

    def errors(self, **provides):
        doc = base_unit()
        doc["provides"].update(provides)
        return schema.validate(doc, self.kind, self.registry)

    def test_install_is_an_argv(self):
        self.assertEqual([], self.errors(install=["install.sh"]))
        self.assertEqual([], self.errors(install=["bash", "install.sh"]))
        self.assertNotEqual([], self.errors(install=[]))
        self.assertNotEqual([], self.errors(install="install.sh"))
        self.assertNotEqual([], self.errors(install=[""]))

    def test_plugin_forms(self):
        for entry in ({"name": "a", "manifest": ".claude-plugin/plugin.json"},
                      {"name": "a", "source": "plugin"},
                      {"name": "a", "catalog": "plugins/catalog.json"}):
            with self.subTest(entry=entry):
                self.assertEqual([], self.errors(plugins=[entry]))

    def test_plugin_needs_exactly_one_origin(self):
        for entry in ({"name": "a"},
                      {"name": "a", "manifest": "m.json", "source": "plugin"},
                      {"name": "a", "source": "plugin", "catalog": "c.json"},
                      {"name": "a", "source": "/abs"},
                      {"manifest": "m.json"},
                      {"name": "a", "other": "x", "manifest": "m.json"}):
            with self.subTest(entry=entry):
                self.assertNotEqual([], self.errors(plugins=[entry]))

    def test_only_the_conservative_oneof_rule_fires(self):
        new_doc = json.loads((UNIT_DIR / "unit.schema.json").read_text(encoding="utf-8"))
        old_doc = copy.deepcopy(new_doc)
        provides = old_doc["properties"]["provides"]["properties"]
        del provides["install"]
        item = provides["plugins"]["items"]
        del item["properties"]["source"], item["properties"]["catalog"], item["oneOf"]
        item["required"] = ["name", "manifest"]
        perm = json.loads((UNIT_DIR.parent.parent / "permissions" / "v1" / "permissions.schema.json").read_text(encoding="utf-8"))
        urn = "urn:swissknifeman:aicore:"
        old = schema.Registry({old_doc["$id"]: old_doc, perm["$id"]: perm}, urn_prefix=urn, kinds=())
        new = schema.Registry({new_doc["$id"]: new_doc, perm["$id"]: perm}, urn_prefix=urn, kinds=())
        found = compare(old, old_doc["$id"], new, new_doc["$id"])
        # the comparer cannot prove that a new oneOf keeps the old branch valid, so it grades the addition as
        # breaking although every old document matches exactly the manifest branch (checked above and by the
        # unit.json of every module); every other change is an addition
        self.assertEqual({"oneof-changed", "property-added", "required-removed"}, {change.rule for change in found})
        self.assertEqual(["/properties/provides/properties/plugins/items/oneOf"],
                         [change.path for change in found if change.breaking])


if __name__ == "__main__":
    unittest.main()
