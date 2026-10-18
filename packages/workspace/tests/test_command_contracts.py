"""The typed outputs of the workspace commands (``schemas/command/v1``): the real ``--json`` output of every command
validates against its contract, and a document that breaks the contract does not."""
import json
import os
import subprocess
import unittest
from unittest import mock

from aicore.util import schema
from aicore.workspace import write_project

from tests import MODULE_ROOT, TempCase, git

CONTRACT = MODULE_ROOT / "schemas" / "command" / "v1"
KINDS = ["common", "connect", "error", "init", "list", "project-attach", "project-list"]


def load_schema(kind: str) -> dict:
    return json.loads((CONTRACT / f"{kind}.schema.json").read_text(encoding="utf-8"))


class ContractFilesTests(unittest.TestCase):
    def test_the_set_loads_under_the_closed_profile(self):
        registry, kinds = schema.load_contract_set(CONTRACT)
        self.assertEqual(kinds, KINDS)
        for kind in kinds:
            self.assertEqual(registry.for_kind(kind)[1], f"urn:swissknifeman:workspace:command:{kind}:v1")

    def test_every_object_is_closed_and_every_property_described(self):
        def walk(node, where):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object" and "properties" in node:
                self.assertIs(node.get("additionalProperties"), False, where)
            for name, child in node.get("properties", {}).items():
                self.assertIn("description", child, f"{where}/{name}")
                walk(child, f"{where}/{name}")
            for name, child in node.get("$defs", {}).items():
                self.assertIn("description", child, f"{where}/$defs/{name}")
                walk(child, f"{where}/$defs/{name}")
            walk(node.get("items"), f"{where}/items")

        for kind in KINDS:
            walk(load_schema(kind), kind)

    def test_the_contract_is_registered_in_the_unit(self):
        unit = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
        ids = {item["id"]: item["path"] for item in unit["provides"]["contracts"]}
        self.assertEqual(ids["urn:swissknifeman:workspace:command"], "schemas/command/v1")


class CommandOutputCase(TempCase):
    """``self.valid(kind, *args)`` runs a command with ``--json`` and checks its stdout against the contract."""

    def setUp(self):
        super().setUp()
        self.registry, _ = schema.load_contract_set(CONTRACT)

    def issues(self, kind, doc):
        return [issue.message for issue in schema.validate(doc, kind, self.registry)]

    def valid(self, kind, *args, code=0):
        status, out, err = self.run_cli(*args, "--json")
        self.assertEqual(status, code, err)
        doc = json.loads(out)  # the whole stdout is one document
        self.assertEqual(self.issues(kind, doc), [], doc)
        return doc

    def bare(self, name="origin.git"):
        path = self.root / name
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True, capture_output=True)
        return path


class SuccessOutputTests(CommandOutputCase):
    def test_init_created_and_already_initialized(self):
        created = self.valid("init", "init", "--code", "axioma")
        self.assertEqual((created["created"], created["already_initialized"]), (True, False))
        again = self.valid("init", "init", "--code", "axioma")
        self.assertEqual((again["created"], again["already_initialized"]), (False, True))

    def test_list_without_and_with_workspaces(self):
        self.assertEqual(self.valid("list", "list"), {"workspaces": []})
        self.run_cli("init", "--code", "axioma")
        rows = self.valid("list", "list")["workspaces"]
        self.assertEqual([(row["code"], row["remote"], row["projects"]) for row in rows], [("axioma", None, 0)])
        self.run_cli("connect", "--remote", "file://" + str(self.bare()))
        self.assertTrue(self.valid("list", "list")["workspaces"][0]["remote"].startswith("file://"))

    def test_list_row_of_a_workspace_with_a_broken_document(self):
        self.run_cli("init", "--code", "axioma")
        (self.ws / "workspace.json").write_text("{", encoding="utf-8")
        rows = self.valid("list", "list")["workspaces"]
        self.assertIsNone(rows[0]["workspace_id"])

    def test_connect_empty_and_same_remote(self):
        self.run_cli("init", "--code", "axioma")
        empty = self.valid("connect", "connect", "--remote", "file://" + str(self.bare("empty.git")))
        self.assertEqual((empty["classification"], empty["branch"]), ("empty", "main"))
        git(self.ws, "remote", "remove", "origin")
        same = self.bare("same.git")
        git(self.ws, "push", "-q", str(same), "HEAD:refs/heads/main")
        self.assertEqual(self.valid("connect", "connect", "--remote", "file://" + str(same))["classification"], "same")

    def test_project_list_empty_bound_unbound_and_invalid(self):
        self.run_cli("init", "--code", "axioma")
        self.assertEqual(self.valid("project-list", "project", "list"), {"projects": []})
        alpha = self.checkout("alpha")
        self.valid("project-attach", "project", "attach", "--project", str(alpha))
        write_project(self.ws, "unbound", "Unbound")
        broken = self.ws / "projects" / "broken"
        broken.mkdir()
        (broken / "project.json").write_text("{", encoding="utf-8")
        rows = {row["project_id"]: row for row in self.valid("project-list", "project", "list")["projects"]}
        self.assertEqual(set(rows), {"alpha", "unbound", "broken"})
        self.assertEqual((rows["alpha"]["bound"], rows["alpha"]["paths"]), (True, [str(alpha)]))
        self.assertEqual((rows["unbound"]["bound"], rows["unbound"]["paths"], rows["unbound"]["status"]),
                         (False, [], "active"))
        self.assertEqual((rows["broken"]["status"], rows["broken"]["name"]), ("invalid", None))
        self.assertIn("error", rows["broken"])

    def test_project_attach_new_again_and_legacy(self):
        self.run_cli("init", "--code", "axioma")
        alpha = self.checkout("alpha")
        first = self.valid("project-attach", "project", "attach", "--project", str(alpha))
        self.assertEqual((first["created"], first["marker_written"], first["plans_store"]), (True, True, "workspace"))
        self.assertIn("next", first)
        again = self.valid("project-attach", "project", "attach", "--project", str(alpha))
        self.assertEqual((again["created"], again["marker_written"]), (False, False))
        self.assertNotIn("next", again)
        legacy = self.valid("project-attach", "project", "attach", "--project", str(self.checkout("beta", plans=["p1"])),
                            "--name", "Beta", "--code", "beta-code")
        self.assertEqual((legacy["plans_store"], legacy["project_id"], legacy["name"]), ("legacy", "beta-code", "Beta"))


