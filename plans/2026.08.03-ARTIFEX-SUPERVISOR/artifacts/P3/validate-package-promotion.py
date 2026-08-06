#!/usr/bin/env python3
"""Validate the immutable prototype-to-package G1 promotion baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


STAGE1 = "40781d376a1ee489d61e8ff3ce93fbdb751b2f9f"
PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
GENERATION_SCHEMA = "artifex-business-successor-generation-v1"
GENERATION_KEYS = {"schema_version", "generation_version", "predecessor", "successor", "generation_hash"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
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


def canonical_hash(value: Any, *, omit: str | None = None) -> str:
    body = {key: item for key, item in value.items() if key != omit} if isinstance(value, dict) and omit else value
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_package_generation(root: Path, generation_path: Path) -> None:
    """D129, same helper shape as `validate-shadow.py`'s (1a): the live half must
    not vanish. The current package is asserted against the sole G2B digest in
    `business-successor-generation-v1.json`; the frozen G1 predecessor pin below
    stays a Git-blob comparison against the manifest's own frozen snapshot."""
    generation = load(generation_path)
    if (set(generation) != GENERATION_KEYS
            or generation.get("schema_version") != GENERATION_SCHEMA
            or generation.get("generation_version") != "1.0.0"):
        raise ValueError("G2B generation closed schema")
    if generation.get("generation_hash") != canonical_hash(generation, omit="generation_hash"):
        raise ValueError("G2B generation hash")
    predecessor = generation.get("predecessor", {})
    successor = generation.get("successor", {})
    if predecessor.get("generation") != "G2" or successor.get("generation") != "G2B":
        raise ValueError("G2B generation lineage")
    g2_digest = predecessor.get("digest")
    if not isinstance(g2_digest, str) or not HEX64.fullmatch(g2_digest):
        raise ValueError("G2 predecessor digest")
    rows = successor.get("package_files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("G2B package rows")
    for row in rows:
        path = root / row["path"]
        if not path.is_file() or sha256(path) != row["sha256"]:
            raise ValueError(f"current package differs from G2B: {row['path']}")


def validate(root: Path, package: Path, manifest: dict, manifest_path: Path,
             historical: str | None, generation_path: Path) -> None:
    if set(manifest) != {"schema_version", "generation", "source_map", "closed_package_files"} or manifest["schema_version"] != "artifex-package-promotion-v1":
        raise ValueError("manifest shape")
    stage_files = set(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", STAGE1).splitlines())
    if stage_files != STAGE1_FILES:
        raise ValueError("stage-1 D95 file set")
    if git(root, "merge-base", "--is-ancestor", STAGE1, "HEAD") != "":
        raise ValueError("stage-1 commit is not reachable")
    text = "\n".join(path.read_text(encoding="utf-8") for path in (package / "lib").rglob("*.py"))
    if "plans/" in text or "artifacts/supervisor" in text:
        raise ValueError("plan-local runtime import")
    # D129 — the manifest is FROZEN at the single commit that ever changed it:
    # resolved at run time here, never hard-coded; `--historical-commit` stays an
    # explicit override for the historical replays that already pass it. G1 is
    # current only at P3.8 close — once a successor starts (D89/D118/D119), the
    # frozen side is always proven against Git blobs at that resolved commit,
    # never against a live-tree file-content comparison.
    frozen_commit = historical or git(root, "log", "-1", "--format=%H", "--", manifest_path.relative_to(root).as_posix())
    if not frozen_commit:
        raise ValueError("frozen manifest anchor unresolved")
    head = git(root, "rev-parse", "HEAD")
    if frozen_commit == "HEAD" or git(root, "rev-parse", frozen_commit) == head:
        raise ValueError("historical baseline cannot be the current tree")
    for row in manifest["closed_package_files"]:
        blob = subprocess.run(["git", "show", f"{frozen_commit}:{row['path']}"], cwd=root, capture_output=True, check=False)
        if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != row["sha256"]:
            raise ValueError("historical package blob mismatch")
    # D129 — the live half would otherwise be asserted against nothing (the old
    # `--historical-commit` branch skipped the current-tree comparison entirely).
    validate_package_generation(root, generation_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--prototype", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--historical-commit")
    parser.add_argument("--generation", type=Path,
                        help="G2B generation manifest; defaults to the frozen P5 one")
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
        generation_path = args.generation or (
            root / "plans" / PLAN_ID / "artifacts" / "P5" / "business-successor-generation-v1.json")
        validate(root, package, load(args.manifest), args.manifest.resolve(),
                 args.historical_commit, generation_path)
        print("package promotion validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"package promotion validator: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
