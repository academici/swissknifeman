"""aicore.content.commands: strict frontmatter, the description, the fence split, runtime provenance."""
import unittest

from aicore.content import commands

GOOD = b'---\nname: demo\ndescription: "Plan it: now"\nmodel: sonnet\n---\nBody line\n'


class StrictFrontmatterCase(unittest.TestCase):
    def test_normal_command(self):
        self.assertEqual(commands.strict_frontmatter_fields(GOOD),
                         {"name": "demo", "description": '"Plan it: now"', "model": "sonnet"})

    def test_value_may_contain_colons_and_is_stripped(self):
        self.assertEqual(commands.strict_frontmatter_fields(b"---\n key :  a: b  \n---\n"), {"key": "a: b"})

    def test_empty_frontmatter(self):
        self.assertEqual(commands.strict_frontmatter_fields(b"---\n---\nx\n"), {})

    def assert_error(self, content, message):
        with self.assertRaises(ValueError) as raised:
            commands.strict_frontmatter_fields(content)
        self.assertEqual(str(raised.exception), message)

    def test_missing_fences(self):
        self.assert_error(b"name: x\n", "opening delimiter is missing")
        self.assert_error(b"", "opening delimiter is missing")
        self.assert_error(b"---\nname: x\n", "closing delimiter is missing")

    def test_malformed_duplicate_and_empty_keys(self):
        self.assert_error(b"---\nname\n---\n", "frontmatter field is malformed")
        self.assert_error(b"---\na: 1\na: 2\n---\n", "frontmatter field is empty or duplicated")
        self.assert_error(b"---\n: 1\n---\n", "frontmatter field is empty or duplicated")

    def test_not_utf8(self):
        self.assert_error(b"---\n\xff: 1\n---\n", "command source is not UTF-8")


class DescriptionCase(unittest.TestCase):
    def test_plain_and_quoted(self):
        self.assertEqual(commands.frontmatter_description(b"---\ndescription: Do it\n---\n"), "Do it")
        self.assertEqual(commands.frontmatter_description(GOOD), "Plan it: now")
        self.assertEqual(commands.frontmatter_description(b'---\ndescription: "a \\"b\\" \\u00e9"\n---\n'),
                         'a "b" é')

    def assert_error(self, content, message, **kwargs):
        with self.assertRaises(ValueError) as raised:
            commands.frontmatter_description(content, **kwargs)
        self.assertEqual(str(raised.exception), message)

    def test_errors_carry_the_default_code(self):
        self.assert_error(b"---\nname: x\n---\n", "CMD_SOURCE_DRIFT: command description is missing")
        self.assert_error(b"---\ndescription: \"open\n---\n",
                          "CMD_SOURCE_DRIFT: command description is malformed")
        self.assert_error(b"\xff", "CMD_SOURCE_DRIFT: command source is not UTF-8")

    def test_code_is_a_parameter(self):
        self.assert_error(b"---\nname: x\n---\n", "OTHER_CODE: command description is missing", code="OTHER_CODE")

    def test_empty_quoted_value_is_refused(self):
        self.assert_error(b'---\ndescription: ""\n---\n', "description must be a non-empty string")


class SplitCommandCase(unittest.TestCase):
    def test_frontmatter_and_body(self):
        self.assertEqual(commands.split_command(GOOD), (
            'name: demo\ndescription: "Plan it: now"\nmodel: sonnet\n', "Body line\n"))

    def test_body_keeps_later_rules_and_line_endings(self):
        self.assertEqual(commands.split_command(b"---\r\na: b\r\n---\r\nx\r\n---\r\ny\r\n"),
                         ("a: b\r\n", "x\r\n---\r\ny\r\n"))

    def test_empty_body_and_empty_frontmatter(self):
        self.assertEqual(commands.split_command(b"---\n---\n"), ("", ""))

    def assert_error(self, content, message):
        with self.assertRaises(ValueError) as raised:
            commands.split_command(content)
        self.assertEqual(str(raised.exception), message)

    def test_missing_fences(self):
        self.assert_error(b"name: x\n---\n", "canonical frontmatter opening fence is missing")
        self.assert_error(b"", "canonical frontmatter opening fence is missing")
        self.assert_error(b"---\nname: x\n", "canonical frontmatter closing fence is missing")

    def test_not_utf8_is_the_decode_error(self):
        with self.assertRaises(UnicodeDecodeError):
            commands.split_command(b"---\n\xff\n---\n")


class RuntimeProvenanceCase(unittest.TestCase):
    def test_exact_text(self):
        self.assertEqual(
            commands.runtime_provenance("Codex", "commands/run.md", "sha256:abc", "demo.codex-command/1.2.3"),
            "<!-- Generated Codex runtime projection; do not edit as source.\n"
            "Canonical source: commands/run.md\n"
            "Canonical SHA-256: sha256:abc\n"
            "Adapter: demo.codex-command/1.2.3\n"
            "-->\n")

    def test_title_is_a_parameter(self):
        self.assertTrue(commands.runtime_provenance("Cursor", "a", "b", "c").startswith(
            "<!-- Generated Cursor runtime projection;"))


if __name__ == "__main__":
    unittest.main()
