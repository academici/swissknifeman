"""Every schema of aicore: closed, described, and exercised by its valid and invalid examples."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aicore.util import schema

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
CONTRACTS = sorted(path.parent for path in SCHEMAS.glob("*/v*/*.schema.json"))


def examples(contract: Path, group: str) -> list:
    return sorted((contract / "examples" / group).glob("*.json"))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestContractExamples(unittest.TestCase):
    def test_contracts_are_found(self):
        self.assertTrue({"unit", "check-result", "digest", "common", "event", "artifact-ref", "permissions",
                         "extension", "plugin-request", "plugin-response", "plugin-describe"}
                        <= {path.parent.name for path in CONTRACTS})

    def test_every_contract_loads_under_the_closed_profile(self):
        for contract in CONTRACTS:
            with self.subTest(contract=f"{contract.parent.name}/{contract.name}"):
                registry, kind = schema.load_contract(contract)
                self.assertEqual(kind, contract.parent.name)
                self.assertEqual(registry.for_kind(kind)[1], f"urn:swissknifeman:aicore:{kind}:{contract.name}")

    def test_example_counts(self):
        for contract in CONTRACTS:
            with self.subTest(contract=contract.parent.name):
                self.assertGreaterEqual(len(examples(contract, "valid")), 1)
                self.assertGreaterEqual(len(examples(contract, "invalid")), 3)

    def test_extension_contracts_have_two_valid_and_three_invalid_examples(self):
        for name in ("event", "artifact-ref", "permissions", "extension", "plugin-request", "plugin-response",
                     "plugin-describe"):
            with self.subTest(contract=name):
                self.assertGreaterEqual(len(examples(SCHEMAS / name / "v1", "valid")), 2)
                self.assertGreaterEqual(len(examples(SCHEMAS / name / "v1", "invalid")), 3)

    def test_documents_name_their_own_schema(self):
        """A document whose schema requires ``$schema`` carries the contract id there."""
        for contract in CONTRACTS:
            kind = contract.parent.name
            if kind in ("event", "common", "digest", "unit", "check-result") or "$schema" not in load(
                    contract / f"{kind}.schema.json").get("required", ()):
                continue
            for path in examples(contract, "valid"):
                with self.subTest(example=f"{kind}/{path.name}"):
                    self.assertEqual(f"urn:swissknifeman:aicore:{kind}:v1", load(path).get("$schema"))

    def test_every_contract_of_the_extension_layer_is_listed_in_the_unit(self):
        unit = load(SCHEMAS.parent / "unit.json")
        listed = {entry["id"].rpartition(":")[2]: entry for entry in unit["provides"]["contracts"]}
        for contract in CONTRACTS:
            kind = contract.parent.name
            with self.subTest(contract=kind):
                self.assertIn(kind, listed)
                self.assertEqual((f"schemas/{kind}/v1", "v1"), (listed[kind]["path"], listed[kind]["version"]))
        readme = (SCHEMAS / "README.md").read_text(encoding="utf-8")
        for contract in CONTRACTS:
            self.assertIn(f"| `{contract.parent.name}` | {contract.name} |", readme)

    def test_valid_examples_pass_and_invalid_fail(self):
        for contract in CONTRACTS:
            registry, kind = schema.load_contract(contract)
            for path in examples(contract, "valid"):
                with self.subTest(example=f"{kind}/valid/{path.name}"):
                    self.assertEqual(schema.validate(load(path), kind, registry), [])
            for path in examples(contract, "invalid"):
                with self.subTest(example=f"{kind}/invalid/{path.name}"):
                    self.assertNotEqual(schema.validate(load(path), kind, registry), [])

    def test_every_object_is_closed_and_every_property_described(self):
        def walk(node, where):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object" and ("properties" in node or "patternProperties" in node):
                self.assertIs(node.get("additionalProperties"), False, where)
            for name, child in node.get("properties", {}).items():
                self.assertIn("description", child, f"{where}/{name}")
                walk(child, f"{where}/{name}")
            for name, child in node.get("$defs", {}).items():
                self.assertIn("description", child, f"{where}/$defs/{name}")
                walk(child, f"{where}/$defs/{name}")
            for pattern, child in node.get("patternProperties", {}).items():
                self.assertIn("description", child, f"{where}/patternProperties/{pattern}")
                walk(child, f"{where}/patternProperties/{pattern}")
            walk(node.get("items"), f"{where}/items")
            walk(node.get("propertyNames"), f"{where}/propertyNames")

        for contract in CONTRACTS:
            kind = contract.parent.name
            walk(load(contract / f"{kind}.schema.json"), kind)


def pattern_keys(node):
    """Every key of every ``patternProperties`` below ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "patternProperties":
                yield from value
                for child in value.values():
                    yield from pattern_keys(child)
            elif key in ("properties", "$defs"):
                for child in value.values():
                    yield from pattern_keys(child)
            elif key in ("items", "propertyNames"):
                yield from pattern_keys(value)
            elif key == "oneOf":
                for child in value:
                    yield from pattern_keys(child)


