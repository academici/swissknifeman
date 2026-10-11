"""Extension slots: orchestration.scenario and orchestration.options stay optional; a bridge supplies the options schema."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import bridges, check, context, extensions, ops, schema, store  # noqa: E402
from task.plan.model import PlanError  # noqa: E402

try:
    from . import test_envelope, test_lifecycle
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import test_envelope
    import test_lifecycle

SHIPPED = Path(__file__).resolve().parents[2] / "bridges"
OPTIONS = {"reviewer": "grok/grok-4.7/high", "limits": {"review_rounds": 2},
           "stages": [{"role": "executor", "model_class": "implementation"}], "on_blocked": "report"}
SUPPLIED = {
    "$schema": schema.DIALECT, "$id": "urn:test:options:v1", "type": "object",
    "properties": {"reviewer": {"$ref": "#/$defs/selector"}, "limits": {"type": "object"},
                   "stages": {"type": "array"}, "on_blocked": {"type": "string", "enum": ["stop", "report"]}},
    "additionalProperties": False,
    "$defs": {"selector": {"type": "string", "pattern": "^[a-z][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._:-]*(/[a-z]+)?$"}},
}


def errors(plan) -> list:
    return [issue for issue in check.check(plan) if issue.level == "error"]


def manifest(name: str, extends: dict | None = None) -> dict:
    document = {"$schema": "urn:swissknifeman:task:plan:bridge:v1", "name": name, "partner": "partner-x",
                "direction": "out", "contract": "partner-x/v1", "summary": "Test bridge.",
                "entrypoints": {"probe": "probe.py"}}
    if extends is not None:
        document["extends"] = extends
    return document


class SlotCase(test_lifecycle.LifeCase):
    """LIFE plan with a temporary bridge root (no bridge until a test adds one)."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bridge_root = Path(tmp.name) / "bridges"
        patcher = mock.patch.object(bridges, "default_root", return_value=self.bridge_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        extensions.clear_cache()
        self.addCleanup(extensions.clear_cache)

    def add_bridge(self, name: str, document: dict | None = SUPPLIED, path: str = "schemas/options.schema.json"):
        directory = self.bridge_root / name
        (directory / Path(path).parent).mkdir(parents=True, exist_ok=True)
        (directory / "probe.py").write_text("", encoding="utf-8")
        if document is not None:
            (directory / path).write_text(json.dumps(document), encoding="utf-8")
        (directory / "bridge.json").write_text(json.dumps(manifest(name, {"orchestration.options": path})),
                                               encoding="utf-8")
        extensions.clear_cache()

    def item(self, ref: str = "P1.1") -> dict:
        return copy.deepcopy(store.load_plan(self.root).items[ref])


class WithoutTheFieldTests(SlotCase):
    def test_a_plan_without_the_fields_reads_no_bridge_and_keeps_its_context(self):
        with mock.patch.object(bridges, "scan", side_effect=AssertionError("bridges read")):
            plan = store.load_plan(self.root)
            self.assertEqual(errors(plan), [])
            ops.patch(plan, "P1.1", {"summary": "changed"})
            pack = context.collect(store.load_plan(self.root), "P1.1", with_scout=False)
        self.assertEqual(pack["orchestration"], {"strategy": "dag", "scenario": "solo", "scenario_source": "default"})

    def test_the_scenario_is_stored_without_a_bridge_and_resolved_item_phase_plan(self):
        plan = store.load_plan(self.root)
        ops.patch(plan, "plan", {"orchestration": {"scenario": "plan-wide"}})
        ops.patch(plan, "P1", {"orchestration": {"scenario": "phase-wide"}})
        ops.patch(plan, "P1.1", {"orchestration": {"scenario": "careful"}})
        plan = store.load_plan(self.root)
        found = {ref: context.collect(plan, ref, with_scout=False)["orchestration"] for ref in ("P1.1", "P1.2", "P2.1")}
        self.assertEqual({ref: (o["scenario"], o["scenario_source"]) for ref, o in found.items()},
                         {"P1.1": ("careful", "item"), "P1.2": ("phase-wide", "phase"), "P2.1": ("plan-wide", "plan")})
        with self.assertRaises(PlanError) as caught:
            ops.patch(plan, "P1.1", {"orchestration": {"scenario": "Not A Name"}})
        self.assertEqual(caught.exception.code, "SCHEMA_INVALID")


class SuppliedTests(SlotCase):
    def test_supplied_options_are_accepted_and_refused_by_the_bridge_schema(self):
        self.add_bridge("exec")
        plan = store.load_plan(self.root)
        ops.patch(plan, "P1.1", {"orchestration": {"scenario": "standard", "options": OPTIONS}})
        self.assertEqual(self.item()["orchestration"]["options"], OPTIONS)
        self.assertEqual(errors(store.load_plan(self.root)), [])
        for wrong, code in (({"reviewer": "Bad Selector"}, "pattern"), ({"colour": 1}, "additional"),
                            ({"on_blocked": "later"}, "enum"), ([1], "type")):
            with self.subTest(wrong=wrong):
                with self.assertRaises(PlanError) as caught:
                    ops.patch(store.load_plan(self.root), "P1.2", {"orchestration": {"options": wrong}})
                self.assertEqual(caught.exception.code, "SCHEMA_INVALID")
                self.assertEqual({issue.code for issue in caught.exception.issues}, {code})

    def test_the_shipped_bridge_supplies_the_run_options(self):
        with mock.patch.object(bridges, "default_root", return_value=SHIPPED):
            extensions.clear_cache()
            self.assertEqual(len(extensions.suppliers("orchestration.options")), 1)
            item = self.item()
            item["orchestration"] = {"scenario": "standard", "options": {
                **OPTIONS, "rules": ["Keep the diff small."], "skills": [{"role": "executor", "names": ["tdd"]}],
                "limits": {"review_rounds": 2, "tokens_max": 0}}}
            self.assertEqual(schema.validate(item, "item"), [])
            item["orchestration"]["options"]["stages"][0]["effort"] = "max"
            self.assertEqual([i.code for i in schema.validate(item, "item")], ["enum"])
        extensions.clear_cache()


class UnavailableTests(SlotCase):
    def assert_unavailable(self, needle: str):
        item = self.item()
        item["orchestration"] = {"options": OPTIONS}
        issues = schema.validate(item, "item")
        self.assertEqual([(i.path, i.code) for i in issues], [("/orchestration/options", "extension")])
        self.assertIn("EXTENSION_UNAVAILABLE: orchestration.options: ", issues[0].message)
        self.assertIn(needle, issues[0].message)
        with self.assertRaises(PlanError) as caught:
            ops.patch(store.load_plan(self.root), "P1.1", {"orchestration": {"options": OPTIONS}})
        self.assertEqual(caught.exception.code, "EXTENSION_UNAVAILABLE")
        self.assertNotIn("orchestration", self.item())

    def test_options_without_a_supplier_are_refused_with_a_clear_code(self):
        self.add_bridge("plain", document=None, path="probe.py")  # a file, but no bridge is an extension of it
        (self.bridge_root / "plain" / "bridge.json").write_text(json.dumps(manifest("plain")), encoding="utf-8")
        extensions.clear_cache()
        self.assert_unavailable("no bridge supplies it")

    def test_two_suppliers_are_ambiguous(self):
        self.add_bridge("first")
        self.add_bridge("second")
        self.assert_unavailable("bridges first, second all supply it")

    def test_an_unusable_supplied_schema_is_unavailable_not_a_crash(self):
        self.add_bridge("broken", document={"type": "object", "minimum": 1})
        self.assert_unavailable("unsupported keyword 'minimum'")

    def test_check_reports_the_field_and_the_cli_returns_the_code(self):
        status, out, _ = test_envelope.run("--output", "json", "set", str(self.root), "P1.1", "--json",
                                           json.dumps({"orchestration": {"options": OPTIONS}}))
        document = json.loads(out)
        self.assertEqual(schema.validate(document, "envelope"), [])
        self.assertNotEqual(status, 0)
        self.assertEqual(document["error"]["code"], "EXTENSION_UNAVAILABLE")
        store.atomic_write(self.root / "phases/P1/P1.1.json", json.dumps(
            {**self.item(), "orchestration": {"options": OPTIONS}}, ensure_ascii=False, indent=2) + "\n")
        found = errors(store.load_plan(self.root))
        self.assertEqual([(e.code, e.where) for e in found], [("schema", "phases/P1/P1.1.json/orchestration/options")])
        self.assertIn("EXTENSION_UNAVAILABLE", found[0].message)


class ManifestTests(SlotCase):
    def test_extends_must_name_a_known_slot_and_a_file_inside_the_bridge(self):
        self.add_bridge("exec")
        path = self.bridge_root / "exec" / "bridge.json"
        for extends in ({"orchestration.options": "missing.json"}, {"orchestration.options": "../exec/../x.json"},
                        {"orchestration.options": "/etc/hostname"}, {"item.extra": "probe.py"}):
            with self.subTest(extends=extends):
                path.write_text(json.dumps(manifest("exec", extends)), encoding="utf-8")
                with self.assertRaises(PlanError) as caught:
                    bridges.load(path.parent)
                self.assertEqual(caught.exception.code, "BRIDGE_INVALID")


if __name__ == "__main__":
    unittest.main()
