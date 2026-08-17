#!/usr/bin/env python3
"""Verify P7.1's exact evidence members without reading provider transcripts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXCLUDED = ("raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    root = Path(args.bundle_root)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    privacy = manifest.get("privacy", {})
    if privacy.get("minimized") is not True or privacy.get("excluded_classes") != list(EXCLUDED):
        raise ValueError("privacy declaration mismatch")
    expected = sorted(manifest.get("files", []))
    actual = sorted(path.name for path in root.iterdir() if path.is_file() and path.name not in {"manifest.json", "verify.py"})
    if actual != expected:
        raise ValueError("bundle members are not exact")
    forbidden_markers = ("BEGIN PRIVATE KEY", "api_key", "authorization: bearer")
    for name in expected:
        text = (root / name).read_text(encoding="utf-8")
        if any(marker.lower() in text.lower() for marker in forbidden_markers):
            raise ValueError(f"privacy marker in {name}")
    acceptance = json.loads((root / "acceptance-results.json").read_text(encoding="utf-8"))
    if acceptance.get("deferred", {}).get("decision") != "D88":
        raise ValueError("D88 deferred-boundary declaration is missing")
    blockers = json.loads((root / "release-blockers.json").read_text(encoding="utf-8"))
    if blockers.get("package_blockers") != acceptance.get("required_release_blockers"):
        raise ValueError("package blocker projection mismatch")
    print("P7.1 evidence verifier: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P7.1 evidence verifier: {exc}", file=sys.stderr)
        raise SystemExit(2)
