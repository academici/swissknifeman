"""Every gui contract listed in unit.json: closed, described, loaded through aicore and exercised by its examples.

An invalid example is named ``<case>.<code>.json``: it must fail with that ValidationIssue code. The test walks
``provides.contracts`` of ``unit.json``, so a new contract only needs its entry and its examples.
"""
import json
import unittest
from pathlib import Path

from aicore.util import schema

from gui import contracts

MODULE_ROOT = Path(__file__).resolve().parents[1]
UNIT = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
LISTED = UNIT["provides"].get("contracts", [])


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def name_of(entry: dict) -> str:
    return entry["id"].rpartition(":")[2]


def examples(entry: dict, group: str) -> list:
    return sorted((MODULE_ROOT / entry["path"] / "examples" / group).glob("*.json"))


def codes(issues) -> list:
    return sorted({issue.code for issue in issues})


class TestRegistration(unittest.TestCase):
    def test_contracts_are_listed(self):
        self.assertTrue({"contribution", "view-data"} <= {name_of(entry) for entry in LISTED})

    def test_every_contract_folder_is_listed_and_every_entry_exists(self):
        on_disk = {f"schemas/{path.parent.parent.name}/{path.parent.name}"
                   for path in contracts.SCHEMAS.glob("*/v*/*.schema.json")}
        self.assertEqual(on_disk, {entry["path"] for entry in LISTED})

    def test_entries_follow_the_layout(self):
        for entry in LISTED:
            with self.subTest(contract=entry["id"]):
                name = name_of(entry)
                self.assertEqual(f"urn:swissknifeman:gui:{name}", entry["id"])
                self.assertEqual(f"schemas/{name}/{entry['version']}", entry["path"])
                self.assertEqual("development", entry["stability"])

    def test_readme_has_a_row_per_contract(self):
        readme = (contracts.SCHEMAS / "README.md").read_text(encoding="utf-8")
        for entry in LISTED:
            self.assertIn(f"| `{name_of(entry)}` | `{entry['id']}:{entry['version']}` |", readme)


class TestContracts(unittest.TestCase):
    def test_every_contract_loads_under_the_closed_profile(self):
        for entry in LISTED:
            with self.subTest(contract=entry["id"]):
                registry, kind = contracts.load(name_of(entry), entry["version"])
                self.assertEqual(name_of(entry), kind)
                self.assertEqual(f"{entry['id']}:{entry['version']}", registry.for_kind(kind)[1])

    def test_example_counts(self):
        for entry in LISTED:
            with self.subTest(contract=entry["id"]):
                self.assertGreaterEqual(len(examples(entry, "valid")), 2)
                self.assertGreaterEqual(len(examples(entry, "invalid")), 3)

    def test_documents_name_their_own_contract(self):
        for entry in LISTED:
            for path in examples(entry, "valid"):
                with self.subTest(example=f"{name_of(entry)}/{path.name}"):
                    self.assertEqual(f"{entry['id']}:{entry['version']}", load(path).get("$schema"))

    def test_valid_examples_pass(self):
        for entry in LISTED:
            registry, kind = contracts.load(name_of(entry), entry["version"])
            for path in examples(entry, "valid"):
                with self.subTest(example=f"{kind}/valid/{path.name}"):
                    self.assertEqual([], contracts.validate(load(path), kind, entry["version"]))
                    self.assertEqual([], schema.validate(load(path), kind, registry))

    def test_invalid_examples_fail_with_the_code_in_their_name(self):
        for entry in LISTED:
            registry, kind = contracts.load(name_of(entry), entry["version"])
            for path in examples(entry, "invalid"):
                with self.subTest(example=f"{kind}/invalid/{path.name}"):
                    expected = path.name[:-len(".json")].rpartition(".")[2]
                    self.assertIn(expected, schema.ERROR_CODES, "name the file <case>.<code>.json")
                    self.assertIn(expected, codes(contracts.validate(load(path), kind, entry["version"])))
                    self.assertNotEqual([], schema.validate(load(path), kind, registry))

    def test_every_object_is_closed_and_every_property_described(self):
        def walk(node, where):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object" and ("properties" in node or "patternProperties" in node):
                self.assertIs(node.get("additionalProperties"), False, where)
            if node.get("type") == "object" and "properties" not in node and "patternProperties" not in node:
                # An open object is allowed only for a document of another contract, which its description names.
                self.assertIn("contract", node.get("description", ""), where)
            for keyword in ("properties", "$defs", "patternProperties"):
                for name, child in node.get(keyword, {}).items():
                    self.assertIn("description", child, f"{where}/{keyword}/{name}")
                    walk(child, f"{where}/{keyword}/{name}")
            for keyword in ("items", "propertyNames"):
                walk(node.get(keyword), f"{where}/{keyword}")
            for index, child in enumerate(node.get("oneOf", ())):
                walk(child, f"{where}/oneOf/{index}")

        for entry in LISTED:
            name = name_of(entry)
            walk(load(MODULE_ROOT / entry["path"] / f"{name}.schema.json"), name)

    def test_pattern_keys_and_patterns_are_anchored(self):
        def walk(node, where):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "pattern" and isinstance(value, str):
                        self.assertTrue(value.startswith("^") and value.endswith("$"), f"{where}: {value}")
                    elif key == "patternProperties":
                        for pattern in value:
                            self.assertTrue(pattern.startswith("^") and pattern.endswith("$"), f"{where}: {pattern}")
                    walk(value, f"{where}/{key}")
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, f"{where}/{index}")

        for entry in LISTED:
            name = name_of(entry)
            walk(load(MODULE_ROOT / entry["path"] / f"{name}.schema.json"), name)

    def test_unknown_contract_is_a_profile_error(self):
        with self.assertRaises(schema.SchemaProfileError):
            contracts.load("absent")


