#!/usr/bin/env python3
"""Validate an explicitly supplied registry snapshot and atomically refresh its copy."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path("core/locale/data/language-subtag-registry.txt"))
    parser.add_argument("--provenance", type=Path, default=Path("core/locale/data/upstream.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = args.source.read_bytes()
    if not data.startswith(b"File-Date: ") or b"\n%%\n" not in data:
        raise SystemExit("invalid IANA registry structure")
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    digest = hashlib.sha256(data).hexdigest()
    if (provenance.get("file_date") != data.splitlines()[0].decode().removeprefix("File-Date: ")
            or provenance.get("sha256") != digest or provenance.get("bytes") != len(data)):
        raise SystemExit("source does not match reviewed provenance")
    if args.check:
        if not args.target.is_file() or args.target.read_bytes() != data:
            raise SystemExit("target differs from reviewed source")
        return 0
    args.target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.target.parent, delete=False) as handle:
        handle.write(data); temporary = Path(handle.name)
    temporary.replace(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
