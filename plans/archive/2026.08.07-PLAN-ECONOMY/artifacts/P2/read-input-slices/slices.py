#!/usr/bin/env python3
"""Generate and verify bounded, content-preserving read-input slices.

The manifest is an evidence carrier: every source is partitioned in byte order,
so consumers can read a bounded named slice while the verifier can reassemble
the original bytes and prove both source and slice hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
MANIFEST = OUT / "manifest.json"
MAX_BYTES = 60_000
SOURCES = (
    Path("packages/skiller/skills/general/plan-protocol/SKILL.md"),
    Path("plans/2026.08.07-PLAN-ECONOMY/findings/13-design-audit-2026-08-07.md"),
    Path("plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md"),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def partition(data: bytes):
    lines = data.splitlines(keepends=True)
    chunks, current, start = [], [], 1
    size = 0
    for line_no, line in enumerate(lines, start=1):
        if current and size + len(line) > MAX_BYTES:
            chunks.append((start, line_no - 1, b"".join(current)))
            current, size, start = [], 0, line_no
        current.append(line)
        size += len(line)
    if current:
        chunks.append((start, len(lines), b"".join(current)))
    return chunks


def generate() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.slice.md"):
        old.unlink()
    records = []
    for source in SOURCES:
        data = (ROOT / source).read_bytes()
        parts = []
        for index, (start, end, chunk) in enumerate(partition(data), start=1):
            name = f"{source.stem}-{index:02d}-L{start}-L{end}.slice.md"
            (OUT / name).write_bytes(chunk)
            parts.append({"path": name, "line_start": start, "line_end": end,
                          "bytes": len(chunk), "sha256": sha(chunk)})
        records.append({"source": str(source), "source_sha256": sha(data),
                        "source_bytes": len(data), "slices": parts})
    payload = {"schema": "read-input-slices-v1", "max_slice_bytes": MAX_BYTES,
               "sources": records}
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def verify() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for record in manifest["sources"]:
        source = (ROOT / record["source"]).read_bytes()
        parts = []
        for part in record["slices"]:
            data = (OUT / part["path"]).read_bytes()
            assert len(data) == part["bytes"] and sha(data) == part["sha256"], part["path"]
            assert len(data) <= manifest["max_slice_bytes"], part["path"]
            parts.append(data)
        assert sha(source) == record["source_sha256"], record["source"]
        assert b"".join(parts) == source, record["source"]
    print("HASHES-OK")
    print("REASSEMBLY-OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "verify"))
    args = parser.parse_args()
    if args.command == "generate":
        generate()
    else:
        verify()


if __name__ == "__main__":
    main()
