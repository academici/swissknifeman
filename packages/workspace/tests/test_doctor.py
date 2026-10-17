"""workspace doctor: structure, documents, bindings, legacy plans and git version, as check-result/v1."""
import json
import unittest
from pathlib import Path
from unittest import mock

import aicore
from aicore.util import schema
from aicore.workspace import bind, new_id, write_marker, write_project

from tests import BRIDGE_ROOT, MODULE_ROOT, TempCase
from workspace import doctor, gitutil, layout, projects

CHECK_RESULT = Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"
IDS = ["workspace.layout", "workspace.documents", "workspace.bindings", "workspace.legacy-plans", "workspace.git",
       "workspace.plans-migrator"]


class DoctorCase(TempCase):
    def checks(self):
        results = doctor.run_checks()
        registry, kind = schema.load_contract(CHECK_RESULT)
        for item in results:
            self.assertEqual(schema.validate(item, kind, registry), [], item)
        self.assertEqual([item["check_id"] for item in results], IDS)
        return {item["check_id"]: item for item in results}

    def statuses(self):
        return {key: value["status"] for key, value in self.checks().items()}


class StructureTests(DoctorCase):
    def test_without_a_workspace_the_layout_is_a_warning_and_documents_are_skipped(self):
        statuses = self.statuses()
        self.assertEqual(statuses["workspace.layout"], "warn")
        self.assertEqual(statuses["workspace.documents"], "skip")
        self.assertIn("workspace init", self.checks()["workspace.layout"]["remediation"])
        self.assertIn("WORKSPACE_NOT_INITIALIZED", self.checks()["workspace.layout"]["observed"])

    def test_a_fresh_workspace_is_all_ok(self):
        layout.init()
        self.assertEqual(set(self.statuses().values()), {"ok"})

    def test_unknown_entries_are_warnings(self):
        layout.init()
        (self.ws / "stray.txt").write_text("x", encoding="utf-8")
        project_id = new_id("prj")
        write_project(self.ws, project_id, "p")
        (self.ws / "projects" / project_id / "scratch").mkdir()
        (self.ws / "projects" / "loose").mkdir()
        item = self.checks()["workspace.layout"]
        self.assertEqual(item["status"], "warn")
        text = "\n".join(item["evidence"])
        self.assertIn("'stray.txt'", text)
        self.assertIn("projects/loose", text)
        self.assertIn(f"projects/{project_id}/scratch", text)

    def test_a_missing_git_repository_fails_the_layout(self):
        layout.init()
        import shutil
        shutil.rmtree(self.ws / ".git")
        self.assertEqual(self.statuses()["workspace.layout"], "fail")

    def test_a_damaged_workspace_json_fails_the_layout_and_skips_documents(self):
        layout.init()
        (self.ws / "workspace.json").write_text("{broken", encoding="utf-8")
        item = self.checks()["workspace.layout"]
        self.assertEqual(item["status"], "fail")
        self.assertIn("WORKSPACE_LAYOUT_INVALID", item["observed"])
        self.assertEqual(self.checks()["workspace.documents"]["status"], "skip")

    def test_documents_are_checked_against_their_contracts(self):
        layout.init()
        project_id = new_id("prj")
        write_project(self.ws, project_id, "p")
        folder = self.ws / "projects" / project_id
        self.assertEqual(self.statuses()["workspace.documents"], "ok")
        (folder / "project.json").write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
        (folder / "local-only.json").write_text("{}", encoding="utf-8")
        (folder / "migrations").mkdir()
        (folder / "migrations" / "mig_X.json").write_text("[]", encoding="utf-8")
        other = new_id("prj")
        write_project(self.ws, other, "q")
        (self.ws / "projects" / other / "project.json").write_text(
            (self.ws / "projects" / other / "project.json").read_text(encoding="utf-8").replace(other, project_id),
            encoding="utf-8")
        item = self.checks()["workspace.documents"]
        self.assertEqual(item["status"], "fail")
        text = "\n".join(item["evidence"])
        for fragment in (f"projects/{project_id}/project.json", f"projects/{project_id}/local-only.json",
                         f"projects/{project_id}/migrations/mig_X.json", "not its folder"):
            self.assertIn(fragment, text)

    def test_a_project_folder_without_project_json_fails(self):
        layout.init()
        (self.ws / "projects" / new_id("prj")).mkdir()
        self.assertEqual(self.statuses()["workspace.documents"], "fail")


