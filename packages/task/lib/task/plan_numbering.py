"""Next plan identity: day ordinal `№N` and repository-wide `PLAN<N>` Short ID.

The two numbers have different scopes and an agent cannot guess either one:

* `№N` in `YYYY.MM.DD-№N-CODENAME` is unique within its date, across live and archived plans;
* `Short ID | PLAN<N>` in plan Meta is the next free number above the maximum in the repository,
  across live and archived plans, and is never recycled.

Stdlib only; read-only. Re-run right before writing the plan, concurrent allocations are
reconciled by `plan-lint` (Short ID collisions across live/archive siblings).
"""
from __future__ import annotations

import argparse
from datetime import date as _date
import json
from pathlib import Path
import re
import sys

ARCHIVE = "archive"
_DIR_ID = re.compile(r"^(?P<date>\d{4}\.\d{2}\.\d{2})-№(?P<ordinal>[1-9][0-9]*)-(?P<codename>[A-Z][A-Z0-9-]*)$")
_DATE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
_CODENAME = re.compile(r"^[A-Z][A-Z0-9-]*$")
_SHORT_ROW = re.compile(r"^\s*\|\s*Short ID\s*\|\s*(PLAN[1-9][0-9]*)\s*\|\s*$")


class NumberingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def find_plans_root(start: str | Path | None = None) -> Path:
    """Nearest `plans/` at or above `start`; `<start>/plans` (maybe absent) when none exists."""
    base = Path(start or Path.cwd()).resolve()
    for candidate in (base, *base.parents):
        if (candidate / "plans").is_dir():
            return candidate / "plans"
        if candidate.name == "plans" and candidate.is_dir():
            return candidate
    return base / "plans"


def _short_id(plan_md: Path) -> int | None:
    try:
        lines = plan_md.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines[:60]:  # Meta is the first table of plan.md
        match = _SHORT_ROW.match(line)
        if match:
            return int(match.group(1)[4:])
    return None


def scan(plans_root: str | Path) -> list[dict]:
    """One row per distinct plan directory name in `plans/` and `plans/archive/`."""
    root = Path(plans_root)
    rows: dict[str, dict] = {}
    for parent in (root, root / ARCHIVE):
        if not parent.is_dir():
            continue
        for path in sorted(parent.iterdir()):
            if not path.is_dir() or path.name == ARCHIVE or path.name.startswith("."):
                continue
            row = rows.setdefault(path.name, {"id": path.name, "short_id": None})
            if row["short_id"] is None:
                row["short_id"] = _short_id(path / "plan.md")
    return list(rows.values())


def next_identity(plans_root: str | Path, *, date: str | None = None,
                  codename: str | None = None) -> dict:
    date = date or _date.today().strftime("%Y.%m.%d")
    if not _DATE.fullmatch(date):
        raise NumberingError("PLAN_NUMBER_DATE_INVALID", f"expected YYYY.MM.DD, received {date!r}")
    if codename is not None and not _CODENAME.fullmatch(codename):
        raise NumberingError("PLAN_NUMBER_CODENAME_INVALID",
                             f"view code name [A-Z][A-Z0-9-]*, received {codename!r}")
    rows = scan(plans_root)
    ordinals = [int(m["ordinal"]) for row in rows
                if (m := _DIR_ID.match(row["id"])) and m["date"] == date]
    shorts = [row["short_id"] for row in rows if row["short_id"] is not None]
    ordinal = max(ordinals, default=0) + 1
    short_number = max(shorts, default=0) + 1
    plan_id = f"{date}-№{ordinal}-{codename}" if codename else None
    if plan_id and any(row["id"] == plan_id for row in rows):
        raise NumberingError("PLAN_NUMBER_COLLISION", f"plan {plan_id} already exists")
    return {
        "plan_id": plan_id,
        "date": date,
        "ordinal": ordinal,
        "short_id": f"PLAN{short_number}",
        "title_prefix": f"Plan №{ordinal} —",
        "plans_root": str(Path(plans_root)),
        "scanned": {"plans": len(rows), "with_short_id": len(shorts),
                    "max_short_id": max(shorts, default=0),
                    "max_ordinal_on_date": max(ordinals, default=0)},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Next plan number: daily №N and repository Short ID PLAN<N> "
                    "on live and archived plans (read-only).")
    parser.add_argument("--plans-root", type=Path, help="directory plans/ (default nearest up from cwd)")
    parser.add_argument("--date", help="YYYY.MM.DD (default today)")
    parser.add_argument("--codename", help="CODE-NAME [A-Z][A-Z0-9-]*; gives ready plan_id")
    args = parser.parse_args(argv)
    try:
        result = next_identity(args.plans_root or find_plans_root(), date=args.date,
                               codename=args.codename)
    except NumberingError as exc:
        print(json.dumps({"error": exc.code, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
