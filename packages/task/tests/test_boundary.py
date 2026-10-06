"""Package boundary: the core never names another package of the repository.

Knowledge of a partner lives only in ``bridges/<partner>/``. The root ``core`` library is the shared
foundation and stays allowed. ``boundary_allowlist.json`` lists temporary violations by file with the
owning plan item; it may only shrink, so a stale entry fails the test as well.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve().relative_to(ROOT).as_posix()
ALLOWLIST = ROOT / "tests" / "boundary_allowlist.json"

_NAMES = "orch|skiller|harness|maind|analyst|artifex"
FORBIDDEN = (
    re.compile(rf"packages/({_NAMES})\b"),
    re.compile(rf"^\s*(from|import)\s+({_NAMES})\b"),
    re.compile(rf"\b({_NAMES})\b"),
    re.compile(r"exec/v1"),
    re.compile(r"urn:swissknifeman:orch:"),
    re.compile(r"\b(general|quality|system|devops|oss-dev|repository-bootstrap)[/:][a-z][a-z0-9-]+"),
)
SKIPPED_DIRS = ("bridges/", "docs/.vitepress/cache/", "docs/.vitepress/dist/")
SKIPPED_PARTS = {"__pycache__", "node_modules"}
SKIPPED_FILES = {"CHANGELOG.md", SELF}
REASON = re.compile(r"^P7\.[0-9]+: \S")


def core_files() -> list[str]:
    files = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT).as_posix()
        if (not path.is_file() or relative in SKIPPED_FILES or relative.startswith(SKIPPED_DIRS)
                or SKIPPED_PARTS & set(path.relative_to(ROOT).parts)):
            continue
        files.append(relative)
    return files


def violations(relative: str) -> list[str]:
    try:
        text = (ROOT / relative).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []  # binary files carry no references
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            match = pattern.search(line)
            if match:
                found.append(f"{relative}:{number}: {match.group(0).strip()}")
                break
    return found


def allowlist() -> dict[str, str]:
    return json.loads(ALLOWLIST.read_text(encoding="utf-8")) if ALLOWLIST.exists() else {}


class BoundaryTests(unittest.TestCase):
    def test_core_names_no_other_package(self):
        allowed = allowlist()
        found = [hit for relative in core_files() if relative not in allowed for hit in violations(relative)]
        self.assertEqual(found, [], "core references another package; move it into bridges/<partner>/:\n"
                         + "\n".join(found))

    def test_allowlist_only_shrinks(self):
        stale = [f"{relative}: {reason}" for relative, reason in allowlist().items()
                 if not (ROOT / relative).is_file() or not violations(relative)]
        self.assertEqual(stale, [], "remove stale allowlist entries:\n" + "\n".join(stale))

    def test_allowlist_entries_name_their_owner(self):
        for relative, reason in allowlist().items():
            with self.subTest(relative):
                self.assertRegex(reason, REASON)
                self.assertFalse(relative.startswith(("/", "packages/")), "paths are relative to the package")

    def test_root_core_library_stays_allowed(self):
        for line in ("from core.provider import render", "import core", "MONOREPO_ROOT/core/provider.py"):
            with self.subTest(line):
                self.assertFalse(any(p.search(line) for p in FORBIDDEN))

    def test_tokens_are_caught_and_longer_words_are_not(self):
        for line in ("see packages/maind/README.md", "import skiller.registry", "the orch runner",
                     "contract exec/v1", "urn:swissknifeman:orch:exec:brief:v1", "quality:code-review"):
            with self.subTest(line):
                self.assertTrue(any(p.search(line) for p in FORBIDDEN))
        for line in ("orchestration and the orchestrator", "harnessing", "task:plan-run"):
            with self.subTest(line):
                self.assertFalse(any(p.search(line) for p in FORBIDDEN))


if __name__ == "__main__":
    unittest.main()
