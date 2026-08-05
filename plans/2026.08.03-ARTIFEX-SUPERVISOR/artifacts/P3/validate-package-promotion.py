#!/usr/bin/env python3
"""Validate the immutable prototype-to-package G1 promotion baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


STAGE1 = "40781d376a1ee489d61e8ff3ce93fbdb751b2f9f"
PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
STAGE1_FILES = {
    ".swissknifeman/provider-artifacts.lock.json", "packages/artifex/AGENTS.md", "packages/artifex/CLAUDE.md",
    "packages/harness/configs/common/instructions/catalog.json", "packages/harness/configs/common/instructions/packages/artifex/claude-code.md",
    "packages/harness/configs/common/instructions/packages/artifex/codex.md", "packages/harness/configs/common/instructions/packages/artifex/common.md",
    "packages/harness/lib/harness/instructions.py", "packages/harness/tests/fixtures_data/instruction-compatibility-v1.json",
    "packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json", "packages/harness/tests/test_instruction_compatibility.py",
    "packages/harness/tests/test_instruction_size_gate.py", "packages/harness/tests/test_provider_instructions.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest object required")
    return value


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def source_rows(root: Path, package: Path) -> list[dict[str, str]]:
    prototype = root / "plans" / PLAN_ID / "artifacts" / "supervisor"
    pairs: list[tuple[Path, Path]] = []
    for source in sorted((prototype / "artifex").rglob("*.py")):
        pairs.append((source, package / "lib" / "artifex" / source.relative_to(prototype / "artifex")))
    for source in sorted((prototype / "tests").glob("*.py")):
        pairs.append((source, package / "tests" / source.name))
    return [{"source": source.relative_to(root).as_posix(), "package": successor.relative_to(root).as_posix(),
             "source_sha256": sha256(source), "package_sha256": sha256(successor)} for source, successor in pairs]


def closed_rows(root: Path, package: Path) -> list[dict[str, str]]:
    keep = [package / "README.md", package / "bin" / "artifex", package / "scripts" / "test.sh", package / "scripts" / "validate.sh"]
    keep += sorted((package / "lib").rglob("*.py")) + sorted((package / "tests").glob("*.py"))
    return [{"path": path.relative_to(root).as_posix(), "sha256": sha256(path)} for path in keep]


def expected(root: Path, package: Path) -> dict:
    guides = {path: sha256(root / path) for path in ("packages/artifex/AGENTS.md", "packages/artifex/CLAUDE.md")}
    lock = ".swissknifeman/provider-artifacts.lock.json"
    return {"schema_version": "artifex-package-promotion-v1", "generation": {"stage1_commit": STAGE1, "lock": lock,
            "lock_sha256": sha256(root / lock), "guides": guides}, "source_map": source_rows(root, package),
            "closed_package_files": closed_rows(root, package)}


def validate(root: Path, package: Path, manifest: dict, historical: str | None) -> None:
    if set(manifest) != {"schema_version", "generation", "source_map", "closed_package_files"} or manifest["schema_version"] != "artifex-package-promotion-v1":
        raise ValueError("manifest shape")
    stage_files = set(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", STAGE1).splitlines())
    if stage_files != STAGE1_FILES:
        raise ValueError("stage-1 D95 file set")
    if git(root, "merge-base", "--is-ancestor", STAGE1, "HEAD") != "":
        raise ValueError("stage-1 commit is not reachable")
    wanted = expected(root, package)
    if manifest != wanted:
        raise ValueError("current package or source/provenance drift")
    text = "\n".join(path.read_text(encoding="utf-8") for path in (package / "lib").rglob("*.py"))
    if "plans/" in text or "artifacts/supervisor" in text:
        raise ValueError("plan-local runtime import")
    if historical:
        head = git(root, "rev-parse", "HEAD")
        if historical == "HEAD" or git(root, "rev-parse", historical) == head:
            raise ValueError("historical baseline cannot be the current tree")
        for row in manifest["closed_package_files"]:
            blob = subprocess.run(["git", "show", f"{historical}:{row['path']}"], cwd=root, capture_output=True, check=False)
            if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != row["sha256"]:
                raise ValueError("historical package blob mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--prototype", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--historical-commit")
    args = parser.parse_args(argv)
    package = args.package.resolve(strict=True)
    root = package.parents[1]
    if args.prototype.resolve(strict=True) != root / "plans" / PLAN_ID / "artifacts" / "P3" / "adapter-manifest-v1.json":
        raise ValueError("prototype anchor mismatch")
    value = expected(root, package)
    if args.write:
        args.manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("package promotion manifest: written")
    else:
        validate(root, package, load(args.manifest), args.historical_commit)
        print("package promotion validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"package promotion validator: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
