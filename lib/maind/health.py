"""maind health — клиентский healthcheck связи проекта с хабом (память + maind MCP).

Запускается ИЗ проекта (--cwd) или по id (--project). НЕ блокирует: всегда печатает статус
connected|partial|standalone и подсказки. --fix поднимает память и дописывает MCP-серверы.

Здесь же провиженеры доставки «приоритета №1» в проекты (вызываются из sync):
- health-doc  — управляемый блок priority-block.md в <project>/CLAUDE.md (idempotent, по хэшу);
- health-hook — SessionStart-хук в <project>/.claude/settings.json + копия скрипта (синкается).
Источник истины — templates/health/* в самом maind; mode install/update/auto задаёт «область»."""
import json
import os
import stat
from pathlib import Path

from .common import (atomic_write_json, backup_file, content_hash, die, parse_args,
                     upsert_block, warn)
from .config import load_config
from .memory import health as mem_health
from .memory import resolve_ports
from .namespaces import namespaces_of
from .probe import probe_project
from .projects import get as get_project
from .projects import listing
from .workspace import load_settings, norm_path

BLOCK_MARKER = "maind:healthcheck"
HOOK_SCRIPT = ".claude/maind-health.sh"


# ── шаблоны ──────────────────────────────────────────────────────────────────
def _render(env, relpath, subst):
    """Прочитать шаблон <maind>/templates/<relpath> и подставить {{KEY}} → значение."""
    text = (env.root / "templates" / relpath).read_text(encoding="utf-8")
    for k, v in subst.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _maind_bin(env):
    return str(env.root / "bin" / "maind")


# ── отчёт ────────────────────────────────────────────────────────────────────
def health_report(env, config, project, *, memory_reachable=None):
    """Состояние связи одного проекта с хабом + подсказки по починке."""
    pid = project["id"]
    if memory_reachable is None:
        _, _, url = resolve_ports(env, config)
        memory_reachable = mem_health(url)
    rep = probe_project(env, config, project, memory_reachable=memory_reachable)
    c = rep.get("configured", {})
    hints = []
    if not memory_reachable:
        hints.append("демон памяти не запущен → maind start --only memory")
    if not c.get("agentmemory_mcp"):
        hints.append(f"нет agentmemory MCP в проекте → maind sync --only mcp --project {pid}")
    if not c.get("maind_mcp"):
        hints.append(f"нет maind MCP в проекте → maind sync --only mcp --project {pid}")
    return {
        "id": pid, "scope": rep.get("memory_scope", f"project:{pid}"),
        "namespaces": sorted(namespaces_of(project)),
        "status": rep.get("status", "standalone"),
        "memory_daemon": memory_reachable,
        "agentmemory_mcp": bool(c.get("agentmemory_mcp")),
        "maind_mcp": bool(c.get("maind_mcp")),
        "graphify_mcp": bool(c.get("graphify_mcp")),
        "path": rep.get("path"), "hints": hints,
    }


def _target(env, config, opts):
    """Целевой проект: --project <id> | --cwd (матч cwd по local_path) | дефолт = cwd."""
    if opts.get("project"):
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"проект не найден в .maind.json: {opts['project']}")
        return proj
    cwd = norm_path(os.getcwd())
    for p in listing(env, config):
        lp = p.get("local_path")
        if not lp:
            continue
        base = norm_path(lp)
        if cwd == base or cwd.startswith(base + os.sep):
            return p
    die("не удалось определить проект из текущего каталога — укажите --project <id>")


# ── провиженеры (вызываются из sync) ─────────────────────────────────────────
def _act(mode, state):
    """Нужно ли применять при данном mode и состоянии артефакта (absent/stale/fresh)."""
    if state == "fresh":
        return False
    if mode == "install":
        return state == "absent"
    if mode == "update":
        return state == "stale"
    return True  # auto


def _result(pid, name, state, applied, dry, detail=""):
    status = "dry" if dry and applied else ("ok" if applied else "skip")
    return {"provisioner": name, "id": pid, "status": status,
            "changed": applied and not dry, "state": state, "detail": detail}


