"""Frontmatter: reading values and lists, rendering with quoting, round trips."""
import tempfile
import unittest
from pathlib import Path

from brain import frontmatter


class TestParse(unittest.TestCase):
    def test_scalars_lists_and_quotes(self):
        text = "---\ntype: project\nrepo: ~/p\ntags: [a, \"b, c\", 'd']\nname: \"x: y\"\nempty:\n---\nbody: not a field\n"
        self.assertEqual({"type": "project", "repo": "~/p", "tags": ["a", "b, c", "d"], "name": "x: y", "empty": ""},
                         frontmatter.parse(text))

    def test_without_block_or_unclosed_or_broken_is_empty(self):
        self.assertEqual({}, frontmatter.parse("# no frontmatter\n"))
        self.assertEqual({}, frontmatter.parse("---\nkey: value\n"))
        self.assertEqual({}, frontmatter.parse("---\nthis line has no key\n---\n"))
        self.assertEqual({}, frontmatter.parse(""))

    def test_crlf_and_comments(self):
        self.assertEqual({"a": "1"}, frontmatter.parse("---\r\n# note\r\na: 1\r\n---\r\n"))

    def test_read_missing_or_binary_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual({}, frontmatter.read(Path(tmp) / "absent.md"))
            binary = Path(tmp) / "b.md"
            binary.write_bytes(b"---\n\xff\xfe: x\n---\n")
            self.assertEqual({}, frontmatter.read(binary))


class TestRender(unittest.TestCase):
    def test_order_is_kept_and_plain_values_stay_plain(self):
        self.assertEqual("---\nz: 1\na: plain text\nl: [x, y]\n---\n",
                         frontmatter.render([("z", 1), ("a", "plain text"), ("l", ["x", "y"])]))

    def test_special_values_are_quoted_and_round_trip(self):
        values = ["has: colon", "has # hash", "[bracket]", " lead", "trail ", 'say "hi"', "back\\slash",
                  "two\nlines", "it's", "", "a, b"]
        for value in values:
            with self.subTest(value=value):
                text = frontmatter.render([("k", value), ("l", [value, "plain"])])
                self.assertEqual({"k": value, "l": [value, "plain"]}, frontmatter.parse(text))

    def test_quoting_escapes_quote_and_backslash(self):
        self.assertIn('k: "say \\"hi\\""', frontmatter.render([("k", 'say "hi"')]))
        self.assertIn('k: "a\\\\b:"', frontmatter.render([("k", "a\\b:")]))


if __name__ == "__main__":
    unittest.main()
