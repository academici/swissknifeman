"""Read-only, fail-soft ecosystem monitoring for projects and daemons.

The JSON-first report is safe when files, daemons, or systemctl are unavailable.
"""
import json
import os
import subprocess
from pathlib import Path

from . import codegraph
from .mcpconfig import MCP_FILES, has_server
from .memory import health, resolve_ports
from .memory import status as memory_status
from .provision.workspace import norm_path, trusted_dirs

_SKILL_KEY = {"swissknifeman": "swissknifeman", "laravel-boost": "laravel_boost"}


def _read_skills_lock(project_path):
    f = project_path / "skills-lock.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_agent_pack_lock(project_path):
    """Return `.claude/agent-pack.lock.json` or None. Structure:
    {schema, packs: {<name>: {version, files:[{local_modified}], …}}}."""
    f = project_path / ".claude" / "agent-pack.lock.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def probe_project(env, config, project, *, memory_reachable=None, trusted=None,
                  provider_context=None):
    """Return one read-only project status report.

    Pass precomputed trusted paths in loops to avoid repeated configuration reads.
    """
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if trusted is None:
        trusted = trusted_dirs(env)
    if not path or not path.is_dir():
        return {"id": pid, "name": project.get("name", pid), "path": local,
                "status": "missing-path", "configured": {}, "skills": {},
                "agent_packs": {}, "daemons": {}, "trusted": False}

    def any_has(name):
        return any(has_server(path / rel, name) for rel in MCP_FILES.values())

    files = [rel for rel in MCP_FILES.values() if (path / rel).is_file()]
    lock = _read_skills_lock(path)
    skills = {"total": 0, "swissknifeman": 0, "laravel_boost": 0, "local": 0}
    if lock:
        lock_skills = lock.get("skills") or {}
        entries = lock_skills if isinstance(lock_skills, list) else lock_skills.values()
        for e in entries:
            skills["total"] += 1
            skills[_SKILL_KEY.get(e.get("source", "local"), "local")] += 1

    # Harness agent-pack layer: installed packs and local modifications.
    ap_lock = _read_agent_pack_lock(path)
    ap_names = sorted((ap_lock.get("packs") or {}).keys()) if ap_lock else []
    ap_modified = bool(ap_lock and any(
        fl.get("local_modified")
        for pk in (ap_lock.get("packs") or {}).values()
        for fl in (pk.get("files") or [])))
    agent_packs = {"installed": ap_names, "count": len(ap_names),
                   "lock": ap_lock is not None, "modified": ap_modified}

    mem_mcp = any_has("maind")       # maind replaces the raw agentmemory server.
    code_server = codegraph.server_name(project, codegraph.settings(config))
    configured = {
        "agentmemory_mcp": any_has("agentmemory"),   # Informational: raw-server footgun.
        "maind_mcp": mem_mcp,
        "code_mcp": any_has(code_server), "mcp_files": files,
        "skills_lock": lock is not None, "skills_count": skills["total"],
        "boost": (path / "boost.json").is_file(),
        "deployed_flag": bool(project.get("deployed")),
    }

    if memory_reachable is None:
        _, _, url = resolve_ports(env, config)
        memory_reachable = health(url)

    if mem_mcp and memory_reachable:
        status = "connected"
    elif mem_mcp or configured["deployed_flag"]:
        status = "partial"   # Server without daemon, or deployment flag without server.
    else:
        status = "standalone"

    result = {"id": pid, "name": project.get("name", pid), "path": str(path),
            "memory_scope": project.get("memory_scope") or f"project:{pid}",
            "configured": configured, "skills": skills, "agent_packs": agent_packs,
            "daemons": {"memory_reachable": memory_reachable},
            "trusted": norm_path(local) in trusted, "status": status}
    if provider_context is not None:
        from .provision.workspace import provider_trust
        result["provider_trust"] = provider_trust(provider_context,
                                                   trusted=result["trusted"])
    return result


def drift_hints(env, config, report):
    """Return read-only project-layer drift with an exact repair command.

    This is the shared source for projects status, health, and umbrella status.
    """
    pid = report.get("id")
    c = report.get("configured", {})
    hints = []
    # MCP/memory: configured server without daemon, or deployment drift.
    if report.get("status") == "partial":
        if c.get("maind_mcp") and not report.get("daemons", {}).get("memory_reachable"):
            hints.append({"layer": "memory",
                          "issue": "MCP памяти настроен, но демон не отвечает",
                          "fix": "maind start --only memory"})
        elif c.get("deployed_flag") and not c.get("maind_mcp"):
            hints.append({"layer": "mcp",
                          "issue": "deployed-флаг есть, но maind-сервер не в .mcp.json "
                                   "(починка не сработает, если провайдерский план проекта "
                                   "отказал unmanaged-target)",
                          "fix": f"maind sync --only mcp --project {pid}"})
    # Roles/agents: project profile expects packs absent from the lock.
    try:
        from .projects import get as _get
        from .provision.sync import _resolve_agent_pack
        expected = _resolve_agent_pack(config, _get(config, pid) or {})
    except (SystemExit, Exception):       # Fail soft when a profile is unavailable.
        expected = []
    installed = set((report.get("agent_packs") or {}).get("installed") or [])
    missing = [p for p in expected if p not in installed]
    if missing:
        hints.append({"layer": "agent-pack",
                      "issue": f"профиль ожидает паки {', '.join(missing)} — не установлены",
                      "fix": f"maind sync --only agent-pack --project {pid}"})
    return hints


def detect_docs_watcher(env):
    """brain docs-watcher: pidfile ~/.brain/docs-watcher.pid (kill -0) → systemctl --user."""
    pid_file = env.home / ".brain" / "docs-watcher.pid"
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return {"running": True, "via": "pidfile", "pid": pid}
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass  # Invalid PID file or dead process; check systemd below.
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", "docs-watcher.service"],
                           capture_output=True, text=True, check=False, timeout=3)
        if r.stdout.strip() == "active":
            return {"running": True, "via": "systemd", "pid": None}
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass  # Missing systemctl or timeout means watcher is not running.
    return {"running": False, "via": None, "pid": None}


def probe_hub(env, config):
    """Return read-only hub status for memory, graph, and docs watcher."""
    mem = memory_status(env, config)
    adapter = (config.get("graph") or {}).get("adapter", "federation")
    try:
        if adapter == "disabled":
            gstats = {"nodes": 0, "edges": 0}
        else:
            from .federation import Federation
            gstats = Federation(env, config).stats()
    except SystemExit:
        gstats = {"nodes": 0, "edges": 0}
    return {
        "memory": {"running": mem["running"], "url": mem["url"], "pid": mem["pid"]},
        "graph": {"adapter": adapter, "nodes": gstats["nodes"], "edges": gstats["edges"]},
        "docs_watcher": detect_docs_watcher(env),
    }
