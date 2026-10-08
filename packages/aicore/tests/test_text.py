"""Tests aicore.util.text.parse_frontmatter — single superset-parser frontmatter.

Launch: bash packages/aicore/scripts/test.sh"""
import unittest

from aicore.util.text import parse_frontmatter, parse_inline_list


class TestParseFrontmatter(unittest.TestCase):
    def test_basic_scalars_and_quotes(self):
        fm = parse_frontmatter('---\nname: foo\nversion: "1.2.3"\ndesc: \'q\'\n---\nbody\n')
        self.assertEqual(fm["name"], "foo")
        self.assertEqual(fm["version"], "1.2.3")
        self.assertEqual(fm["desc"], "q")

    def test_no_frontmatter(self):
        self.assertEqual(parse_frontmatter("just body\nname: x\n"), {})
        self.assertEqual(parse_frontmatter(""), {})

    def test_body_after_close_ignored(self):
        fm = parse_frontmatter("---\nname: foo\n---\nkey: should-not-parse\n")
        self.assertNotIn("key", fm)

    def test_block_scalar_literal_keeps_newlines(self):
        fm = parse_frontmatter("---\ndescription: |\n  line one\n  line two\n---\n")
        self.assertEqual(fm["description"], "line one\nline two")

    def test_block_scalar_folded_joins_with_space(self):
        fm = parse_frontmatter("---\ndescription: >\n  a\n  b\nrisk: low\n---\n")
        self.assertEqual(fm["description"], "a b")
        self.assertEqual(fm["risk"], "low")  # key after block scalar is not lost

    def test_block_scalar_with_chomp_indicators(self):
        for header in ("|-", ">+", "|2", ">-"):
            fm = parse_frontmatter(f"---\nd: {header}\n  x\n---\n")
            self.assertEqual(fm["d"], "x", header)

    def test_value_starting_with_gt_is_scalar_not_block(self):
        fm = parse_frontmatter("---\ndescription: > see the docs\nname: foo\n---\n")
        self.assertEqual(fm["description"], "> see the docs")
        self.assertEqual(fm["name"], "foo")

    def test_bom_stripped(self):
        fm = parse_frontmatter("﻿---\nname: foo\n---\nbody\n")
        self.assertEqual(fm["name"], "foo")

    def test_crlf_normalized(self):
        fm = parse_frontmatter("---\r\nname: foo\r\n---\r\n")
        self.assertEqual(fm["name"], "foo")

    def test_inline_list_becomes_list(self):
        fm = parse_frontmatter("---\nrequires: [a, b, c]\ntags: []\n---\n")
        self.assertEqual(fm["requires"], ["a", "b", "c"])
        self.assertEqual(fm["tags"], [])

    def test_multiline_dash_list(self):
        fm = parse_frontmatter("---\nuses:\n  - proj-a\n  - proj-b\ntitle: t\n---\n")
        self.assertEqual(fm["uses"], ["proj-a", "proj-b"])
        self.assertEqual(fm["title"], "t")  # the key after the list is not eaten

    def test_empty_value_without_items_stays_string(self):
        # compatible with skiller: empty scalar — "", NOT [] (otherwise description
        # without a value would become a list and would end up as a list in skills.json)
        fm = parse_frontmatter("---\ndescription:\nname: foo\n---\n")
        self.assertEqual(fm["description"], "")
        self.assertEqual(fm["name"], "foo")


class TestParseInlineList(unittest.TestCase):
    def test_raw_string_forms(self):
        self.assertEqual(parse_inline_list(""), [])
        self.assertEqual(parse_inline_list("not-a-list"), [])
        self.assertEqual(parse_inline_list("[]"), [])
        self.assertEqual(parse_inline_list('["x", "y"]'), ["x", "y"])

    def test_already_list_passthrough(self):
        # parse_frontmatter can now return list — the normalizer tolerates it
        self.assertEqual(parse_inline_list(["a", "b"]), ["a", "b"])
        self.assertEqual(parse_inline_list([]), [])
        self.assertEqual(parse_inline_list(['"q"', "  x  "]), ["q", "x"])


if __name__ == "__main__":
    unittest.main()
