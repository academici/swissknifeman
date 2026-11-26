"""Run a local unit/contract subset for changed modules and their reverse dependencies.

Use --base to compare to a branch or --module to preview a manifest change. Manifest and
registration changes include bootstrap and architecture checks. Shared inputs fall back
to the full unit/contract and architecture suites. Full CI, PostgreSQL and e2e still apply.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .check_touched import ROOT, changed_paths
    from .source_index import _imported_modules
else:
    from check_touched import ROOT, changed_paths
    from source_index import _imported_modules

_EXCLUDED = frozenset({"architecture", "e2e", "evals", "perf"})
_TEST_FLAGS = ("-m", "not pg and not e2e and not evals and not perf")
_BOOTSTRAP_TESTS = Path("tests/unit/bootstrap/test_modules.py")


def _module_dependencies() -> dict[str, frozenset[str]]:
    # Importing the catalog validates manifests, including the ones under review.
    from skm.bootstrap.modules import MODULE_CATALOG

    return {entry.id: frozenset(entry.depends_on) for entry in MODULE_CATALOG}


def reverse_dependents(modules: set[str], dependencies: dict[str, frozenset[str]]) -> set[str]:
    affected = set(modules)
    added = set(modules)
    while added:
        added = {name for name, parents in dependencies.items() if name not in affected and parents & added}
        affected.update(added)
    return affected


def plan(paths: Sequence[str], known_modules: set[str]) -> tuple[set[str], set[Path]] | None:
    """Return module/test inputs or None when a change has suite-wide impact."""
    modules: set[str] = set()
    tests: set[Path] = set()
    for changed in paths:
        path = Path(changed)
        match path.parts:
            case ("src", "skm", "modules", module, *_) if module in known_modules:
                modules.add(module)
            case ("tests", suite, *_) if suite in _EXCLUDED:
                continue
            case ("tests", *_) if path.name.startswith("test_") and path.suffix == ".py":
                if not (ROOT / path).is_file():
                    return None
                tests.add(path)
            case ("docs", *_) | ("working", *_):
                continue
            case _:
                return None
    return modules, tests


def _is_registration_change(changed: str) -> bool:
    match Path(changed).parts:
        case ("src", "skm", "modules", _, "module.py"):
            return True
        case ("src", "skm", "modules", _, *_, "registry.py" | "registration.py"):
            return True
        case _:
            return False


def importing_tests(affected: set[str]) -> set[Path]:
    if not affected:
        return set()
    local = {}
    for path in (ROOT / "tests").rglob("*.py"):
        relative = path.relative_to(ROOT)
        dotted = ".".join(relative.relative_to("tests").with_suffix("").parts).removesuffix(".__init__")
        local[dotted] = relative

    imports = {path: tuple(_imported_modules(path)) for path in local.values()}
    prefixes = tuple(f"skm.modules.{module}." for module in sorted(affected))

    def reaches_affected(test: Path) -> bool:
        todo, visited = [test], set()
        while todo:
            path = todo.pop()
            if path in visited:
                continue
            visited.add(path)
            for name in imports[path]:
                if (name + ".").startswith(prefixes):
                    return True
                if (target := local.get(name.removeprefix("tests."))) is not None:
                    todo.append(target)
        return False

    return {
        path
        for path in local.values()
        if path.name.startswith("test_")
        and path.parts[1] not in _EXCLUDED
        and (affected.intersection(path.parts[2:-1]) or reaches_affected(path))
    }


def _local_tests(
    paths: Sequence[str], dependencies: dict[str, frozenset[str]], registration_changed: bool
) -> set[Path] | None:
    selection = plan(paths, set(dependencies))
    if selection is None:
        return None
    modules, tests = selection
    affected = reverse_dependents(modules, dependencies)
    matches = importing_tests(affected)
    if affected and not matches:
        return None
    tests.update(matches)
    if registration_changed:
        tests.add(_BOOTSTRAP_TESTS)
    print(f"Affected modules {', '.join(sorted(affected)) or '(none)'}. Test files {len(tests)}.")
    return tests


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--module", action="append", default=[], help="Preview a module manifest change.")
    parser.add_argument("--workers", default="4")
    parser.add_argument("--arch-workers", default="2")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = (
            tuple(f"src/skm/modules/{module}/module.py" for module in args.module)
            if args.module
            else changed_paths(ROOT, args.base)
        )
    except (OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"cannot determine changed files: {error}\n")

    registration_changed = any(map(_is_registration_change, paths))
    try:
        dependencies = _module_dependencies()
    except (AttributeError, ImportError, SyntaxError, TypeError, ValueError) as error:
        print(f"Cannot load the module catalog ({error}).")
        tests = None
    else:
        if unknown := set(args.module) - dependencies.keys():
            parser.error(f"unknown module: {', '.join(sorted(unknown))}")
        tests = _local_tests(paths, dependencies, registration_changed)

    full = tests is None
    architecture = (
        full or registration_changed or any(path.startswith("tests/architecture/") for path in paths)
    )
    targets = ["--ignore=tests/architecture"] if tests is None else sorted(map(str, tests))
    if not targets and not architecture:
        print("No applicable test files selected.")
        return 0
    executable = shutil.which(args.uv)
    if executable is None:
        parser.exit(2, f"cannot find {args.uv}\n")
    print("Full suite selected." if full else "Local test selection.", flush=True)
    base = [executable, "run", "--frozen", "pytest", "-q"]
    commands = []
    if targets:
        commands.append([*base, "-n", args.workers, "--dist", "worksteal", *_TEST_FLAGS, *targets])
    if architecture:
        commands.append([*base, "-n", args.arch_workers, "--dist", "loadfile", "tests/architecture"])
    status = 0
    for command in commands:
        print(shlex.join(command), flush=True)
        if not args.dry_run:
            result = subprocess.run(command, cwd=ROOT, check=False)
            status = status or result.returncode
    return status


if __name__ == "__main__":
    raise SystemExit(main())
