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

from .common import (atomic_write_json, atomic_write_text, backup_file,
                     content_hash, die, parse_args, upsert_block, warn)
from .config import load_config
from .memory import forget as mem_forget
from .memory import health as mem_health
from .memory import recall as mem_recall
from .memory import resolve_ports
from .memory import store as mem_store
from .namespaces import namespaces_of, private_scope
from .probe import probe_project
from .projects import get as get_project
from .projects import match_cwd
from .workspace import load_settings

BLOCK_MARKER = "maind:healthcheck"
HOOK_SCRIPT = ".claude/maind-health.sh"


# ── шаблоны ──────────────────────────────────────────────────────────────────
def _render(env, relpath, subst):
    """Прочитать шаблон <maind>/templates/<relpath> и подставить {{KEY}} → значение."""
    text = (env.root / "templates" / relpath).read_text(encoding="utf-8")
    for k, v in subst.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


# Путь к лаунчеру maind в хук-скриптах больше НЕ подставляется: шаблоны резолвят его
# в рантайме (env MAIND_BIN → PATH), чтобы в артефакт не попадал машинно-специфичный
# абсолютный путь. См. templates/health/*.sh.


# ── проба памяти и режима хука ───────────────────────────────────────────────
def hook_memory_mode(project):
    """MODE из <project>/.claude/memory.env.ini (режим хука памяти) или None.
    Источник истины «намерения» памяти проекта — читают и health, и sync (memory-hook)."""
    lp = project.get("local_path")
    if not lp:
        return None
    f = Path(os.path.expanduser(lp)) / ".claude" / "memory.env.ini"
    if not f.is_file():
        return None
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("MODE="):
            return s.split("=", 1)[1].split("#")[0].strip().strip("\"'")
    return None


def _native_memory_state(project):
    """(native_off, digest_hook_wired) из <project>/.claude/settings.json — для MODE=maind
    нативная авто-память должна быть выключена, а SessionStart-инжект дайджеста — на месте."""
    lp = project.get("local_path")
    if not lp:
        return (None, None)
    settings, _ = load_settings(Path(os.path.expanduser(lp)) / ".claude" / "settings.json")
    native_off = settings.get("autoMemoryEnabled") is False
    cmds = [h.get("command", "") for g in (settings.get("hooks") or {}).get("SessionStart", [])
            for h in g.get("hooks", [])]
    return (native_off, any("maind-memory" in c for c in cmds))


def memory_roundtrip(env, config, project, memory_reachable):
    """Доказать, что память РЕАЛЬНО работает: write→recall→forget по temp-факту в приватном
    scope. Ловит раскол (хук пишет не в тот стор), сломанный forget и потерю изоляции."""
    if not memory_reachable:
        return {"ok": False, "detail": "демон не запущен"}
    _, _, url = resolve_ports(env, config)
    scope = private_scope(project)
    token = f"maind-health-probe-{project['id']}"
    try:
        res = mem_store(url, scope, "health-probe", token)
        mid = (res.get("memory") or {}).get("id") if isinstance(res, dict) else None
        found = any(token in (r.get("text") or "") for r in mem_recall(url, scope, token))
        if mid:
            mem_forget(url, scope, mid)          # чисто за собой
        return {"ok": bool(found),
                "detail": scope if found else "запись не нашлась при recall (раскол стора?)"}
    except RuntimeError as e:
        return {"ok": False, "detail": str(e)}


