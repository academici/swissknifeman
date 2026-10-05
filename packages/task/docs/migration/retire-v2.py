#!/usr/bin/env python3
"""Remove verified legacy active carriers after a successful JSON import.

This is deliberately a migration-only tool.  It accepts only the exact files
recorded by ``legacy-v2.py`` and refuses to remove anything whose SHA-256 has
changed since conversion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("--source-map", required=True, type=Path)
    args = parser.parse_args()

    plan = args.plan.expanduser().resolve()
    source_map = json.loads(args.source_map.read_text(encoding="utf-8"))
    recorded_plan = Path(source_map["source_path"]).expanduser().resolve()
    if plan != recorded_plan:
        raise SystemExit(f"plan mismatch: {plan} != {recorded_plan}")
    if not (plan / "plan.json").is_file():
        raise SystemExit("refusing to retire sources before plan.json exists")

    hashes: dict[str, str] = source_map["source_files"]
    retire: list[str] = source_map["retire_files"]
    if len(retire) != len(set(retire)):
        raise SystemExit("duplicate retire path")

    resolved: list[tuple[str, Path]] = []
    errors: list[str] = []
    for relative in retire:
        candidate = (plan / relative).resolve()
        if candidate == plan or plan not in candidate.parents:
            errors.append(f"unsafe path: {relative}")
            continue
        if relative.startswith("views/") or relative.endswith(".json"):
            errors.append(f"refusing generated/current carrier: {relative}")
            continue
        if relative not in hashes:
            errors.append(f"missing source hash: {relative}")
            continue
        if not candidate.is_file():
            errors.append(f"missing source file: {relative}")
            continue
        actual = sha256(candidate)
        if actual != hashes[relative]:
            errors.append(f"changed source file: {relative}: {actual} != {hashes[relative]}")
            continue
        resolved.append((relative, candidate))
    if errors:
        raise SystemExit("source verification failed:\n" + "\n".join(errors))

    for _relative, candidate in resolved:
        candidate.unlink()

    for directory in sorted(
        (path for path in plan.rglob("*") if path.is_dir() and path != plan / "views"),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass

    print(json.dumps({"plan": str(plan), "retired": len(resolved)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
