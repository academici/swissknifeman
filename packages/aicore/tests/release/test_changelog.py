"""The CHANGELOG format: the Unreleased section, its move under a version, the released headings."""
from datetime import date
import unittest

from aicore.release.changelog import (parse_released, read_unreleased_section, release_changelog,
                                      unreleased_is_empty)

WITH_RELEASE = """# Changelog

## [Unreleased]

### Added

- something

## [1.2.0] - 2026-07-01

### Added

- previous

## [1.1.0] - 2026-06-01
"""


class ParseReleasedTests(unittest.TestCase):
    def test_released_versions_keep_file_order(self):
        self.assertEqual(parse_released(WITH_RELEASE), (["1.2.0", "1.1.0"], False))

    def test_only_unreleased_has_no_released_headings(self):
        self.assertEqual(parse_released("# Changelog\n\n## [Unreleased]\n\n- x\n"), ([], False))

    def test_heading_without_date_is_malformed(self):
        self.assertEqual(parse_released("## [Unreleased]\n\n## [1.2.0 no date]\n"), ([], True))

    def test_malformed_heading_is_reported_next_to_valid_ones(self):
        text = "## [Unreleased]\n\n## [1.2.0] - 2026-07-01\n\n## [oops]\n"
        self.assertEqual(parse_released(text), (["1.2.0"], True))


class UnreleasedSectionTests(unittest.TestCase):
    def test_reads_body_between_headings(self):
        text = ("# Changelog\n\n## [Unreleased]\n### Added\n- new thing\n\n"
                "## [0.7.1] - 2026-06-28\n### Fixed\n- old\n")
        lines, start, end, body = read_unreleased_section(text)
        self.assertEqual(lines[start], "## [Unreleased]")
        self.assertEqual(lines[end], "## [0.7.1] - 2026-06-28")
        self.assertIn("- new thing", body)
        self.assertNotIn("- old", body)

    def test_title_is_matched_leniently(self):
        self.assertIsNotNone(read_unreleased_section("##   [unreleased]  \n- x\n"))

    def test_missing_section_returns_none(self):
        self.assertIsNone(read_unreleased_section("# Changelog\n\nnothing here\n"))

    def test_section_runs_to_end_of_file_without_next_heading(self):
        _, start, end, body = read_unreleased_section("## [Unreleased]\n- a\n- b\n")
        self.assertEqual((start, end, body), (0, 3, ["- a", "- b"]))

    def test_empty_section_detected(self):
        _, _, _, body = read_unreleased_section(
            "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n- x\n")
        self.assertTrue(unreleased_is_empty(body))

    def test_section_with_only_group_headers_is_empty(self):
        _, _, _, body = read_unreleased_section(
            "# Changelog\n\n## [Unreleased]\n### Added\n### Fixed\n\n## [0.1.0]\n")
        self.assertTrue(unreleased_is_empty(body))

    def test_section_with_entry_is_not_empty(self):
        _, _, _, body = read_unreleased_section(
            "# Changelog\n\n## [Unreleased]\n### Added\n- entry\n\n## [0.1.0]\n")
        self.assertFalse(unreleased_is_empty(body))


class ReleaseChangelogTests(unittest.TestCase):
    def test_unreleased_body_moves_under_the_new_version(self):
        result = release_changelog(WITH_RELEASE, "v1.3.0")
        today = date.today().isoformat()
        self.assertIn(f"## [Unreleased]\n\n## [1.3.0] - {today}\n\n### Added\n\n- something\n", result)
        self.assertTrue(result.endswith("## [1.1.0] - 2026-06-01\n"))

    def test_other_sections_stay_untouched(self):
        result = release_changelog(WITH_RELEASE, "1.3.0")
        self.assertIn("## [1.2.0] - 2026-07-01\n\n### Added\n\n- previous\n", result)
        self.assertEqual(parse_released(result)[0][:3], ["1.3.0", "1.2.0", "1.1.0"])

    def test_the_new_unreleased_section_is_empty(self):
        result = release_changelog(WITH_RELEASE, "v1.3.0")
        _, _, _, body = read_unreleased_section(result)
        self.assertTrue(unreleased_is_empty(body))
