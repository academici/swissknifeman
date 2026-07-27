#!/usr/bin/env python3
"""Сканер дрейфа пина Serena по флоту (read-only, stdlib-only). Plan P5.3.

Для каждого проекта с `mcp.code:true` в корневом `config.json` снимает: наличие
`.mcp.json`, запись `serena` в нём, пиннован ли источник `--from`, фактически
резолвящуюся сегодня версию (через тот же `uvx`) и вердикт `maind sync --only mcp
--dry-run --json`. Никаких записей в чужие деревья — только чтение и subprocess
dry-run/version-запросы.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "config.json"


def fleet_projects(config_path=CONFIG_PATH):
    data = json.loads(config_path.read_text())
    return [p for p in data.get("projects", []) if (p.get("mcp") or {}).get("code")]


def _find_from_arg(args):
    for i, a in enumerate(args or []):
        if a == "--from" and i + 1 < len(args):
            return args[i + 1]
    return None


def inspect_mcp_json(local_path):
    if not local_path:
        return {"exists": False, "reason": "no-local_path"}
    mcp_path = Path(local_path) / ".mcp.json"
    if not mcp_path.exists():
        return {"exists": False, "path": str(mcp_path)}
    try:
        data = json.loads(mcp_path.read_text())
    except Exception as exc:
        return {"exists": True, "path": str(mcp_path), "error": f"json-parse: {exc}"}
    servers = data.get("mcpServers") or data.get("servers") or {}
    serena = servers.get("serena")
    if serena is None:
        return {"exists": True, "path": str(mcp_path), "serena": None}
    from_arg = _find_from_arg(serena.get("args"))
    pinned = bool(from_arg) and "@" in from_arg
    return {
        "exists": True,
        "path": str(mcp_path),
        "serena_command": serena.get("command"),
        "from": from_arg,
        "pinned": pinned,
    }


def resolved_version(from_arg, command="uvx", timeout=90):
    if not from_arg:
        return None, "no-from-arg"
    try:
        proc = subprocess.run(
            [command, "--from", from_arg, "serena", "--version"],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:
        return None, f"exec-error: {exc}"
    if proc.returncode != 0:
        return None, f"non-zero-exit: {proc.stderr.strip()[:300]}"
    return proc.stdout.strip(), None


def sync_verdict(project_id, timeout=60):
    try:
        proc = subprocess.run(
            ["maind", "sync", "--project", project_id, "--only", "mcp",
             "--dry-run", "--json"],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:
        return {"error": f"exec-error: {exc}"}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"raw_stdout": proc.stdout.strip()[:500],
                 "raw_stderr": proc.stderr.strip()[:500]}


def scan():
    results = []
    for p in fleet_projects():
        pid = p["id"]
        local_path = p.get("local_path")
        mcp_info = inspect_mcp_json(local_path)
        from_arg = mcp_info.get("from")
        version, version_error = resolved_version(from_arg)
        results.append({
            "id": pid,
            "local_path": local_path,
            "mcp_json": mcp_info,
            "resolved_version": version,
            "resolved_version_error": version_error,
            "sync_verdict": sync_verdict(pid),
        })
    return results


def main(argv):
    as_json = "--json" in argv
    results = scan()
    if as_json:
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
    else:
        for r in results:
            print(r["id"], "pinned=" + str(r["mcp_json"].get("pinned")),
                  "resolved=" + str(r["resolved_version"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
