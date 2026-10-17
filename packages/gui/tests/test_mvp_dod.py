"""docs/mvp-dod.md: every row names an existing test file that contains the named test or scenario."""
import re
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[1]
DOC = MODULE_ROOT / "docs" / "mvp-dod.md"
KINDS = ("auto", "owner")
ROW = re.compile(r"^\|\s*(\d+)\s*\|(.+)\|\s*(auto|owner)\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*$")


def rows():
    found = []
    for number, line in enumerate(DOC.read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"^\|\s*\d+\s*\|", line):
            match = ROW.match(line)
            found.append((number, line, match))
    return found


class TestMvpDod(unittest.TestCase):
    def test_the_table_is_there_and_every_row_is_well_formed(self):
        table = rows()
        self.assertGreaterEqual(len(table), 30)
        for number, line, match in table:
            self.assertIsNotNone(match, f"{DOC.name}:{number}: not `| # | item | auto|owner | `file` | `name` |`: {line}")

    def test_every_file_exists_and_contains_the_name(self):
        for number, _line, match in rows():
            _num, _item, _kind, file, name = match.groups()
            path = REPO_ROOT / file
            if not file.startswith("packages/gui/") and not (REPO_ROOT / "bridges").is_dir():
                continue  # the module alone, outside the hub checkout: the bridges are not here
            self.assertTrue(path.is_file(), f"{DOC.name}:{number}: {file} does not exist")
            self.assertIn(name, path.read_text(encoding="utf-8"), f"{DOC.name}:{number}: {file} has no `{name}`")

    def test_owner_rows_point_to_the_owner_runbook(self):
        owner = [match.groups() for _n, _l, match in rows() if match.group(3) == "owner"]
        self.assertTrue(owner)
        for _num, _item, _kind, file, _name in owner:
            self.assertEqual("packages/gui/docs/desktop-release.md", file)

    def test_every_dod_item_of_the_source_is_covered(self):
        numbers = {match.group(1) for _n, _l, match in rows()}
        self.assertLessEqual({str(n) for n in range(1, 8)}, numbers)  # the seven items of the source DoD

    def test_files_stay_inside_the_repository(self):
        for number, _line, match in rows():
            file = match.group(4)
            self.assertFalse(file.startswith("/") or ".." in Path(file).parts, f"{DOC.name}:{number}: {file}")


if __name__ == "__main__":
    unittest.main()
