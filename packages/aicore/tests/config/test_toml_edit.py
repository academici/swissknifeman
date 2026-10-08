"""The TOML editor: every branch of set/unset, preserved bytes, rendering and the re-parse check."""
import unittest
from unittest import mock

from aicore.config import toml, toml_edit
from aicore.config.toml_edit import TomlEditError, set_value, unset_value

DOC = """\
# Example configuration
schema_version = 1

[analyst.recompute]   # thresholds
candidate_min_n = 5   # keep this comment
    indented = "x"    # indented key

# a note that belongs to the next block

[analyst.digest]
top_n = 3
# trailing comment of the block

[other]
a = 1
"""


def other_lines(before, after, skip):
    """Lines of ``before`` and ``after`` outside the line numbers in ``skip`` (0-based, before)."""
    kept = [line for index, line in enumerate(before.splitlines(keepends=True)) if index not in skip]
    return kept, after.splitlines(keepends=True)


class SetReplaceTests(unittest.TestCase):
    def test_replaces_the_value_and_keeps_the_comment_and_other_lines(self):
        new = set_value(DOC, ("analyst", "recompute", "candidate_min_n"), 9)
        self.assertIn("candidate_min_n = 9   # keep this comment\n", new)
        before, after = other_lines(DOC, new, {4})
        self.assertEqual([line for line in after if "candidate_min_n" not in line], before)
        self.assertEqual(toml.loads(new)["analyst"]["recompute"]["candidate_min_n"], 9)

    def test_keeps_indentation(self):
        new = set_value(DOC, ("analyst", "recompute", "indented"), "y")
        self.assertIn('    indented = "y"    # indented key\n', new)

    def test_changes_the_type(self):
        new = set_value(DOC, ("analyst", "recompute", "candidate_min_n"), "five")
        self.assertEqual(toml.loads(new)["analyst"]["recompute"]["candidate_min_n"], "five")

    def test_replaces_a_value_that_contains_a_hash_inside_a_string(self):
        text = '[t]\nk = "a # b"   # real comment\n'
        self.assertEqual(set_value(text, ("t", "k"), "z"), '[t]\nk = "z"   # real comment\n')

    def test_value_without_trailing_newline_at_end_of_file(self):
        self.assertEqual(set_value("[t]\nk = 1", ("t", "k"), 2), "[t]\nk = 2")

    def test_quoted_header_parts_and_spaces(self):
        text = '[ a . "b c" ]\nk = 1\n'
        self.assertEqual(set_value(text, ("a", "b c", "k"), 2), '[ a . "b c" ]\nk = 2\n')

    def test_quoted_key_is_found(self):
        text = '[t]\n"odd key" = 1\n'
        self.assertEqual(set_value(text, ("t", "odd key"), 2), '[t]\n"odd key" = 2\n')


class SetInsertTests(unittest.TestCase):
    def test_inserts_after_the_last_key_of_the_block_before_trailing_comments(self):
        new = set_value(DOC, ("analyst", "digest", "window"), 7)
        self.assertIn("top_n = 3\nwindow = 7\n# trailing comment of the block\n", new)
        before, after = other_lines(DOC, new, set())
        self.assertEqual([line for line in after if "window" not in line], before)

    def test_inserts_into_the_first_block_before_the_note_of_the_next(self):
        new = set_value(DOC, ("analyst", "recompute", "extra"), "v")
        self.assertIn('    indented = "x"    # indented key\nextra = "v"\n\n# a note', new)

    def test_inserts_right_after_an_empty_header(self):
        text = "[t]  # empty\n\n[u]\nk = 1\n"
        self.assertEqual(set_value(text, ("t", "k"), 1), "[t]  # empty\nk = 1\n\n[u]\nk = 1\n")

    def test_inserts_after_the_last_line_without_a_newline(self):
        self.assertEqual(set_value("[t]\na = 1", ("t", "b"), 2), "[t]\na = 1\nb = 2")

    def test_header_comments_are_not_a_key(self):
        text = "[t]\n# k = 1\n"
        self.assertEqual(set_value(text, ("t", "k"), 5), "[t]\nk = 5\n# k = 1\n")

    def test_crlf_files_keep_their_line_ending(self):
        text = "[t]\r\na = 1\r\n\r\n[u]\r\nb = 2\r\n"
        new = set_value(text, ("t", "c"), 3)
        self.assertEqual(new, "[t]\r\na = 1\r\nc = 3\r\n\r\n[u]\r\nb = 2\r\n")
        self.assertEqual(set_value(text, ("v", "d"), 4), text + "\r\n[v]\r\nd = 4\r\n")


