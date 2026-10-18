"""Several workspaces on one machine: codes, the choice of the workspace, ``list``, ``clone`` and the codes of projects."""
import json
import os
from pathlib import Path
from unittest import mock

from aicore.workspace import WorkspaceError, read_marker, read_workspace
from aicore.workspace.integration import check_project
from tests import TempCase, git
from workspace import layout, projects, remote


class TwoWorkspaces(TempCase):
    """The sandbox has the workspace ``axioma``; ``other`` is a second one on the same machine."""

    def setUp(self):
        super().setUp()
        self.run_cli("init", "--code", "axioma")
        self.run_cli("init", "--code", "other")
        self.other = self.ws.parent / "other"
        # no selection by the environment: the commands choose by --workspace, the project or the only workspace
        os.environ.pop("SKM_WORKSPACE", None)
        # the commands run from the sandbox, not from the checkout of the test run, whose own marker would choose a workspace
        patcher = mock.patch("workspace.cli.Path.cwd", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_code_names_the_folder_and_the_document(self):
        self.assertEqual(read_workspace(self.ws)["code"], "axioma")
        self.assertEqual(read_workspace(self.other)["code"], "other")
        self.assertNotEqual(read_workspace(self.ws)["workspace_id"], read_workspace(self.other)["workspace_id"])

    def test_bad_codes_are_refused_and_nothing_is_made(self):
        for bad in ("Axioma", "a_b", "a-", "a--b", "1a", "a" * 41):
            code, _, err = self.run_cli("init", "--code", bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("WORKSPACE_CODE_INVALID", err)
        self.assertEqual(sorted(p.name for p in self.ws.parent.iterdir()), ["axioma", "other"])

    def test_list_shows_every_workspace(self):
        listed = self.json_cli("list")["workspaces"]
        self.assertEqual([row["code"] for row in listed], ["axioma", "other"])
        self.assertEqual(listed[0]["root"], str(self.ws))
        self.assertEqual(listed[0]["projects"], 0)

    def test_several_workspaces_need_a_choice(self):
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertIn("WORKSPACE_AMBIGUOUS", err)
        self.assertEqual(self.json_cli("status", "--workspace", "other")["code"], "other")
        self.assertEqual(self.json_cli("--workspace=axioma", "status")["code"], "axioma")
        with mock.patch.dict(os.environ, {"SKM_WORKSPACE": "other"}):
            self.assertEqual(self.json_cli("status")["code"], "other")

    def test_the_option_is_taken_anywhere_and_the_environment_is_restored(self):
        self.run_cli("status", "--workspace", "other", "--json")
        self.assertNotIn("SKM_WORKSPACE", os.environ)

    def test_the_workspace_of_the_project_you_are_in_is_chosen(self):
        root = self.checkout("alpha")
        self.assertEqual(self.run_cli("project", "attach", "--project", str(root), "--workspace", "other", "--json")[0], 0)
        self.assertEqual(read_marker(root)["workspace"], "other")
        with mock.patch("workspace.cli.Path.cwd", return_value=root):
            self.assertEqual(self.json_cli("status")["code"], "other")

    def test_an_unknown_workspace_is_not_initialized(self):
        code, _, err = self.run_cli("status", "--workspace", "nothing")
        self.assertEqual(code, 1)
        self.assertIn("WORKSPACE_NOT_INITIALIZED", err)

    def test_a_project_belongs_to_one_workspace(self):
        root = self.checkout("alpha")
        self.run_cli("project", "attach", "--project", str(root), "--workspace", "axioma")
        code, _, err = self.run_cli("project", "attach", "--project", str(root), "--workspace", "other")
        self.assertEqual(code, 1)
        self.assertIn("WORKSPACE_MISMATCH", err)
        code, _, err = self.run_cli("project", "rebind", "alpha", "--path", str(root), "--workspace", "other")
        self.assertEqual(code, 1)

    def test_scan_skips_the_checkouts_of_another_workspace(self):
        mine, theirs = self.checkout("mine"), self.checkout("theirs")
        self.run_cli("project", "attach", "--project", str(mine), "--workspace", "axioma")
        self.run_cli("project", "attach", "--project", str(theirs), "--workspace", "other")
        scan = self.json_cli("project", "scan", str(mine.parent), "--workspace", "axioma")
        self.assertEqual([item["project_id"] for item in scan["bound"]], ["mine"])
        self.assertEqual([item["reason"] for item in scan["skipped"]], ["OTHER_WORKSPACE"])

    def test_init_in_a_folder_of_another_workspace_is_refused(self):
        with self.assertRaises(WorkspaceError) as caught:
            layout.init("third", self.ws)
        self.assertEqual(caught.exception.code, "WORKSPACE_CODE_MISMATCH")


class ProjectCodes(TempCase):
    def setUp(self):
        super().setUp()
        layout.init("axioma")

    def test_the_code_is_made_from_the_folder_name(self):
        for name, code in (("alpha", "alpha"), ("My_App", "my-app"), ("Foo  Bar.v2", "foo-bar-v2"), ("2fast", "p-2fast"),
                           ("***", "project")):
            self.assertEqual(projects.slug(name), code, name)
        self.assertEqual(len(projects.slug("x" * 80)), 40)

    def test_an_explicit_code_and_a_bad_one(self):
        root = self.checkout("alpha")
        self.assertEqual(projects.attach(root, code="core")["project_id"], "core")
        self.assertEqual(read_marker(root)["project_id"], "core")
        other = self.checkout("beta")
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(other, code="Bad_Code")
        self.assertEqual(caught.exception.code, "PROJECT_CODE_INVALID")

    def test_a_taken_code_is_refused(self):
        projects.attach(self.checkout("alpha"), code="core")
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(self.checkout("beta"), code="core")
        self.assertEqual(caught.exception.code, "PROJECT_CODE_TAKEN")

    def test_the_workspace_documents_hold_the_code(self):
        root = self.checkout("alpha")
        projects.attach(root)
        self.assertEqual(json.loads((self.ws / "projects" / "alpha" / "project.json").read_text())["project_id"], "alpha")
        marker = json.loads((root / ".swissknifeman" / "project.json").read_text())
        self.assertEqual((marker["workspace"], marker["project_id"]), ("axioma", "alpha"))


class CloneDerivesTheCode(TempCase):
    def test_clone_puts_the_workspace_under_its_own_code(self):
        layout.init("axioma")
        bare = self.root / "origin.git"
        git(self.root, "init", "-q", "--bare", "-b", "main", str(bare))
        remote.connect("file://" + str(bare))
        from workspace import sync
        sync.sync(push=True)
        with mock.patch.dict(os.environ, {"SKM_HOME": str(self.root / "skm-b"), "SKM_WORKSPACES_ROOT": str(self.root / "wss-b")}):
            os.environ.pop("SKM_WORKSPACE", None)
            result = remote.clone("file://" + str(bare))
            self.assertEqual((result["code"], result["root"]), ("axioma", str(self.root / "wss-b" / "axioma")))
            self.assertEqual(read_workspace(self.root / "wss-b" / "axioma")["code"], "axioma")
            self.assertEqual([p.name for p in (self.root / "wss-b").iterdir()], ["axioma"])  # the staging clone is gone
            with self.assertRaises(WorkspaceError) as caught:  # the second clone finds the folder taken
                remote.clone("file://" + str(bare))
            self.assertEqual(caught.exception.code, "WORKSPACE_ROOT_NOT_EMPTY")
            self.assertEqual([p.name for p in (self.root / "wss-b").iterdir()], ["axioma"])

    def test_a_wrong_code_leaves_nothing(self):
        layout.init("axioma")
        bare = self.root / "origin.git"
        git(self.root, "init", "-q", "--bare", "-b", "main", str(bare))
        remote.connect("file://" + str(bare))
        from workspace import sync
        sync.sync(push=True)
        with mock.patch.dict(os.environ, {"SKM_HOME": str(self.root / "skm-b"), "SKM_WORKSPACES_ROOT": str(self.root / "wss-b")}):
            os.environ.pop("SKM_WORKSPACE", None)
            with self.assertRaises(WorkspaceError) as caught:
                remote.clone("file://" + str(bare), code="other")
            self.assertEqual(caught.exception.code, "WORKSPACE_CODE_MISMATCH")
            self.assertEqual(list((self.root / "wss-b").iterdir()), [])


class Integration(TempCase):
    """What ``project doctor`` asks: the marker, the workspace, the project in it, the binding, the folder name."""

    def setUp(self):
        super().setUp()
        layout.init("axioma")

    def statuses(self, root):
        return {item["status"] for item in check_project(root)}, " ".join(item["observed"] for item in check_project(root))

    def test_a_checkout_without_a_marker_is_skipped(self):
        self.assertEqual(self.statuses(self.checkout("plain"))[0], {"skip"})

    def test_an_attached_checkout_is_integrated(self):
        root = self.checkout("alpha")
        projects.attach(root)
        self.assertEqual(self.statuses(root)[0], {"ok"})

    def test_a_missing_binding_a_missing_project_and_a_missing_workspace_fail(self):
        root = self.checkout("alpha")
        projects.attach(root)
        from aicore.workspace import unbind
        unbind("alpha")
        statuses, text = self.statuses(root)
        self.assertIn("fail", statuses)
        self.assertIn("does not bind", text)
        import shutil
        shutil.rmtree(self.ws / "projects" / "alpha")
        self.assertIn("has no project", self.statuses(root)[1])
        shutil.rmtree(self.ws)
        self.assertIn("not on this machine", self.statuses(root)[1])

    def test_a_checkout_bound_elsewhere_fails_and_a_renamed_folder_warns(self):
        root = self.checkout("alpha")
        projects.attach(root)
        moved = Path(str(root) + "-copy")
        import shutil
        shutil.copytree(root, moved)
        statuses, text = self.statuses(moved)
        self.assertIn("fail", statuses)
        self.assertIn("not to this checkout", text)
        self.assertIn("is called", text)  # alpha-copy is not alpha
