"""gui.core.inputs: every field type, defaults, unknown and missing fields, project paths after realpath."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from gui.core import inputs
from gui.errors import GuiError


def field(name, kind, **extra):
    return {"name": name, "title": name.title(), "type": kind, "required": extra.pop("required", False), **extra}


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "src").mkdir()

    def issues(self, fields, values, root=None):
        with self.assertRaises(GuiError) as caught:
            inputs.validate(fields, values, root)
        self.assertEqual("INPUT_INVALID", caught.exception.code)
        return {(issue["pointer"], issue["code"]) for issue in caught.exception.issues}

    def test_scalars(self):
        fields = [field("s", "string"), field("i", "integer"), field("n", "number"), field("b", "boolean"),
                  field("e", "enum", enum=["a", "b"])]
        self.assertEqual({"s": "x", "i": 3, "n": 1.5, "b": False, "e": "b"},
                         inputs.validate(fields, {"s": "x", "i": 3, "n": 1.5, "b": False, "e": "b"}))
        self.assertEqual({("/params/s", "type"), ("/params/i", "type"), ("/params/n", "type"),
                          ("/params/b", "type"), ("/params/e", "enum")},
                         self.issues(fields, {"s": 1, "i": True, "n": "1", "b": "true", "e": "c"}))
        self.assertEqual({("/params/i", "type"), ("/params/n", "type")},
                         self.issues(fields, {"i": 1.0, "n": float("inf")}))

    def test_limits_and_pattern(self):
        fields = [field("s", "string", pattern="^[a-z]+$"), field("i", "integer", minimum=1, maximum=5)]
        self.assertEqual({("/params/s", "pattern"), ("/params/i", "minimum")}, self.issues(fields, {"s": "aB", "i": 0}))
        self.assertEqual({("/params/i", "maximum")}, self.issues(fields, {"i": 6}))
        self.assertEqual({("/params/s", "max_length")}, self.issues([field("s", "string")], {"s": "a" * 4097}))
        self.assertEqual({("/params/s", "invalid")}, self.issues([field("s", "string")], {"s": "a\x00"}))

    def test_required_default_unknown(self):
        fields = [field("r", "string", required=True), field("d", "integer", default=7)]
        self.assertEqual({"r": "x", "d": 7}, inputs.validate(fields, {"r": "x"}))
        self.assertEqual({("/params/r", "required"), ("/params/x", "unknown")}, self.issues(fields, {"x": 1}))
        self.assertEqual({("/params", "type")}, self.issues(fields, ["r"]))

    def test_reference_types(self):
        fields = [field("plan", "plan-ref"), field("item", "item-ref"), field("model", "model-ref"),
                  field("secret", "secret-ref")]
        good = {"plan": "2026.10.16-№1-SKM-GUI", "item": "P2.2", "model": "anthropic/claude-opus-5-5",
                "secret": "env://GUI_TOKEN"}
        self.assertEqual(good, inputs.validate(fields, good))
        self.assertEqual({"plan": "PLAN5"}, inputs.validate(fields, {"plan": "PLAN5"}))
        bad = {"plan": "plan5", "item": "2.2", "model": "claude", "secret": "file:///etc/passwd"}
        self.assertEqual({(f"/params/{name}", "pattern") for name in bad}, self.issues(fields, bad))

    def test_project_path(self):
        fields = [field("p", "project-path")]
        self.assertEqual({"p": "src"}, inputs.validate(fields, {"p": "src/../src/."}, self.root))
        self.assertEqual({"p": os.path.join("src", "new.txt")}, inputs.validate(fields, {"p": "src/new.txt"}, self.root))
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (self.root / "link").symlink_to(outside)
        for value in ("..", "../x", "/etc/passwd", "link", "link/x", ""):
            with self.subTest(value=value):
                self.assertEqual({("/params/p", "path_escape")}, self.issues(fields, {"p": value}, self.root))
        self.assertEqual({("/params/p", "path_escape")}, self.issues(fields, {"p": "src"}, None))

    def test_pointer_prefix_for_commands(self):
        with self.assertRaises(GuiError) as caught:
            inputs.validate([field("x", "integer")], {"x": "1"}, pointer="/input")
        self.assertEqual("/input/x", caught.exception.issues[0]["pointer"])


if __name__ == "__main__":
    unittest.main()
