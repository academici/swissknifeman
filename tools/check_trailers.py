"""Check the trailer structure of published SKM integration commits in a Git revision or range."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from uuid import UUID

from skm.modules.execution.domain.integration import (
    FINDING_KEY,
    OPTIONAL_TRAILERS,
    REPEATABLE_TRAILERS,
    REQUIRED_TRAILERS,
    SESSION_REF,
    TASK_SPEC_DIGEST,
    TASK_SPEC_REF,
    TRAILER_NAMES,
)

_REQUIRED = tuple(name for name, _ in REQUIRED_TRAILERS)
_CANONICAL = {name.lower(): name for name, _ in (*REQUIRED_TRAILERS, *OPTIONAL_TRAILERS)}
_MARKERS = {"skm-run", "skm-effect", "skm-output", "task-spec-ref", "task-spec-digest"}
_TRAILER = re.compile(r"([A-Za-z][A-Za-z0-9-]*): (.+)")
_POSITIVE = re.compile(r"[1-9][0-9]*")


def _name(line: str) -> str:
    return line.partition(":")[0].strip().lower()


def _uuid(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def check_message(message: str) -> tuple[str, ...]:
    """Return diagnostics for a managed commit. Ordinary and internal snapshot commits pass."""
    if not any(_name(line) in _MARKERS for line in message.splitlines()):
        return ()
    lines = message.rstrip("\n").split("\n")
    split = max((n for n, line in enumerate(lines) if not line), default=-1)
    errors: list[str] = []
    if split < 1 or any(_name(line) in TRAILER_NAMES for line in lines[:split]):
        errors.append("identity trailers must occur only in a final, blank-line-separated block")

    values: dict[str, list[str]] = {}
    for line in lines[split + 1 :]:
        match = _TRAILER.fullmatch(line)
        if match is None or not line.isprintable() or line != line.rstrip():
            errors.append("malformed trailer line")
            continue
        name, value = match.groups()
        canonical = _CANONICAL.get(name.lower(), name)
        if canonical != name or value != value.strip():
            errors.append(f"noncanonical {canonical} trailer")
        values.setdefault(canonical, []).append(value)

    errors.extend(f"missing {name}" for name in _REQUIRED if name not in values)
    names = tuple(name for name in values if name in _REQUIRED)
    if len(names) == len(_REQUIRED) and names != _REQUIRED:
        errors.append("required SKM trailers are out of order")
    errors.extend(
        f"duplicate {name}"
        for name, entries in values.items()
        if name.lower() in TRAILER_NAMES and name not in REPEATABLE_TRAILERS and len(entries) != 1
    )
    return (*errors, *_check_values(values))


def _check_values(values: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []

    adhoc = values.get("SKM-Plan") == ["adhoc"]
    errors.extend(
        f"invalid {name}"
        for name in ("SKM-Run", "SKM-Plan", "SKM-Attempt", "SKM-Output", "SKM-Effect", "SKM-Review")
        if (name != "SKM-Plan" or not adhoc) and any(not _uuid(value) for value in values.get(name, []))
    )

    for name in ("SKM-Revision", "SKM-Output-No", "SKM-Review-Round"):
        pattern = re.compile("0") if adhoc and name == "SKM-Revision" else _POSITIVE
        if any(pattern.fullmatch(value) is None for value in values.get(name, [])):
            errors.append(f"invalid {name}")
    for first, second in (("Task-Spec-Ref", "Task-Spec-Digest"), ("SKM-Review", "SKM-Review-Round")):
        if (first in values) != (second in values):
            errors.append(f"{first} and {second} must occur together")
    if "Task-Spec-Ref" in values:
        errors.extend(
            f"missing {name}" for name in ("SKM-Output-No", "Plan", "Plan-Ref") if name not in values
        )

    for name, pattern in (
        ("Task-Spec-Ref", TASK_SPEC_REF),
        ("Task-Spec-Digest", TASK_SPEC_DIGEST),
        ("SKM-Findings", FINDING_KEY),
        ("Executor-Session", SESSION_REF),
        ("Reviewer-Session", SESSION_REF),
    ):
        if any(pattern.fullmatch(value) is None for value in values.get(name, [])):
            errors.append(f"invalid {name}")
    if "Plan-Ref" in values and values["Plan-Ref"] != values.get("SKM-Task"):
        errors.append("Plan-Ref differs from SKM-Task")
    for sessions, performers in (("Executor-Session", "Executed-By"), ("Reviewer-Session", "Reviewed-By")):
        if len(values.get(sessions, [])) > len(values.get(performers, [])):
            errors.append(f"{sessions} requires matching {performers} attribution")
    return errors


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", nargs="?", default="HEAD", help="one commit or a Git range (A..B)")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        if ".." in args.revision:
            commits = _git(args.repo, "rev-list", "--end-of-options", args.revision, "--").splitlines()
        else:
            commits = [
                _git(
                    args.repo, "rev-parse", "--verify", "--end-of-options", args.revision + "^{commit}"
                ).strip()
            ]
        failed = False
        for commit in commits:
            for issue in check_message(_git(args.repo, "show", "-s", "--format=%B", commit, "--")):
                print(f"{commit}: {issue}")
                failed = True
    except (OSError, subprocess.CalledProcessError):
        parser.error("cannot read the requested Git commit or range")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
