"""Run-report and codegraph data from analyst, read through its public JSON commands.

maind never imports analyst: ``aicore.util.partners`` finds the command and the output is checked only
for the fields maind uses. A missing or failing analyst is reported as a problem (``PARTNER_UNAVAILABLE``,
``PARTNER_FAILED`` or ``PARTNER_BAD_OUTPUT``), never raised.
"""
from __future__ import annotations

from aicore.util.partners import PartnerError, PartnerUnavailable, run_partner_json

LEGACY_ENV = ("MAIND_ANALYST_BIN",)


def _problem(exc):
    text = str(exc)
    code = text.split(":", 1)[0] if text.startswith("PARTNER_") else "PARTNER_FAILED"
    return {"code": code, "message": text}


def _call(args, valid):
    try:
        data = run_partner_json("analyst", args, legacy_env=LEGACY_ENV)
    except (PartnerUnavailable, PartnerError) as exc:
        return None, _problem(exc)
    if not valid(data):
        return None, {"code": "PARTNER_BAD_OUTPUT",
                      "message": f"PARTNER_BAD_OUTPUT: analyst {args[0]} {args[1]} output lacks the expected fields"}
    return data, None


def _is_lookup(data):
    lookup = data.get("lookup") if isinstance(data, dict) else None
    return (isinstance(lookup, dict) and isinstance(lookup.get("status"), str)
            and isinstance(data.get("events"), list)
            and (data.get("report") is None or isinstance(data.get("report"), dict))
            and (data.get("codegraph") is None or isinstance(data.get("codegraph"), dict)))


def _is_codegraph(data):
    reports = data.get("reports") if isinstance(data, dict) else None
    return isinstance(reports, list) and all(
        isinstance(row, dict) and isinstance(row.get("provider"), str) and isinstance(row.get("summary"), dict)
        for row in reports)


def run_lookup(project_path, session=None, project_id=None):
    """``analyst runs show``: ``(payload, None)`` or ``(None, {"code", "message"})``."""
    args = ["runs", "show", "--project", str(project_path)]
    if session:
        args += ["--session", session]
    if project_id:
        args += ["--project-id", project_id]
    return _call(args + ["--json"], _is_lookup)


def codegraph_reports(project_path, limit=None):
    """``analyst runs codegraph``: ``(payload, None)`` or ``(None, {"code", "message"})``."""
    args = ["runs", "codegraph", "--project", str(project_path)]
    if limit:
        args += ["--limit", str(limit)]
    return _call(args + ["--json"], _is_codegraph)
