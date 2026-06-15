"""Мониторинг экосистемы: состояние проектов и демонов (read-only, fail-soft).

JSON-first — это контракт для будущей GUI-панели. Все пробы устойчивы: нет файла/демона/
systemctl → безопасные поля, без исключений."""
import json
import os
import subprocess
from pathlib import Path

from .mcpconfig import MCP_FILES, has_server
from .memory import health, resolve_ports
from .memory import status as memory_status
from .workspace import norm_path, trusted_dirs

_SKILL_KEY = {"swissknifeman": "swissknifeman", "laravel-boost": "laravel_boost"}


def _read_skills_lock(project_path):
    f = project_path / "skills-lock.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def probe_project(env, config, project, *, memory_reachable=None, trusted=None):
    """Состояние одного проекта (read-only). status ∈ connected|partial|standalone|missing-path.

    trusted: множество доверенных каталогов (из hub-настроек). None → читаем один раз тут;
    в цикле передавайте заранее вычисленное (как memory_reachable)."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if trusted is None:
        trusted = trusted_dirs(env)
    if not path or not path.is_dir():
        return {"id": pid, "name": project.get("name", pid), "path": local,
                "status": "missing-path", "configured": {}, "skills": {}, "daemons": {},
                "trusted": False}

    def any_has(name):
        return any(has_server(path / rel, name) for rel in MCP_FILES.values())

    files = [rel for rel in MCP_FILES.values() if (path / rel).is_file()]
    lock = _read_skills_lock(path)
    skills = {"total": 0, "swissknifeman": 0, "laravel_boost": 0, "local": 0}
    if lock:
        for e in (lock.get("skills") or {}).values():
            skills["total"] += 1
            skills[_SKILL_KEY.get(e.get("source", "local"), "local")] += 1

    agentmemory_mcp = any_has("agentmemory")
    configured = {
        "agentmemory_mcp": agentmemory_mcp, "maind_mcp": any_has("maind"),
        "graphify_mcp": any_has("graphify"), "mcp_files": files,
        "skills_lock": lock is not None, "skills_count": skills["total"],
        "boost": (path / "boost.json").is_file(),
        "deployed_flag": bool(project.get("deployed")),
    }

    if memory_reachable is None:
        _, _, url = resolve_ports(env, config)
        memory_reachable = health(url)

    if agentmemory_mcp and memory_reachable:
        status = "connected"
    elif agentmemory_mcp or configured["deployed_flag"]:
        status = "partial"   # сервер без живого демона, или флаг без сервера (drift)
    else:
        status = "standalone"

    return {"id": pid, "name": project.get("name", pid), "path": str(path),
            "memory_scope": project.get("memory_scope") or f"project:{pid}",
            "configured": configured, "skills": skills,
            "daemons": {"memory_reachable": memory_reachable},
            "trusted": norm_path(local) in trusted, "status": status}


def detect_docs_watcher(env):
    """brain docs-watcher: pidfile ~/.brain/docs-watcher.pid (kill -0) → systemctl --user."""
    pid_file = env.home / ".brain" / "docs-watcher.pid"
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return {"running": True, "via": "pidfile", "pid": pid}
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", "docs-watcher.service"],
                           capture_output=True, text=True, check=False, timeout=3)
        if r.stdout.strip() == "active":
            return {"running": True, "via": "systemd", "pid": None}
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return {"running": False, "via": None, "pid": None}


def probe_hub(env, config):
    """Состояние хаба: память, граф, docs-watcher (read-only)."""
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
