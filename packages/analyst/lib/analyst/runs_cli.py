"""analyst runs — read-only JSON access to a project's run reports and analytics events.

``runs show`` and ``runs codegraph`` print the contracts ``run-lookup/v1`` and ``run-codegraph/v1``;
other modules read them through ``aicore.util.partners`` instead of importing analyst.
"""
import json
import os
from dataclasses import fields
from pathlib import Path

from .codegraph import MAX_REPORTS, load_reports, scan_run_report
from aicore.util.cli import parse_args
from aicore.util.term import die
from .run_reports import find_analytics_events, find_run_report_result

LOOKUP_SCHEMA = "urn:swissknifeman:analyst:run-lookup:v1"
CODEGRAPH_SCHEMA = "urn:swissknifeman:analyst:run-codegraph:v1"

_HELP = """analyst runs show --project DIR [--session ID] [--project-id ID] [--json]
  The provenance-checked run report of DIR (newest, or the one of --session), its codegraph
  usage summary and the neutral analytics events. Exit 0 also when there is no report.
analyst runs codegraph --project DIR [--limit N] [--json]
  Codegraph usage summaries of the newest run reports (Claude Code, Cursor and Codex runs folders).
  --json prints the contract run-lookup/v1 or run-codegraph/v1."""


def _jsonable(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _lookup_payload(project, session, project_id):
    lookup = find_run_report_result(project, session=session or None, project_id=project_id or None)
    diagnostic = _jsonable(lookup.diagnostic) if lookup.diagnostic is not None else None
    reason = diagnostic.get("code") if isinstance(diagnostic, dict) else None
    return {
        "$schema": LOOKUP_SCHEMA,
        "project": str(project),
        "lookup": {"status": lookup.status, "path": lookup.path, "reason": reason},
        "report": lookup.report,
        "codegraph": scan_run_report(lookup.report) if lookup.report is not None else None,
        "events": [{field.name: _jsonable(getattr(event, field.name)) for field in fields(event)} for event in find_analytics_events(project, session=session or None)],
    }


def _codegraph_payload(project, limit):
    return {
        "$schema": CODEGRAPH_SCHEMA,
        "project": str(project),
        "reports": [{"provider": provider, "path": path, "mtime": float(mtime),
                     "summary": scan_run_report(report)}
                    for mtime, provider, path, report in load_reports(project, limit)],
    }


def _text_lookup(payload):
    lookup = payload["lookup"]
    line = f"run report: {lookup['status']}"
    if lookup["path"]:
        line += f" ({lookup['path']})"
    if lookup["reason"]:
        line += f" reason={lookup['reason']}"
    codegraph = payload["codegraph"]
    if codegraph is not None:
        line += f"; codegraph calls={codegraph['calls']} ops={codegraph['ops']}"
    return f"{line}; events={len(payload['events'])}"


def _text_codegraph(payload):
    rows = [f"{row['provider']} {row['path']} calls={row['summary']['calls']}" for row in payload["reports"]]
    return "\n".join(rows) if rows else "no run reports"


def cmd_runs(env, argv):
    """analyst runs show|codegraph --project DIR [...] [--json]"""
    if not argv or argv[0] in ("-h", "--help"):
        print(_HELP)
        return
    verb, rest = argv[0], argv[1:]
    if verb not in ("show", "codegraph"):
        die(f"unknown runs command: {verb}", code=2)
    spec = {"--project": "str", "--json": "bool"}
    spec.update({"--session": "str", "--project-id": "str"} if verb == "show" else {"--limit": "str"})
    try:
        opts, _ = parse_args(rest, spec)
    except SystemExit as exc:
        raise SystemExit(2) from exc
    if opts["help"]:
        print(_HELP)
        return
    if not opts["project"]:
        die("--project is required", code=2)
    project = Path(os.path.expanduser(opts["project"])).resolve()
    if verb == "show":
        payload = _lookup_payload(project, opts["session"], opts["project_id"])
        text = _text_lookup
    else:
        limit = MAX_REPORTS
        if opts["limit"]:
            try:
                limit = int(opts["limit"])
            except ValueError:
                die(f"--limit expects an integer, received: {opts['limit']}", code=2)
            if limit <= 0:
                die("--limit must be positive", code=2)
        payload = _codegraph_payload(project, limit)
        text = _text_codegraph
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if opts["json"] else text(payload))
