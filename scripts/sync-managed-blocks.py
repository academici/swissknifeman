#!/usr/bin/env python3
"""Managed blocks: a canonical text is exported from its owner and copied into target files.

Source marks an exported fragment:
    <!-- export:begin <anchor> -->
    ...text...
    <!-- export:end <anchor> -->
Target holds a generated copy (the block is created once by hand, then only `--write` touches it):
    <!-- managed:begin id=<id> source=<repo-path>#<anchor> sha256=<64hex> -->
    ...the exported text, unchanged...
    <!-- managed:end id=<id> -->

sha256 is taken over the exported text (UTF-8, `\\n`-normalized, without the marker lines).
Config: configs/managed-blocks.json {"version": 1, "blocks": [{id, source, anchor, target}]}.

  --check   DRIFT/MISSING/ERROR lines and exit 1 on any mismatch; `managed-blocks: OK` and exit 0 otherwise
  --write   rewrite only the content between managed:begin/end (and the sha256 in the header);
            nothing is written when any block is MISSING/ERROR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

CONFIG_REL = "configs/managed-blocks.json"
NAME = r"[A-Za-z0-9._-]+"
EXPORT_BEGIN = re.compile(rf"^<!-- export:begin ({NAME}) -->$")
EXPORT_END = re.compile(rf"^<!-- export:end ({NAME}) -->$")
MANAGED_BEGIN = re.compile(r"^<!-- managed:begin id=(\S+)(?:\s.*)? -->$")


class BlockError(Exception):
    """A block cannot be checked/written; `kind` is the report keyword (MISSING or ERROR)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path, what: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise BlockError("MISSING", f"{what} file not found: {path}") from None
    except UnicodeDecodeError:
        raise BlockError("ERROR", f"{what} file is not UTF-8: {path}") from None


def find_single(lines: list[str], match, what: str) -> int | None:
    """Index of the only line for which `match(line)` is true; None when absent."""
    found = [i for i, line in enumerate(lines) if match(line.rstrip("\r"))]
    if len(found) > 1:
        raise BlockError("ERROR", f"{what} occurs {len(found)} times")
    return found[0] if found else None


def exported_text(source: Path, anchor: str) -> str:
    lines = read_text(source, "source").split("\n")
    begin = find_single(lines, lambda s: s == f"<!-- export:begin {anchor} -->", f"export:begin {anchor}")
    end = find_single(lines, lambda s: s == f"<!-- export:end {anchor} -->", f"export:end {anchor}")
    if begin is None or end is None or end < begin:
        raise BlockError("MISSING", f"export markers for anchor '{anchor}' not found in {source}")
    return "\n".join(line.rstrip("\r") for line in lines[begin + 1 : end])


def locate_block(lines: list[str], block_id: str, target: Path) -> tuple[int, int]:
    begin = find_single(
        lines,
        lambda s: (m := MANAGED_BEGIN.match(s)) is not None and m.group(1) == block_id,
        f"managed:begin id={block_id}",
    )
    end = find_single(lines, lambda s: s == f"<!-- managed:end id={block_id} -->", f"managed:end id={block_id}")
    if begin is None or end is None or end < begin:
        raise BlockError("MISSING", f"managed markers for id '{block_id}' not found in {target}")
    return begin, end


def header_for(block: dict, text: str) -> str:
    return f"<!-- managed:begin id={block['id']} source={block['source']}#{block['anchor']} sha256={digest(text)} -->"


def end_marker(block: dict) -> str:
    return f"<!-- managed:end id={block['id']} -->"


def block_in_sync(lines: list[str], span: tuple[int, int], block: dict, text: str) -> bool:
    begin, end = span
    current = "\n".join(line.rstrip("\r") for line in lines[begin + 1 : end])
    return lines[begin].rstrip("\r") == header_for(block, text) and current == text


def rewrite_block(lines: list[str], span: tuple[int, int], block: dict, text: str) -> list[str]:
    begin, end = span
    cr = "\r" if lines[begin].endswith("\r") else ""
    body = text.split("\n") if text else []
    fresh = [header_for(block, text), *body, end_marker(block)]
    return lines[:begin] + [line + cr for line in fresh] + lines[end + 1 :]


def load_config(path: Path, root: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"ERROR config: not found: {path}") from None
    except (OSError, ValueError) as exc:
        raise SystemExit(f"ERROR config: cannot read {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("blocks"), list):
        raise SystemExit(f"ERROR config: {path} must be {{\"version\": 1, \"blocks\": [...]}}")
    seen: set[str] = set()
    for i, block in enumerate(data["blocks"]):
        if not isinstance(block, dict) or any(
            not isinstance(block.get(key), str) or not block[key] for key in ("id", "source", "anchor", "target")
        ):
            raise SystemExit(f"ERROR config: blocks[{i}] needs non-empty string id, source, anchor, target")
        if not re.fullmatch(NAME, block["id"]) or not re.fullmatch(NAME, block["anchor"]):
            raise SystemExit(f"ERROR config: blocks[{i}] id/anchor must match {NAME}")
        if block["id"] in seen:
            raise SystemExit(f"ERROR config: duplicate block id '{block['id']}'")
        seen.add(block["id"])
        for key in ("source", "target"):
            resolved = (root / block[key]).resolve()
            if root.resolve() not in resolved.parents:
                raise SystemExit(f"ERROR config: blocks[{i}].{key} escapes the root: {block[key]}")
    return data["blocks"]


def run(root: Path, config: Path, write: bool) -> int:
    blocks = load_config(config, root)
    problems: list[str] = []
    texts: dict[Path, list[str]] = {}
    changed: dict[Path, list[str]] = {}
    for block in blocks:
        target = root / block["target"]
        try:
            text = exported_text(root / block["source"], block["anchor"])
            lines = changed.get(target) or texts.get(target)
            if lines is None:
                lines = texts[target] = read_text(target, "target").split("\n")
            span = locate_block(lines, block["id"], target)
        except BlockError as exc:
            problems.append(f"{exc.kind} {block['id']}: {exc}")
            continue
        if block_in_sync(lines, span, block, text):
            continue
        if write:
            changed[target] = rewrite_block(lines, span, block, text)
            print(f"WRITE {block['id']}: {block['target']}")
        else:
            problems.append(f"DRIFT {block['id']}: {block['target']}")
    for line in problems:
        print(line)
    if problems:
        return 1
    for target, lines in changed.items():
        target.write_bytes("\n".join(lines).encode("utf-8"))
    print("managed-blocks: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or regenerate managed blocks copied from canonical sources.")
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument("--config", help=f"config path (default: <root>/{CONFIG_REL})")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report drift without writing")
    mode.add_argument("--write", action="store_true", help="regenerate the content of managed blocks")
    args = parser.parse_args(argv)
    root = Path(args.root)
    config = Path(args.config) if args.config else root / CONFIG_REL
    return run(root, config, write=args.write)


if __name__ == "__main__":
    sys.exit(main())
