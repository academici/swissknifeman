"""Build a valid execution-input without a plan: ad-hoc work or a read-only review."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from orch import CONTRACT_VERSION
from orch.contracts import canonical_digest, validate

SCHEMA = "urn:swissknifeman:orch:exec:execution-input:v1"
DEFAULT_ROUTE = {"class": "implementation", "effort": "high"}
REVIEW_PROCEDURE = "Every finding has severity, file:line, failure scenario"
_CHECK_ID = re.compile(r"^V[0-9]+$")


class AdhocError(Exception):
    """``USAGE`` is a caller mistake (exit 2); ``INPUT_INVALID`` means the result broke the contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _usage(message: str) -> AdhocError:
    return AdhocError("USAGE", message)


def _pair(item: str, flag: str) -> tuple[str, str]:
    check_id, separator, body = item.partition("=")
    if not separator or not _CHECK_ID.match(check_id) or not body.strip():
        raise _usage(f"{flag} expects 'V<number>=TEXT', got {item!r}")
    return check_id, body


def _split_review(review: str) -> tuple[str, str]:
    base, separator, head = review.partition("..")
    if not separator or not base or not head or ".." in head:
        raise _usage(f"--review expects BASE..HEAD, got {review!r}")
    return base, head


def build_adhoc_input(goal: str | None, include: Iterable[str], exclude: Iterable[str] = (),
                      checks: Iterable[str] = (), procedures: Iterable[str] = (),
                      reads: Iterable[str] = (), route: dict | None = None,
                      review: str | None = None, why: str | None = None,
                      expect: str | None = None, created_by: str = "owner") -> dict:
    """Execution-input for ad-hoc work or, with ``review='BASE..HEAD'``, a read-only review.

    ``checks`` are ``'V1=CMD'`` (expected ``expect``, default ``exit 0``), ``procedures`` are
    ``'V2=TEXT'`` (expected ``observed``). Without any of them the input is refused: acceptance is mandatory,
    except that a review falls back to the findings-shape procedure.
    """
    include, exclude, reads = list(include), list(exclude), list(reads)
    parsed = [(*_pair(item, "--check"), "cmd") for item in checks]
    parsed += [(*_pair(item, "--procedure"), "procedure") for item in procedures]
    provenance: dict
    if review is not None:
        base, head = _split_review(review)
        target = f"diff {base}..{head}"
        goal = goal or f"Independent read-only review of {target}"
        include = include or [target]
        parsed = parsed or [("V1", REVIEW_PROCEDURE, "procedure")]
        provenance = {"kind": "review", "base": base, "head": head, "target": target}
    else:
        if not goal or not goal.strip():
            raise _usage("a goal is required")
        provenance = {"kind": "adhoc", "request": goal, "created_by": created_by}
    if not include:
        raise _usage("at least one include entry is required")
    if not parsed:
        raise _usage("acceptance is mandatory: give at least one --check or --procedure")
    ids = [check_id for check_id, _, _ in parsed]
    if len(set(ids)) != len(ids):
        raise _usage("check ids must be unique")
    scope: dict = {"include": include, "exclude": exclude}
    if review is not None:
        scope["read_only"] = True
    acceptance_checks = []
    for check_id, body, carrier in sorted(parsed, key=lambda row: int(row[0][1:])):
        check = {"id": check_id, carrier: body,
                 "expect": (expect or "exit 0") if carrier == "cmd" else "observed", "kind": "acceptance"}
        acceptance_checks.append(check)
    report = ["summary", "open_issues"] if review is not None else ["summary", "changed_paths"]
    if review is None and any(carrier == "cmd" for _, _, carrier in parsed):
        report.insert(2, "checks_run")
    doc: dict = {
        "$schema": SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "input_id": "adhoc@" + "0" * 12,
        "digest": "",
        "provenance": provenance,
        "goal": goal,
    }
    if why:
        doc["why"] = why
    doc["scope"] = scope
    doc["acceptance"] = {"checks": acceptance_checks}
    if reads:
        doc["reads"] = [{"path": path, "why": "named in the request", "required": True,
                         "exists": Path(path).exists()} for path in reads]
    doc["route"] = {"minimum": {**DEFAULT_ROUTE, **(route or {})}}
    doc["result_contract"] = {
        "report": report,
        "write_authority": "none" if review is not None else "code_scope",
        "commit_owner": "coordinator",
        "plan_mutation": "forbidden",
    }
    digest = canonical_digest(doc)
    doc["digest"], doc["input_id"] = digest, f"adhoc@{digest[:12]}"
    errors = [issue for issue in validate(doc, "execution-input") if issue.level == "error"]
    if errors:
        raise AdhocError("INPUT_INVALID", "; ".join(f"{issue.path or '/'} {issue.code}: {issue.message}"
                                                    for issue in errors))
    return doc
