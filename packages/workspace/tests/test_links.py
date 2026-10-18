"""The optional links plans/ and tasks/ of a checkout (D5): link, unlink, the setting, attach, sync and the readers that must
ignore a link into the bound workspace."""
import os
import unittest

from aicore.state import machine_config_file
from aicore.workspace import (WorkspaceError, is_workspace_link, legacy_plans_present, read_local_config, read_marker)
from aicore.workspace.links import read_exclude

from tests import TempCase, git, new_code
from workspace import layout, links, migrate, policy, projects, sync


class LinkCase(TempCase):
    def setUp(self):
        super().setUp()
        layout.init("axioma")

    def attached(self, name="alpha", **kwargs):
        root = self.checkout(name)
        result = projects.attach(root, **kwargs)
        return root, result["project_id"]

    def folder(self, project_id):
        return self.ws / "projects" / project_id

    def machine(self, text):
        path = machine_config_file(env=self.env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n[workspace]\n" + text, encoding="utf-8")


class LinkTests(LinkCase):
    def test_the_setting_is_off_by_default_and_attach_makes_no_link(self):
        root, project_id = self.attached()
        self.assertFalse(links.enabled(root))
        self.assertFalse(os.path.lexists(root / "plans"))
        self.assertFalse(os.path.lexists(root / "tasks"))
        self.assertEqual(read_exclude(root), [])

    def test_link_makes_both_links_to_the_workspace_folders_and_hides_them_from_git(self):
        root, project_id = self.attached()
        doc = links.link(root)
        self.assertEqual([(row["name"], row["action"]) for row in doc["links"]], [("plans", "created"), ("tasks", "created")])
        for name in ("plans", "tasks"):
            self.assertTrue(os.path.islink(root / name))
            self.assertEqual(os.path.realpath(root / name), str(self.folder(project_id) / name))
        self.assertTrue((self.folder(project_id) / "tasks" / ".gitkeep").is_file())
        self.assertEqual(read_exclude(root), ["plans", "tasks"])
        self.assertEqual(git(root, "status", "--porcelain", "--untracked-files=all").split(), ["??", ".swissknifeman/project.json"])
        self.assertEqual(doc["exclude"], str(root / ".git" / "info" / "exclude"))
        self.assertTrue(is_workspace_link(root, "plans") and is_workspace_link(root, "tasks"))

    def test_link_records_the_choice_for_the_project_only(self):
        root, project_id = self.attached()
        other, other_id = self.attached("beta")
        links.link(root)
        self.assertTrue(links.enabled(root))
        self.assertFalse(links.enabled(other))
        self.assertEqual(read_local_config(self.ws, project_id)["workspace"], {"link_folders": True})
        self.assertIsNone(read_local_config(self.ws, other_id))

    def test_link_again_changes_nothing(self):
        root, _ = self.attached()
        links.link(root)
        before = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        doc = links.link(root)
        self.assertEqual([row["action"] for row in doc["links"]], ["kept", "kept"])
        self.assertEqual((root / ".git" / "info" / "exclude").read_text(encoding="utf-8"), before)

    def test_a_real_folder_is_never_replaced(self):
        root, _ = self.attached()
        (root / "tasks").mkdir()
        (root / "tasks" / "todo.md").write_text("mine\n", encoding="utf-8")
        doc = links.link(root)
        rows = {row["name"]: row for row in doc["links"]}
        self.assertEqual((rows["tasks"]["action"], rows["tasks"]["reason"]), ("refused", "real-folder"))
        self.assertEqual(rows["plans"]["action"], "created")
        self.assertFalse(os.path.islink(root / "tasks"))
        self.assertEqual((root / "tasks" / "todo.md").read_text(encoding="utf-8"), "mine\n")
        self.assertEqual(read_exclude(root), ["plans"])
        self.assertEqual(links.unlink(root)["links"][1]["action"], "skipped")
        self.assertEqual((root / "tasks" / "todo.md").read_text(encoding="utf-8"), "mine\n")

    def test_a_link_to_another_place_is_left_alone(self):
        root, _ = self.attached()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        os.symlink(str(elsewhere), root / "tasks")
        doc = links.link(root)
        rows = {row["name"]: row for row in doc["links"]}
        self.assertEqual((rows["tasks"]["action"], rows["tasks"]["reason"]), ("refused", "link-elsewhere"))
        self.assertEqual(os.path.realpath(root / "tasks"), str(elsewhere))
        self.assertFalse(is_workspace_link(root, "tasks"))
        self.assertEqual(links.unlink(root)["links"][1]["action"], "skipped")
        self.assertTrue(os.path.islink(root / "tasks"))

    def test_plans_of_a_checkout_that_keeps_them_are_not_linked(self):
        root = self.checkout("old", plans=("p1",))
        project_id = projects.attach(root)["project_id"]
        self.assertEqual(read_marker(root)["plans_store"], "legacy")
        doc = links.link(root)
        rows = {row["name"]: row for row in doc["links"]}
        self.assertEqual((rows["plans"]["action"], rows["plans"]["reason"]), ("skipped", "plans-store-legacy"))
        self.assertEqual(rows["tasks"]["action"], "created")
        self.assertTrue((root / "plans" / "p1" / "plan.json").is_file() and not os.path.islink(root / "plans"))
        self.assertTrue(legacy_plans_present(root))  # a real folder keeps its own answer
        self.assertTrue(self.folder(project_id).is_dir())

    def test_unlink_removes_the_links_the_exclude_lines_and_turns_the_setting_off(self):
        root, project_id = self.attached()
        links.link(root)
        doc = links.unlink(root)
        self.assertEqual([row["action"] for row in doc["links"]], ["removed", "removed"])
        self.assertFalse(os.path.lexists(root / "plans") or os.path.lexists(root / "tasks"))
        self.assertEqual(read_exclude(root), [])
        self.assertNotIn("skm:links", (root / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
        self.assertFalse(links.enabled(root))
        self.assertEqual(read_local_config(self.ws, project_id)["workspace"], {"link_folders": False})
        self.assertTrue((self.folder(project_id) / "plans").is_dir())  # the workspace keeps its folders
        self.assertEqual([row["action"] for row in links.unlink(root)["links"]], ["absent", "absent"])

    def test_the_lines_of_the_user_in_the_exclude_file_stay(self):
        root, _ = self.attached()
        exclude = root / ".git" / "info" / "exclude"
        exclude.write_text("*.log\n", encoding="utf-8")
        links.link(root)
        links.unlink(root)
        self.assertEqual(exclude.read_text(encoding="utf-8"), "*.log\n")

    def test_a_checkout_without_a_marker_or_a_project_is_refused(self):
        root = self.checkout("bare")
        with self.assertRaises(WorkspaceError) as caught:
            links.link(root)
        self.assertEqual(caught.exception.code, "PROJECT_MARKER_MISSING")
        other, project_id = self.attached("gamma")
        import shutil
        shutil.rmtree(self.folder(project_id))
        with self.assertRaises(WorkspaceError) as caught:
            links.link(other)
        self.assertEqual(caught.exception.code, "PROJECT_UNKNOWN")

    def test_a_checkout_that_is_not_a_git_repository_is_linked_without_an_exclude_file(self):
        root, _ = self.attached()
        import shutil
        shutil.rmtree(root / ".git")
        doc = links.link(root)
        self.assertIsNone(doc["exclude"])
        self.assertTrue(os.path.islink(root / "plans"))


class SettingTests(LinkCase):
    def test_attach_with_the_flag_links_and_remembers(self):
        root, project_id = self.attached(link_folders=True)
        self.assertTrue(os.path.islink(root / "plans") and os.path.islink(root / "tasks"))
        self.assertTrue(links.enabled(root))

    def test_attach_follows_the_machine_setting(self):
        self.machine("link_folders = true\n")
        root, _ = self.attached()
        self.assertTrue(os.path.islink(root / "plans") and os.path.islink(root / "tasks"))

    def test_attach_result_carries_the_links_only_when_there_were_some(self):
        plain = projects.attach(self.checkout("one"))
        self.assertNotIn("links", plain)
        linked = projects.attach(self.checkout("two"), link_folders=True)
        self.assertEqual([row["action"] for row in linked["links"]["links"]], ["created", "created"])

    def test_the_project_override_beats_the_machine_setting_both_ways(self):
        self.machine("link_folders = true\n")
        root, project_id = self.attached()
        links.unlink(root)  # project: false
        self.assertFalse(links.enabled(root))
        self.assertIsNone(links.ensure(root))
        other, _ = self.attached("beta")
        self.assertTrue(links.enabled(other))
        self.machine("link_folders = false\n")
        self.assertFalse(links.enabled(other))
        links.link(other)
        self.assertTrue(links.enabled(other))

    def test_ensure_reports_a_failure_instead_of_raising(self):
        self.machine("link_folders = true\n")
        root, project_id = self.attached()
        import shutil
        shutil.rmtree(self.folder(project_id))
        doc = links.ensure(root)
        self.assertEqual(doc["problem"], "PROJECT_UNKNOWN")
        self.assertEqual(doc["links"], [])


class SyncTests(LinkCase):
    def test_sync_makes_and_repairs_the_links_of_projects_whose_setting_is_on(self):
        root, _ = self.attached(link_folders=True)
        other, _ = self.attached("beta")  # setting off: untouched
        os.unlink(root / "tasks")
        report = sync.sync(commit=True)
        self.assertEqual(report["result"], "ok")
        self.assertEqual([entry["path"] for entry in report["links"]], [str(root)])
        self.assertEqual([row["action"] for row in report["links"][0]["links"]], ["kept", "created"])
        self.assertTrue(os.path.islink(root / "tasks"))
        self.assertFalse(os.path.lexists(other / "plans"))
        self.assertNotIn("links", sync.sync(commit=True))  # nothing new: the report stays as it was

    def test_sync_commits_the_tasks_folder_of_the_workspace(self):
        root, project_id = self.attached(link_folders=True)
        sync.sync(commit=True)
        tracked = git(self.ws, "ls-files").split("\n")
        self.assertIn(f"projects/{project_id}/tasks/.gitkeep", tracked)
        self.assertFalse([path for path in tracked if "/local/" in path])


class ReaderTests(LinkCase):
    def test_a_linked_plans_folder_is_not_a_legacy_copy(self):
        root, project_id = self.attached()
        plan = self.folder(project_id) / "plans" / "p1"
        plan.mkdir(parents=True)
        (plan / "plan.json").write_text("{}\n", encoding="utf-8")
        links.link(root)
        self.assertTrue((root / "plans" / "p1" / "plan.json").is_file())
        self.assertFalse(legacy_plans_present(root))

    def test_a_link_to_a_folder_outside_the_bound_project_still_counts(self):
        root, project_id = self.attached()
        elsewhere = self.root / "elsewhere"
        (elsewhere / "p1").mkdir(parents=True)
        (elsewhere / "p1" / "plan.json").write_text("{}\n", encoding="utf-8")
        os.symlink(str(elsewhere), root / "plans")
        self.assertTrue(legacy_plans_present(root))

    def test_migrate_refuses_to_treat_the_link_as_an_old_copy(self):
        root, project_id = self.attached()
        links.link(root)
        for call in (lambda: migrate.build_plan(root), lambda: migrate.cleanup(root, project_id)):
            with self.assertRaises(WorkspaceError) as caught:
                call()
            self.assertEqual(caught.exception.code, "PLANS_LINKED")

    def test_the_policy_tracks_tasks_of_a_project(self):
        self.assertIn("tasks", policy.TRACKED_PROJECT_ENTRIES)

    def test_removing_an_empty_project_ignores_the_tasks_keep_file(self):
        root, project_id = self.attached()
        links.link(root)
        links.unlink(root)
        (self.folder(project_id) / "local").mkdir(exist_ok=True)
        import shutil
        shutil.rmtree(self.folder(project_id) / "local")
        self.assertEqual(projects._held(self.folder(project_id)), [])


class CliTests(LinkCase):
    def test_project_link_and_unlink_print_and_validate(self):
        root, project_id = self.attached()
        code, out, err = self.run_cli("project", "link", "--project", str(root))
        self.assertEqual(code, 0, err)
        self.assertIn(f"created {root}/plans", out)
        doc = self.json_cli("project", "unlink", "--project", str(root))
        self.assertEqual((doc["project_id"], doc["enabled"]), (project_id, False))
        self.assertEqual([row["action"] for row in doc["links"]], ["removed", "removed"])

    def test_project_add_with_the_flag(self):
        root = self.checkout(new_code("cli"))
        doc = self.json_cli("project", "add", "--path", str(root), "--link-folders")
        self.assertEqual([row["action"] for row in doc["links"]["links"]], ["created", "created"])

    def test_a_refusal_is_printed_on_stderr_and_does_not_fail(self):
        root, _ = self.attached()
        (root / "plans").mkdir()
        code, out, err = self.run_cli("project", "link", "--project", str(root))
        self.assertEqual(code, 0)
        self.assertIn("refused", err)
        self.assertIn("real-folder", err)


if __name__ == "__main__":
    unittest.main()