class TestPatternPropertiesInContracts(unittest.TestCase):
    def test_pattern_keys_are_anchored(self):
        for contract in CONTRACTS:
            kind = contract.parent.name
            for pattern in pattern_keys(load(contract / f"{kind}.schema.json")):
                with self.subTest(contract=kind, pattern=pattern):
                    self.assertTrue(pattern.startswith("^") and pattern.endswith("$"), pattern)


class TestCommonContract(unittest.TestCase):
    """The shared definitions, and the R02 rule for namespaced extension keys."""

    FIXTURE = {
        "$schema": schema.DIALECT, "$id": "urn:swissknifeman:aicore:fixture:v1", "title": "fixture",
        "description": "Test fixture that references the shared definitions.", "type": "object",
        "additionalProperties": False,
        "properties": {
            "extensions": {"$ref": "urn:swissknifeman:aicore:common:v1#/$defs/extensions",
                           "description": "Namespaced extension values."},
            "at": {"$ref": "urn:swissknifeman:aicore:common:v1#/$defs/rfc3339_utc",
                   "description": "A timestamp."},
        },
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        shutil.copytree(SCHEMAS / "common", root / "common")
        contract = root / "fixture" / "v1"
        contract.mkdir(parents=True)
        (contract / "fixture.schema.json").write_text(json.dumps(self.FIXTURE), encoding="utf-8")
        schema.clear_registry_cache()
        self.addCleanup(schema.clear_registry_cache)
        self.registry, self.kind = schema.load_contract(contract)

    def codes(self, doc):
        return sorted((issue.path, issue.code) for issue in schema.validate(doc, self.kind, self.registry))

    def test_namespaced_key_passes_with_any_value(self):
        for value in (1, "s", None, [1], {"a": {"b": 2}}):
            with self.subTest(value=value):
                self.assertEqual(self.codes({"extensions": {"acme.flag": value}}), [])
        self.assertEqual(self.codes({"extensions": {"acme.sub.flag-1": True}}), [])

    def test_key_without_namespace_is_additional(self):
        self.assertEqual(self.codes({"extensions": {"flag": 1}}), [("/extensions/flag", "additional")])
        self.assertEqual(self.codes({"extensions": {"Acme.flag": 1}}), [("/extensions/Acme.flag", "additional")])
        self.assertEqual(self.codes({"extensions": {"acme.flag\n": 1}}), [("/extensions/acme.flag\n", "additional")])

    def test_shared_formats(self):
        self.assertEqual(self.codes({"at": "2026-10-09T02:15:31Z"}), [])
        self.assertEqual(self.codes({"at": "2026-10-09T02:15:31.5Z"}), [])
        self.assertEqual(self.codes({"at": "2026-10-09 02:15:31"}), [("/at", "pattern")])

    def test_shared_definitions_match_unit(self):
        unit = load(SCHEMAS / "unit" / "v1" / "unit.schema.json")["$defs"]
        common = load(SCHEMAS / "common" / "v1" / "common.schema.json")["$defs"]
        for name in ("semver", "relpath", "argv", "stability"):
            self.assertEqual(unit[name], common[name], name)


def check(kind, doc):
    registry, _kind = schema.load_contract(SCHEMAS / kind / "v1")
    return sorted((issue.path, issue.code) for issue in schema.validate(doc, kind, registry))


def example(kind, group, name):
    return load(SCHEMAS / kind / "v1" / "examples" / group / f"{name}.json")


class TestPermissionsContract(unittest.TestCase):
    def test_root_and_embeddable_definition_have_the_same_properties(self):
        document = load(SCHEMAS / "permissions" / "v1" / "permissions.schema.json")
        root = {name: body for name, body in document["properties"].items() if name != "$schema"}
        self.assertEqual(document["$defs"]["permissions"]["properties"], root)
        self.assertEqual(set(root), {"filesystem", "network", "secrets", "shell", "env", "profile"})

    def test_filesystem_areas_match_the_unit_manifest_language(self):
        defs = load(SCHEMAS / "permissions" / "v1" / "permissions.schema.json")["$defs"]["permissions"]
        self.assertEqual(["project", "state", "provider-surfaces", "home"], defs["properties"]["filesystem"]["items"]["enum"])

    def test_unit_and_extension_embed_the_definition_by_reference(self):
        target = "urn:swissknifeman:aicore:permissions:v1#/$defs/permissions"
        self.assertEqual(target, load(SCHEMAS / "unit" / "v1" / "unit.schema.json")["properties"]["permissions"]["$ref"])
        self.assertEqual(target, load(SCHEMAS / "extension" / "v1" / "extension.schema.json")["properties"]["permissions"]["$ref"])

    def test_both_users_reject_what_the_definition_rejects(self):
        unit = example("unit", "valid", "capability")
        manifest = example("extension", "valid", "subscriber")
        for permissions, accepted in (({"env": ["PATH"], "profile": "read-only"}, True), ({"env": ["path"]}, False),
                                      ({"profile": "container"}, False), ({"filesystem": ["root"]}, False),
                                      ({"sudo": True}, False)):
            with self.subTest(permissions=permissions):
                self.assertEqual(accepted, check("unit", dict(unit, permissions=permissions)) == [])
                self.assertEqual(accepted, check("extension", dict(manifest, permissions=permissions)) == [])


class TestEventContract(unittest.TestCase):
    def event(self, **extra):
        return dict(example("event", "valid", "minimal"), **extra)

    def test_unknown_extension_attributes_are_accepted_when_scalar(self):
        for value in ("text", 7, True):
            with self.subTest(value=value):
                self.assertEqual([], check("event", self.event(acmeflag=value)))
        for value in (None, [1], {"a": 1}, 1.5):
            with self.subTest(value=value):
                self.assertNotEqual([], check("event", self.event(acmeflag=value)))

    def test_attribute_names_follow_cloudevents(self):
        for name in ("Acme", "acme_flag", "acme-flag", "a" * 21, "", "acme.flag"):
            with self.subTest(name=name):
                self.assertEqual([(f"/{name}", "additional")], check("event", self.event(**{name: 1})))
        self.assertEqual([], check("event", self.event(**{"a" * 20: 1})))

    def test_data_is_an_object_and_never_an_extension(self):
        self.assertEqual([], check("event", self.event(data={"a": [1, {"b": None}]})))
        for value in ("text", 1, [1], None):
            self.assertNotEqual([], check("event", self.event(data=value)), value)

    def test_the_envelope_has_no_project_and_no_binary_payload(self):
        self.assertEqual([("/project", "additional")], check("event", self.event(project="x")))
        self.assertEqual([("/data_base64", "additional")], check("event", self.event(data_base64="AA==")))

    def test_type_and_source_formats(self):
        for kind, accepted in (("planner.plan.closed", True), ("planner.plan.item.closed", True), ("a1.b-c.d", True),
                               ("planner.plan", False), ("Planner.plan.closed", False), ("planner..closed", False),
                               ("1planner.plan.closed", False)):
            self.assertEqual(accepted, check("event", self.event(type=kind)) == [], kind)
        self.assertNotEqual([], check("event", self.event(source="planner")))
        self.assertNotEqual([], check("event", self.event(source="urn:swissknifeman:module:Planner")))

    def test_time_is_utc_with_a_z_suffix(self):
        for text, accepted in (("2026-10-09T12:00:00Z", True), ("2026-10-09T12:00:00.123Z", True),
                               ("2026-10-09T12:00:00+03:00", False), ("2026-10-09 12:00:00Z", False)):
            self.assertEqual(accepted, check("event", self.event(time=text)) == [], text)

    def test_trace_and_correlation_fields(self):
        self.assertEqual([], check("event", self.event(correlationid="x" * 128)))
        self.assertNotEqual([], check("event", self.event(correlationid="x" * 129)))
        self.assertNotEqual([], check("event", self.event(correlationid="")))
        self.assertNotEqual([], check("event", self.event(traceparent="00-abc-def-01")))
        self.assertNotEqual([], check("event", self.event(causationid="x")))


class TestPluginProtocolContracts(unittest.TestCase):
    def test_request_embeds_the_event_contract(self):
        request = example("plugin-request", "valid", "event")
        self.assertEqual([], check("plugin-request", request))
        broken = dict(request, event=dict(request["event"], type="two.segments"))
        self.assertEqual([("/event/type", "pattern")], check("plugin-request", broken))

    def test_describe_digest_is_the_digest_of_the_manifest_provides(self):
        from aicore.util import digest
        for name in ("command", "subscriber"):
            manifest = example("extension", "valid", name)
            described = {"$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1",
                         "id": manifest["id"], "kind": manifest["kind"], "version": manifest["version"],
                         "capabilities_digest": digest.digest_json(manifest["provides"]),
                         "transport": "stdio-json"}
            self.assertEqual([], check("plugin-describe", described), name)
            response = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                        "request_id": "0123456789abcdef0123456789abcdef", "status": "ok", "output": described}
            self.assertEqual([], check("plugin-response", response), name)

    def test_the_manifest_protocol_range_uses_the_unit_pattern(self):
        unit = load(SCHEMAS / "unit" / "v1" / "unit.schema.json")["properties"]["protocol"]
        extension = load(SCHEMAS / "extension" / "v1" / "extension.schema.json")["properties"]["protocol"]
        self.assertEqual(unit["properties"], extension["properties"])

    def test_error_codes_and_statuses(self):
        base = example("plugin-response", "valid", "error")
        self.assertEqual([("/error/code", "pattern")], check("plugin-response", dict(base, error={"code": "lower", "message": "m"})))
        self.assertEqual([("/error", "required")], check("plugin-response", dict(base, error={"code": "OK_CODE"}))[:1])
        for status in ("ok", "skipped", "error"):
            self.assertEqual([], check("plugin-response", dict(base, status=status)))