def apply_health_doc(env, config, project, mode, dry):
    """Управляемый блок priority-block.md в <project>/CLAUDE.md."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "health-doc", "absent", False, dry, "нет пути")
    block = _render(env, "health/priority-block.md",
                    {"SCOPE": project.get("memory_scope") or f"project:{pid}",
                     "PROJECT": pid})
    claude = path / "CLAUDE.md"
    text = claude.read_text(encoding="utf-8") if claude.is_file() else ""
    new_text, _changed, state = upsert_block(text, block, BLOCK_MARKER)
    if not _act(mode, state):
        return _result(pid, "health-doc", state, False, dry, "CLAUDE.md")
    if not dry:
        if claude.is_file():
            backup_file(claude)
        claude.write_text(new_text, encoding="utf-8")
    return _result(pid, "health-doc", state, True, dry, "CLAUDE.md")


def _file_state(path, content):
    if not path.is_file():
        return "absent"
    try:
        cur = path.read_text(encoding="utf-8")
    except OSError:
        return "absent"
    return "fresh" if content_hash(cur) == content_hash(content) else "stale"


def _merge_session_hook(settings, command):
    """Идемпотентно добавить/обновить SessionStart-хук maind в настройки Claude."""
    hooks = settings.setdefault("hooks", {})
    sessions = hooks.setdefault("SessionStart", [])
    for group in sessions:
        for h in group.get("hooks", []):
            if "maind-health" in h.get("command", ""):
                if h["command"] != command:
                    h["command"] = command
                    return settings, True
                return settings, False
    sessions.append({"hooks": [{"type": "command", "command": command}]})
    return settings, True


def apply_health_hook(env, config, project, mode, dry):
    """SessionStart-скрипт + запись хука в <project>/.claude/settings.json."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "health-hook", "absent", False, dry, "нет пути")
    script = _render(env, "health/session-start-hook.sh", {"MAIND_BIN": _maind_bin(env)})
    script_path = path / HOOK_SCRIPT
    state = _file_state(script_path, script)
    settings_path = path / ".claude" / "settings.json"
    command = f"bash {script_path}"
    settings, _existed = load_settings(settings_path)
    _, hook_changed = _merge_session_hook(json.loads(json.dumps(settings)), command)
    # состояние = скрипт устарел ИЛИ хука ещё нет в настройках
    if state == "fresh" and hook_changed:
        state = "stale"
    if not _act(mode, state):
        return _result(pid, "health-hook", state, False, dry, ".claude/")
    if not dry:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if script_path.is_file():
            backup_file(script_path)
        script_path.write_text(script, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        merged, changed = _merge_session_hook(settings, command)
        if changed:
            if settings_path.is_file():
                backup_file(settings_path)
            atomic_write_json(settings_path, merged)
    return _result(pid, "health-hook", state, True, dry, ".claude/maind-health.sh + settings")


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_health(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--cwd": "bool", "--fix": "bool",
                                "--strict": "bool", "--json": "bool"})
    if opts["help"]:
        print("maind health [--project ID | --cwd] [--fix] [--strict] [--json]")
        return
    config, _src = load_config(env)
    project = _target(env, config, opts)
    rep = health_report(env, config, project)

    if opts["fix"] and rep["status"] != "connected":
        if not rep["memory_daemon"]:
            try:
                from .memory import start as mem_start
                mem_start(env, config)
            except SystemExit as e:
                warn(f"не удалось поднять память: {e}")
        from .sync import run_sync
        run_sync(env, config, [project], only="mcp")
        rep = health_report(env, config, project)

    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _, _, url = resolve_ports(env, config)
        icon = {"connected": "✓", "partial": "⚠", "standalone": "✗"}.get(rep["status"], "·")
        print(f"{icon} mAInd health — project:{rep['id']} (scope {rep['scope']})")
        ok = lambda b: "ok  " if b else "FAIL"
        print(f"  [{ok(rep['memory_daemon'])}] демон памяти ({url})")
        print(f"  [{ok(rep['agentmemory_mcp'])}] agentmemory MCP в проекте")
        print(f"  [{ok(rep['maind_mcp'])}] maind MCP в проекте")
        print(f"  статус: {rep['status']}")
        for h in rep["hints"]:
            print(f"    → {h}")
    if opts["strict"] and rep["status"] != "connected":
        raise SystemExit(1)
