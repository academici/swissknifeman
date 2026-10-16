"""TOML reading: both backends agree, errors carry the file and the line, LineIndex maps keys."""
import sys
import tempfile
import unittest
from pathlib import Path

from aicore.config import ConfigError, toml

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALID = ("basic", "strings", "numbers", "dates", "structures", "crlf")


def backends():
    names = ["vendored"]
    if sys.version_info >= (3, 11):
        names.append("stdlib")
    return names


class ParityTests(unittest.TestCase):
    def read(self, name):
        return (FIXTURES / (name + ".toml")).read_bytes().decode("utf-8")

    def test_every_fixture_parses_identically_on_both_backends(self):
        if sys.version_info < (3, 11):
            self.skipTest("tomllib needs Python 3.11+; the vendored path is exercised below")
        for name in VALID:
            with self.subTest(fixture=name):
                text = self.read(name)
                self.assertEqual(toml._parse(text, "stdlib"), toml._parse(text, "vendored"))

    def test_vendored_backend_reads_the_fixtures(self):
        for name in VALID:
            with self.subTest(fixture=name):
                self.assertIsInstance(toml._parse(self.read(name), "vendored"), dict)

    def test_known_values(self):
        for backend in backends():
            with self.subTest(backend=backend):
                data = toml.loads(self.read("basic"), backend=backend)
                self.assertEqual(data["schema_version"], 1)
                self.assertEqual(data["analyst"]["recompute"]["names"], ["a", "b", "c"])
                self.assertEqual(data["analyst"]["quoted key"], {"a.b": 1, "single": 2})
                strings = toml.loads(self.read("strings"), backend=backend)
                self.assertIn("\t", strings["basic"])
                self.assertEqual(strings["literal"], "C:\\path\\no\\escapes")
                self.assertEqual(strings["empty"], "")
                self.assertEqual(toml.loads(self.read("numbers"), backend=backend)["hex"], 0xDEADBEEF)

    def test_default_backend_matches_the_interpreter(self):
        self.assertEqual(toml.default_backend(), "stdlib" if sys.version_info >= (3, 11) else "vendored")
        self.assertEqual(toml.loads("a = 1"), {"a": 1})

    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            toml._parse("a = 1", "other")


class ErrorTests(unittest.TestCase):
    def test_syntax_error_reports_file_and_line_on_every_backend(self):
        text = (FIXTURES / "invalid_syntax.toml").read_text(encoding="utf-8")
        for backend in backends():
            with self.subTest(backend=backend):
                with self.assertRaises(ConfigError) as caught:
                    toml.loads(text, source="cfg.toml", backend=backend)
                error = caught.exception
                self.assertEqual(error.code, "CONFIG_FILE_INVALID")
                self.assertEqual(error.file, "cfg.toml")
                self.assertEqual(error.line, 4)
                self.assertTrue(str(error).startswith("cfg.toml:4: "))
                self.assertTrue(str(error).endswith("[CONFIG_FILE_INVALID]"))

    def test_duplicate_key_reports_its_line(self):
        text = (FIXTURES / "invalid_duplicate.toml").read_text(encoding="utf-8")
        for backend in backends():
            with self.subTest(backend=backend):
                with self.assertRaises(ConfigError) as caught:
                    toml.loads(text, backend=backend)
                self.assertEqual(caught.exception.line, 5)

    def test_error_text_does_not_repeat_the_document(self):
        for backend in backends():
            with self.assertRaises(ConfigError) as caught:
                toml.loads('token = "s3cr3t-value" = 1', backend=backend)
            self.assertNotIn("s3cr3t-value", str(caught.exception))

    def test_load_file_reads_and_indexes(self):
        data, index = toml.load_file(FIXTURES / "basic.toml")
        self.assertEqual(data["title"], "Example")
        self.assertEqual(index.lookup(("analyst", "recompute", "candidate_min_n")), 13)

    def test_load_file_accepts_a_bom(self):
        data, _ = toml.load_file(FIXTURES / "bom.toml")
        self.assertEqual(data, {"a": 1, "t": {"b": 2}})

    def test_load_file_names_the_file_in_a_syntax_error(self):
        with self.assertRaises(ConfigError) as caught:
            toml.load_file(FIXTURES / "invalid_syntax.toml")
        self.assertTrue(caught.exception.file.endswith("invalid_syntax.toml"))
        self.assertEqual(caught.exception.line, 4)

    def test_load_file_missing_and_not_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as caught:
                toml.load_file(Path(tmp) / "none.toml")
            self.assertEqual(caught.exception.code, "CONFIG_FILE_INVALID")
            bad = Path(tmp) / "bad.toml"
            bad.write_bytes(b"a = '\xff'\n")
            with self.assertRaises(ConfigError) as caught:
                toml.load_file(bad)
            self.assertIn("UTF-8", str(caught.exception))

    def test_config_error_text_skips_empty_parts(self):
        from aicore.config import ConfigError as Error
        self.assertEqual(str(Error("X", "msg")), "msg [X]")
        self.assertEqual(str(Error("X", "msg", file="f.toml")), "f.toml: msg [X]")
        self.assertEqual(str(Error("X", "msg", file="f.toml", line=3, layer="project", key="a.b")),
                         "f.toml:3: project: a.b: msg [X]")
        self.assertEqual(str(Error("X", "msg", line=3)), "line 3: msg [X]")