class ErrorOutputTests(CommandOutputCase):
    def refusal(self, *args, status=1, env=None):
        with mock.patch.dict(os.environ, env or {}):
            code, out, err = self.run_cli(*args, "--json")
        self.assertEqual(code, status, err)
        doc = json.loads(out)
        self.assertEqual(self.issues("error", doc), [], doc)
        self.assertEqual(err, f"{doc['error']['code']}: {doc['error']['message']}\n")
        return doc["error"]

    def test_a_refusal_prints_the_error_document_and_the_stderr_line(self):
        self.assertEqual(self.refusal("status")["code"], "WORKSPACE_NOT_INITIALIZED")
        self.assertEqual(self.refusal("project", "list")["code"], "WORKSPACE_NOT_INITIALIZED")
        self.assertEqual(self.refusal("init", "--code", "Bad Code")["code"], "WORKSPACE_CODE_INVALID")
        self.run_cli("init", "--code", "axioma")
        self.assertEqual(self.refusal("project", "show", "nothing")["code"], "PROJECT_UNKNOWN")
        self.assertEqual(self.refusal("project", "attach", "--project", str(self.root / "absent"))["code"],
                         "PROJECT_CONTEXT_REQUIRED")

    def test_a_refusal_before_the_workspace_is_chosen(self):
        self.run_cli("init", "--code", "axioma")
        self.run_cli("init", "--code", "beta")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.root)  # outside any project: its marker would choose the workspace
        self.assertEqual(self.refusal("project", "list", env={"SKM_WORKSPACE": ""})["code"], "WORKSPACE_AMBIGUOUS")

    def test_an_invalid_argument_value_is_exit_two_with_its_document(self):
        error = self.refusal("init", "--code", "axioma", status=2, env={"SKM_WORKSPACES_ROOT": "relative"})
        self.assertEqual(error["code"], "INVALID_ARGUMENT")
        self.assertIn("SKM_WORKSPACES_ROOT", error["message"])

    def test_no_document_without_json(self):
        code, out, err = self.run_cli("status")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("WORKSPACE_NOT_INITIALIZED: "))


class BrokenDocumentTests(CommandOutputCase):
    def test_documents_that_break_the_contract_are_rejected(self):
        good = self.valid("init", "init", "--code", "axioma")
        row = {"code": "a", "workspace_id": None, "root": "/r", "remote": None, "projects": 0}
        project = {"project_id": "a", "name": "A", "status": "active", "bound": False, "paths": []}
        connect = {"root": "/r", "remote": "u", "branch": "main", "classification": "empty", "next": "n"}
        attach = {"workspace": "w", "project_id": "p", "name": "P", "created": True, "marker_written": True,
                  "plans_store": "legacy", "binding": {"paths": ["/p"], "primary": "/p"}}
        cases = {
            "init": [dict(good, extra=1), {k: v for k, v in good.items() if k != "device_id"},
                     dict(good, code="Axioma"), dict(good, workspace_id="ws_1"), dict(good, root="relative"),
                     dict(good, created="yes")],
            "list": [{}, {"workspaces": [{k: v for k, v in row.items() if k != "projects"}]},
                     {"workspaces": [dict(row, projects=-1)]}, {"workspaces": [dict(row, code="A")]}],
            "connect": [dict(connect, classification="other"), {k: v for k, v in connect.items() if k != "next"}],
            "project-list": [{"projects": [dict(project, status="gone")]}, {"projects": [dict(project, paths=["rel"])]},
                             {"projects": [dict(project, error="lower")]}],
            "project-attach": [dict(attach, plans_store="elsewhere"),
                               dict(attach, binding={"paths": [], "primary": "/p"}), dict(attach, next="")],
            "error": [{}, {"error": {"code": "lower", "message": "m"}}, {"error": {"code": "A", "message": ""}},
                      {"code": "A", "message": "m"}],
        }
        for kind, documents in cases.items():
            for number, document in enumerate(documents):
                with self.subTest(kind=kind, case=number):
                    self.assertNotEqual(self.issues(kind, document), [])


if __name__ == "__main__":
    unittest.main()