class BindingTests(DoctorCase):
    def setUp(self):
        super().setUp()
        layout.init()

    def test_bound_checkouts_are_ok(self):
        projects.attach(self.checkout("alpha"))
        item = self.checks()["workspace.bindings"]
        self.assertEqual((item["status"], item["observed"]), ("ok", "1 projects bound on this machine"))

    def test_a_missing_path_and_a_foreign_marker_are_warnings_with_codes(self):
        root = self.checkout("alpha")
        project_id = projects.attach(root)["project_id"]
        gone = self.checkout("gone")
        stranger = self.checkout("stranger")
        write_marker(stranger, new_id("prj"), "workspace")
        plain = self.checkout("plain")
        for path in (gone, stranger, plain):
            bind(project_id, path)
        import shutil
        shutil.rmtree(gone)
        item = self.checks()["workspace.bindings"]
        self.assertEqual(item["status"], "warn")
        text = "\n".join(item["evidence"])
        self.assertIn("BINDING_PATH_MISSING", text)
        self.assertEqual(text.count("BINDING_MARKER_MISMATCH"), 2)
        self.assertIn("project rebind", item["remediation"])

    def test_a_binding_of_a_project_missing_in_the_workspace_is_reported(self):
        bind(new_id("prj"), self.checkout("alpha"))
        self.assertIn("PROJECT_UNKNOWN", "\n".join(self.checks()["workspace.bindings"]["evidence"]))

    def test_a_damaged_bindings_file_fails(self):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "bindings.json").write_text("{broken", encoding="utf-8")
        statuses = self.statuses()
        self.assertEqual((statuses["workspace.bindings"], statuses["workspace.legacy-plans"]), ("fail", "skip"))

    def test_legacy_plans_beside_a_workspace_store(self):
        root = self.checkout("alpha")
        projects.attach(root)
        self.assertEqual(self.statuses()["workspace.legacy-plans"], "ok")
        (root / "plans" / "p1").mkdir(parents=True)
        (root / "plans" / "p1" / "plan.json").write_text("{}", encoding="utf-8")
        item = self.checks()["workspace.legacy-plans"]
        self.assertEqual(item["status"], "warn")
        self.assertIn("LEGACY_PLANS_PRESENT", item["evidence"][0])

    def test_plans_beside_a_legacy_marker_are_expected(self):
        root = self.checkout("alpha", plans=["p1"])
        projects.attach(root)
        self.assertEqual(self.statuses()["workspace.legacy-plans"], "ok")


class GitTests(DoctorCase):
    def test_git_versions(self):
        for version, status in (((2, 43, 0), "ok"), ((2, 38, 0), "ok"), ((2, 30, 2), "warn"), (None, "fail")):
            with self.subTest(version=version), mock.patch.object(gitutil, "git_version", return_value=version):
                item = self.checks()["workspace.git"]
                self.assertEqual(item["status"], status)
                if status != "ok":
                    self.assertIn("WORKSPACE_GIT_TOO_OLD", item["observed"])



@unittest.skipUnless(BRIDGE_ROOT.is_dir(), "the hub bridge workspace-planner is not next to the module")
class MigratorTests(DoctorCase):
    def test_the_bridge_of_the_hub_is_found_by_its_port(self):
        item = self.checks()["workspace.plans-migrator"]
        self.assertEqual(item["status"], "ok")
        self.assertIn("workspace-planner", item["observed"])

    def test_without_a_plugin_the_check_warns_with_the_way_to_register_it(self):
        with mock.patch.dict("os.environ", {"SKM_UNITS_PATH": str(MODULE_ROOT)}):
            with mock.patch("workspace.migrator_port._unit_folders", return_value=[]):
                item = self.checks()["workspace.plans-migrator"]
        self.assertEqual(item["status"], "warn")
        self.assertIn("MIGRATOR_UNAVAILABLE", item["observed"])
        self.assertIn("plugins.workspace-planner.manifest", item["remediation"])


if __name__ == "__main__":
    unittest.main()
