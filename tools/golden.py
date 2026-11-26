"""Check golden references or explicitly regenerate expectations with pytest."""

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root: Path) -> int:
    tests = root / "tests"
    golden = tests / "golden"
    references: set[tuple[str, str]] = set()
    # AST accepts the documented literal pair regardless of quote style/line breaks.
    for source in tests.rglob("test_*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"), filename=str(source))):
            if not isinstance(node, ast.Call):
                continue
            values = [
                value.value
                for value in node.args[:2]
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
            if len(values) == 2:
                references.add((values[0], values[1]))
    errors: list[str] = []
    for fixture in sorted(golden.rglob("*")):
        if (
            not fixture.is_file()
            or fixture.name.endswith(".source.txt")
            or fixture.suffix not in {".json", ".txt"}
        ):
            continue
        relative = fixture.relative_to(golden).with_suffix("").as_posix()
        if not any(f"{suite}/{case}" == relative for suite, case in references):
            errors.append(f"orphan golden: {fixture.relative_to(root)}")
    # Legacy imports are explicitly located here or marked by a source sidecar.
    legacy = tests / "fixtures" / "legacy"
    derived = {
        p
        for p in legacy.rglob("*")
        if p.is_file() and p.suffix in {".json", ".txt", ".jsonl"} and not p.name.endswith(".source.txt")
    }
    errors.extend(
        f"legacy fixture needs provenance: {fixture.relative_to(root)}"
        for fixture in sorted(derived)
        if not fixture.with_suffix(".source.txt").is_file()
    )
    for base in (golden, legacy):
        for source in sorted(base.rglob("*.source.txt")):
            text = source.read_text(encoding="utf-8")
            if not re.search(r"(?m)^source:[ \t]*[^ \t\r\n][^\r\n]*$", text) or not re.search(
                r"(?m)^commit:[ \t]*[0-9a-fA-F]{7,40}[ \t]*$", text
            ):
                errors.append(f"legacy provenance needs source path and commit: {source.relative_to(root)}")
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="reject orphan goldens and missing legacy provenance")
    update = commands.add_parser("update", help="explicitly update goldens; affected tests report XFAIL")
    update.add_argument("pattern", help="pytest -k expression")
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(ROOT)
    env = {**os.environ, "SKM_GOLDEN_UPDATE": "1"}
    print(
        "GOLDEN UPDATE: affected tests report XFAIL; inspect and explain every changed fixture.", flush=True
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-k", args.pattern], cwd=ROOT, env=env, check=False
    )
    git = shutil.which("git")
    if git is None:
        print("git is required to inspect golden updates", file=sys.stderr)
        return result.returncode or 1
    diff = subprocess.run([git, "diff", "--stat", "--", "tests/golden"], cwd=ROOT, check=False)
    return result.returncode or diff.returncode


if __name__ == "__main__":
    raise SystemExit(main())
