"""maind health — клиентский healthcheck связи проекта с хабом (память + maind MCP).

Запускается ИЗ проекта (--cwd) или по id (--project). НЕ блокирует: всегда печатает статус
connected|partial|standalone и подсказки. --fix поднимает память и дописывает MCP-серверы.

Здесь же провиженеры доставки «приоритета №1» в проекты (вызываются из sync):
- health-doc  — управляемый блок priority-block.md в <project>/CLAUDE.md (idempotent, по хэшу);
- health-hook — SessionStart-хук в <project>/.claude/settings.json + копия скрипта (синкается).
Источник истины — templates/health/* в самом maind; mode install/update/auto задаёт «область»."""
import copy
import json
import os
import stat
from pathlib import Path

from core.http import HTTPUnauthorizedError

from .common import (atomic_write_json, atomic_write_text, backup_file,
                     content_hash, die, parse_args, upsert_block, warn)
from .config import load_config
from .mcpconfig import check_hygiene
from .memory import auth_headers, resolve_secret
from .memory import forget as mem_forget
from .memory import health as mem_health
from .memory import recall as mem_recall
from .memory import resolve_ports
from .memory import store as mem_store
from .namespaces import namespaces_of, private_scope
from .probe import probe_project
from .projects import get as get_project
from .projects import match_cwd
from .provision.workspace import load_settings

BLOCK_MARKER = "maind:healthcheck"
HOOK_SCRIPT = ".claude/maind-health.sh"
FEATURE_HOOK_SCRIPT = ".claude/maind-feature-log.sh"
MEMORY_HOOK_SCRIPT = ".claude/maind-memory.sh"


def _status(ok: bool) -> str:
    """Метка чек-строки для cmd_health."""
    return "ok  " if ok else "FAIL"


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
    scope. Ловит раскол (хук пишет не в тот стор), сломанный forget и потерю изоляции.
    401 различается от прочих сбоев отдельно (findings §2: /agentmemory/health не 401'ит,
    поэтому «недоступен» и «неавторизован» неразличимы без реального протектед-вызова —
    ровно это здесь и делает store/recall/forget)."""
    if not memory_reachable:
        return {"ok": False, "detail": "демон не запущен"}
    _, _, url = resolve_ports(env, config)
    headers = auth_headers(resolve_secret(env, config))
    scope = private_scope(project)
    token = f"maind-health-probe-{project['id']}"
    try:
        res = mem_store(url, scope, "health-probe", token, headers=headers)
        mid = (res.get("memory") or {}).get("id") if isinstance(res, dict) else None
        found = any(token in (r.get("text") or "")
                    for r in mem_recall(url, scope, token, headers=headers))
        if mid:
            mem_forget(url, scope, mid, headers=headers)          # чисто за собой
        return {"ok": bool(found),
                "detail": scope if found else "запись не нашлась при recall (раскол стора?)"}
    except HTTPUnauthorizedError:
        return {"ok": False, "detail": "неавторизован (401) — проверьте секрет памяти"}
    except RuntimeError as e:
        return {"ok": False, "detail": str(e)}


# ── отчёт ────────────────────────────────────────────────────────────────────
def health_report(env, config, project, *, memory_reachable=None, provider_context=None,
                  deep=False):
    """Состояние связи проекта; мутирующий round-trip выполняется только в deep-режиме."""
    pid = project["id"]
    if memory_reachable is None:
        _, _, url = resolve_ports(env, config)
        memory_reachable = mem_health(url)
    rep = probe_project(env, config, project, memory_reachable=memory_reachable,
                        provider_context=provider_context)
    c = rep.get("configured", {})
    hook_mode = hook_memory_mode(project)
    native_off, digest_hook = _native_memory_state(project)
    roundtrip = (memory_roundtrip(env, config, project, memory_reachable) if deep
                 else {"ok": None, "detail": "пропущен (используйте --deep)"})
    local = project.get("local_path")
    hygiene = check_hygiene(os.path.expanduser(local)) if local else []
    hints = []
    if not memory_reachable:
        hints.append("демон памяти не запущен → maind start --only memory")
    if hook_mode not in ("maind", "manual"):
        hints.append(f"память проекта не настроена → maind onboard {pid} --memory manual")
    elif hook_mode == "maind" and not (native_off and digest_hook):
        hints.append("MODE=maind, но native-память не выключена / нет digest-инжекта → "
                     f"maind onboard {pid} --memory maind")
    elif hook_mode == "manual" and not native_off:
        hints.append("MODE=manual, но native-память включена → "
                     f"maind onboard {pid} --memory manual")
    if deep and not roundtrip["ok"] and memory_reachable:
        hints.append(f"память не проходит round-trip ({roundtrip['detail']}) — "
                     "remember/recall идут в разные сторы?")
    if not c.get("maind_mcp"):
        hints.append(f"нет maind MCP в проекте → maind sync --only mcp --project {pid}")
    for issue in hygiene:
        f = issue["file"]
        if "tracked-in-git" in issue["problems"]:
            hints.append(f"{f} закоммичен в git (должен быть только .example) → "
                         f"git rm --cached {f} (файл на диске останется)")
        if "missing-example" in issue["problems"]:
            hints.append(f"нет {f}.example → maind sync --only mcp --project {pid} "
                         "(эмитит портируемый шаблон + .gitignore; чинит только если "
                         "провайдерский план проекта зелёный — отказавший unmanaged-target "
                         "эмиссии не получит)")
    result = {
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
        "mcp_hygiene": hygiene,
        "path": rep.get("path"), "hints": hints,
    }
    if "provider_trust" in rep:
        result["provider_trust"] = rep["provider_trust"]
    return result


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


def _remove_script_hook(project, dry, *, name, script_rel, event, marker, detail):
    """Remove a managed hook registration and script while preserving other hooks."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, name, "absent", False, dry, "нет пути")
    settings_path = path / ".claude" / "settings.json"
    settings, existed = load_settings(settings_path)
    changed = False
    groups = (settings.get("hooks") or {}).get(event) or []
    kept_groups = []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if marker not in h.get("command", "")]
        if len(hooks) != len(group.get("hooks", [])):
            changed = True
        if hooks:
            kept_groups.append({**group, "hooks": hooks})
    if changed:
        settings["hooks"][event] = kept_groups
        if not kept_groups:
            settings["hooks"].pop(event, None)
    script_path = path / script_rel
    if script_path.exists():
        changed = True
    if changed and not dry:
        if existed:
            backup_file(settings_path)
            atomic_write_json(settings_path, settings)
        script_path.unlink(missing_ok=True)
    return _result(pid, name, "stale" if changed else "fresh", changed, dry, detail)


