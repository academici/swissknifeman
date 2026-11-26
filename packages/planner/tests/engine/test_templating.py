"""Mustache subset: variables, sections, partials, standalone-line rules, fail-closed syntax."""
import sys
import unittest
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan.templating import TemplateError, render  # noqa: E402


def no_partials(name):
    raise TemplateError(f"no partial {name}")


def run(template, context=None, partials=None):
    partials = partials or {}

    def loader(name):
        if name not in partials:
            raise TemplateError(f"missing partial {name!r}")
        return partials[name]

    return render(template, context if context is not None else {}, loader)


class VariableTests(unittest.TestCase):
    def test_lookup_dotted_and_dot(self):
        self.assertEqual(run("{{a}}-{{b.c}}-{{b.d.e}}", {"a": 1, "b": {"c": "x", "d": {"e": 2.5}}}), "1-x-2.5")
        self.assertEqual(run("{{#l}}[{{.}}]{{/l}}", {"l": ["a", "b"]}), "[a][b]")

    def test_missing_key_renders_empty(self):
        self.assertEqual(run("<{{nope}}|{{a.nope}}|{{nope.deeper}}>", {"a": {"x": 1}}), "<||>")

    def test_no_escaping_and_scalar_forms(self):
        self.assertEqual(run("{{t}}", {"t": "<b>&\"'</b>"}), "<b>&\"'</b>")
        self.assertEqual(run("{{t}}/{{f}}/{{n}}", {"t": True, "f": False, "n": None}), "true/false/")

    def test_non_scalar_variable_is_refused(self):
        for value in ([1], {"a": 1}):
            with self.assertRaises(TemplateError):
                run("{{x}}", {"x": value})

    def test_whitespace_inside_tags_is_ignored(self):
        self.assertEqual(run("{{ a }}{{#  l }}{{ . }}{{/ l  }}", {"a": "x", "l": [1, 2]}), "x12")

    def test_text_without_tags_and_empty_template(self):
        self.assertEqual(run("plain {single} braces\n"), "plain {single} braces\n")
        self.assertEqual(run(""), "")


class SectionTests(unittest.TestCase):
    def test_list_iterates_with_element_pushed_and_outer_context_visible(self):
        out = run("{{#items}}{{id}}:{{prefix}};{{/items}}", {"prefix": "p", "items": [{"id": 1}, {"id": 2}]})
        self.assertEqual(out, "1:p;2:p;")

    def test_dict_and_truthy_scalar_render_once(self):
        self.assertEqual(run("{{#d}}{{x}}{{/d}}", {"d": {"x": "v"}}), "v")
        self.assertEqual(run("{{#s}}yes{{/s}}", {"s": "text"}), "yes")
        self.assertEqual(run("{{#s}}[{{.}}]{{/s}}", {"s": "text"}), "[text]")
        self.assertEqual(run("{{#b}}on{{/b}}", {"b": True}), "on")

    def test_falsy_values_render_nothing_and_trigger_inverted_sections(self):
        for falsy in ([], {}, "", None, False, 0):
            with self.subTest(falsy=falsy):
                ctx = {"x": falsy}
                self.assertEqual(run("{{#x}}A{{/x}}{{^x}}B{{/x}}", ctx), "B")
        self.assertEqual(run("{{#x}}A{{/x}}{{^x}}B{{/x}}", {}), "B")
        self.assertEqual(run("{{#x}}A{{/x}}{{^x}}B{{/x}}", {"x": [0]}), "A")

    def test_nested_sections_and_dotted_section_names(self):
        ctx = {"a": [{"n": "1", "b": [{"m": "x"}, {"m": "y"}]}, {"n": "2", "b": []}], "next": {"flag": True, "v": "q"}}
        self.assertEqual(run("{{#a}}{{n}}{{#b}}{{m}}{{/b}}{{^b}}-{{/b}};{{/a}}", ctx), "1xy;2-;")
        self.assertEqual(run("{{#next.flag}}{{next.v}}{{/next.flag}}", ctx), "q")

    def test_inner_scope_shadows_outer_and_falls_back(self):
        ctx = {"v": "outer", "w": "w-outer", "items": [{"v": "inner"}]}
        self.assertEqual(run("{{#items}}{{v}}/{{w}}{{/items}}", ctx), "inner/w-outer")


