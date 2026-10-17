"""Forms of gui-planner: the schema-form and model-picker queries, and the form annotations against the real planner
schemas (every pointer exists, the editable roots are properties, the enum table for the frontend is current)."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from .test_queries import BRIDGE, FIXTURES, GUI_DOC, PLAN, AdapterCase

sys.path.insert(0, str(BRIDGE))
import adapter  # noqa: E402

FORMS = {form["id"]: form for form in GUI_DOC["forms"]}
ENUM_POINTERS = ("/route/class", "/route/effort", "/review/mode", "/review/reviewer/class", "/review/reviewer/provider",
                 "/review/reviewer/effort", "/authority/kind", "/rag/need", "/rag/status")
ENUMS_FILE = FIXTURES / "plan-enums.json"


class TestFormQueries(AdapterCase):
    def test_item_form_carries_the_document_and_its_revision(self):
        out = self.ok("gui-planner.item-form", context={"item_id": "P2.2"}, params={"item_id": "P2.2"})
        self.assertEqual("gui-planner.item", out["form"])
        self.assertEqual("Query", out["document"]["title"])
        self.assertRegex(out["revision"], r"^sha256:[0-9a-f]{64}$")
        self.assertIn(out["form"], FORMS)

    def test_the_revision_of_the_form_is_the_one_the_planner_reports_for_a_write(self):
        first = self.ok("gui-planner.item-form", context={"item_id": "P2.1"})["revision"]
        self.assertEqual(first, self.ok("gui-planner.item-form", context={"item_id": "P2.1"})["revision"])

    def test_phase_form(self):
        out = self.ok("gui-planner.phase-form", params={"phase": "P2"})
        self.assertEqual(("gui-planner.phase", "Phase P2"), (out["form"], out["document"]["title"]))
        self.assertEqual("PLANNER_CONTEXT_MISSING", self.query("gui-planner.phase-form").code)

    def test_form_errors_keep_the_planner_code(self):
        self.assertEqual("PLAN_NOT_FOUND", self.query("gui-planner.item-form", umbrella="umbrella-missing",
                                                      context={"item_id": "P2.1"}).code)

    def test_models_lists_the_aicore_catalog_as_provider_model_rows(self):
        out = self.ok("gui-planner.models")
        rows = {row["id"]: row["cells"] for row in out["rows"]}
        self.assertIn("claude-code/sonnet", rows)
        self.assertEqual(("claude-code", "sonnet"), (rows["claude-code/sonnet"]["provider"], rows["claude-code/sonnet"]["model"]))
        self.assertIn("implementation", rows["claude-code/sonnet"]["class"])
        self.assertTrue(all("/" in row_id for row_id in rows))
        self.assertEqual(len(rows), out["total"])

    def test_models_without_a_reachable_catalog_is_unavailable(self):
        (self.home / "aicore-root").unlink()
        self.assertEqual("MODEL_CATALOG_UNAVAILABLE", self.query("gui-planner.models").code)
        (self.home / "aicore-root").write_text(os.environ["AICORE_ROOT"], encoding="utf-8")
        self.assertEqual("MODEL_CATALOG_UNAVAILABLE", self.query("gui-planner.models", umbrella="umbrella-fail").code)


def _planner_schema(kind):
    command = shutil.which("swissknifeman")
    if command is None:
        raise unittest.SkipTest("swissknifeman is not on PATH: the planner schemas cannot be read")
    out = subprocess.run([command, "planner", "--output", "json", "schema", kind], capture_output=True, text=True,
                         timeout=60, stdin=subprocess.DEVNULL, cwd=str(BRIDGE.parents[1]))  # planner needs a project
    try:
        return json.loads(out.stdout)["data"]
    except ValueError:
        raise unittest.SkipTest("the planner command line did not answer here: " + out.stderr.strip()[:200]) from None


class TestFormAnnotations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = _planner_schema("defs")["$defs"]
        cls.schemas = {kind: _planner_schema(kind) for kind in ("item", "phase", "decision")}

    def resolve(self, node):
        while True:
            if "$ref" in node:
                node = self.defs[node["$ref"].split("#/$defs/")[1]]
            elif "oneOf" in node:
                node = [branch for branch in node["oneOf"] if branch.get("type") != "null"][0]
            else:
                return node

    def at(self, kind, pointer):
        node = self.schemas[kind]
        for part in pointer.strip("/").split("/"):
            properties = self.resolve(node).get("properties", {})
            self.assertIn(part, properties, f"{kind}: {pointer} is not in the planner schema")
            node = properties[part]
        return self.resolve(node)

    def test_every_pointer_of_every_form_exists_in_the_planner_schema(self):
        for form_id, kind in (("gui-planner.item", "item"), ("gui-planner.phase", "phase"),
                              ("gui-planner.decision", "decision")):
            self.assertEqual(f"urn:swissknifeman:task:plan:{kind}:v1", FORMS[form_id]["schema"])
            for field in FORMS[form_id]["fields"]:
                with self.subTest(form=form_id, pointer=field["pointer"]):
                    self.at(kind, field["pointer"])

    def test_the_groups_used_are_declared_and_lifecycle_fields_are_readonly(self):
        for form in FORMS.values():
            groups = {group["id"] for group in form["groups"]}
            self.assertTrue({field["group"] for field in form["fields"]} <= groups, form["id"])
        item = {field["pointer"]: field for field in FORMS["gui-planner.item"]["fields"]}
        for pointer in ("/status", "/result", "/updated_at", "/artifacts"):
            self.assertTrue(item[pointer].get("readonly"), pointer)
        roots = {field["pointer"].split("/")[1] for field in item.values() if not field.get("readonly")}
        self.assertLessEqual(roots, adapter.ALLOW_ITEM)
        phase = {field["pointer"].split("/")[1] for field in FORMS["gui-planner.phase"]["fields"]
                 if not field.get("readonly")}
        self.assertLessEqual(phase, adapter.ALLOW_PHASE)

    def test_the_allowlists_are_properties_of_the_planner_schemas(self):
        self.assertLessEqual(adapter.ALLOW_ITEM, set(self.schemas["item"]["properties"]))
        self.assertLessEqual(adapter.ALLOW_PHASE, set(self.schemas["phase"]["properties"]))

    def test_the_enum_table_for_the_frontend_is_current(self):
        found = {}
        for pointer in ENUM_POINTERS:
            enum = self.at("item", pointer).get("enum")
            if enum:
                found[pointer] = enum
        if os.environ.get("SKM_REGENERATE_FIXTURES"):
            ENUMS_FILE.write_text(json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(ENUMS_FILE.read_text(encoding="utf-8")), found,
                         "plan-enums.json is stale: run the tests with SKM_REGENERATE_FIXTURES=1")
        self.assertIn("/route/class", found)


if __name__ == "__main__":
    unittest.main()
