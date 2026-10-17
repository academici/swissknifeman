"""workspace project attach|list|show|scan|rebind|detach."""
import json
import os
import subprocess
import unittest

from aicore.workspace import (WorkspaceError, bind, new_id, read_bindings, read_marker, read_project, write_marker,
                              write_project)

from tests import TempCase, git
from workspace import layout, projects

REMOTE = "git@github.com:academici/swissknifeman.git"
SAME_REMOTE_URL = "https://token@github.com/academici/swissknifeman"


class ProjectCase(TempCase):
    def setUp(self):
        super().setUp()
        layout.init()

    def workspace_files(self):
        return sorted(str(p.relative_to(self.ws)) for p in self.ws.rglob("*") if ".git" not in p.parts)


class AttachTests(ProjectCase):
    def test_a_new_checkout_gets_a_project_a_marker_a_plans_folder_and_a_binding(self):
        root = self.checkout("alpha")
        result = projects.attach(root)
        project_id = result["project_id"]
        self.assertTrue(project_id.startswith("prj_"))
        self.assertEqual((result["created"], result["marker_written"], result["plans_store"]), (True, True, "workspace"))
        self.assertEqual(read_marker(root), {"$schema": "urn:swissknifeman:aicore:project-marker:v1",
                                             "project_id": project_id, "plans_store": "workspace"})
        record = read_project(self.ws, project_id)
        self.assertEqual((record["name"], record["identity"]["remotes"], record["status"]), ("alpha", [], "active"))
        self.assertTrue((self.ws / "projects" / project_id / "plans").is_dir())
        self.assertEqual(result["binding"], {"paths": [str(root)], "primary": str(root)})
        self.assertEqual(read_bindings()["projects"][project_id]["paths"], [str(root)])

    def test_the_marker_is_written_but_never_committed(self):
        root = self.checkout("alpha")
        result = projects.attach(root)
        self.assertEqual(git(root, "status", "--porcelain").strip(), "?? .swissknifeman/")
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True, text=True)
        self.assertNotEqual(head.returncode, 0)  # no commit was made
        self.assertIn("add .swissknifeman/project.json", result["next"])
        self.assertIn(str(root), result["next"])

    def test_a_checkout_with_plan_folders_waits_for_migration(self):
        root = self.checkout("alpha", plans=["2026.10.01-№1-X"])
        result = projects.attach(root)
        self.assertEqual(result["plans_store"], "legacy")
        self.assertEqual(read_marker(root)["plans_store"], "legacy")
        self.assertFalse((self.ws / "projects" / result["project_id"] / "plans").exists())
        self.assertTrue((self.ws / "projects" / result["project_id"] / "project.json").is_file())

    def test_a_plans_folder_with_only_files_counts_as_empty(self):
        root = self.checkout("alpha")
        (root / "plans").mkdir()
        (root / "plans" / "README.md").write_text("x", encoding="utf-8")
        self.assertEqual(projects.attach(root)["plans_store"], "workspace")

    def test_attach_again_only_keeps_the_binding(self):
        root = self.checkout("alpha")
        first = projects.attach(root)
        files = self.workspace_files()
        again = projects.attach(root)
        self.assertEqual((again["project_id"], again["created"], again["marker_written"]), (first["project_id"], False, False))
        self.assertNotIn("next", again)
        self.assertEqual(self.workspace_files(), files)
        self.assertEqual(read_bindings()["projects"][first["project_id"]]["paths"], [str(root)])

    def test_a_second_clone_with_the_marker_joins_the_same_project(self):
        first = self.checkout("alpha")
        project_id = projects.attach(first)["project_id"]
        clone = self.checkout("alpha-clone")
        write_marker(clone, project_id, "workspace")  # arrives with git pull
        result = projects.attach(clone)
        self.assertEqual((result["project_id"], result["created"], result["marker_written"]), (project_id, False, False))
        self.assertEqual(result["binding"]["paths"], [str(first), str(clone)])
        self.assertEqual(result["binding"]["primary"], str(first))

    def test_a_marker_whose_project_is_missing_creates_the_project_record_only(self):
        root = self.checkout("alpha", remotes=[("origin", SAME_REMOTE_URL)])
        project_id = new_id("prj")
        write_marker(root, project_id, "workspace")
        result = projects.attach(root)
        self.assertEqual((result["project_id"], result["created"], result["marker_written"]), (project_id, True, False))
        record = read_project(self.ws, project_id)
        self.assertEqual(record["identity"]["remotes"], ["github.com/academici/swissknifeman"])
        self.assertFalse((self.ws / "projects" / project_id / "plans").exists())  # sync/clone brings the plans

    def test_remotes_match_only_with_confirmation(self):
        first = self.checkout("alpha", remotes=[("origin", REMOTE)])
        project_id = projects.attach(first)["project_id"]
        self.assertEqual(read_project(self.ws, project_id)["identity"]["remotes"],
                         ["github.com/academici/swissknifeman"])
        other = self.checkout("renamed", remotes=[("origin", SAME_REMOTE_URL)])
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(other, interactive=False)
        self.assertEqual(caught.exception.code, "ATTACH_CONFIRM_REQUIRED")
        self.assertIn(project_id, str(caught.exception))
        self.assertIsNone(read_marker(other))
        self.assertEqual(list(read_bindings()["projects"]), [project_id])
        result = projects.attach(other, yes=True)
        self.assertEqual((result["project_id"], result["created"], result["marker_written"]), (project_id, False, True))
        self.assertEqual(result["binding"]["paths"], [str(first), str(other)])
        self.assertEqual(read_marker(other)["project_id"], project_id)

    def test_an_interactive_answer_decides(self):
        first = self.checkout("alpha", remotes=[("origin", REMOTE)])
        project_id = projects.attach(first)["project_id"]
        no = self.checkout("no", remotes=[("origin", REMOTE)])
        questions = []
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(no, interactive=True, confirm=lambda q: questions.append(q) or False)
        self.assertEqual(caught.exception.code, "ATTACH_CONFIRM_REQUIRED")
        self.assertIn(project_id, questions[0])
        yes = self.checkout("yes", remotes=[("origin", REMOTE)])
        self.assertEqual(projects.attach(yes, interactive=True, confirm=lambda q: True)["project_id"], project_id)

    def test_several_matching_projects_are_ambiguous_even_with_yes(self):
        one = write_project(self.ws, new_id("prj"), "one", remotes=["github.com/academici/swissknifeman"])
        two = write_project(self.ws, new_id("prj"), "two", remotes=["github.com/academici/swissknifeman"])
        root = self.checkout("alpha", remotes=[("origin", REMOTE)])
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(root, yes=True)
        self.assertEqual(caught.exception.code, "PROJECT_AMBIGUOUS")
        self.assertIn(one["project_id"], str(caught.exception))
        self.assertIn(two["project_id"], str(caught.exception))
        self.assertIsNone(read_marker(root))

    def test_the_basename_is_never_an_identity(self):
        first = self.checkout("same", remotes=[("origin", "git@github.com:a/one.git")])
        second_dir = self.root / "other" / "same"
        second_dir.mkdir(parents=True)
        git(second_dir, "init", "-q")
        git(second_dir, "remote", "add", "origin", "git@github.com:a/two.git")
        a, b = projects.attach(first), projects.attach(second_dir)
        self.assertNotEqual(a["project_id"], b["project_id"])
        third_dir = self.root / "third" / "same"
        third_dir.mkdir(parents=True)
        git(third_dir, "init", "-q")
        self.assertNotIn(projects.attach(third_dir)["project_id"], (a["project_id"], b["project_id"]))

    def test_a_local_remote_is_not_an_identity(self):
        a = self.checkout("a", remotes=[("origin", "/srv/shared.git")])
        b = self.checkout("b", remotes=[("origin", "/srv/shared.git")])
        first, second = projects.attach(a), projects.attach(b)
        self.assertNotEqual(first["project_id"], second["project_id"])
        self.assertEqual(read_project(self.ws, first["project_id"])["identity"]["remotes"], [])

    def test_an_invalid_marker_is_refused(self):
        root = self.checkout("alpha")
        (root / ".swissknifeman").mkdir()
        (root / ".swissknifeman" / "project.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(root)
        self.assertEqual(caught.exception.code, "PROJECT_MARKER_INVALID")
        self.assertEqual(read_bindings()["projects"], {})

    def test_attach_needs_a_workspace_and_a_folder(self):
        root = self.checkout("alpha")
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(self.root / "missing")
        self.assertEqual(caught.exception.code, "BINDING_PATH_MISSING")
        os.environ["SKM_WORKSPACE_ROOT"] = str(self.root / "no-workspace")
        with self.assertRaises(WorkspaceError) as caught:
            projects.attach(root)
        self.assertEqual(caught.exception.code, "WORKSPACE_NOT_INITIALIZED")

    def test_the_project_record_holds_no_absolute_path_or_userinfo(self):
        root = self.checkout("alpha", remotes=[("origin", SAME_REMOTE_URL)])
        project_id = projects.attach(root)["project_id"]
        text = (self.ws / "projects" / project_id / "project.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("token", text)
        self.assertNotIn(str(self.root), (root / ".swissknifeman" / "project.json").read_text(encoding="utf-8"))

    def test_an_unusable_name_is_a_value_error(self):
        with self.assertRaises(ValueError):
            projects.attach(self.checkout("alpha"), name="~home")
        self.assertEqual(read_bindings()["projects"], {})


class ListShowTests(ProjectCase):
    def test_list_and_show(self):
        root = self.checkout("alpha", plans=["p1"])
        project_id = projects.attach(root)["project_id"]
        other = write_project(self.ws, new_id("prj"), "unbound")
        rows = {row["project_id"]: row for row in projects.list_projects()}
        self.assertEqual(rows[project_id], {"project_id": project_id, "name": "alpha", "status": "active", "bound": True,
                                            "paths": [str(root)]})
        self.assertEqual((rows[other["project_id"]]["bound"], rows[other["project_id"]]["paths"]), (False, []))
        folder = self.ws / "projects" / project_id
        (folder / "plans" / "2026.10.17-№1-X").mkdir(parents=True)
        (folder / "plans" / "archive" / "old").mkdir(parents=True)
        (folder / "legacy-plans" / "notes").mkdir(parents=True)
        (folder / "migrations").mkdir()
        (folder / "migrations" / "mig_X.json").write_text("{}", encoding="utf-8")
        shown = projects.show(project_id)
        self.assertEqual(shown["project"]["name"], "alpha")
        self.assertEqual(shown["binding"]["paths"], [str(root)])
        self.assertEqual(shown["plans"], {"plans": ["2026.10.17-№1-X"], "archived": ["old"], "legacy": ["notes"],
                                          "migrations": ["mig_X"]})

    def test_show_of_an_unknown_project(self):
        for value in (new_id("prj"), "nonsense", "../x"):
            with self.assertRaises(WorkspaceError) as caught:
                projects.show(value)
            self.assertEqual(caught.exception.code, "PROJECT_UNKNOWN")

    def test_a_damaged_project_is_listed_as_invalid(self):
        project_id = new_id("prj")
        folder = self.ws / "projects" / project_id
        folder.mkdir(parents=True)
        (folder / "project.json").write_text("{broken", encoding="utf-8")
        row = projects.list_projects()[0]
        self.assertEqual((row["project_id"], row["status"], row["error"]), (project_id, "invalid", "WORKSPACE_LAYOUT_INVALID"))


class ScanTests(ProjectCase):
    def marked(self, relative, project_id, store="workspace"):
        path = self.root / "scan" / relative
        path.mkdir(parents=True)
        write_marker(path, project_id, store)
        return path

    def test_scan_binds_known_projects_and_reports_unknown_ones(self):
        project_id = projects.attach(self.checkout("alpha"))["project_id"]
        known = self.marked("a/b/repo", project_id)
        deep = self.marked("1/2/3/4/repo", project_id)  # depth 5: too deep
        modules = self.marked("node_modules/x", project_id)
        vendor = self.marked("vendor/y", project_id)
        stranger = self.marked("c/stranger", new_id("prj"))
        broken = self.root / "scan" / "d" / "broken"
        (broken / ".swissknifeman").mkdir(parents=True)
        (broken / ".swissknifeman" / "project.json").write_text("[]", encoding="utf-8")
        files = self.workspace_files()
        result = projects.scan([self.root / "scan", self.root / "missing"])
        self.assertEqual([item["path"] for item in result["bound"]], [str(known)])
        self.assertEqual([item["project_id"] for item in result["unknown"]], [read_marker(stranger)["project_id"]])
        reasons = {item["path"]: item["reason"] for item in result["skipped"]}
        self.assertEqual(reasons[str(broken)], "PROJECT_MARKER_INVALID")
        self.assertEqual(reasons[str(self.root / "missing")], "missing")
        paths = read_bindings()["projects"][project_id]["paths"]
        self.assertIn(str(known), paths)
        for left_out in (deep, modules, vendor, stranger):
            self.assertNotIn(str(left_out), paths)
        self.assertEqual(self.workspace_files(), files)  # scan creates no project

    def test_the_directory_itself_may_be_a_checkout(self):
        project_id = projects.attach(self.checkout("alpha"))["project_id"]
        root = self.marked("direct", project_id)
        self.assertEqual(projects.scan([root])["bound"][0]["path"], str(root))

    def test_a_checkout_is_not_searched_inside(self):
        project_id = projects.attach(self.checkout("alpha"))["project_id"]
        outer = self.marked("outer", project_id)
        inner = outer / "nested"
        inner.mkdir()
        write_marker(inner, project_id, "workspace")
        self.assertEqual([item["path"] for item in projects.scan([self.root / "scan"])["bound"]], [str(outer)])


class RebindDetachTests(ProjectCase):
    def test_rebind_replaces_the_paths(self):
        first = self.checkout("alpha")
        project_id = projects.attach(first)["project_id"]
        second = self.checkout("moved")
        write_marker(second, project_id, "workspace")
        result = projects.rebind(project_id, second)
        self.assertEqual(result["binding"], {"paths": [str(second)], "primary": str(second)})

    def test_rebind_refuses_other_markers_missing_paths_and_unknown_projects(self):
        first = self.checkout("alpha")
        project_id = projects.attach(first)["project_id"]
        stranger = self.checkout("stranger")
        write_marker(stranger, new_id("prj"), "workspace")
        plain = self.checkout("plain")
        cases = ((project_id, stranger, "BINDING_MARKER_MISMATCH"), (project_id, plain, "BINDING_MARKER_MISMATCH"),
                 (project_id, self.root / "gone", "BINDING_PATH_MISSING"), (new_id("prj"), first, "PROJECT_UNKNOWN"))
        for pid, path, code in cases:
            with self.subTest(code=code, path=path.name):
                with self.assertRaises(WorkspaceError) as caught:
                    projects.rebind(pid, path)
                self.assertEqual(caught.exception.code, code)
        self.assertEqual(read_bindings()["projects"][project_id]["paths"], [str(first)])

    def test_detach_one_path_or_all_and_the_workspace_stays(self):
        first = self.checkout("alpha")
        project_id = projects.attach(first)["project_id"]
        second = self.checkout("second")
        write_marker(second, project_id, "workspace")
        projects.attach(second)
        files = self.workspace_files()
        result = projects.detach(project_id, second)
        self.assertEqual((result["removed"], result["binding"]["paths"]), (True, [str(first)]))
        self.assertFalse(projects.detach(project_id, second)["removed"])
        result = projects.detach(project_id)
        self.assertEqual((result["removed"], result["binding"]), (True, None))
        self.assertEqual(self.workspace_files(), files)
        self.assertEqual(read_bindings()["projects"], {})
        self.assertIsNotNone(read_marker(first))  # the checkout is not touched either

    def test_detach_of_an_unknown_project(self):
        with self.assertRaises(WorkspaceError) as caught:
            projects.detach(new_id("prj"))
        self.assertEqual(caught.exception.code, "PROJECT_UNKNOWN")

    def test_a_binding_of_a_project_missing_in_the_workspace_can_be_dropped(self):
        orphan = new_id("prj")
        bind(orphan, self.root)
        self.assertTrue(projects.detach(orphan)["removed"])


if __name__ == "__main__":
    unittest.main()
