"""What the filesystem research source may read: secret names, git ignore rules, the type of the opened file."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from orch import research
from orch.research import local_files, sources


class LocalFilesCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, name: str, data, mode: str = "w") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, mode) as handle:
            handle.write(data)
        return path

    def ask(self, text: str = "gateway timeout") -> list:
        source = sources.Source(id="fs", kind="filesystem", roots=(str(self.root),))
        return research.query(source, text, cwd=self.root)["sources"]


class SecretNameTests(unittest.TestCase):
    def test_secret_names(self):
        for name in (".env", ".env.local", ".envrc", ".git-credentials", "credentials", "aws_credentials.json",
                     "server.pem", "tls.key", "AuthKey.p8", ".pgpass", ".htpasswd", "kubeconfig", "db_password.txt"):
            self.assertTrue(local_files.is_secret_name(name), name)

    def test_ordinary_names(self):
        for name in ("README.md", "env.py", "environment.md", "keyboard.txt", "monkey.py", "notes.txt"):
            self.assertFalse(local_files.is_secret_name(name), name)


class ReadTextTests(LocalFilesCase):
    def test_a_regular_utf8_file_is_read(self):
        self.assertEqual("gateway\n", local_files.read_text(self.write("a.md", "gateway\n")))

    def test_a_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.root / "pipe")  # also what a file swapped for a fifo after the walk looks like
        self.assertIsNone(local_files.read_text(self.root / "pipe"))

    def test_a_symlink_is_not_followed(self):
        target = self.write("outside/.ssh-key-copy.txt", "gateway timeout secret\n")
        (self.root / "link.md").symlink_to(target)
        self.assertIsNone(local_files.read_text(self.root / "link.md"))

    def test_a_file_above_the_limit_or_not_utf8_is_refused(self):
        self.assertIsNone(local_files.read_text(self.write("big.md", "x" * 11), limit=10))
        self.assertIsNone(local_files.read_text(self.write("bin.md", b"gateway \xff\xfe", "wb")))

    def test_a_missing_file_is_refused(self):
        self.assertIsNone(local_files.read_text(self.root / "gone.md"))


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitIgnoreTests(LocalFilesCase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def test_files_git_ignores_are_not_read(self):
        self.write(".gitignore", "build/\n*.log\n")
        self.write("build/out.md", "gateway timeout\n")
        self.write("run.log", "gateway timeout\n")
        self.write("notes.md", "gateway timeout\n")
        self.assertEqual(["notes.md"], self.ask())

    def test_the_local_exclude_file_is_respected(self):
        self.write(".git/info/exclude", "private.md\n")
        self.write("private.md", "gateway timeout\n")
        self.write("notes.md", "gateway timeout\n")
        self.assertEqual(["notes.md"], self.ask())

    def test_outside_a_work_tree_only_the_name_rules_apply(self):
        plain = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, plain)
        self.assertIsNone(local_files.git_visible(plain))


class SecretFilesInTheWalkTests(LocalFilesCase):
    def test_secret_files_are_skipped_and_ordinary_ones_cited(self):
        self.write(".envrc", "export GATEWAY_TIMEOUT_TOKEN=abc # gateway timeout\n")
        self.write(".git-credentials", "https://u:gateway timeout@host\n")
        self.write("certs/server.pem", "gateway timeout\n")
        self.write(".aws/config", "gateway timeout\n")
        self.write("notes.md", "gateway timeout is 30s\n")
        self.assertEqual(["notes.md"], self.ask())


if __name__ == "__main__":
    unittest.main()