class SetNewTableTests(unittest.TestCase):
    def test_appends_a_new_table(self):
        new = set_value(DOC, ("fresh", "sub", "k"), True)
        self.assertTrue(new.endswith("[other]\na = 1\n\n[fresh.sub]\nk = true\n"))
        self.assertTrue(new.startswith(DOC))

    def test_text_without_final_newline_is_finished_first(self):
        self.assertEqual(set_value("a = 1", ("t", "k"), 1), "a = 1\n\n[t]\nk = 1\n")

    def test_empty_text(self):
        self.assertEqual(set_value("", ("t", "k"), 1), "[t]\nk = 1\n")

    def test_quoted_names_in_the_new_header(self):
        self.assertEqual(set_value("", ("my mod", "a.b", "k"), 1), '["my mod"."a.b"]\nk = 1\n')

    def test_parent_defined_only_by_a_subtable_header(self):
        text = "[a.b.c]\nx = 1\n"
        new = set_value(text, ("a", "b", "k"), 2)
        self.assertEqual(toml.loads(new), {"a": {"b": {"c": {"x": 1}, "k": 2}}})


class UnsetTests(unittest.TestCase):
    def test_removes_the_definition_line_only(self):
        new = unset_value(DOC, ("analyst", "recompute", "candidate_min_n"))
        before, after = other_lines(DOC, new, {4})
        self.assertEqual(after, before)
        self.assertNotIn("candidate_min_n", toml.loads(new)["analyst"]["recompute"])

    def test_the_table_stays_when_it_becomes_empty(self):
        text = "[t]\nk = 1\n\n[u]\nj = 2\n"
        new = unset_value(text, ("t", "k"))
        self.assertEqual(new, "[t]\n\n[u]\nj = 2\n")
        self.assertEqual(toml.loads(new), {"t": {}, "u": {"j": 2}})

    def test_absent_key_or_table_returns_the_text_unchanged(self):
        self.assertEqual(unset_value(DOC, ("analyst", "recompute", "nope")), DOC)
        self.assertEqual(unset_value(DOC, ("nope", "k")), DOC)

    def test_last_line_without_newline(self):
        self.assertEqual(unset_value("[t]\na = 1\nb = 2", ("t", "b")), "[t]\na = 1\n")

    def test_set_then_unset_round_trips(self):
        added = set_value(DOC, ("analyst", "digest", "window"), 7)
        self.assertEqual(unset_value(added, ("analyst", "digest", "window")), DOC)


class RefusalTests(unittest.TestCase):
    def refused(self, text, path, reason, operation="set"):
        with self.assertRaises(TomlEditError) as caught:
            if operation == "set":
                set_value(text, path, 1)
            else:
                unset_value(text, path)
        message = str(caught.exception)
        self.assertIn(f"cannot edit {'.'.join(path)} in place", message)
        self.assertIn(reason, message)
        self.assertIn("edit the file by hand", message)

    def test_dotted_key_in_a_parent_table(self):
        self.refused("[a]\nb.c = 1\n", ("a", "b", "c"), "dotted key")
        self.refused("[a]\nb.c = 1\n", ("a", "b", "c"), "dotted key", "unset")

    def test_dotted_key_at_the_root(self):
        self.refused("a.b.c = 1\n", ("a", "b", "c"), "dotted key")

    def test_inline_table(self):
        self.refused("[a]\nb = { c = 1 }\n", ("a", "b", "c"), "inline table")
        self.refused("a = { b = { c = 1 } }\n", ("a", "b", "c"), "inline table", "unset")

    def test_array_of_tables(self):
        text = "[[a]]\nb = 1\n"
        self.refused(text, ("a", "b"), "array of tables")
        self.refused(text, ("a", "b"), "array of tables", "unset")
        self.refused(text + "[a.sub]\nx = 1\n", ("a", "sub", "k"), "array of tables")

    def test_multi_line_value(self):
        self.refused('[a]\nb = """\nx\n"""\n', ("a", "b"), "several lines")
        self.refused("[a]\nb = [\n 1,\n]\n", ("a", "b"), "several lines", "unset")

    def test_target_is_a_table(self):
        self.refused("[a.b]\nx = 1\n", ("a", "b"), "table")
        self.refused("[a]\nb.x = 1\n", ("a", "b"), "table")

    def test_invalid_path(self):
        for path in (("only",), (), ("a", ""), ("a", 1)):
            with self.assertRaises(ValueError):
                set_value("", path, 1)
            with self.assertRaises(ValueError):
                unset_value("", path)

    def test_invalid_source_text_is_reported_by_the_reader(self):
        from aicore.config import ConfigError
        with self.assertRaises(ConfigError) as caught:
            set_value("a = = 1\n", ("t", "k"), 1, source="cfg.toml")
        self.assertEqual(caught.exception.file, "cfg.toml")
        self.assertEqual(caught.exception.line, 1)


