"""gui.core.argv: argv only from the descriptor (I4), argv[0] inside the owner root, flags, dry run, cwd (I5)."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from gui.core import argv
from gui.errors import GuiError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "units" / "exec-demo" / "xdemo"
COMMANDS = {c["id"]: c for c in json.loads((FIXTURE / "gui.json").read_text(encoding="utf-8"))["commands"]}


class TestBuild(unittest.TestCase):
    def build(self, command="xdemo.echo", values=None, **kwargs):
        return argv.build(COMMANDS[command], FIXTURE, values if values is not None else {"name": "World"}, **kwargs)

    def test_literals_one_value_per_input_and_flags_in_input_order(self):
        built = self.build(values={"name": "World", "loud": True, "count": 3})
        self.assertEqual((os.path.realpath(FIXTURE / "bin" / "echo-args"), "--", "World", "--loud", "--count", "3"),
                         built.argv)
        self.assertEqual("project", built.cwd_kind)
        self.assertTrue(built.digest.startswith("sha256:"))

    def test_false_boolean_and_absent_flag_add_nothing(self):
        self.assertEqual(3, len(self.build(values={"name": "x", "loud": False}).argv))

    def test_value_with_spaces_or_shell_text_stays_one_element(self):
        value = "a b; rm -rf / $(id) `x` | y"
        self.assertEqual(value, self.build(values={"name": value}).argv[2])

    def test_leading_dash_is_refused_for_a_positional_input(self):
        for value in ("-rf", "--help", "-"):
            with self.subTest(value=value), self.assertRaises(GuiError) as caught:
                self.build(values={"name": value})
            self.assertEqual("INPUT_INVALID", caught.exception.code)
            self.assertEqual("leading_dash", caught.exception.issues[0]["code"])

    def test_missing_positional_is_refused(self):
        with self.assertRaises(GuiError) as caught:
            self.build(values={})
        self.assertEqual("required", caught.exception.issues[0]["code"])

    def test_dry_run(self):
        self.assertEqual("--dry-run", self.build(dry_run=True).argv[-1])
        with self.assertRaises(GuiError):
            self.build("xdemo.fail", {}, dry_run=True)
        command = dict(COMMANDS["xdemo.echo"], dry_run={"input": "loud"})
        built = argv.build(command, FIXTURE, {"name": "x"}, dry_run=True)
        self.assertEqual("--loud", built.argv[-1])

    def test_program_outside_or_not_executable(self):
        root = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "bin").mkdir()
        (root / "bin" / "plain").write_text("#!/bin/sh\n")
        os.symlink("/bin/sh", root / "bin" / "outside")
        base = {"id": "o.x", "exec": {"kind": "argv", "argv": ["bin/outside"], "cwd": "owner"}}
        for literal, code in (("bin/outside", "PATH_ESCAPE"), ("../x", "PATH_ESCAPE"), ("/bin/sh", "PATH_ESCAPE"),
                              ("bin/plain", "HANDLER_FAILED"), ("bin/missing", "HANDLER_FAILED")):
            with self.subTest(literal=literal), self.assertRaises(GuiError) as caught:
                argv.build(dict(base, exec={"kind": "argv", "argv": [literal], "cwd": "owner"}), root, {})
            self.assertEqual(code, caught.exception.code)

    def test_cwd(self):
        built = self.build("xdemo.ticks", {})
        self.assertEqual(Path(os.path.realpath(FIXTURE)), argv.cwd(built, FIXTURE, None, None))
        project = self.build()
        with self.assertRaises(GuiError):
            argv.cwd(project, FIXTURE, None, None)

        class Registry:
            def resolve(self, project_id):
                return Path("/somewhere") / project_id

        self.assertEqual(Path("/somewhere/p-1"), argv.cwd(project, FIXTURE, Registry(), "p-1"))


if __name__ == "__main__":
    unittest.main()
