"""workspace connect, clone and status --fetch on local bare repositories (file:// URLs, no network)."""
import json
import subprocess
import unittest
from unittest import mock

from aicore.workspace import WorkspaceError, read_device

from tests import TempCase, git
from workspace import gitutil, layout, remote


class RemoteCase(TempCase):
    def bare(self, name="origin.git"):
        path = self.root / name
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True, capture_output=True)
        return path

    def url(self, path):
        return "file://" + str(path)

    def push_all(self, bare):
        git(self.ws, "push", "-q", str(bare), "HEAD:refs/heads/main")

    def commit(self, cwd, name):
        (cwd / name).write_text(name, encoding="utf-8")
        git(cwd, "add", name)
        git(cwd, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", name)

    def code(self, call, *args, **kwargs):
        with self.assertRaises(WorkspaceError) as caught:
            call(*args, **kwargs)
        return caught.exception.code


class ConnectTests(RemoteCase):
    def test_empty_remote_is_added_and_nothing_is_pushed(self):
        layout.init("axioma")
        bare = self.bare()
        head = git(self.ws, "rev-parse", "HEAD")
        doc = remote.connect(self.url(bare))
        self.assertEqual((doc["classification"], doc["branch"], doc["next"]),
                         ("empty", "main", "swissknifeman workspace sync --push"))
        self.assertEqual(git(self.ws, "remote").split(), ["origin"])
        self.assertEqual(git(self.ws, "rev-parse", "HEAD"), head)
        self.assertEqual(git(bare, "branch", "--list").strip(), "")
        self.assertEqual(list((self.ws / ".staging").iterdir()), [])

    def test_same_workspace_is_connected(self):
        layout.init("axioma")
        bare = self.bare()
        self.push_all(bare)
        self.assertEqual(remote.connect(self.url(bare))["classification"], "same")
        self.assertEqual(list((self.ws / ".staging").iterdir()), [])

    def test_other_workspace_is_refused_and_config_is_unchanged(self):
        layout.init("axioma")
        bare = self.bare()
        other = self.root / "other"
        layout.init("axioma", other)
        git(other, "push", "-q", str(bare), "HEAD:refs/heads/main")
        before = (self.ws / ".git" / "config").read_text(encoding="utf-8")
        self.assertEqual(self.code(remote.connect, self.url(bare)), "REMOTE_OTHER_WORKSPACE")
        self.assertEqual((self.ws / ".git" / "config").read_text(encoding="utf-8"), before)
        self.assertEqual(list((self.ws / ".staging").iterdir()), [])

    def test_foreign_repository_is_refused(self):
        layout.init("axioma")
        bare = self.bare()
        work = self.root / "work"
        work.mkdir()
        git(work, "init", "-q", "-b", "main")
        self.commit(work, "a.txt")
        git(work, "push", "-q", str(bare), "HEAD:refs/heads/main")
        before = (self.ws / ".git" / "config").read_text(encoding="utf-8")
        self.assertEqual(self.code(remote.connect, self.url(bare)), "REMOTE_FOREIGN")
        self.assertEqual((self.ws / ".git" / "config").read_text(encoding="utf-8"), before)
        self.assertEqual(list((self.ws / ".staging").iterdir()), [])

    def test_second_connect_is_refused(self):
        layout.init("axioma")
        bare = self.bare()
        remote.connect(self.url(bare))
        self.assertEqual(self.code(remote.connect, self.url(bare)), "REMOTE_ALREADY_SET")

    def test_unreachable_remote_hides_the_token(self):
        layout.init("axioma")
        with self.assertRaises(WorkspaceError) as caught:
            remote.connect("file://user:s3cret@" + str(self.root / "missing.git"))
        self.assertEqual(caught.exception.code, "REMOTE_UNREACHABLE")
        self.assertNotIn("s3cret", str(caught.exception))
        self.assertEqual(git(self.ws, "remote").split(), [])

    def test_not_initialized(self):
        self.assertEqual(self.code(remote.connect, self.url(self.bare())), "WORKSPACE_NOT_INITIALIZED")

    def test_old_git_is_refused(self):
        layout.init("axioma")
        with mock.patch.object(gitutil, "git_version", return_value=(2, 37, 9)):
            self.assertEqual(self.code(remote.connect, self.url(self.bare())), "WORKSPACE_GIT_TOO_OLD")
            self.assertEqual(self.code(remote.clone, self.url(self.bare()), self.root / "c"), "WORKSPACE_GIT_TOO_OLD")
        with mock.patch.object(gitutil, "git_version", return_value=(2, 38)):
            self.assertEqual(gitutil.require_version(), (2, 38))

    def test_cli_output_has_no_userinfo(self):
        layout.init("axioma")
        bare = self.bare()
        url = "file://tok:s3cret@" + str(bare)
        code, out, err = self.run_cli("connect", "--remote", url)
        self.assertEqual(code, 0, err)
        self.assertNotIn("s3cret", out + err)
        self.assertIn("next: swissknifeman workspace sync --push", out)
        code, out, err = self.run_cli("connect", "--remote", url, "--json")
        self.assertEqual(code, 1)
        self.assertIn("REMOTE_ALREADY_SET", err)
        self.assertNotIn("s3cret", out + err)

    def test_option_like_url_is_a_usage_error(self):
        layout.init("axioma")
        code, _, err = self.run_cli("connect", "--remote=--upload-pack=x")
        self.assertEqual(code, 2, err)


class CloneTests(RemoteCase):
    def source(self):
        layout.init("axioma")
        bare = self.bare()
        self.push_all(bare)
        return bare

    def test_clone_makes_the_workspace_and_a_device(self):
        bare = self.source()
        workspace_id = json.loads((self.ws / "workspace.json").read_text(encoding="utf-8"))["workspace_id"]
        target = self.root / "second"
        doc = remote.clone(self.url(bare), target)
        self.assertEqual((doc["workspace_id"], doc["root"], doc["branch"]), (workspace_id, str(target), "main"))
        self.assertEqual(doc["next"], "swissknifeman workspace project scan ~/projects")
        self.assertTrue((target / ".staging").is_dir())
        self.assertEqual(read_device()["device_id"], doc["device_id"])
        self.assertEqual(git(target, "remote").split(), ["origin"])

    def test_existing_device_is_kept(self):
        bare = self.source()
        before = read_device()
        doc = remote.clone(self.url(bare), self.root / "second")
        self.assertEqual(doc["device_id"], before["device_id"])
        self.assertEqual(read_device(), before)

    def test_non_empty_target_is_refused_and_untouched(self):
        bare = self.source()
        target = self.root / "busy"
        target.mkdir()
        (target / "keep.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.code(remote.clone, self.url(bare), target), "WORKSPACE_ROOT_NOT_EMPTY")
        self.assertEqual([p.name for p in target.iterdir()], ["keep.txt"])

    def test_empty_existing_target_is_used(self):
        bare = self.source()
        target = self.root / "emptydir"
        target.mkdir()
        remote.clone(self.url(bare), target)
        self.assertTrue((target / "workspace.json").is_file())

    def test_foreign_remote_leaves_nothing_behind(self):
        bare = self.bare()
        work = self.root / "work"
        work.mkdir()
        git(work, "init", "-q", "-b", "main")
        self.commit(work, "a.txt")
        git(work, "push", "-q", str(bare), "HEAD:refs/heads/main")
        target = self.root / "second"
        self.assertEqual(self.code(remote.clone, self.url(bare), target), "REMOTE_FOREIGN")
        self.assertFalse(target.exists())
        empty = self.root / "emptydir"
        empty.mkdir()
        self.assertEqual(self.code(remote.clone, self.url(self.bare("e.git")), empty), "REMOTE_FOREIGN")
        self.assertEqual(list(empty.iterdir()), [])

    def test_unreachable_has_no_token(self):
        with self.assertRaises(WorkspaceError) as caught:
            remote.clone("file://u:s3cret@" + str(self.root / "missing.git"), self.root / "second")
        self.assertEqual(caught.exception.code, "REMOTE_UNREACHABLE")
        self.assertNotIn("s3cret", str(caught.exception))
        self.assertFalse((self.root / "second").exists())

    def test_cli_clone(self):
        bare = self.source()
        code, out, err = self.run_cli("clone", self.url(bare), "--root", str(self.root / "second"), "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["remote"], self.url(bare))


class StatusFetchTests(RemoteCase):
    def test_ahead_behind_diverged_after_fetch(self):
        layout.init("axioma")
        bare = self.bare()
        self.push_all(bare)
        remote.connect(self.url(bare))
        second = self.root / "second"
        remote.clone(self.url(bare), second)
        self.commit(second, "remote.txt")
        git(second, "push", "-q", "origin", "HEAD:main")
        git_state = self.json_cli("status")["git"]
        self.assertEqual((git_state["ahead"], git_state["behind"]), (None, None))  # nothing fetched yet
        state = self.json_cli("status", "--fetch")["git"]
        self.assertEqual((state["ahead"], state["behind"], state["diverged"]), (0, 1, False))
        self.assertTrue(state["fetched_at"])
        self.commit(self.ws, "local.txt")
        state = self.json_cli("status", "--fetch")["git"]
        self.assertEqual((state["ahead"], state["behind"], state["diverged"]), (1, 1, True))
        self.assertEqual(state["remote"], self.url(bare))

    def test_fetch_failure_is_unreachable(self):
        layout.init("axioma")
        bare = self.bare()
        remote.connect(self.url(bare))
        bare.rename(self.root / "gone.git")
        code, _, err = self.run_cli("status", "--fetch")
        self.assertEqual(code, 1)
        self.assertIn("REMOTE_UNREACHABLE", err)


class RedactTests(unittest.TestCase):
    def test_redact_text(self):
        self.assertEqual(gitutil.redact_remote_text("fatal: https://u:tok@host/x.git failed"),
                         "fatal: https://host/x.git failed")


if __name__ == "__main__":
    unittest.main()