# ── отчёт ────────────────────────────────────────────────────────────────────
def health_report(env, config, project, *, memory_reachable=None):
    """Состояние связи одного проекта с хабом + проба памяти + подсказки по починке."""
    pid = project["id"]
    if memory_reachable is None:
        _, _, url = resolve_ports(env, config)
        memory_reachable = mem_health(url)
    rep = probe_project(env, config, project, memory_reachable=memory_reachable)
    c = rep.get("configured", {})
    hook_mode = hook_memory_mode(project)
    native_off, digest_hook = _native_memory_state(project)
    roundtrip = memory_roundtrip(env, config, project, memory_reachable)
    hints = []
    if not memory_reachable:
        hints.append("демон памяти не запущен → maind start --only memory")
    if hook_mode != "maind":
        hints.append("хук памяти не в режиме maind → maind onboard "
                     f"{pid} (запишет .claude/memory.env.ini MODE=maind)")
    elif not (native_off and digest_hook):
        hints.append("MODE=maind, но native-память не выключена / нет digest-инжекта → "
                     f"maind onboard {pid} (autoMemoryEnabled:false + .claude/maind-memory.sh)")
    if not roundtrip["ok"] and memory_reachable:
        hints.append(f"память не проходит round-trip ({roundtrip['detail']}) — "
                     "remember/recall идут в разные сторы?")
    if not c.get("maind_mcp"):
        hints.append(f"нет maind MCP в проекте → maind sync --only mcp --project {pid}")
    return {
        "id": pid, "scope": rep.get("memory_scope", f"project:{pid}"),
        "namespaces": sorted(namespaces_of(project)),
        "status": rep.get("status", "standalone"),
        "memory_daemon": memory_reachable,
        "hook_memory_mode": hook_mode,
        "native_memory_off": native_off,
        "digest_hook": digest_hook,
        "memory_roundtrip": roundtrip["ok"],
        "agentmemory_mcp": bool(c.get("agentmemory_mcp")),
        "maind_mcp": bool(c.get("maind_mcp")),
        "code_mcp": bool(c.get("code_mcp")),
        "path": rep.get("path"), "hints": hints,
    }


def _target(env, config, opts):
    """Целевой проект: --project <id> | --cwd (матч cwd по local_path) | дефолт = cwd."""
    if opts.get("project"):
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"проект не найден в config.json: {opts['project']}")
        return proj
    proj = match_cwd(env, config)
    if proj is None:
        die("не удалось определить проект из текущего каталога — укажите --project <id>")
    return proj


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
        atomic_write_text(claude, new_text)
    return _result(pid, "health-doc", state, True, dry, "CLAUDE.md")


def _file_state(path, content):
    if not path.is_file():
        return "absent"
    try:
        cur = path.read_text(encoding="utf-8")
    except OSError:
        return "absent"
    return "fresh" if content_hash(cur) == content_hash(content) else "stale"


def _merge_session_hook(settings, command, event="SessionStart", marker="maind-health"):
    """Идемпотентно добавить/обновить хук maind (по marker в команде) в событие event."""
    hooks = settings.setdefault("hooks", {})
    sessions = hooks.setdefault(event, [])
    for group in sessions:
        for h in group.get("hooks", []):
            if marker in h.get("command", ""):
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
    script = _render(env, "health/session-start-hook.sh", {})
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
        atomic_write_text(script_path, script)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        merged, changed = _merge_session_hook(settings, command)
        if changed:
            if settings_path.is_file():
                backup_file(settings_path)
            atomic_write_json(settings_path, merged)
    return _result(pid, "health-hook", state, True, dry, ".claude/maind-health.sh + settings")


FEATURE_HOOK_SCRIPT = ".claude/maind-feature-log.sh"


