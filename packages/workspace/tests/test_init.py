"""workspace init and status: layout, git, device, refusals, locks and events."""
import fcntl
import json
import os
import subprocess
import unittest
from unittest import mock

from aicore.workspace import WorkspaceError, read_device, read_workspace, validate_document

from tests import TempCase, git
from workspace import gitutil, layout


class InitTests(TempCase):
    def test_init_creates_the_layout_a_git_repository_and_the_device(self):
        result = layout.init("axioma")
        self.assertEqual((result["created"], result["already_initialized"]), (True, False))
        self.assertEqual(result["root"], str(self.ws))
        for name in (".gitignore", ".gitattributes", "README.md", "workspace.json", "projects/.gitkeep"):
            self.assertTrue((self.ws / name).is_file(), name)
        self.assertTrue((self.ws / ".staging").is_dir())
        document = read_workspace(self.ws)
        self.assertEqual((document["workspace_id"], document["layout"]), (result["workspace_id"], 2))
        self.assertEqual(document["created_by"], result["device_id"])
        device = read_device()
        self.assertEqual(device["device_id"], result["device_id"])
        self.assertEqual(validate_document("workspace-device", device), [])
        self.assertFalse((self.ws / "device.json").exists())  # machine files stay out of the git tree
        self.assertTrue((self.state.parent / "device.json").is_file())

    def test_the_repository_has_one_commit_on_main_with_the_device_trailer(self):
        result = layout.init("axioma")
        self.assertEqual(git(self.ws, "symbolic-ref", "--short", "HEAD").strip(), "main")
        self.assertEqual(git(self.ws, "rev-list", "--count", "HEAD").strip(), "1")
        message = git(self.ws, "log", "-1", "--format=%B")
        self.assertTrue(message.startswith("skm(workspace): init"))
        self.assertIn(f"Workspace-Device: {result['device_id']}", message)
        self.assertEqual(git(self.ws, "status", "--porcelain", "--untracked-files=all"), "")
        tracked = git(self.ws, "ls-files").split()
        self.assertEqual(sorted(tracked), [".gitattributes", ".gitignore", "README.md", "projects/.gitkeep", "workspace.json"])

    def test_baseline_files(self):
        layout.init("axioma")
        ignore = (self.ws / ".gitignore").read_text(encoding="utf-8").splitlines()
        for line in ("/.staging/", "**/.lock", "**/views/", "**/context/", ".env", "*.pem", "*.swp"):
            self.assertIn(line, ignore)
        attributes = (self.ws / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("**/log.jsonl merge=union", attributes)
        self.assertIn("**/views/** linguist-generated=true", attributes)
        self.assertIn("*.json text=auto eol=lf", attributes)

    def test_workspace_documents_hold_no_absolute_path(self):
        layout.init("axioma")
        for name in ("workspace.json", "README.md", ".gitignore", ".gitattributes"):
            text = (self.ws / name).read_text(encoding="utf-8")
            self.assertNotIn(str(self.root), text, name)
            self.assertNotIn("/home/", text, name)

    def test_second_init_is_a_no_op(self):
        first = layout.init("axioma")
        head = git(self.ws, "rev-parse", "HEAD")
        second = layout.init("axioma")
        self.assertEqual((second["created"], second["already_initialized"]), (False, True))
        self.assertEqual((second["workspace_id"], second["device_id"]), (first["workspace_id"], first["device_id"]))
        self.assertEqual(git(self.ws, "rev-parse", "HEAD"), head)

    def test_a_non_empty_folder_without_workspace_json_is_refused_and_untouched(self):
        self.ws.mkdir()
        (self.ws / "notes.txt").write_text("mine", encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            layout.init("axioma")
        self.assertEqual(caught.exception.code, "WORKSPACE_ROOT_NOT_EMPTY")
        self.assertEqual(sorted(p.name for p in self.ws.iterdir()), ["notes.txt"])
        self.assertEqual((self.ws / "notes.txt").read_text(encoding="utf-8"), "mine")
        self.assertFalse((self.root / "skm").exists())  # not even the device, the state folder or the lock

    def test_a_git_repository_without_workspace_json_is_refused(self):
        self.ws.mkdir()
        git(self.ws, "init", "-q")
        with self.assertRaises(WorkspaceError) as caught:
            layout.init("axioma")
        self.assertEqual(caught.exception.code, "WORKSPACE_ROOT_NOT_EMPTY")

    def test_a_file_in_place_of_the_root_is_refused(self):
        self.ws.write_text("x", encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            layout.init("axioma")
        self.assertEqual(caught.exception.code, "WORKSPACE_ROOT_NOT_EMPTY")
        self.assertEqual(self.ws.read_text(encoding="utf-8"), "x")

    def test_an_empty_existing_folder_is_used_and_root_overrides_the_default(self):
        other = self.root / "elsewhere"
        other.mkdir()
        result = layout.init("axioma", other)
        self.assertEqual(result["root"], str(other))
        self.assertTrue((other / "workspace.json").is_file())
        self.assertFalse(self.ws.exists())

    def test_a_failure_part_way_removes_what_init_created(self):
        real = gitutil.git

        def failing(args, cwd, **kwargs):
            if "commit" in args:
                return subprocess.CompletedProcess(["git"], 1, "", "boom https://user:secret@example.com/x.git")
            return real(args, cwd, **kwargs)

        with mock.patch.object(gitutil, "git", failing):
            with self.assertRaises(WorkspaceError) as caught:
                layout.init("axioma")
        self.assertNotIn("secret", str(caught.exception))
        self.assertFalse(self.ws.exists())
        self.ws.mkdir()
        with mock.patch.object(gitutil, "git", failing):
            with self.assertRaises(WorkspaceError):
                layout.init("axioma")
        self.assertEqual(list(self.ws.iterdir()), [])

    def test_git_that_is_too_old_for_init_is_refused(self):
        with mock.patch.object(gitutil, "git_version", return_value=(2, 20, 0)):
            with self.assertRaises(WorkspaceError) as caught:
                layout.init("axioma")
        self.assertEqual(caught.exception.code, "WORKSPACE_GIT_TOO_OLD")
        self.assertFalse(self.ws.exists())

    def test_init_waits_for_the_git_lock_and_then_refuses(self):
        self.state.mkdir(parents=True)
        fd = os.open(str(self.state / "git.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with mock.patch.object(gitutil, "lock_timeout", return_value=0.2):
            with self.assertRaises(WorkspaceError) as caught:
                layout.init("axioma")
        self.assertEqual(caught.exception.code, "WORKSPACE_GIT_LOCKED")
        self.assertFalse(self.ws.exists())

    def test_the_lock_timeout_comes_from_the_configuration(self):
        self.assertEqual(gitutil.lock_timeout(), 60.0)
        config = self.root / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("schema_version = 1\n[workspace.git]\nlock_timeout_s = 7\n", encoding="utf-8")
        self.assertEqual(gitutil.lock_timeout(), 7.0)

    def test_a_relative_workspace_root_is_a_value_error(self):
        with mock.patch.dict(os.environ, {"SKM_WORKSPACES_ROOT": "relative"}):
            with self.assertRaises(ValueError):
                layout.init("axioma")

    def test_git_calls_are_argument_lists_in_the_c_locale(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(["git"], 0, "", "")
            gitutil.git(["status"], self.root)
        argv = run.call_args.args[0]
        self.assertEqual(argv, ["git", "status"])
        self.assertIsInstance(argv, list)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C")

    def test_init_journals_the_event_once(self):
        self.run_cli("init", "--code", "axioma")
        self.run_cli("init", "--code", "axioma")
        journal = self.root / "skm" / "state" / "events" / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["type"] for e in events], ["workspace.root.initialized"])
        self.assertEqual(events[0]["source"], "urn:swissknifeman:module:workspace")
        self.assertEqual(events[0]["data"], {"code": "axioma", "workspace_id": read_workspace(self.ws)["workspace_id"]})


class StatusTests(TempCase):
    def test_status_before_init_is_refused(self):
        with self.assertRaises(WorkspaceError) as caught:
            layout.status()
        self.assertEqual(caught.exception.code, "WORKSPACE_NOT_INITIALIZED")
        self.ws.mkdir()
        with self.assertRaises(WorkspaceError):
            layout.status()

    def test_fresh_workspace(self):
        result = layout.init("axioma")
        status = layout.status()
        self.assertEqual(status["workspace_id"], result["workspace_id"])
        self.assertEqual(status["git"], {"branch": "main", "dirty": 0, "remote": None, "ahead": None, "behind": None,
                                         "diverged": False, "fetched_at": None})
        self.assertEqual(status["projects"], [])
        self.assertIsNone(status["last_sync"])

    def test_dirty_counts_changed_paths(self):
        layout.init("axioma")
        (self.ws / "stray.txt").write_text("x", encoding="utf-8")
        (self.ws / "README.md").write_text("changed", encoding="utf-8")
        self.assertEqual(layout.status()["git"]["dirty"], 2)

    def test_the_remote_is_shown_without_user_information(self):
        layout.init("axioma")
        git(self.ws, "remote", "add", "origin", "https://user:secret@example.com/team/ws.git")
        remote = layout.status()["git"]["remote"]
        self.assertEqual(remote, "https://example.com/team/ws.git")
        self.assertNotIn("secret", json.dumps(layout.status()))

    def test_ahead_behind_and_fetch_against_a_local_remote(self):
        layout.init("axioma")
        bare = self.root / "remote.git"
        git(self.root, "init", "-q", "--bare", str(bare))
        git(self.ws, "remote", "add", "origin", str(bare))
        git(self.ws, "push", "-q", "-u", "origin", "main")
        state = layout.status()["git"]
        self.assertEqual((state["ahead"], state["behind"], state["diverged"]), (0, 0, False))
        (self.ws / "extra.txt").write_text("x", encoding="utf-8")
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "local")
        state = layout.status()["git"]
        self.assertEqual((state["ahead"], state["behind"]), (1, 0))
        other = self.root / "other"
        git(self.root, "clone", "-q", "-b", "main", str(bare), str(other))
        (other / "remote.txt").write_text("y", encoding="utf-8")
        git(other, "add", "-A")
        git(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "remote")
        git(other, "push", "-q", "origin", "main")
        self.assertEqual(layout.status()["git"]["behind"], 0)  # no network without --fetch
        fetched = layout.status(fetch=True)["git"]
        self.assertEqual((fetched["ahead"], fetched["behind"], fetched["diverged"]), (1, 1, True))
        self.assertRegex(fetched["fetched_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_fetch_failure_is_remote_unreachable(self):
        layout.init("axioma")
        git(self.ws, "remote", "add", "origin", str(self.root / "missing.git"))
        with self.assertRaises(WorkspaceError) as caught:
            layout.status(fetch=True)
        self.assertEqual(caught.exception.code, "REMOTE_UNREACHABLE")

    def test_last_sync_is_read_from_the_machine_file(self):
        layout.init("axioma")
        (self.state / "sync.json").write_text(json.dumps({"at": "2026-10-17T09:30:00Z"}), encoding="utf-8")
        self.assertEqual(layout.status()["last_sync"], {"at": "2026-10-17T09:30:00Z"})


if __name__ == "__main__":
    unittest.main()
