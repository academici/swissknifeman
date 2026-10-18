"""aicore.util.schema._compile: every `$` is an end-of-string anchor (ECMA-262), not Python's "before a final newline"."""
import unittest

from aicore.util.schema import _compile

ALTERNATIVES = (
    "^$|^[a-z][a-z0-9-]*$",
    "^[a-z][a-z0-9_]*$|^[A-Z][A-Z0-9_]*$",
    "^(?:abc$|def)$",
)


class AnchorTests(unittest.TestCase):
    def test_trailing_newline_never_matches(self):
        for pattern in ALTERNATIVES:
            for value in ("\n", "abc\n", "ABC\n", "def\n"):
                with self.subTest(pattern=pattern, value=value):
                    self.assertIsNone(_compile(pattern).search(value))

    def test_plain_values_still_match(self):
        self.assertTrue(_compile(ALTERNATIVES[0]).search(""))
        self.assertTrue(_compile(ALTERNATIVES[0]).search("abc-1"))
        self.assertTrue(_compile(ALTERNATIVES[1]).search("ABC_1"))
        self.assertTrue(_compile(ALTERNATIVES[2]).search("def"))

    def test_dollar_in_class_and_escaped_dollar_are_literal(self):
        self.assertTrue(_compile(r"^[$a]+$").search("$a$"))
        self.assertTrue(_compile(r"^[]$]+$").search("]$"))
        self.assertTrue(_compile(r"^[^$]+$").search("abc"))
        self.assertTrue(_compile(r"^a\$$").search("a$"))
        self.assertIsNone(_compile(r"^a\$$").search("a$\n"))


if __name__ == "__main__":
    unittest.main()