class RenderTests(unittest.TestCase):
    def test_strings_are_escaped(self):
        self.assertEqual(toml_edit.render_value('a"b\\c'), r'"a\"b\\c"')
        self.assertEqual(toml_edit.render_value("t\tn\nr\rb\bf\f"), r'"t\tn\nr\rb\bf\f"')
        self.assertEqual(toml_edit.render_value("\x00\x1f\x7f"), r'"\u0000\u001F\u007F"')
        self.assertEqual(toml_edit.render_value("é Привет"), '"é Привет"')

    def test_every_string_round_trips_through_both_parsers(self):
        for text in ('plain', 'a"b', 'back\\slash', 'line\nbreak', '\x00\x01', '# not a comment', ' padded ',
                     'it\'s', ' ', 'tab\t'):
            with self.subTest(text=text):
                new = set_value("", ("t", "k"), text)
                self.assertEqual(toml.loads(new)["t"]["k"], text)

    def test_scalars(self):
        self.assertEqual(toml_edit.render_value(True), "true")
        self.assertEqual(toml_edit.render_value(False), "false")
        self.assertEqual(toml_edit.render_value(-7), "-7")
        self.assertEqual(toml_edit.render_value(0.5), "0.5")
        self.assertEqual(toml_edit.render_value(1e-07), "1e-07")
        self.assertEqual(toml_edit.render_value(1e22), "1e+22")
        self.assertEqual(toml_edit.render_value(-0.0), "-0.0")

    def test_floats_round_trip(self):
        for number in (0.1, 1e22, 1e-07, 123456789.123456789, -0.0, 5e-324):
            with self.subTest(number=number):
                self.assertEqual(toml.loads(set_value("", ("t", "k"), number))["t"]["k"], number)

    def test_lists(self):
        self.assertEqual(toml_edit.render_value([]), "[]")
        self.assertEqual(toml_edit.render_value([1, "a", True, 2.5]), '[1, "a", true, 2.5]')
        self.assertEqual(toml_edit.render_value(("x", "y")), '["x", "y"]')

    def test_unsupported_values_are_rejected(self):
        for bad in (float("nan"), float("inf"), -float("inf"), None, {"a": 1}, [[1]], b"x", "\ud800"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    set_value("", ("t", "k"), bad)

    def test_keys(self):
        self.assertEqual(toml_edit.render_key("abc_1-x"), "abc_1-x")
        self.assertEqual(toml_edit.render_key("a b"), '"a b"')
        self.assertEqual(toml_edit.render_key("a.b"), '"a.b"')
        self.assertEqual(toml_edit.render_key("é"), '"é"')

    def test_bool_stays_a_bool(self):
        new = set_value("[t]\nk = 1\n", ("t", "k"), True)
        self.assertIs(toml.loads(new)["t"]["k"], True)


class VerificationTests(unittest.TestCase):
    def test_a_wrong_rendering_is_caught_before_any_text_is_returned(self):
        with mock.patch.object(toml_edit, "render_value", return_value="2"):
            with self.assertRaises(TomlEditError) as caught:
                set_value("[t]\nk = 1\n", ("t", "k"), 3)
        self.assertIn("did not give the expected document", str(caught.exception))

    def test_a_rendering_that_breaks_the_syntax_is_caught(self):
        with mock.patch.object(toml_edit, "render_value", return_value="= ="):
            with self.assertRaises(TomlEditError) as caught:
                set_value("[t]\nk = 1\n", ("t", "k"), 3)
        self.assertIn("invalid TOML", str(caught.exception))

    def test_an_integer_for_a_bool_is_a_mismatch(self):
        with mock.patch.object(toml_edit, "render_value", return_value="1"):
            with self.assertRaises(TomlEditError):
                set_value("[t]\nk = 0\n", ("t", "k"), True)

    def test_a_removal_that_removes_too_much_is_caught(self):
        with mock.patch.object(toml_edit, "_expected", side_effect=lambda old, path, value, remove: {}):
            with self.assertRaises(TomlEditError):
                unset_value("[t]\nk = 1\n", ("t", "k"))

    def test_the_input_is_never_modified_on_refusal(self):
        text = "[a]\nb.c = 1\n"
        with self.assertRaises(TomlEditError):
            set_value(text, ("a", "b", "c"), 2)
        self.assertEqual(text, "[a]\nb.c = 1\n")


class BackendParityTests(unittest.TestCase):
    def test_edit_results_parse_the_same_on_the_vendored_backend(self):
        new = set_value(DOC, ("analyst", "digest", "window"), [1, 2])
        self.assertEqual(toml.loads(new, backend="vendored"), toml.loads(new))


if __name__ == "__main__":
    unittest.main()