def apply_feature_log_hook(env, config, project, mode, dry):
    """SessionEnd-скрипт фиксации нового коммита в общую память (maind fleet log) + хук."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "feature-log-hook", "absent", False, dry, "нет пути")
    script = _render(env, "health/feature-log-hook.sh", {"PROJECT": pid})
    script_path = path / FEATURE_HOOK_SCRIPT
    state = _file_state(script_path, script)
    settings_path = path / ".claude" / "settings.json"
    command = f"bash {script_path}"
    settings, _existed = load_settings(settings_path)
    _, hook_changed = _merge_session_hook(json.loads(json.dumps(settings)), command,
                                          event="SessionEnd", marker="maind-feature-log")
    if state == "fresh" and hook_changed:
        state = "stale"
    if not _act(mode, state):
        return _result(pid, "feature-log-hook", state, False, dry, ".claude/")
    if not dry:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if script_path.is_file():
            backup_file(script_path)
        atomic_write_text(script_path, script)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        merged, changed = _merge_session_hook(settings, command, event="SessionEnd",
                                              marker="maind-feature-log")
        if changed:
            if settings_path.is_file():
                backup_file(settings_path)
            atomic_write_json(settings_path, merged)
    return _result(pid, "feature-log-hook", state, True, dry,
                   ".claude/maind-feature-log.sh + settings")


MEMORY_HOOK_SCRIPT = ".claude/maind-memory.sh"


def apply_memory_hook(env, config, project, mode, dry):
    """SessionStart-хук инжекта дайджеста памяти (additionalContext) + выключение НАТИВНОЙ
    авто-памяти (`autoMemoryEnabled:false`). Ставится для проектов на `MODE=maind`: maind
    становится источником контекста вместо native MEMORY.md (даёт авто-загрузку, которой у
    демона иначе нет). Идемпотентно. Парный «не-maind» путь делает revert — `revert_memory_hook`."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "memory-hook", "absent", False, dry, "нет пути")
    try:
        script = _render(env, "health/memory-digest-hook.sh", {})
    except OSError as e:                         # шаблон недоступен (standalone-safe)
        return _result(pid, "memory-hook", "absent", False, dry, f"шаблон недоступен: {e}")
    script_path = path / MEMORY_HOOK_SCRIPT
    state = _file_state(script_path, script)
    settings_path = path / ".claude" / "settings.json"
    command = f"bash {script_path}"
    settings, _existed = load_settings(settings_path)
    _, hook_changed = _merge_session_hook(json.loads(json.dumps(settings)), command,
                                          marker="maind-memory")
    native_off = settings.get("autoMemoryEnabled") is False
    if state == "fresh" and (hook_changed or not native_off):
        state = "stale"
    if not _act(mode, state):
        return _result(pid, "memory-hook", state, False, dry, ".claude/ (native off + digest)")
    if not dry:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if script_path.is_file():
            backup_file(script_path)
        atomic_write_text(script_path, script)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        merged, _ = _merge_session_hook(settings, command, marker="maind-memory")
        merged["autoMemoryEnabled"] = False          # выключить нативную авто-память
        if settings_path.is_file():
            backup_file(settings_path)
        atomic_write_json(settings_path, merged)
    return _result(pid, "memory-hook", state, True, dry,
                   ".claude/maind-memory.sh + autoMemoryEnabled:false")


def revert_memory_hook(env, config, project, dry):
    """Откат к нативной памяти: снять SessionStart-хук инжекта и вернуть авто-память
    (`autoMemoryEnabled` убрать). Для проектов, ушедших с `MODE=maind` на native."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "memory-hook", "absent", False, dry, "нет пути")
    settings_path = path / ".claude" / "settings.json"
    settings, existed = load_settings(settings_path)
    changed = False
    sessions = (settings.get("hooks") or {}).get("SessionStart") or []
    for group in sessions:
        kept = [h for h in group.get("hooks", []) if "maind-memory" not in h.get("command", "")]
        if len(kept) != len(group.get("hooks", [])):
            group["hooks"] = kept
            changed = True
    if settings.pop("autoMemoryEnabled", None) is not None:
        changed = True
    if changed and not dry and existed:
        backup_file(settings_path)
        atomic_write_json(settings_path, settings)
    return _result(pid, "memory-hook", "stale" if changed else "fresh", changed, dry,
                   "native восстановлена")


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
        print(f"  [{ok(rep['maind_mcp'])}] maind MCP в проекте")
        print(f"  [{ok(rep['hook_memory_mode'] == 'maind')}] хук памяти MODE=maind "
              f"({rep['hook_memory_mode'] or 'не задан'})")
        if rep['hook_memory_mode'] == 'maind':
            print(f"  [{ok(rep['native_memory_off'] and rep['digest_hook'])}] native off + "
                  "digest-инжект (SessionStart)")
        print(f"  [{ok(rep['memory_roundtrip'])}] память round-trip (write→recall→forget)")
        print(f"  ns: [{', '.join(rep['namespaces'])}]  статус: {rep['status']}")
        for h in rep["hints"]:
            print(f"    → {h}")
    # strict падает, если связь не connected ИЛИ память не проходит round-trip
    if opts["strict"] and (rep["status"] != "connected" or not rep["memory_roundtrip"]):
        raise SystemExit(1)
