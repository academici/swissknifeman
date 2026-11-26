"""Explicit golden comparisons, readable diffs and legacy provenance."""

import difflib
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden"
UPDATE = False  # Runner control captured before host environment isolation.


def golden_path(suite: str, case: str, extension: str) -> Path:
    for part in (suite, case):
        if not part or Path(part).is_absolute() or any(p in {"..", "."} for p in part.split("/")):
            raise ValueError("golden suite and case must be relative paths without traversal")
    target = GOLDEN_ROOT / suite / f"{case}.{extension}"
    if not target.resolve().is_relative_to(GOLDEN_ROOT.resolve()):
        raise ValueError("golden path escapes the golden directory")
    return target


def assert_legacy_source(fixture: Path) -> str:
    """Validate provenance beside an explicitly legacy-derived fixture.

    Require a donor-relative source and a commit. Verify snapshot bytes when recorded.
    Never import the donor or invent a revision when updating expected output.
    """
    provenance = fixture.with_suffix(".source.txt")
    if not provenance.is_file():
        raise AssertionError(f"legacy fixture needs provenance: {provenance}")
    source = provenance.read_text(encoding="utf-8")
    snapshot = re.search(r"(?m)^snapshot-sha256:[ \t]*([0-9a-f]{64})[ \t]*$", source)
    has_commit = re.search(r"(?m)^commit:[ \t]*[0-9a-fA-F]{7,40}[ \t]*$", source)
    if not re.search(r"(?m)^source:[ \t]*[^ \t\r\n][^\r\n]*$", source) or not has_commit:
        raise AssertionError(f"legacy provenance needs source path and commit: {provenance}")
    if snapshot and hashlib.sha256(fixture.read_bytes()).hexdigest() != snapshot[1]:
        raise AssertionError(f"legacy fixture does not match snapshot-sha256: {fixture}")
    return source


def assert_golden(suite: str, case: str, actual: str | JsonValue) -> None:
    text = (
        actual
        if isinstance(actual, str)
        else json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    target = golden_path(suite, case, "txt" if isinstance(actual, str) else "json")
    provenance = target.with_suffix(".source.txt")
    if provenance.exists():
        assert_legacy_source(target)
    if UPDATE or os.environ.get("SKM_GOLDEN_UPDATE") == "1":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        # Dynamic xfail is non-strict even though ordinary xfails are strict.
        pytest.xfail(f"golden updated: {target}; inspect and explain the diff")
    if not target.is_file():
        raise AssertionError(f"missing golden: {target}; explicitly run tools/golden.py update <pattern>")
    expected = target.read_bytes().decode("utf-8")
    if expected != text:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=str(target),
                tofile="actual",
            )
        )
        raise AssertionError(f"golden mismatch:\n{diff}")