class TestDiscriminatedValidation(unittest.TestCase):
    def test_view_data_is_told_apart_by_view(self):
        name, branches = contracts.discriminator("view-data")
        self.assertEqual("view", name)
        self.assertEqual(11, len(branches))

    def test_contribution_has_no_discriminator(self):
        self.assertIsNone(contracts.discriminator("contribution"))

    def test_branch_issues_name_the_field(self):
        document = {"$schema": contracts.urn("view-data"), "view": "resource-list", "rows": []}
        self.assertEqual(["required"], codes(contracts.validate(document, "view-data")))
        registry, kind = contracts.load("view-data")
        self.assertEqual(["one_of"], codes(schema.validate(document, kind, registry)))

    def test_unknown_kind_falls_back_to_one_of(self):
        for document in ({"$schema": contracts.urn("view-data"), "view": "chart"}, {"view": 1}, [], "x"):
            with self.subTest(document=document):
                self.assertIn("one_of", codes(contracts.validate(document, "view-data")))

    def test_same_verdict_as_the_whole_one_of(self):
        registry, kind = contracts.load("view-data")
        entry = next(e for e in LISTED if name_of(e) == "view-data")
        for path in examples(entry, "valid") + examples(entry, "invalid"):
            with self.subTest(example=path.name):
                document = load(path)
                self.assertEqual(bool(contracts.validate(document, "view-data")),
                                 bool(schema.validate(document, kind, registry)))


class TestContribution(unittest.TestCase):
    def full(self):
        entry = next(e for e in LISTED if name_of(e) == "contribution")
        return load(MODULE_ROOT / entry["path"] / "examples" / "valid" / "full.json")

    def argv_codes(self, part):
        document = self.full()
        document["commands"][0]["exec"]["argv"][2] = part
        return codes(contracts.validate(document, "contribution"))

    def test_views_match_view_data_kinds(self):
        registry, kind = contracts.load("contribution")
        views = set(registry.for_kind(kind)[0]["$defs"]["view"]["enum"])
        _, branches = contracts.discriminator("view-data")
        self.assertEqual(views, set(branches))

    def test_argv_part_is_a_literal_or_exactly_one_input(self):
        self.assertEqual([], self.argv_codes("--plan"))
        self.assertEqual([], self.argv_codes({"input": "plan"}))
        for part in ({"input": "plan", "prefix": "--plan="}, {"input": "plan", "suffix": "x"}, {"literal": "a"},
                     {"input": "Plan"}, {"input": ["plan", "item"]}, "", 1, None, ["plan"]):
            with self.subTest(part=part):
                self.assertNotEqual([], self.argv_codes(part))

    def test_flags_are_long_options(self):
        document = self.full()
        for flag, valid in (("--dry-run", True), ("--x1", True), ("-n", False), ("--Dry", False), ("--", False),
                            ("--a b", False), ("--a=b", False)):
            with self.subTest(flag=flag):
                document["commands"][0]["input"][3]["flag"] = flag
                self.assertEqual(valid, not contracts.validate(document, "contribution"))

    def test_route_paths_stay_relative_and_simple(self):
        document = self.full()
        for path, valid in (("plans/:plan", True), ("a/b-c/:x_y", True), ("/plans", False), ("plans/..", False),
                            ("plans//x", False), ("plans/:Plan", False), ("plans/", False), ("Plans", False)):
            with self.subTest(path=path):
                document["routes"][1]["path"] = path
                self.assertEqual(valid, not contracts.validate(document, "contribution"))

    def test_terminal_effect_is_expressible_for_the_resolver_to_refuse(self):
        document = self.full()
        document["commands"][0]["effects"] = ["terminal"]
        self.assertEqual([], contracts.validate(document, "contribution"))

    def test_exec_is_invoke_or_argv(self):
        document = self.full()
        for exec_, valid in (({"kind": "invoke"}, True), ({"kind": "shell", "command": "ls"}, False),
                             ({"kind": "argv", "argv": ["bin/x"]}, False), ({"kind": "invoke", "argv": ["x"]}, False)):
            with self.subTest(exec_=exec_):
                document["commands"][1]["exec"] = exec_
                self.assertEqual(valid, not contracts.validate(document, "contribution"))


if __name__ == "__main__":
    unittest.main()
