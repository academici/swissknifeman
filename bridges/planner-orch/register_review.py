"""Registration of an orch reviewer's review-findings into the plan (``register-review``).

The verdict becomes a knowledge document (``add-document``) and a ``note`` event that names the document and
the actual reviewer route and session (W5, W6). The bridge writes only through ``PLANNER_PLAN_PY``; the document
travels as ``--json`` text, so no file is written next to the plan. A repeat is a no-op: an identical document
and a note already in the journal are skipped.

Run as ``plan.py bridge planner-orch register-review <plan> <ref> --findings FINDINGS.json --actor P/M[/E]
[--plans-root DIR] [--dry-run]``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from register import Refusal, _text, finish_receipt, journal, load_json, run_plan, execute

DOCUMENT_SCHEMA = "urn:swissknifeman:task:plan:document:v1"
VERDICTS = ("GREEN", "ATTENTION", "RED")
FINDING_FIELDS = ("severity", "confidence", "location", "failure_scenario", "basis")
_REF = re.compile(r"^P[0-9]+(?:\.[0-9]+)?$", re.ASCII)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)


def check_findings(findings) -> dict:
    """The review-findings or ``REGISTER_FINDINGS_INVALID``; closed like the stage-report."""
    def invalid(message: str) -> Refusal:
        return Refusal("REGISTER_FINDINGS_INVALID", message)

    if not isinstance(findings, dict) or set(findings) != {"verdict", "reviewer", "findings", "date"}:
        raise invalid("review-findings are {verdict, reviewer, findings, date}")
    if findings["verdict"] not in VERDICTS:
        raise invalid(f"verdict must be one of {', '.join(VERDICTS)}")
    reviewer = findings["reviewer"]
    if not isinstance(reviewer, dict) or set(reviewer) != {"route", "session"} \
            or not all(_text(reviewer[key]) for key in ("route", "session")):
        raise invalid("reviewer is {route, session} with the actual reviewer route and session")
    if not isinstance(findings["date"], str) or not _DATE.fullmatch(findings["date"]):
        raise invalid("date must be YYYY-MM-DD")
    if not isinstance(findings["findings"], list):
        raise invalid("findings must be a list")
    for index, finding in enumerate(findings["findings"]):
        if not isinstance(finding, dict) or set(finding) != set(FINDING_FIELDS) \
                or not all(_text(finding[key]) or isinstance(finding[key], (int, float)) and
                           not isinstance(finding[key], bool) for key in FINDING_FIELDS):
            raise invalid(f"findings[{index}] needs non-empty {', '.join(FINDING_FIELDS)}")
    return findings


def review_document(ref: str, findings: dict) -> dict:
    """The knowledge document ``review-<ref>-<date>`` with sections ``verdict`` and ``findings``."""
    reviewer, date = findings["reviewer"], findings["date"]
    body = ("```json\n" + json.dumps(findings["findings"], ensure_ascii=False, indent=2) + "\n```"
            if findings["findings"] else "No findings.")
    return {
        "$schema": DOCUMENT_SCHEMA,
        "id": f"review-{ref.replace('.', '-').replace('/', '-')}-{date}",
        "title": f"Review {ref} {date}",
        "applies_to": [ref],
        "sections": [
            {"id": "verdict", "title": "Verdict",
             "text": f"{findings['verdict']}. Reviewer route {reviewer['route']}, session {reviewer['session']}."},
            {"id": "findings", "title": "Findings", "text": body},
        ],
    }


def plan_calls(findings: dict, args) -> list[list[str]]:
    """``add-document`` then one ``log … --type note``; pure, like ``register.plan_calls``."""
    findings = check_findings(findings)
    if not _REF.fullmatch(args.ref or ""):
        raise Refusal("REGISTER_FINDINGS_INVALID", f"ref {args.ref!r} must be an item Pn.m or a phase Pn")
    doc = review_document(args.ref, findings)
    root = ["--plans-root", str(args.plans_root)] if args.plans_root else []
    reviewer = findings["reviewer"]
    summary = (f"review {findings['verdict']}: @plan/knowledge/{doc['id']}.json; "
               f"reviewer {reviewer['route']} session {reviewer['session']}")
    return [
        ["add-document", args.plan, "--json", json.dumps(doc, ensure_ascii=False)] + root,
        ["log", args.plan, args.ref, "--type", "note", "--summary", summary, "--actor", args.actor] + root,
    ]


def _stored(plan: str, plans_root, doc_id: str):
    """The stored knowledge document ``doc_id`` or None."""
    argv = ["--output", "json", "get", plan, f"knowledge/{doc_id}"]
    if plans_root:
        argv += ["--plans-root", str(plans_root)]
    done = run_plan(argv)
    return json.loads(done.stdout)["data"]["doc"] if done.returncode == 0 else None


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plan.py bridge planner-orch register-review",
                                description="Register orch review-findings into the plan through plan.py.")
    p.add_argument("plan", help="plan id, PLAN<N> or path")
    p.add_argument("ref", metavar="item|phase")
    p.add_argument("--findings", required=True, help="review-findings JSON file")
    p.add_argument("--actor", required=True, metavar="P/M[/E]", help="the registrar")
    p.add_argument("--plans-root", type=Path)
    p.add_argument("--dry-run", action="store_true", help="print the argv lists as JSON and write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        calls = plan_calls(load_json(args.findings, "REGISTER_FINDINGS_INVALID", "review-findings"), args)
    except Refusal as refusal:
        print(refusal, file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(calls, ensure_ascii=False, indent=2))
        return 0
    receipt = {"plan": args.plan, "ref": args.ref, "calls": []}
    add, note = calls
    doc = json.loads(add[add.index("--json") + 1])
    if _stored(args.plan, args.plans_root, doc["id"]) == doc:
        receipt["calls"].append({"argv": add, "exit": 0, "result": "no-op"})
        add = None
    seen, entry = journal(args.plan, args.plans_root, None, {"note"})
    if seen is None:
        receipt["calls"].append(entry)
        return finish_receipt(receipt, args.plan, args.plans_root, 1)
    return finish_receipt(receipt, args.plan, args.plans_root,
                          execute([argv for argv in (add, note) if argv], seen, receipt))


if __name__ == "__main__":
    sys.exit(main())
