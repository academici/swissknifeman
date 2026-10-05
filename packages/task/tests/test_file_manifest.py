"""Concrete source inventory stays bounded around generated dependency trees."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from task import file_manifest


class FileManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True)

    def write(self, relative, content="source\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_source_glob_omits_ignored_dependencies_with_pnpm_cycle(self):
        self.git("init", "-q")
        self.write(".gitignore", "node_modules/\n")
        self.write("apps/demo/src/main.ts")
        self.git("add", ".")
        self.write("apps/demo/src/new.ts")
        dependency = self.write("node_modules/.pnpm/pkg/node_modules/pkg/index.js").parent
        (dependency / "node_modules").symlink_to(dependency.parent, target_is_directory=True)
        link = self.root / "apps/demo/node_modules/pkg"
        link.parent.mkdir(parents=True)
        link.symlink_to(dependency, target_is_directory=True)
        self.assertEqual(file_manifest.expand(self.root, ["apps/**"], required=True),
                         ("apps/demo/src/main.ts", "apps/demo/src/new.ts"))

    def test_glob_retains_tracked_ignored_member(self):
        self.git("init", "-q")
        self.write(".gitignore", "apps/demo/generated/\n")
        self.write("apps/demo/generated/contract.json")
        self.git("add", "-f", "apps/demo/generated/contract.json")
        self.assertEqual(file_manifest.expand(self.root, ["apps/**"], required=True),
                         ("apps/demo/generated/contract.json",))

    def test_explicit_ignored_inputs_are_preserved(self):
        self.git("init", "-q")
        self.write(".gitignore", "vendor/\ncomposer.lock\n")
        self.write("vendor/pkg/source.py")
        self.write("composer.lock")
        self.assertEqual(file_manifest.expand(self.root, ["vendor/pkg/**", "composer.lock"], required=True),
                         ("composer.lock", "vendor/pkg/source.py"))

    def test_braces_hidden_untracked_and_base_tombstone_are_preserved(self):
        self.git("init", "-q")
        deleted = self.write("src/deleted.py")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        deleted.unlink()
        self.write("src/nested/new.py")
        self.write("src/.hidden.py")
        self.assertEqual(file_manifest.expand(self.root, ["src/{deleted,.hidden}.py", "src/**/*.py"],
                                              base="HEAD", required=True),
                         ("src/.hidden.py", "src/deleted.py", "src/nested/new.py"))

    def test_standalone_cycle_is_a_leaf_and_hidden_files_are_included(self):
        self.write("src/main.py")
        self.write("src/.hidden.py")
        (self.root / "src/loop").symlink_to(".", target_is_directory=True)
        self.assertEqual(file_manifest.expand(self.root, ["src/**"], required=True),
                         ("src/.hidden.py", "src/loop", "src/main.py"))

    def test_glob_external_symlink_still_fails_closed(self):
        self.git("init", "-q")
        self.write("src/main.py")
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "src/external").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(file_manifest.ManifestError, "REVIEW_PATH_INVALID"):
                file_manifest.expand(self.root, ["src/**"], required=True)

    def test_required_missing_member_is_not_hidden(self):
        self.git("init", "-q")
        self.write("src/one.py")
        with self.assertRaisesRegex(file_manifest.ManifestError, "REVIEW_REQUIRED_PATH_MISSING"):
            file_manifest.expand(self.root, ["src/{one,missing}.py"], required=True)


if __name__ == "__main__":
    unittest.main()