class TestUnitContractExtensions(unittest.TestCase):
    def unit(self, **changes):
        document = example("unit", "valid", "capability")
        document.update(changes)
        return document

    def test_subscriptions(self):
        subscription = {"id": "notify", "on": ["a.b.*"], "run": ["bin/x"]}
        self.assertEqual([], check("unit", self.unit(subscribes=[subscription])))
        for broken in (dict(subscription, run=[]), dict(subscription, on=[]), dict(subscription, id="Notify"),
                       dict(subscription, timeout_seconds=0), dict(subscription, timeout_seconds=3601),
                       dict(subscription, extra=1), {"id": "notify", "on": ["a"]}):
            with self.subTest(subscription=broken):
                self.assertNotEqual([], check("unit", self.unit(subscribes=[broken])))
        self.assertNotEqual([], check("unit", self.unit(subscribes=[])))

    def test_names_that_other_modules_build_on(self):
        provides = self.unit()["provides"]
        for key, bad in (("events", ["sample.done"]), ("events", ["Sample.item.done"]), ("overlay_slots", ["a:b"]),
                         ("overlay_slots", ["Intro"]), ("extension_points", [{"id": "a.b", "description": "d"}])):
            with self.subTest(key=key, bad=bad):
                self.assertNotEqual([], check("unit", self.unit(provides=dict(provides, **{key: bad}))))

    def test_all_manifests_of_the_repository_pass(self):
        for manifest in sorted(SCHEMAS.parent.parent.glob("*/unit.json")):
            with self.subTest(manifest=manifest.parent.name):
                self.assertEqual([], check("unit", load(manifest)))


class TestDigestContract(unittest.TestCase):
    def test_digest_schema_accepts_only_tagged_form(self):
        contract = SCHEMAS / "digest" / "v1"
        registry, kind = schema.load_contract(contract)
        tagged = "sha256:" + "0" * 64
        self.assertEqual(schema.validate(tagged, kind, registry), [])
        for bad in (tagged.upper(), "0" * 64, tagged + "0", 5):
            self.assertTrue(schema.validate(bad, kind, registry), repr(bad))
        root, owner = registry.resolve("#/$defs/hex", registry.for_kind(kind)[1])
        self.assertEqual(schema.validate_node(registry, root, owner, "0" * 64), [])
        self.assertTrue(schema.validate_node(registry, root, owner, tagged))


if __name__ == "__main__":
    unittest.main()
