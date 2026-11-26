"""Markdown selectors preserve fenced content, nesting, line endings and exact ranges."""

import pytest

from skm.modules.context.domain.sections import extract_heading, extract_line_range, extract_sections

_MD = (
    "# Project\nintro\n## Security\n- forbid escape\n### Files\n"
    "```md\n## Fake\n```\nkeep\n## Testing\nrun tests\n"
)


def test_sections_match_case_insensitive_dotted_names_and_keep_subtrees():
    text, titles = extract_sections(_MD, ("project.security",))
    assert titles == ("Security",)
    assert text == "## Security\n- forbid escape\n### Files\n```md\n## Fake\n```\nkeep\n"
    assert extract_heading(_MD, "security") == text


def test_parent_and_child_selection_never_duplicates_lines():
    text, titles = extract_sections(_MD, ("Security", "Files"))
    assert text.count("keep") == 1
    assert titles == ("Security", "Files")


def test_wildcard_preserves_entire_file_without_changing_line_endings():
    source = "preamble\r\n# Title\r\nbody\r\n"
    assert extract_sections(source, ("*",)) == (source, ("*",))


def test_missing_or_fenced_heading_is_not_evidence_of_reading_section():
    assert extract_sections(_MD, ("Missing", "Fake")) == ("", ())
    assert extract_sections(_MD, ()) == ("", ())


def test_setext_headings_closing_atx_hashes_and_long_fences():
    source = "Security\n========\nbody\n~~~python\n# Fake\n~~~~\n## Details ##\nkeep\nNext\n====\ndrop\n"
    text, titles = extract_sections(source, ("security",))
    assert titles == ("Security",)
    assert text.endswith("keep\n")
    assert "# Fake" in text
    assert "drop" not in text
    assert extract_heading(source, "details") == "## Details ##\nkeep\n"


@pytest.mark.parametrize(
    ("start", "end", "expected"), [(1, 1, "one\r\n"), (2, 3, "two\r\nthree"), (3, 9, "three"), (4, 5, "")]
)
def test_line_ranges_are_one_based_inclusive(start, end, expected):
    assert extract_line_range("one\r\ntwo\r\nthree", start, end) == expected


@pytest.mark.parametrize(("start", "end"), [(0, 1), (-1, 2), (3, 2)])
def test_invalid_ranges_are_refused(start, end):
    with pytest.raises(ValueError, match="1-based and inclusive"):
        extract_line_range(_MD, start, end)
