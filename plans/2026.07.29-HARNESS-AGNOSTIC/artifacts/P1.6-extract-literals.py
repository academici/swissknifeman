#!/usr/bin/env python3
"""Extract the 105 mandatory literals from research/05 §2 and write the D76 coverage
fixture. Re-running this script must reproduce `instruction-literal-coverage-v1.json`
byte-for-byte (2026.07.29-HARNESS-AGNOSTIC P1.6, provenance narrowed to §2 — P2.6/D81)."""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages/harness/lib"))
sys.path.insert(0, str(REPO_ROOT))

from harness.instructions import literal_coverage_section  # noqa: E402

MATRIX_PATH = REPO_ROOT / "plans/2026.07.29-HARNESS-AGNOSTIC/research/05-instruction-canon-routing.md"
FIXTURE_PATH = (REPO_ROOT
                / "packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json")
SOURCE_SECTION = "## 2. Матрица покрытия"
SOURCE_HASH_SCOPE = "section"
FIXTURE_VERSION = "1.1.2"
OWNER_DECISION = "2026.07.29-HARNESS-AGNOSTIC D76"
CATALOG_VERSION_AT_CAPTURE = "1.1.1"

_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_BACKTICK_WRAP = re.compile(r"^(`{1,2})(.*)\1$", re.DOTALL)
_HOME_PREFIX = re.compile(r"^(ID|NEW|EXT)\s+(.+)$")


def _unwrap_backticks(cell: str) -> str:
    match = _BACKTICK_WRAP.match(cell)
    unwrapped = match.group(2) if match else cell
    return unwrapped.strip()


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [part.strip().replace("\\|", "|") for part in _CELL_SPLIT.split(body)]


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells)


def extract_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) != 5:
            continue
        if cells[0] == "Источник (файл · раздел)" or _is_separator(cells):
            continue
        rows.append(cells)
    return rows


def extract_literals(rows: list[list[str]]) -> list[dict]:
    literals = []
    seen: set[tuple[str, str]] = set()
    for source, rule, home, rationale, literal_cell in rows:
        literal = _unwrap_backticks(literal_cell.strip())
        if literal in ("", "—"):
            continue
        home_text = _unwrap_backticks(home.strip())
        match = _HOME_PREFIX.match(home_text)
        if not match:
            continue
        semantic_id = match.group(2).strip()
        key = (semantic_id, literal)
        if key in seen:
            # Same rule reasserted verbatim in another package's subtable (e.g.
            # root.docs-build repeated across skiller/harness/maind) — one home,
            # one obligation, checking it twice adds nothing.
            continue
        seen.add(key)
        literals.append({"semantic_id": semantic_id, "literal": literal})
    return literals


def build_fixture(section: str, rows: list[list[str]], literals: list[dict]) -> dict:
    return {
        "contract_version": "1.0.0",
        "fixture_version": FIXTURE_VERSION,
        "provenance": {
            "source": "plans/2026.07.29-HARNESS-AGNOSTIC/research/05-instruction-canon-routing.md",
            "source_section": SOURCE_SECTION,
            "source_sha256": hashlib.sha256(section.encode("utf-8")).hexdigest(),
            "source_hash_scope": SOURCE_HASH_SCOPE,
            "generator": "plans/2026.07.29-HARNESS-AGNOSTIC/artifacts/P1.6-extract-literals.py",
            "owner_decision": OWNER_DECISION,
            "row_count": len(rows),
            "literal_count": len(literals),
            "catalog_version_at_capture": CATALOG_VERSION_AT_CAPTURE,
        },
        "literals": literals,
    }


def main() -> int:
    raw = MATRIX_PATH.read_bytes()
    text = raw.decode("utf-8")
    section = literal_coverage_section(text, SOURCE_SECTION)
    if section is None:
        raise ValueError(f"section {SOURCE_SECTION!r} not found in {MATRIX_PATH}")
    rows = extract_rows(section)
    literals = extract_literals(rows)
    fixture = build_fixture(section, rows, literals)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print(f"rows={len(rows)} literals={len(literals)} -> {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