class LineIndexTests(unittest.TestCase):
    def setUp(self):
        self.index = toml.LineIndex.from_text((FIXTURES / "index.toml").read_text(encoding="utf-8"))

    def test_headers_keys_dotted_and_quoted(self):
        lookup = self.index.lookup
        self.assertEqual(lookup(("top",)), 1)
        self.assertEqual(lookup(("a", "b")), 2)
        self.assertEqual(lookup(("a", "b", "c")), 3)
        self.assertEqual(lookup(("a", "b", "d e")), 4)
        self.assertEqual(lookup(("a", "b", "f", "g")), 5)
        self.assertEqual(lookup(("a", "b", "f")), 5)
        self.assertEqual(lookup(("tail", "lit key")), 22)

    def test_inline_table_indexes_only_its_key(self):
        self.assertEqual(self.index.lookup(("a", "b", "inline")), 6)
        self.assertEqual(self.index.lookup(("a", "b", "inline", "x")), 6)  # nearest ancestor

    def test_multiline_string_and_array_do_not_confuse_the_scan(self):
        self.assertEqual(self.index.lookup(("a", "b", "text")), 7)
        self.assertNotIn(("not", "a", "header"), self.index)
        self.assertNotIn(("a", "b", "key"), self.index)
        self.assertEqual(self.index.lookup(("a", "b", "arr")), 11)
        self.assertEqual(self.index.lookup(("a", "b", "after")), 16)

    def test_array_of_tables_indexes_the_header_only(self):
        self.assertEqual(self.index.lookup(("items",)), 17)
        self.assertNotIn(("items", "name"), self.index)
        self.assertEqual(self.index.lookup(("items", "name")), 17)  # falls back to the header

    def test_unknown_path_and_empty_path(self):
        self.assertIsNone(self.index.lookup(("nope",)))
        self.assertIsNone(self.index.lookup(()))
        self.assertEqual(self.index.lookup(("tail", "missing", "deeper")), 21)

    def test_exact_beats_ancestor(self):
        self.assertEqual(self.index.lookup(("a", "b", "c")), 3)

    def test_subtable_of_an_array_of_tables_is_not_indexed(self):
        text = (FIXTURES / "structures.toml").read_text(encoding="utf-8")
        index = toml.LineIndex.from_text(text)
        self.assertEqual(index.lookup(("servers",)), 16)
        self.assertNotIn(("servers", "limits"), index)
        self.assertEqual(index.lookup(("server", "host", "port")), 14)
        self.assertEqual(index.lookup(("inline",)), 10)
        self.assertEqual(index.lookup(("multi_line",)), 6)

    def test_crlf_text_has_the_same_lines(self):
        text = (FIXTURES / "crlf.toml").read_bytes().decode("utf-8")
        index = toml.LineIndex.from_text(text)
        self.assertEqual(index.lookup(("a",)), 1)
        self.assertEqual(index.lookup(("t",)), 2)
        self.assertEqual(index.lookup(("t", "c")), 4)

    def test_len_counts_indexed_paths(self):
        self.assertGreater(len(self.index), 10)
        self.assertEqual(len(toml.LineIndex()), 0)


if __name__ == "__main__":
    unittest.main()
