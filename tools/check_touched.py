"""Run a read-only preflight for committed and local changes, without guessing affected tests.

Examples: ``uv run --frozen python tools/check_touched.py --base new --dry-run``;
``make check-touched`` checks changes since HEAD, including staged and untracked files.
Behavioral unit/contract tests and required PostgreSQL/e2e runs remain separate.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_CONFIG = {"pyproject.toml", "uv.lock", "ruff.toml", "pyrightconfig.json", "tools/pyrightconfig.json"}
_UV = ("uv", "run", "--frozen")


def _git(root: Path, *args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise FileNotFoundError("git is not installed")
    result = subprocess.run([executable, *args], cwd=root, check=True, capture_output=True, timeout=30)
    return os.fsdecode(result.stdout)


def changed_paths(root: Path, base: str) -> tuple[str, ...]:
    """Branch changes since merge-base, plus staged, unstaged and untracked paths.

    Keep deletions and both sides of renames: these can break inventory and links.
    Separate diffs retain a staged edit even if the working copy reverses it.
    """
    revision = _git(root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}").strip()
    ancestor = _git(root, "merge-base", revision, "HEAD").strip()
    outputs = (
        _git(root, "diff", "--name-only", "-z", "--no-renames", ancestor, "HEAD", "--"),
        _git(root, "diff", "--name-only", "-z", "--no-renames", "--cached", "--"),
        _git(root, "diff", "--name-only", "-z", "--no-renames", "--"),
        _git(root, "ls-files", "--others", "--exclude-standard", "-z"),
    )
    return tuple(sorted({path for output in outputs for path in output.split("\0") if path}))


def _checked_python(path: str) -> bool:
    parts = Path(path).parts
    return (
        path.endswith(".py")
        and parts[0] in {"src", "tests", "tools"}
        and not (path.startswith("src/skm/") and "generated" in parts)
        and not path.startswith(("tests/architecture/fixtures/", "tests/fixtures/plugins/"))
    )


def check_commands(root: Path, paths: Sequence[str]) -> list[tuple[str, ...]]:
    """Choose existing checks; deleted/generated files still trigger structural validation."""
    if not paths:
        return []
    full_static = bool(_CONFIG.intersection(paths))
    python = tuple(path for path in paths if _checked_python(path) and (root / path).is_file())
    commands: list[tuple[str, ...]] = []
    if python or full_static:
        targets = ("src", "tests", "tools") if full_static else python
        commands.extend(((*_UV, "ruff", "check", *targets), (*_UV, "ruff", "format", "--check", *targets)))
        if full_static:
            commands.append((*_UV, "pyright"))
            commands.append((*_UV, "pyright", "--project", "tools/pyrightconfig.json"))
        else:
            code = tuple(path for path in python if not path.startswith("tools/"))
            scripts = tuple(path for path in python if path.startswith("tools/"))
            if code:
                commands.append((*_UV, "pyright", *code))
            if scripts:
                commands.append((*_UV, "pyright", "--project", "tools/pyrightconfig.json", *scripts))
    if full_static or any(
        path.startswith(("src/skm/", "tests/architecture/", "docs/architecture/contracts")) for path in paths
    ):
        # One worker keeps this scoped command usable alongside another active worktree.
        commands.append((*_UV, "pytest", "-q", "-n", "0", "tests/architecture"))
    if full_static or any(
        path.startswith(("src/skm/schemas/", "src/skm/entrypoints/cli/", "tools/codegen/", "tools/schema_"))
        or (path.startswith("src/skm/") and "generated" in Path(path).parts)
        or path in {"tools/gen.py", "docs/reference/cli.md"}
        for path in paths
    ):
        commands.append((*_UV, "python", "tools/schema_check.py"))
    if full_static or any(
        path.startswith("src/skm/adapters/postgres/migrations/") or path == "tools/check_sql.py"
        for path in paths
    ):
        commands.append((*_UV, "python", "tools/check_sql.py"))
    if full_static or any(
        ("/skills/" in path and path.endswith(("manifest.toml", "SKILL.md")))
        or path == "tools/check_skills.py"
        for path in paths
    ):
        commands.append((*_UV, "python", "tools/check_skills.py"))
    if full_static or any(
        (path.startswith(("src/skm/", "tests/")) and path.endswith(".py"))
        or path in {"tools/source_index.py", "docs/reference/source-index.md"}
        for path in paths
    ):
        # Package docstrings, entrypoint files and importing tests feed the generated navigation page.
        commands.append((*_UV, "python", "tools/source_index.py", "--check"))
    # A deleted/renamed code file can break a link in an otherwise unchanged document.
    markdown = tuple(
        path
        for path in paths
        if path.endswith(".md")
        and not path.startswith("docs/")
        and path not in {"README.md", "AGENTS.md"}
        and (root / path).is_file()
    )
    commands.append((*_UV, "python", "tools/check_links.py", "docs", "README.md", "AGENTS.md", *markdown))
    return commands


def affected_tests_command(root: Path, paths: Sequence[str]) -> tuple[str, ...] | None:
    """A command listing tests that import the changed product modules; a hint, never run as a check."""
    product = tuple(
        path
        for path in paths
        if path.startswith("src/skm/") and path.endswith(".py") and (root / path).is_file()
    )
    return (*_UV, "python", "tools/source_index.py", "--tests", *product) if product else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD", help="compare committed changes from merge-base with REF")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the selected checks without running them"
    )
    args = parser.parse_args(argv)
    try:
        paths = changed_paths(ROOT, args.base)
    except (OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"cannot determine changed files: {error}\n")
    if not paths:
        print(f"No changed files relative to {args.base}; no checks ran.")
        return 0
    print(f"Preflight: {len(paths)} changed paths (including deletions).", flush=True)
    for command in check_commands(ROOT, paths):
        print(f"+ {shlex.join(command)}", flush=True)
        if not args.dry_run:
            try:
                result = subprocess.run(command, cwd=ROOT, check=False)
            except OSError as error:
                parser.exit(2, f"cannot run check: {error}\n")
            if result.returncode:
                print(f"Preflight failed: exit {result.returncode}.")
                return 1
    print("Dry run only; no checks ran." if args.dry_run else "Selected preflight checks passed.")
    print("Still run affected unit/contract tests and any required PostgreSQL/e2e checks.")
    hint = affected_tests_command(ROOT, paths)
    if hint is not None:
        print(f"Tests importing the changed product modules: {shlex.join(hint)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
