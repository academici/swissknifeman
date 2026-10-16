"""Integrity of the vendored libraries: files match VENDORED.json, nothing else sits next to them."""
import hashlib
import json
import unittest
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "lib" / "aicore" / "_vendor"
SHA256_WHEEL_TOMLI = "94004df25851c4e811a5135545a470a823f9e31418ea3eb07c9440aec09c4369"


def manifest():
    return json.loads((VENDOR / "VENDORED.json").read_text(encoding="utf-8"))


class TestVendored(unittest.TestCase):
    def test_every_listed_file_matches_its_digest(self):
        for package in manifest()["packages"]:
            for relative, digest in package["files"].items():
                with self.subTest(file=relative):
                    actual = "sha256:" + hashlib.sha256((VENDOR / relative).read_bytes()).hexdigest()
                    self.assertEqual(actual, digest)

    def test_no_unlisted_files_in_a_vendored_package(self):
        for package in manifest()["packages"]:
            directory = VENDOR / package["name"]
            present = {path.relative_to(VENDOR).as_posix() for path in directory.rglob("*")
                       if path.is_file() and "__pycache__" not in path.parts}
            self.assertEqual(present, set(package["files"]))

    def test_manifest_records_the_pin(self):
        (package,) = manifest()["packages"]
        self.assertEqual(package["name"], "tomli")
        self.assertEqual(package["version"], "2.3.1")
        self.assertEqual(package["license"], "MIT")
        self.assertEqual(package["artifact_sha256"], SHA256_WHEEL_TOMLI)
        self.assertEqual(package["artifact"], "tomli-2.3.1-py3-none-any.whl")

    def test_license_text_is_shipped(self):
        self.assertIn("MIT License", (VENDOR / "tomli" / "LICENSE").read_text(encoding="utf-8"))

    def test_vendored_version_matches_the_manifest(self):
        from aicore._vendor import tomli
        self.assertEqual(tomli.__version__, manifest()["packages"][0]["version"])
        self.assertEqual(tomli.loads("a = 1"), {"a": 1})

    def test_the_vendored_branch_stays_on_toml_1_0(self):
        # tomli >= 2.4 reads TOML 1.1 syntax (e.g. a newline inside an inline table).
        from aicore._vendor import tomli
        with self.assertRaises(tomli.TOMLDecodeError):
            tomli.loads("a = {\n  b = 1,\n}\n")


if __name__ == "__main__":
    unittest.main()
