#!/usr/bin/env python3
"""Keep the generated Python types in step with the contract schemas.

    schema-types.py --check | --write [--repo DIR] [--registry FILE]

``configs/schema-types.json`` lists targets ``{root, out}``: the schema directory and the module that
``aicore schema codegen`` generates from it. ``--write`` regenerates every ``out``; ``--check`` writes nothing and
exits 1 (``SCHEMA_CODEGEN_DRIFT: <out>``) for every module that differs from its schemas, 2 on a bad registry.
The generator runs in process (``packages/aicore/lib`` is put on the path); ``bin/aicore`` is not executed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
REGISTRY = "configs/schema-types.json"


def load_registry(repo: Path, registry: Path) -> list:
    try:
        document = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"SCHEMA_TYPES_REGISTRY: cannot read {registry}: {exc}") from None
    targets = document.get("targets") if isinstance(document, dict) else None
    if not isinstance(document, dict) or document.get("version") != 1 or not isinstance(targets, list) or not targets:
        raise SystemExit(f"SCHEMA_TYPES_REGISTRY: {registry} must be {{version: 1, targets: [..]}}")
    seen: set = set()
    for target in targets:
        if not (isinstance(target, dict) and isinstance(target.get("root"), str)
                and isinstance(target.get("out"), str)):
            raise SystemExit(f"SCHEMA_TYPES_REGISTRY: {registry}: every target needs string root and out")
        if target["out"] in seen:
            raise SystemExit(f"SCHEMA_TYPES_REGISTRY: {registry}: out {target['out']} is listed twice")
        seen.add(target["out"])
        if not (repo / target["root"]).is_dir():
            raise SystemExit(f"SCHEMA_TYPES_REGISTRY: {registry}: root {target['root']} is not a directory")
    return targets


def run(repo: Path, registry: Path, check: bool) -> int:
    sys.path.insert(0, str(HUB / "packages" / "aicore" / "lib"))
    from aicore.util import schemacodegen

    status = 0
    for target in load_registry(repo, registry):
        argv = ["--root", target["root"], "--out", target["out"]] + (["--check"] if check else [])
        code = schemacodegen.main(argv, cwd=repo, out=sys.stdout, err=sys.stderr)
        status = max(status, code)
    return status


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail when a generated module differs from its schemas")
    mode.add_argument("--write", action="store_true", help="regenerate every module of the registry")
    parser.add_argument("--repo", default=str(HUB), help="repository root (default: this repository)")
    parser.add_argument("--registry", help=f"registry file (default: <repo>/{REGISTRY})")
    options = parser.parse_args(argv)
    repo = Path(options.repo).resolve()
    registry = Path(options.registry) if options.registry else repo / REGISTRY
    return run(repo, registry, options.check)


if __name__ == "__main__":
    sys.exit(main())