def _apply_script_hook(env, project, mode, dry, *, name, template, script_rel, detail,
                       skip_detail=".claude/", subst=None, event="SessionStart",
                       marker="maind-health", render_safe=False, extra_stale=None,
                       on_settings=None):
    """Идемпотентный скелет hook-провиженера: рендер шаблона → состояние (absent/stale/fresh
    с учётом наличия/дрейфа хука в .claude/settings.json) → _act(mode) → backup+запись скрипта
    (chmod +x) → merge хука в settings. Опции под расхождения провиженеров:
    render_safe — шаблон может отсутствовать (standalone-safe → absent);
    extra_stale(settings)->bool — доп. триггер устаревания (напр. native-память не выключена);
    on_settings(merged)->bool — правка settings перед записью + признак «грязно» (форсит запись)."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, name, "absent", False, dry, "нет пути")
    try:
        script = _render(env, template, subst or {})
    except OSError as e:                         # шаблон недоступен (standalone-safe)
        if render_safe:
            return _result(pid, name, "absent", False, dry, f"шаблон недоступен: {e}")
        raise
    script_path = path / script_rel
    state = _file_state(script_path, script)
    settings_path = path / ".claude" / "settings.json"
    command = f"bash {script_path}"
    settings, _existed = load_settings(settings_path)
    # пробная (на копии) запись хука: состояние = скрипт устарел ИЛИ хука ещё нет в настройках
    _, hook_changed = _merge_session_hook(copy.deepcopy(settings), command,
                                          event=event, marker=marker)
    if state == "fresh" and (hook_changed or (extra_stale(settings) if extra_stale else False)):
        state = "stale"
    if not _act(mode, state):
        return _result(pid, name, state, False, dry, skip_detail)
    if not dry:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if script_path.is_file():
            backup_file(script_path)
        atomic_write_text(script_path, script)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        merged, changed = _merge_session_hook(settings, command, event=event, marker=marker)
        if on_settings and on_settings(merged):
            changed = True
        if changed:
            if settings_path.is_file():
                backup_file(settings_path)
            atomic_write_json(settings_path, merged)
    return _result(pid, name, state, True, dry, detail)


def apply_health_hook(env, config, project, mode, dry):
    """SessionStart-скрипт + запись хука в <project>/.claude/settings.json."""
    return _apply_script_hook(
        env, project, mode, dry, name="health-hook",
        template="health/session-start-hook.sh", script_rel=HOOK_SCRIPT,
        detail=".claude/maind-health.sh + settings")


def apply_feature_log_hook(env, config, project, mode, dry):
    """SessionEnd-скрипт фиксации нового коммита в общую память (maind fleet log) + хук."""
    return _apply_script_hook(
        env, project, mode, dry, name="feature-log-hook",
        template="health/feature-log-hook.sh", script_rel=FEATURE_HOOK_SCRIPT,
        subst={"PROJECT": project["id"]}, event="SessionEnd", marker="maind-feature-log",
        detail=".claude/maind-feature-log.sh + settings")


def revert_health_hook(env, config, project, mode, dry):
    return _remove_script_hook(project, dry, name="health-hook", script_rel=HOOK_SCRIPT,
                               event="SessionStart", marker="maind-health",
                               detail="SessionStart health отключён")


def revert_feature_log_hook(env, config, project, mode, dry):
    return _remove_script_hook(project, dry, name="feature-log-hook",
                               script_rel=FEATURE_HOOK_SCRIPT, event="SessionEnd",
                               marker="maind-feature-log",
                               detail="автопубликация коммитов отключена")


def apply_memory_hook(env, config, project, mode, dry):
    """SessionStart-хук инжекта дайджеста памяти (additionalContext) + выключение НАТИВНОЙ
    авто-памяти (`autoMemoryEnabled:false`). Ставится для проектов на `MODE=maind`: maind
    становится источником контекста вместо native MEMORY.md (даёт авто-загрузку, которой у
    демона иначе нет). Идемпотентно. Парный «не-maind» путь делает revert — `revert_memory_hook`."""
    def _disable_native(merged):
        merged["autoMemoryEnabled"] = False          # выключить нативную авто-память
        return True                                  # settings всегда дописываются
    return _apply_script_hook(
        env, project, mode, dry, name="memory-hook",
        template="health/memory-digest-hook.sh", script_rel=MEMORY_HOOK_SCRIPT,
        marker="maind-memory", render_safe=True,
        extra_stale=lambda s: s.get("autoMemoryEnabled") is not False,
        on_settings=_disable_native, skip_detail=".claude/ (native off + digest)",
        detail=".claude/maind-memory.sh + autoMemoryEnabled:false")


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


def configure_manual_memory(env, config, project, dry):
    """Keep mAInd available through MCP, remove digest injection, keep native auto-memory off."""
    result = _remove_script_hook(project, dry, name="memory-hook",
                                 script_rel=MEMORY_HOOK_SCRIPT, event="SessionStart",
                                 marker="maind-memory", detail="manual MCP mode")
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return result
    settings_path = path / ".claude" / "settings.json"
    settings, existed = load_settings(settings_path)
    native_changed = settings.get("autoMemoryEnabled") is not False
    if native_changed and not dry:
        settings["autoMemoryEnabled"] = False
        if existed:
            backup_file(settings_path)
        atomic_write_json(settings_path, settings)
    if native_changed:
        result["changed"] = not dry
        result["status"] = "dry" if dry else "ok"
        result["state"] = "stale"
    return result


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_health(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--cwd": "bool", "--fix": "bool",
                                "--strict": "bool", "--json": "bool", "--deep": "bool"})
    if opts["help"]:
        print("maind health [--project ID | --cwd] [--fix] [--strict] [--deep] [--json]")
        return
    config, _src = load_config(env)
    project = _target(env, config, opts)
    from .provision.sync import contexts
    context = contexts(env, config, [project])[0]
    rep = health_report(env, config, project, provider_context=context, deep=opts["deep"])

    hygiene_fixable = any("missing-example" in i["problems"] for i in rep["mcp_hygiene"])
    if opts["fix"] and (rep["status"] != "connected" or hygiene_fixable):
        if not rep["memory_daemon"]:
            try:
                from .memory import start as mem_start
                mem_start(env, config)
            except SystemExit as e:
                warn(f"не удалось поднять память: {e}")
        from .provision.sync import run_sync
        run_sync(env, config, [project], only="mcp")
        rep = health_report(env, config, project, provider_context=context, deep=opts["deep"])

    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _, _, url = resolve_ports(env, config)
        icon = {"connected": "✓", "partial": "⚠", "standalone": "✗"}.get(rep["status"], "·")
        print(f"{icon} mAInd health — project:{rep['id']} (scope {rep['scope']})")
        print(f"  [{_status(rep['memory_daemon'])}] демон памяти ({url})")
        print(f"  [{_status(rep['maind_mcp'])}] maind MCP в проекте")
        print(f"  [{_status(rep['hook_memory_mode'] == 'maind')}] хук памяти MODE=maind "
              f"({rep['hook_memory_mode'] or 'не задан'})")
        if rep['hook_memory_mode'] == 'maind':
            print(f"  [{_status(rep['native_memory_off'] and rep['digest_hook'])}] native off + "
                  "digest-инжект (SessionStart)")
        if opts["deep"]:
            print(f"  [{_status(rep['memory_roundtrip'])}] память round-trip (write→recall→forget)")
        else:
            print("  [skip] память round-trip (только --deep)")
        print(f"  [{_status(not rep['mcp_hygiene'])}] конфиг-гигиена .mcp.json "
              "(real gitignored + .example в репо)")
        print(f"  ns: [{', '.join(rep['namespaces'])}]  статус: {rep['status']}")
        for row in rep.get("provider_trust", ()):
            print(f"  [{_status(row['green'])}] provider:{row['provider_id']} trust"
                  + (f" ({', '.join(row['diagnostics'])})" if row["diagnostics"] else ""))
        for h in rep["hints"]:
            print(f"    → {h}")
    # strict падает, если связь не connected, память не проходит round-trip
    # или доверие любого включённого/обязательного provider не подтверждено.
    trust_failed = any(not row["green"] for row in rep.get("provider_trust", ()))
    deep_failed = opts["deep"] and not rep["memory_roundtrip"]
    if opts["strict"] and (rep["status"] != "connected" or deep_failed or trust_failed):
        raise SystemExit(1)
