"""Navigation index of ``src/skm``: what each package is for and which tests import it.

``--write`` regenerates ``docs/reference/source-index.md``; ``--check`` fails when it is stale.
``--files PATH`` prints one docstring line per Python file under PATH, so a reader can pick files
without opening them. ``--outline FILE`` prints a file's public signatures and re-exports, so a
facade is read in a few dozen lines. ``--tests PATH...`` lists the test files importing any of PATH.

Examples::

    uv run --frozen python tools/source_index.py --files src/skm/modules/planning/domain
    uv run --frozen python tools/source_index.py --outline src/skm/modules/planning/public.py
    uv run --frozen python tools/source_index.py --tests src/skm/modules/access/public.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("src/skm")
OUTPUT = Path("docs/reference/source-index.md")
# Children of these packages are listed as separate units; their own loose files form a "root" unit.
_CONTAINERS = frozenset({"adapters", "entrypoints", "modules", "platform"})
# Files a reader opens first when the package has no docstring of its own.
_SUMMARY_FALLBACKS = ("__init__.py", "public.py", "module.py")
# Files that define a module's public surface, listed when present.
_ENTRYPOINTS = ("public.py", "module.py", "ports.py", "registry.py", "application/registry.py")
_TEST_ROOT = Path("tests")
_SKIPPED_PARTS = frozenset({"generated", "__pycache__"})
_MAX_SUMMARY = 200
_MAX_UNNAMED = 3


@dataclass(frozen=True, slots=True)
class Unit:
    """A navigation unit: a package directory, or the loose files of a container package."""

    path: Path
    files: tuple[Path, ...]

    @property
    def dotted(self) -> str:
        return ".".join(self.path.relative_to(PACKAGE.parent).parts)


def _python_files(directory: Path, *, recursive: bool) -> tuple[Path, ...]:
    pattern = "**/*.py" if recursive else "*.py"
    found = (
        path.relative_to(ROOT)
        for path in (ROOT / directory).glob(pattern)
        if not _SKIPPED_PARTS.intersection(path.relative_to(ROOT / directory).parts)
    )
    return tuple(sorted(found))


def units() -> tuple[Unit, ...]:
    """Top-level packages, with container packages split into their children."""
    result: list[Unit] = []
    for child in sorted((ROOT / PACKAGE).iterdir()):
        relative = child.relative_to(ROOT)
        if not child.is_dir() or child.name in _SKIPPED_PARTS:
            continue
        if child.name not in _CONTAINERS:
            result.append(Unit(relative, _python_files(relative, recursive=True)))
            continue
        loose = tuple(path for path in _python_files(relative, recursive=False) if path.name != "__init__.py")
        if loose:
            result.append(Unit(relative, loose))
        for grandchild in sorted(child.iterdir()):
            if grandchild.is_dir() and grandchild.name not in _SKIPPED_PARTS:
                nested = grandchild.relative_to(ROOT)
                result.append(Unit(nested, _python_files(nested, recursive=True)))
    return tuple(unit for unit in result if unit.files)


@cache
def _docstring(path: Path) -> str:
    try:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ""
    return ast.get_docstring(tree) or ""


def first_sentence(text: str) -> str:
    """The first paragraph's first sentence, on one line, safe inside a Markdown table cell."""
    paragraph = " ".join(text.strip().split("\n\n", 1)[0].split())
    head, separator, _ = paragraph.partition(". ")
    sentence = head + "." if separator else paragraph
    if len(sentence) > _MAX_SUMMARY:
        sentence = sentence[: _MAX_SUMMARY - 1].rstrip() + "…"
    return sentence.replace("|", "\\|")


def summary(unit: Unit) -> str:
    for name in _SUMMARY_FALLBACKS:
        path = unit.path / name
        if path in unit.files and _docstring(path):
            return first_sentence(_docstring(path))
    return ""


def _imported_modules(path: Path) -> Iterator[str]:
    try:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # ``from skm.modules.access import public`` imports ``skm.modules.access.public``.
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


@cache
def _test_imports() -> tuple[tuple[Path, frozenset[str]], ...]:
    # Only collected test modules count: fixtures and helpers import product code without testing it.
    tests = sorted(path.relative_to(ROOT) for path in (ROOT / _TEST_ROOT).rglob("test_*.py"))
    return tuple(
        (path, frozenset(name for name in _imported_modules(path) if name.startswith("skm")))
        for path in tests
        if not _SKIPPED_PARTS.intersection(path.parts)
    )


def _covers(imported: Iterable[str], dotted: str) -> bool:
    return any(name == dotted or name.startswith(f"{dotted}.") for name in imported)


def importing_tests(dotted: str) -> tuple[Path, ...]:
    """Test files that import ``dotted`` or anything below it."""
    return tuple(path for path, imported in _test_imports() if _covers(imported, dotted))


def _unit_tests(unit: Unit) -> tuple[Path, ...]:
    if unit.path.name in _CONTAINERS:
        # Loose files of a container: match each file's module rather than the whole container.
        dotted = {".".join(path.with_suffix("").parts[1:]) for path in unit.files}
        return tuple(
            path for path, imported in _test_imports() if any(_covers(imported, name) for name in dotted)
        )
    return importing_tests(unit.dotted)


def test_directories(unit: Unit, tests: Sequence[Path]) -> str:
    """Importing test directories named after the package; other importers are only flagged.

    Listing every importer would make the page churn with each new test; directories named after the
    package are the ones a reader runs first, and ``--tests`` gives the complete list on demand.
    """
    counts = Counter(path.parent.relative_to(_TEST_ROOT) for path in tests)
    named = sorted(directory.as_posix() for directory in counts if unit.path.name in directory.parts)
    if not named:
        # Nothing is named after the package: show where most of its importers live instead.
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0].as_posix()))
        named = [directory.as_posix() for directory, _ in ranked[:_MAX_UNNAMED]]
    shown = ", ".join(f"`{directory}`" for directory in named)
    return f"{shown}; also elsewhere" if len(named) < len(counts) else shown or "—"


