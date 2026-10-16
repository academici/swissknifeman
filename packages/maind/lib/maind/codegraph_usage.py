"""Fleet scan of codegraph MCP usage from Claude/Cursor run-reports (read-only), read through analyst."""
from __future__ import annotations

import os
from pathlib import Path

from .analyst_source import codegraph_reports

_MAX_REPORTS = 40


def scan_project(project_path, *, limit: int = _MAX_REPORTS):
    """Summarize recent codegraph usage for one project directory."""
    path = Path(os.path.expanduser(str(project_path)))
    data, problem = codegraph_reports(path, limit=limit)
    if problem is not None:
        return {"status": "unavailable", "reason": problem["code"], "sessions": 0, "code_sessions": 0,
                "calls": 0, "by_op": {}, "by_provider": {}}
    reports = data["reports"]
    sessions = len(reports)
    code_sessions = 0
    calls = 0
    by_op: dict[str, int] = {}
    by_provider = {"claude-code": {"sessions": 0, "code_sessions": 0, "calls": 0},
                   "cursor": {"sessions": 0, "code_sessions": 0, "calls": 0},
                   "codex": {"sessions": 0, "code_sessions": 0, "calls": 0}}
    for row in reports:
        provider, summary = row["provider"], row["summary"]
        summary = {"calls": int(summary.get("calls") or 0), "by_op": summary.get("by_op") or {}}
        prov = by_provider.setdefault(provider, {"sessions": 0, "code_sessions": 0, "calls": 0})
        prov["sessions"] += 1
        if summary["calls"]:
            code_sessions += 1
            prov["code_sessions"] += 1
        calls += summary["calls"]
        prov["calls"] += summary["calls"]
        for op, cnt in (summary.get("by_op") or {}).items():
            by_op[op] = by_op.get(op, 0) + cnt
    return {
        "status": "ok",
        "sessions": sessions,
        "code_sessions": code_sessions,
        "calls": calls,
        "by_op": by_op,
        "by_provider": by_provider,
    }


def fleet_summary(projects):
    """Aggregate codegraph usage across enabled fleet projects."""
    rows = []
    total_sessions = total_code = total_calls = 0
    for project in projects:
        if not project.get("enabled"):
            continue
        local = project.get("local_path")
        if not local:
            continue
        snap = scan_project(local)
        if snap["status"] == "unavailable":
            rows.append({"id": project["id"], **snap})
            continue
        if not snap["sessions"]:
            continue
        rows.append({"id": project["id"], **snap})
        total_sessions += snap["sessions"]
        total_code += snap["code_sessions"]
        total_calls += snap["calls"]
    rows.sort(key=lambda row: (-row["calls"], row["id"]))
    return {
        "projects": rows,
        "totals": {
            "sessions": total_sessions,
            "code_sessions": total_code,
            "calls": total_calls,
        },
    }


def usage_note(snapshot):
    """One-line fleet summary for doctor audit."""
    totals = snapshot.get("totals") or {}
    sessions = int(totals.get("sessions") or 0)
    if sessions <= 0:
        unavailable = [row for row in snapshot.get("projects") or [] if row.get("status") == "unavailable"]
        if unavailable:
            return f"analyst unavailable ({unavailable[0].get('reason', 'PARTNER_UNAVAILABLE')})"
        return "no run-report'ov"
    code_sessions = int(totals.get("code_sessions") or 0)
    calls = int(totals.get("calls") or 0)
    pct = 100 * code_sessions / sessions if sessions else 0
    return f"{code_sessions}/{sessions} sessions ({pct:.0f}%), calls={calls}"


def format_project_line(row, code_enabled: bool):
    sid = row.get("id", "?")
    sessions = int(row.get("sessions") or 0)
    code_sessions = int(row.get("code_sessions") or 0)
    calls = int(row.get("calls") or 0)
    flag = "code:on" if code_enabled else "code:off"
    if row.get("status") == "unavailable":
        return f"{sid}[{flag}] unavailable ({row.get('reason', 'PARTNER_UNAVAILABLE')})"
    if sessions == 0:
        return None
    pct = 100 * code_sessions / sessions if sessions else 0
    note = f"{code_sessions}/{sessions} ({pct:.0f}%) calls={calls}"
    if code_enabled and code_sessions == 0 and sessions >= 5:
        note += " idle"
    return f"{sid}[{flag}] {note}"
