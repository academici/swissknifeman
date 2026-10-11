"""Shared codegraph / Serena / laravel-boost MCP tool-name helpers (stdlib-only)."""
from __future__ import annotations

_SYMBOL_TOOLS = frozenset({
    "find_symbol", "find_referencing_symbols", "get_symbols_overview",
    "find_implementations", "find_declaration", "replace_symbol_body",
    "insert_after_symbol", "insert_before_symbol", "rename_symbol",
    "safe_delete_symbol", "replace_content", "replace_in_files",
    "get_diagnostics_for_file",
})

_SERVER_MARKERS = (
    "codegraph", "serena", "plugin_core_codegraph", "plugin-core-codegraph",
    "laravel-boost", "laravel_boost",
)


def _server_matches(server: str) -> bool:
    norm = server.lower().replace("-", "_")
    return any(marker.replace("-", "_") in norm for marker in _SERVER_MARKERS)


def codegraph_tool_op(name) -> str | None:
    """Return the symbol-operation id for a provider tool name, or None."""
    if not isinstance(name, str) or not name:
        return None
    if name in _SYMBOL_TOOLS:
        return name
    low = name.lower()
    if low in _SYMBOL_TOOLS:
        return low
    if low.startswith("mcp:"):
        parts = name.split(":", 2)
        if len(parts) >= 3 and _server_matches(parts[1]):
            return parts[2]
        return None
    if not name.startswith("mcp__"):
        return None
    tail = name.rsplit("__", 1)[-1]
    server = name[len("mcp__"):-(len(tail) + 2)]
    if _server_matches(server):
        return tail
    return None


def codegraph_rec():
    """Empty per-operation counter record used in run-reports."""
    return {"calls": 0}


def codegraph_from_by_name(by_name: dict) -> dict[str, dict]:
    """Aggregate codegraph ops from tools.by_name counters."""
    out: dict[str, dict] = {}
    if not isinstance(by_name, dict):
        return out
    for name, count in by_name.items():
        if not isinstance(count, int) or count <= 0:
            continue
        op = codegraph_tool_op(name)
        if op is None:
            continue
        rec = out.setdefault(op, codegraph_rec())
        rec["calls"] += count
    return out


def codegraph_summary(codegraph: dict) -> dict:
    """Roll up a codegraph block for dashboards."""
    if not isinstance(codegraph, dict):
        return {"calls": 0, "ops": 0, "by_op": {}}
    by_op = {}
    total = 0
    for op, rec in codegraph.items():
        if not isinstance(rec, dict):
            continue
        calls = int(rec.get("calls") or 0)
        if calls <= 0:
            continue
        by_op[op] = calls
        total += calls
    return {"calls": total, "ops": len(by_op), "by_op": by_op}


def scan_run_report(report) -> dict:
    """Extract codegraph usage from one SCHEMA=1/2 run-report dict."""
    if not isinstance(report, dict):
        return codegraph_summary({})
    block = report.get("codegraph")
    if isinstance(block, dict) and block:
        return codegraph_summary(block)
    tools = report.get("tools") or {}
    by_name = tools.get("by_name") if isinstance(tools, dict) else None
    return codegraph_summary(codegraph_from_by_name(by_name or {}))


_RUN_DIRS = ((".claude/runs", "claude-code"), (".cursor/runs", "cursor"), (".codex/runs", "codex"))
MAX_REPORTS = 40


def load_reports(project_path, limit: int = MAX_REPORTS):
    """Recent run reports of a project, newest first: ``(mtime, provider, path, report)`` rows.

    Reads the ``.claude``, ``.cursor`` and ``.codex`` runs folders; unreadable or non-object files are skipped.
    """
    import json
    from pathlib import Path

    project = Path(project_path)
    rows = []
    for rel, provider in _RUN_DIRS:
        runs = project / rel
        if not runs.is_dir():
            continue
        for fp in runs.glob("*.json"):
            try:
                mtime = fp.stat().st_mtime
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                rows.append((mtime, provider, str(fp), data))
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows[:limit]
