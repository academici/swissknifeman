"""Host-level Serena / LSP runtime scan for fleet audit (read-only, subprocess ps)."""
from __future__ import annotations

import re
import subprocess

_PROJECT_RE = re.compile(r"--project\s+(\S+)")
_WARN_MB = 500
_CRIT_MB = 1024


def _parse_ps():
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,rss=,args="], text=True, errors="replace", timeout=5)
    except (subprocess.SubprocessError, OSError):
        return []
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, rss_kb, args = parts[0], int(parts[1]), parts[2]
        rows.append((pid, rss_kb, args))
    return rows


def scan_runtime():
    """Summarize duplicate Serena projects and heavy LSP processes on this host."""
    by_project: dict[str, list[dict]] = {}
    heavy: list[dict] = []
    for pid, rss_kb, args in _parse_ps():
        if "serena start-mcp-server" not in args and "intelephense" not in args:
            continue
        mb = rss_kb // 1024
        match = _PROJECT_RE.search(args)
        project = match.group(1) if match else None
        row = {"pid": pid, "mb": mb, "args": args}
        if project:
            by_project.setdefault(project, []).append(row)
        if mb >= _WARN_MB:
            heavy.append({**row, "project": project, "level": "crit" if mb >= _CRIT_MB else "warn"})
    duplicates = [
        {"project": path, "count": len(rows), "pids": [r["pid"] for r in rows],
         "mb_total": sum(r["mb"] for r in rows)}
        for path, rows in sorted(by_project.items()) if len(rows) > 1
    ]
    heavy.sort(key=lambda r: r["mb"], reverse=True)
    return {"duplicates": duplicates, "heavy": heavy[:10]}


def runtime_summary(snapshot):
    parts = []
    for dup in snapshot.get("duplicates") or []:
        parts.append(f"dup:{dup['project']}×{dup['count']}={dup['mb_total']}MB")
    for row in snapshot.get("heavy") or []:
        tag = row.get("project") or "lsp"
        parts.append(f"{tag}:{row['mb']}MB")
    return "; ".join(parts[:6])
