"""Portable package boundary, with a shrinking, item-owned migration allowlist.

Code forbids repository package names and layout helpers. Distributed content
forbids repository paths, while external tool names and the shared core stay allowed.
The filesystem scan also works in a standalone copy without Git.
"""
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SELF = "tests/test_boundary.py"
ALLOWLIST = "tests/boundary_allowlist.json"
BOOTSTRAP = "skills/repository-bootstrap"

PACKAGE_NAMES = "task|orch|harness|maind|analyst|artifex|skiller"
PARTNER_NAMES = "task|orch|harness|maind|analyst|artifex"
PATH_TOKEN = re.compile(rf"packages/({PACKAGE_NAMES})\b")
CODE_TOKENS = (
    ("C1", PATH_TOKEN),
    ("C2", re.compile(rf"^\s*(from|import)\s+({PARTNER_NAMES})\b")),
    ("C3", re.compile(r"\b(orch|harness|maind|analyst|artifex)\b")),
    ("C4", re.compile(r"[\"']task[\"']|/task:")),
    ("C5", re.compile(rf"\.\./({PARTNER_NAMES})\b")),
    ("C6", re.compile(r"find_monorepo_root|sibling_bin")),
)
CONTENT_TOKENS = (("K1", PATH_TOKEN),)
CODE_DIRS = {"lib", "bin", "scripts", "tests", "configs", "profiles", "presets", "schema"}
CODE_FILES = {"install.sh", "sync.sh"}
SKIPPED_FILES = {"CHANGELOG.md", SELF, ALLOWLIST}
SKIPPED_PARTS = {"__pycache__", "node_modules"}
SKIPPED_PREFIXES = ("docs/audits/", "docs/.vitepress/cache/", "docs/.vitepress/dist/")
OWNER_REASON = re.compile(r"^P8\.[2-9]: \S")


def code_zone(relative: str) -> bool:
    path = Path(relative)
    return (path.parts[0] in CODE_DIRS or relative in CODE_FILES
            or len(path.parts) == 1 and path.suffix == ".json")


