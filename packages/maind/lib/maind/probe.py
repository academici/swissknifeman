"""Мониторинг экосистемы: состояние проектов и демонов (read-only, fail-soft).

JSON-first — это контракт для будущей GUI-панели. Все пробы устойчивы: нет файла/демона/
systemctl → безопасные поля, без исключений."""
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
    """`.claude/agent-pack.lock.json` (harness agent-packs) или None. Структура:
    {schema, packs: {<name>: {version, files:[{local_modified}], …}}}."""
    f = project_path / ".claude" / "agent-pack.lock.json"
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

    # Слой ролей/агентов (harness agent-packs): какие паки установлены + есть ли локальные правки.
    ap_lock = _read_agent_pack_lock(path)
    ap_names = sorted((ap_lock.get("packs") or {}).keys()) if ap_lock else []
    ap_modified = bool(ap_lock and any(
        fl.get("local_modified")
        for pk in (ap_lock.get("packs") or {}).values()
        for fl in (pk.get("files") or [])))
    agent_packs = {"installed": ap_names, "count": len(ap_names),
                   "lock": ap_lock is not None, "modified": ap_modified}

    mem_mcp = any_has("maind")       # сервер памяти проекта = maind (raw agentmemory выведен)
    code_server = codegraph.server_name(project, codegraph.settings(config))
    configured = {
        "agentmemory_mcp": any_has("agentmemory"),   # info: остался ли raw-сервер (footgun)
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
        status = "partial"   # сервер без живого демона, или флаг без сервера (drift)
    else:
        status = "standalone"

    return {"id": pid, "name": project.get("name", pid), "path": str(path),
            "memory_scope": project.get("memory_scope") or f"project:{pid}",
            "configured": configured, "skills": skills, "agent_packs": agent_packs,
            "daemons": {"memory_reachable": memory_reachable},
            "trusted": norm_path(local) in trusted, "status": status}


def drift_hints(env, config, report):
    """Рассинхроны слоёв проекта с точной командой починки (read-only). Единый источник
    для `projects status`, `health` и зонтичного `swissknifeman status`. Каждый элемент —
    {layer, issue, fix}. Пусто = всё консистентно (по тому, что видно из файлов)."""
    pid = report.get("id")
    c = report.get("configured", {})
    hints = []
    # MCP / память: сервер настроен, но демон молчит — ИЛИ флаг без сервера (drift провижининга).
    if report.get("status") == "partial":
        if c.get("maind_mcp") and not report.get("daemons", {}).get("memory_reachable"):
            hints.append({"layer": "memory",
                          "issue": "MCP памяти настроен, но демон не отвечает",
                          "fix": "maind start --only memory"})
        elif c.get("deployed_flag") and not c.get("maind_mcp"):
            hints.append({"layer": "mcp",
                          "issue": "deployed-флаг есть, но maind-сервер не в .mcp.json",
                          "fix": f"maind sync --only mcp --project {pid}"})
    # Роли/агенты: профиль типа проекта ожидает паки, которых нет в lock.
    try:
        from .projects import get as _get
        from .provision.sync import _resolve_agent_pack
        expected = _resolve_agent_pack(config, _get(config, pid) or {})
    except (SystemExit, Exception):       # fail-soft: профиль не найден → без подсказки
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
            pass  # pidfile битый/процесс мёртв — падаем в проверку через systemd ниже
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", "docs-watcher.service"],
                           capture_output=True, text=True, check=False, timeout=3)
        if r.stdout.strip() == "active":
            return {"running": True, "via": "systemd", "pid": None}
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass  # нет systemctl / таймаут — считаем watcher не запущенным
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
