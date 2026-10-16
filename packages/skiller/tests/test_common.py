"""Tests common: marker «controlled swissknifeman» in copied SKILL.md.

Byte-accurate round-trip (_mark_skill_managed → strip_skill_managed_marker) for LF,
CRLF and BOM — regression on the bug found in the review: old text-mode version (`.read_text()`)
normalized `\\r\\n`→`\\n`, because of what the hash CRLF-skill after marking/proofreading
disagreed with `hashlib.sha256(read_bytes())` registry (registry.py) — false "update"
on EVERY sync even without real drift."""
import tempfile
import unittest
from pathlib import Path

from aicore.delivery.materialize import (
    SKILL_MANAGED_MARKER, mark_skill_managed as _mark_skill_managed, strip_skill_managed_marker)


class SkillManagedMarkerCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dst = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, raw_bytes):
        (self.dst / "SKILL.md").write_bytes(raw_bytes)

    def _read(self):
        return (self.dst / "SKILL.md").read_bytes()

    def test_lf_round_trip_matches_original_bytes(self):
        original = b"---\nname: foo\n---\n\n# Foo\n"
        self._write(original)
        _mark_skill_managed(self.dst)
        marked = self._read()
        self.assertIn(SKILL_MANAGED_MARKER.encode("utf-8"), marked)
        self.assertEqual(strip_skill_managed_marker(marked), original)

    def test_crlf_round_trip_matches_original_bytes(self):
        original = b"---\r\nname: foo\r\n---\r\n\r\n# Foo\r\n"
        self._write(original)
        _mark_skill_managed(self.dst)
        marked = self._read()
        self.assertIn(b"\r\n", marked)
        self.assertNotIn(b"\n\n\n", marked.replace(b"\r\n", b"\n").replace(b"\n\n", b"|"))
        self.assertEqual(strip_skill_managed_marker(marked), original)

    def test_bom_round_trip_matches_original_bytes(self):
        original = b"\xef\xbb\xbf---\nname: foo\n---\n\n# Foo\n"
        self._write(original)
        _mark_skill_managed(self.dst)
        marked = self._read()
        self.assertTrue(marked.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(strip_skill_managed_marker(marked), original)

    def test_idempotent_second_mark_is_noop(self):
        original = b"---\nname: foo\n---\n\n# Foo\n"
        self._write(original)
        _mark_skill_managed(self.dst)
        once = self._read()
        _mark_skill_managed(self.dst)
        twice = self._read()
        self.assertEqual(once, twice)
        self.assertEqual(once.count(SKILL_MANAGED_MARKER.encode("utf-8")), 1)

    def test_strip_without_marker_is_identity(self):
        original = b"---\nname: foo\n---\n\n# Foo\n"
        self.assertEqual(strip_skill_managed_marker(original), original)

    def test_missing_frontmatter_skips_silently(self):
        original = b"# No frontmatter here\n"
        self._write(original)
        _mark_skill_managed(self.dst)
        self.assertEqual(self._read(), original)

    def test_missing_skill_md_is_noop(self):
        _mark_skill_managed(self.dst)  # should not be thrown
        self.assertFalse((self.dst / "SKILL.md").exists())