def violations(root: Path) -> dict[str, list[str]]:
    found = {}
    if (root / BOOTSTRAP).is_dir():
        found[BOOTSTRAP] = [f"{BOOTSTRAP}:1: K2: repository-only skill directory"]
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if (not path.is_file() or relative in SKIPPED_FILES
                or relative.startswith(SKIPPED_PREFIXES)
                or SKIPPED_PARTS.intersection(path.relative_to(root).parts)
                or relative.startswith(BOOTSTRAP + "/")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        tokens = CODE_TOKENS if code_zone(relative) else CONTENT_TOKENS
        hits = []
        for number, line in enumerate(text.splitlines(), 1):
            for code, pattern in tokens:
                match = pattern.search(line)
                if match:
                    hits.append(f"{relative}:{number}: {code}: {match.group(0).strip()}")
                    break
        if hits:
            found[relative] = hits
    return found


def load_allowlist(root: Path) -> dict[str, str]:
    path = root / ALLOWLIST
    if not path.exists():
        return {}
    allowed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(allowed, dict):
        raise ValueError("allowlist must be an object of concrete paths and owner reasons")
    for relative, reason in allowed.items():
        parts = relative.split("/")
        if (not relative or any(part in {"", ".", ".."} for part in parts)
                or relative.startswith("packages/") or re.search(r"[*?\[\]\\:]", relative)):
            raise ValueError(f"allowlist path must be concrete and package-relative: {relative}")
        if not isinstance(reason, str) or not OWNER_REASON.match(reason):
            raise ValueError(f"allowlist reason must name an owner P8.2-P8.9: {relative}")
    return allowed


def boundary_errors(root: Path) -> list[str]:
    allowed = load_allowlist(root)
    found = violations(root)
    errors = [hit for relative, hits in found.items() if relative not in allowed for hit in hits]
    errors.extend(f"{relative}: stale allowlist entry; remove it ({reason})"
                  for relative, reason in allowed.items() if relative not in found)
    return errors


class BoundaryTests(unittest.TestCase):
    def test_package_boundary_and_allowlist(self):
        errors = boundary_errors(ROOT)
        self.assertEqual(errors, [], "package boundary violations:\n" + "\n".join(errors))


class BoundaryScannerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def allow(self, entries):
        self.write(ALLOWLIST, json.dumps(entries))

    def test_code_tokens_and_line_diagnostics(self):
        samples = {
            "C1": "packages/skiller/lib/module.py",
            "C2": "  from task.module import value",
            "C3": "use maind CLI",
            "C4": "plugin = 'task'",
            "C5": "../task/commands",
            "C6": "root = find_monorepo_root(path)",
        }
        for code, line in samples.items():
            with self.subTest(code=code):
                self.write("lib/module.py", "# clean\n" + line)
                self.assertEqual(violations(self.root)["lib/module.py"],
                                 [f"lib/module.py:2: {code}: "
                                  + next(p.search(line).group(0).strip()
                                         for c, p in CODE_TOKENS if c == code)])
        for line in ("import orch.api", '"task"', "/task:plan-run", "sibling_bin(root)"):
            with self.subTest(line=line):
                self.write("lib/module.py", line)
                self.assertIn("lib/module.py", violations(self.root))

    def test_all_code_zones(self):
        paths = [f"{directory}/example.txt" for directory in CODE_DIRS]
        paths += ["tests/fixtures_data/deep/file.md", "install.sh", "sync.sh", "root.json"]
        for relative in paths:
            self.write(relative, "harness")
        self.assertEqual(set(violations(self.root)), set(paths))

    def test_content_tool_names_allowed_but_repository_paths_rejected(self):
        paths = [f"{directory}/example.md" for directory in (
            "skills/general/example", "references", "docs/guide", "generate-skill",
            "skm", "adapters", "provider-skills", "prompts", ".swissknifeman.example")]
        paths += ["README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "SKILL_TEMPLATE.md"]
        for relative in paths:
            self.write(relative, "orch harness maind analyst artifex 'task' /task:dev\n")
        self.assertEqual(violations(self.root), {})
        for relative in paths:
            self.write(relative, "packages/task/commands\n")
        self.assertEqual(set(violations(self.root)), set(paths))
        self.assertTrue(all(": K1:" in hits[0] for hits in violations(self.root).values()))

    def test_shared_core_and_unrelated_package_names_stay_allowed(self):
        lines = ("from core.paths import find_repo_root", "import core",
                 "$MONOREPO_ROOT/core/provider.py", "packages/core",
                 "packages/vitest", "packages/taskboard", "orchestration",
                 "harnessing", "Maind", "task:plan-run", "task = 'example'")
        self.write("lib/module.py", "\n".join(lines))
        self.assertEqual(violations(self.root), {})

    def test_skipped_files_directories_and_binary(self):
        paths = list(SKIPPED_FILES - {ALLOWLIST}) + [
            "lib/__pycache__/module.py", "node_modules/example/file.txt",
            "docs/audits/old.md", "docs/.vitepress/cache/file.txt", "docs/.vitepress/dist/file.txt"]
        for relative in paths:
            self.write(relative, "packages/task harness")
        self.write("lib/binary.dat", "")
        (self.root / "lib/binary.dat").write_bytes(b"\xff packages/task")
        self.allow({})
        self.assertEqual(violations(self.root), {})
        self.write("docs/audits-current.md", "packages/task")
        self.assertIn("docs/audits-current.md", violations(self.root))

    def test_bootstrap_is_one_structural_entry_even_when_empty(self):
        (self.root / BOOTSTRAP).mkdir(parents=True)
        self.assertEqual(set(violations(self.root)), {BOOTSTRAP})
        self.write(BOOTSTRAP + "/example/SKILL.md", "packages/task")
        self.assertEqual(set(violations(self.root)), {BOOTSTRAP})
        self.allow({BOOTSTRAP: "P8.6: move repository-only skills to their owners"})
        self.assertEqual(boundary_errors(self.root), [])

    def test_missing_allowlist_means_empty(self):
        self.assertEqual(load_allowlist(self.root), {})
        self.write("lib/module.py", "harness")
        self.assertEqual(len(boundary_errors(self.root)), 1)

    def test_allowlist_skips_whole_file_and_retains_other_failures(self):
        self.write("lib/module.py", "harness\npackages/task")
        self.write("lib/new.py", "maind")
        self.allow({"lib/module.py": "P8.5: delegate through host commands"})
        errors = boundary_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("lib/new.py:1:"))

    def test_stale_missing_clean_and_excluded_entries_fail(self):
        for relative in ("lib/missing.py", "lib/clean.py", "CHANGELOG.md", BOOTSTRAP):
            with self.subTest(relative=relative):
                if relative not in {"lib/missing.py", BOOTSTRAP}:
                    self.write(relative, "core")
                self.allow({relative: "P8.6: temporary migration"})
                self.assertIn("stale allowlist entry", boundary_errors(self.root)[0])

    def test_globs_and_nonrelative_or_noncanonical_paths_fail(self):
        for relative in ("lib/*.py", "lib/?.py", "lib/[ab].py", "/lib/file.py",
                         "../file.py", "lib/../file.py", "./file.py", "lib//file.py",
                         "lib/", "C:/file.py", "lib\\file.py", "packages/skiller/file.py", ""):
            with self.subTest(relative=relative):
                self.allow({relative: "P8.5: temporary migration"})
                with self.assertRaisesRegex(ValueError, "concrete and package-relative"):
                    load_allowlist(self.root)

    def test_owner_reason_and_allowlist_shape(self):
        for reason in ("migration", "P8.1: self", "P8.10: unknown", "P8.5: ", 5):
            with self.subTest(reason=reason):
                self.allow({"lib/module.py": reason})
                with self.assertRaisesRegex(ValueError, "must name an owner"):
                    load_allowlist(self.root)
        self.allow([])
        with self.assertRaisesRegex(ValueError, "must be an object"):
            load_allowlist(self.root)


if __name__ == "__main__":
    unittest.main()
