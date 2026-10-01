"""Admission for deterministic local prerequisites declared by item Validation.

The first supported carrier is a literal ``make <target>`` command.  A definitely
missing local target is work for the current attempt, not a terminal product
result.  Dynamic makefiles remain ``unknown`` rather than producing a false
refusal.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path

from task import plan_layout


class ValidationAdmissionError(ValueError):
    pass


_MAKE_COMMAND_RE = re.compile(r"(?<![A-Za-z0-9_${])make\s+([^`;\n·]+)")
_TARGET_RE = re.compile(r"^([^#:=]+?)\s*:(?!=)")
_INCLUDE_RE = re.compile(r"^-?include\s+(.+)$")


def _repository_root(plan_dir: Path) -> Path:
    if plan_dir.parent.name == "plans":
        return plan_dir.parent.parent
    for parent in (plan_dir, *plan_dir.parents):
        if (parent / ".git").exists():
            return parent
    raise ValidationAdmissionError(f"repository root not found for {plan_dir}")


def _validation_text(plan_dir: Path, item_id: str) -> str:
    # Reuse the authoritative plan parser: multiline fields and layout-v2 state
    # merging must not acquire a second implementation here.
    from task import plan_lint

    phase_id = item_id.split(".", 1)[0]
    diagnostics = plan_lint.Diagnostics()
    phase = plan_lint.parse_phase_md(
        plan_layout.phase_path(plan_dir, phase_id), phase_id, diagnostics, layout="v2")
    occurrences = phase["items"].get(item_id) if phase else None
    if diagnostics.errors or not occurrences:
        detail = diagnostics.errors[0] if diagnostics.errors else f"item {item_id} not found"
        raise ValidationAdmissionError(str(detail))
    return (occurrences[0]["fields"].get("Validation", ("", None))[0] or "").strip()


def _make_invocations(text: str) -> tuple[dict, ...]:
    invocations = []
    for match in _MAKE_COMMAND_RE.finditer(text):
        try:
            tokens = shlex.split("make " + match.group(1))
        except ValueError:
            continue
        directory = Path(".")
        makefile = None
        targets = []
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token in ("-C", "--directory") and index + 1 < len(tokens):
                directory = directory / tokens[index + 1]
                index += 2
                continue
            if token.startswith("--directory="):
                directory = directory / token.split("=", 1)[1]
                index += 1
                continue
            if token in ("-f", "--file", "--makefile") and index + 1 < len(tokens):
                makefile = tokens[index + 1]
                index += 2
                continue
            if token.startswith(("--file=", "--makefile=")):
                makefile = token.split("=", 1)[1]
                index += 1
                continue
            if token.startswith("-") or ("=" in token and not token.startswith("=")):
                index += 1
                continue
            targets.append(token)
            index += 1
        for target in targets:
            invocations.append({
                "carrier": match.group(0).strip(),
                "directory": directory.as_posix(),
                "makefile": makefile,
                "target": target,
            })
    return tuple(invocations)


def _makefiles(directory: Path, explicit: str | None) -> tuple[Path, ...]:
    if explicit:
        return (directory / explicit,)
    return tuple(path for name in ("GNUmakefile", "makefile", "Makefile")
                 if (path := directory / name).is_file())


def _target_status(makefiles: tuple[Path, ...], target: str) -> tuple[str, list[str]]:
    if not makefiles:
        return "missing", ["makefile:absent"]
    queue = list(makefiles)
    visited = set()
    declared = set()
    patterns = []
    unresolved_include = False
    evidence = []
    while queue:
        path = queue.pop(0)
        resolved = path.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return "missing", [f"makefile:unreadable:{path}"]
        logical = []
        pending = ""
        for raw in raw_lines:
            pending += raw.rstrip("\\")
            if raw.endswith("\\"):
                continue
            logical.append(pending)
            pending = ""
        for line_number, line in enumerate(logical, 1):
            stripped = line.strip()
            include = _INCLUDE_RE.match(stripped)
            if include:
                for token in include.group(1).split():
                    if any(marker in token for marker in ("$", "*", "?", "[")):
                        unresolved_include = True
                    else:
                        candidate = path.parent / token
                        if candidate.is_file():
                            queue.append(candidate)
                        elif not stripped.startswith("-include"):
                            unresolved_include = True
                continue
            if not line or line.startswith(("\t", " ")):
                continue
            match = _TARGET_RE.match(line)
            if not match:
                continue
            for name in match.group(1).split():
                if "%" in name:
                    patterns.append(name)
                else:
                    declared.add(name)
                evidence.append(f"{path}:{line_number}")
    if target in declared:
        return "available", sorted(set(evidence))
    for pattern in patterns:
        regex = "^" + re.escape(pattern).replace("%", ".+") + "$"
        if re.fullmatch(regex, target):
            return "available", sorted(set(evidence))
    if unresolved_include:
        return "unknown", sorted(set(evidence)) or ["makefile:dynamic-include"]
    return "missing", sorted(set(evidence)) or ["makefile:no-targets"]


def inspect(plan_dir, item_id: str) -> dict:
    plan_dir = Path(plan_dir)
    plan_layout.layout_version(plan_dir)
    root = _repository_root(plan_dir)
    checks = []
    for invocation in _make_invocations(_validation_text(plan_dir, item_id)):
        directory = (root / invocation["directory"]).resolve()
        status, evidence_ids = _target_status(
            _makefiles(directory, invocation["makefile"]), invocation["target"])
        checks.append({
            "carrier": invocation["carrier"],
            "kind": "make-target",
            "target": invocation["target"],
            "status": status,
            "evidence_ids": evidence_ids,
        })
    return {
        "schema_version": "validation-admission/v1",
        "plan_id": plan_dir.name,
        "item_id": item_id,
        "disposition": "local-repair" if any(row["status"] == "missing" for row in checks)
        else "allow",
        "checks": checks,
    }


def local_repair_decision(report: dict) -> dict:
    missing = [row for row in report.get("checks", []) if row.get("status") == "missing"]
    if report.get("disposition") != "local-repair" or not missing:
        raise ValidationAdmissionError("report does not require local repair")
    return {
        "signal_class": "acceptance",
        "scope_class": "item",
        "action": "repair-inline",
        "recovered": False,
        "terminal": False,
        "validation_admission": report,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect deterministic Validation prerequisites.")
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--item", required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect(args.plan_dir, args.item)
    except (ValidationAdmissionError, plan_layout.PlanLayoutError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 2 if report["disposition"] == "local-repair" else 0


if __name__ == "__main__":
    raise SystemExit(main())
