"""The group dispatcher ``aicore <group>`` (``aicore.cli``)."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aicore import cli

PACKAGE = Path(__file__).resolve().parent.parent


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class TestDispatcher(unittest.TestCase):
    def test_help_prints_usage_and_exits_zero(self):
        for word in ("--help", "-h", "help"):
            with self.subTest(word=word):
                code, out, err = run(word)
                self.assertEqual((0, ""), (code, err))
                self.assertEqual(cli.usage(), out)
        self.assertIn("\n  config ", cli.usage())
        self.assertTrue(cli.usage().startswith("usage: aicore <group> [args]\n"))

    def test_no_arguments_is_a_usage_error(self):
        code, out, err = run()
        self.assertEqual((2, ""), (code, out))
        self.assertEqual(cli.usage(), err)

    def test_unknown_group_is_a_usage_error(self):
        code, out, err = run("nosuch", "--help")
        self.assertEqual((2, ""), (code, out))
        self.assertTrue(err.startswith("aicore: unknown group 'nosuch'\n"), err)

    def test_group_receives_the_rest_and_the_streams(self):
        seen = {}

        def handler(argv, *, env, cwd, out, err):
            seen.update(argv=argv, env=env, cwd=cwd)
            out.write("ran\n")
            return 7

        saved = dict(cli.GROUPS)
        self.addCleanup(lambda: (cli.GROUPS.clear(), cli.GROUPS.update(saved)))
        cli.GROUPS["probe"] = (__name__, "_probe_handler", "probe group")
        globals()["_probe_handler"] = handler
        self.addCleanup(lambda: globals().pop("_probe_handler", None))
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["probe", "a", "--b"], env={"K": "v"}, cwd=Path("/x"), out=out, err=err)
        self.assertEqual((7, "ran\n"), (code, out.getvalue()))
        self.assertEqual({"argv": ["a", "--b"], "env": {"K": "v"}, "cwd": Path("/x")}, seen)
        self.assertIn("\n  probe    probe group\n", cli.usage())

    def test_config_group_is_reached_without_the_group_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"HOME": tmp, "SKM_HOME": tmp + "/skm", "SKM_UNITS_PATH": tmp + "/none"}
            out, err = io.StringIO(), io.StringIO()
            code = cli.main(["config", "paths"], env=env, cwd=Path(tmp), out=out, err=err)
            self.assertEqual(0, code, err.getvalue())
            self.assertIn(tmp, out.getvalue())

    def test_module_entry_point(self):
        env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(PACKAGE / "lib")}
        for args, expected in (([], 2), (["--help"], 0), (["nosuch"], 2), (["config", "--help"], 0)):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, "-m", "aicore", *args], env=env, capture_output=True,
                                        text=True)
                self.assertEqual(expected, result.returncode, result.stderr)
        result = subprocess.run([sys.executable, "-m", "aicore", "--help"], env=env, capture_output=True, text=True)
        self.assertEqual(cli.usage(), result.stdout)


if __name__ == "__main__":
    unittest.main()