class PartialTests(unittest.TestCase):
    def test_partial_sees_the_current_context(self):
        self.assertEqual(run("{{#rows}}<{{>cell}}>{{/rows}}", {"rows": [{"x": 1}, {"x": 2}]}, {"cell": "{{x}}"}), "<1><2>")

    def test_standalone_partial_rows_leave_no_blank_lines_e7(self):
        status = ("# Status\n\n| Item | Title |\n|:--|:--|\n{{#items}}\n{{>item-row}}\n{{/items}}\n{{#closed}}\n\nClosed {{at}}\n{{/closed}}\n\nEnd\n")
        out = run(status, {"items": [{"id": "P1.1", "title": "a"}, {"id": "P1.2", "title": "b"}], "closed": {"at": "now"}},
                  {"item-row": "| {{id}} | {{title}} |\n"})
        self.assertEqual(out, "# Status\n\n| Item | Title |\n|:--|:--|\n| P1.1 | a |\n| P1.2 | b |\n\nClosed now\n\nEnd\n")

    def test_standalone_partial_without_trailing_newline_still_renders_whole_lines(self):
        out = run("{{#r}}\n{{>row}}\n{{/r}}\ntail\n", {"r": [{"x": 1}, {"x": 2}]}, {"row": "| {{x}} |"})
        self.assertEqual(out, "| 1 |\n| 2 |\ntail\n")

    def test_inline_partial_adds_nothing(self):
        self.assertEqual(run("a {{>p}} b", {"x": 1}, {"p": "[{{x}}]"}), "a [1] b")

    def test_empty_partial_in_a_standalone_line_adds_no_line(self):
        self.assertEqual(run("a\n{{>p}}\nb\n", {}, {"p": ""}), "a\nb\n")

    def test_partials_nest_and_recursion_is_bounded(self):
        self.assertEqual(run("<{{>a}}>", {"v": 1}, {"a": "A{{>b}}", "b": "B{{v}}"}), "<AB1>")
        with self.assertRaisesRegex(TemplateError, "nest deeper"):
            run("<{{>loop}}>", {}, {"loop": "x{{>loop}}"})

    def test_missing_partial_is_an_error(self):
        with self.assertRaises(TemplateError):
            run("{{>nope}}")

    def test_invalid_partial_name(self):
        for name in ("Bad", "a b", "a.b", "../x"):
            with self.assertRaises(TemplateError):
                run("{{>" + name + "}}")


class StandaloneTests(unittest.TestCase):
    def test_section_lines_vanish_with_their_newline_and_indentation(self):
        self.assertEqual(run("a\n  {{#x}}  \nb\n\t{{/x}}\nc\n", {"x": True}), "a\nb\nc\n")
        self.assertEqual(run("a\n  {{^x}}\nb\n  {{/x}}\nc\n", {"x": True}), "a\nc\n")

    def test_comment_line_vanishes_and_inline_comment_leaves_text(self):
        self.assertEqual(run("a\n{{! note }}\nb\n"), "a\nb\n")
        self.assertEqual(run("a {{! inline}} b\n"), "a  b\n")

    def test_tag_with_surrounding_text_is_not_standalone(self):
        self.assertEqual(run("x {{#a}}y{{/a}} z\n", {"a": True}), "x y z\n")
        self.assertEqual(run("{{#a}}\ny\n{{/a}} tail\n", {"a": True}), "y\n tail\n")

    def test_two_tags_on_one_line_are_not_standalone(self):
        self.assertEqual(run("{{#a}}{{/a}}\nz\n", {"a": True}), "\nz\n")

    def test_tag_at_the_very_start_and_end_of_the_template(self):
        self.assertEqual(run("{{#a}}\nx\n{{/a}}", {"a": True}), "x\n")
        self.assertEqual(run("{{#a}}\nx\n{{/a}}\n", {"a": True}), "x\n")

    def test_variable_only_line_is_never_removed(self):
        self.assertEqual(run("a\n{{v}}\nb\n", {"v": ""}), "a\n\nb\n")

    def test_blank_lines_around_sections_are_kept(self):
        self.assertEqual(run("a\n\n{{#x}}\nb\n{{/x}}\n\nc\n", {"x": [1]}), "a\n\nb\n\nc\n")


class SyntaxErrorTests(unittest.TestCase):
    def test_unknown_or_malformed_tags_fail_closed(self):
        for template in ("{{&x}}", "{{{x}}}", "{{=<% %>=}}", "{{ }}", "{{a b}}", "{{#}}", "{{#.}}", "{{/.}}", "{{>}}",
                         "{{1x}}", "{{a..b}}", "{{a.}}", "stray {{", "stray }}", "{{x", "x}}", "{{#a}}{{/b}}", "{{/a}}",
                         "{{#a}}", "{{#a}}{{#b}}{{/a}}{{/b}}", "{{a{{b}}}}"):
            with self.subTest(template=template):
                with self.assertRaises(TemplateError):
                    run(template, {"a": [1], "b": 1})

    def test_error_type_is_a_value_error(self):
        self.assertTrue(issubclass(TemplateError, ValueError))


if __name__ == "__main__":
    unittest.main()