def _entrypoints(unit: Unit) -> str:
    present = [name for name in _ENTRYPOINTS if unit.path / name in unit.files]
    return ", ".join(f"`{name}`" for name in present) or "—"


def render() -> str:
    lines = [
        "# Source index",
        "",
        "Generated by `make source-index`; do not edit by hand. The sync test",
        "`tests/unit/tools/test_source_index.py` fails when a package docstring, an entrypoint file or",
        "the set of importing test directories changes without regenerating this page.",
        "",
        "Each row is one package. *Summary* is the first sentence of its `__init__.py` docstring",
        "(or of `public.py`/`module.py`). *Tests* are the `tests/` directories named after the package",
        "whose `test_*.py` files import it; when none is named after it, the three directories with most",
        'importers. "Also elsewhere" marks importers in other directories. To go one level deeper',
        "without opening files, list file summaries, a file's public outline or every importing test:",
        "",
        "```sh",
        "uv run --frozen python tools/source_index.py --files src/skm/modules/planning/domain",
        "uv run --frozen python tools/source_index.py --outline src/skm/modules/planning/public.py",
        "uv run --frozen python tools/source_index.py --tests src/skm/modules/planning/domain/rebase.py",
        "```",
        "",
        "| Package | Summary | Entrypoints | Tests |",
        "|---|---|---|---|",
    ]
    for unit in units():
        label = f"{unit.path.as_posix()}/*.py" if unit.path.name in _CONTAINERS else unit.path.as_posix()
        link = f"[`{label}`](../../{unit.path.as_posix()}/)"
        tests = test_directories(unit, _unit_tests(unit))
        lines.append(f"| {link} | {summary(unit) or '—'} | {_entrypoints(unit)} | {tests} |")
    return "\n".join(lines) + "\n"


def file_summaries(target: Path) -> str:
    files = (target,) if target.suffix == ".py" else _python_files(target, recursive=True)
    rows: list[str] = []
    for path in files:
        lines = (ROOT / path).read_text(encoding="utf-8").count("\n")
        rows.append(f"{path.as_posix()}  [{lines} lines]  {first_sentence(_docstring(path)) or '—'}")
    return "\n".join(rows)


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _doc_suffix(node: ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef) -> str:
    summary = first_sentence(ast.get_docstring(node) or "").replace("\\|", "|")
    return f"  # {summary}" if summary else ""


def outline(path: Path) -> str:
    """Public top-level classes and functions with signatures, then names only re-exported by ``__all__``.

    Reading the outline of a facade replaces reading its body: hundreds of lines become one line per name.
    """
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=str(path))
    rows = [f"{path.as_posix()}: {first_sentence(_docstring(path)) or '—'}"]
    defined: set[str] = set()
    exported: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if node.name.startswith("_"):
                continue
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(base) for base in node.bases)
                rows.append(f"  class {node.name}({bases}){_doc_suffix(node)}")
                rows.extend(
                    f"      {_signature(item)}{_doc_suffix(item)}"
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not item.name.startswith("_")
                )
            else:
                rows.append(f"  {_signature(node)}{_doc_suffix(node)}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
                    if target.id == "__all__" and node.value is not None:
                        value = ast.literal_eval(node.value)
                        exported = [str(name) for name in value] if isinstance(value, (list, tuple)) else []
        elif isinstance(node, ast.TypeAlias):
            defined.add(node.name.id)
    reexported = sorted(name for name in exported if name not in defined)
    if reexported:
        rows.append(f"  re-exported: {', '.join(reexported)}")
    return "\n".join(rows)


def _dotted(target: Path) -> str:
    relative = target.with_suffix("") if target.suffix == ".py" else target
    parts = relative.parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _relative(argument: str) -> Path:
    path = Path(argument)
    resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError:
        raise SystemExit(f"{argument}: outside the repository") from None
    if relative.parts[:2] != PACKAGE.parts or not resolved.exists():
        raise SystemExit(f"{argument}: not an existing path under {PACKAGE}")
    return relative


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0] if __doc__ else None)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help=f"regenerate {OUTPUT}")
    mode.add_argument("--check", action="store_true", help=f"fail when {OUTPUT} is stale")
    mode.add_argument("--files", metavar="PATH", help="one docstring line per Python file under PATH")
    mode.add_argument("--outline", metavar="FILE", help="public classes, functions and re-exports of FILE")
    mode.add_argument(
        "--tests", metavar="PATH", nargs="+", help="test files importing any package or module at PATH"
    )
    args = parser.parse_args(argv)
    if args.files:
        print(file_summaries(_relative(args.files)))
        return 0
    if args.outline:
        target = _relative(args.outline)
        if target.suffix != ".py":
            raise SystemExit(f"{args.outline}: --outline takes one Python file")
        print(outline(target))
        return 0
    if args.tests:
        found = {test for target in args.tests for test in importing_tests(_dotted(_relative(target)))}
        print("\n".join(path.as_posix() for path in sorted(found)))
        return 0
    expected = render()
    if args.write:
        (ROOT / OUTPUT).write_text(expected, encoding="utf-8")
        return 0
    current = (ROOT / OUTPUT).read_text(encoding="utf-8") if (ROOT / OUTPUT).exists() else ""
    if current != expected:
        print(f"{OUTPUT} is stale; run: make source-index", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
