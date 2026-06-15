"""maind deploy — провижининг: раскатать MCP-серверы хаба на проекты («клонировать сеть»).

Из .maind.json вписываем в MCP-конфиг каждого проекта серверы хаба (agent-memory + maind),
со scope project:<id>. Слияние недеструктивное (mcpconfig: upsert + .bak), идемпотентное, opt-in.
Демон не обязателен — пишем клиентский конфиг и при выключенном демоне (с предупреждением).
graphify отложен: --with-graphify, и только если установлен graphify-mcp (иначе warn-and-skip)."""
import json
import os
import shutil
from pathlib import Path

from .common import die, now_iso, parse_args, warn
from .config import load_config
from .mcpconfig import MCP_FILES, load_mcp, mcp_path, merge_server, write_mcp
from .memory import health, resolve_ports
from .projects import get as get_project
from .projects import listing, write_config


def _agentmemory_entry(env, config, scope):
    _, _, url = resolve_ports(env, config)
    bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
    return {"command": str(bin_path), "args": ["mcp"],
            "env": {"AGENTMEMORY_URL": url, "AGENTMEMORY_NAMESPACE": scope}}


def _maind_entry(env, scope):
    return {"command": str(env.root / "bin" / "maind"),
            "args": ["mcp", "--scope", scope]}


def _graphify_entry(project_path, command="graphify-mcp"):
    """MCP-сервер код-графа проекта. command переопределяется полем graphify_command
    (задел под сторонний code-intelligence MCP); бинаря может не быть — см. deploy_project."""
    return {"command": command, "args": ["--root", str(project_path)]}


def _resolve_targets(project_path, opt_targets):
    """[(channel, path)]: .mcp.json всегда; .cursor/mcp.json если есть .cursor/ или указан явно."""
    if opt_targets:
        channels = [c.strip() for c in opt_targets.split(",") if c.strip()]
    else:
        channels = ["claude"]
        if (project_path / ".cursor").is_dir():
            channels.append("cursor")
    out = []
    for ch in channels:
        if ch not in MCP_FILES:
            die(f"неизвестный target: {ch} (claude|cursor|vscode)")
        out.append((ch, mcp_path(project_path, ch)))
    return out


def deploy_project(env, config, project, *, targets=None, with_graphify=False,
                   maind_server=True, dry=False):
    """Раскатать серверы хаба в один проект. Возвращает result-dict или None (пропуск)."""
    pid = project["id"]
    local = project.get("local_path")
    if not local:
        warn(f"проект '{pid}': нет local_path — пропускаю")
        return None
    project_path = Path(os.path.expanduser(local))
    if not project_path.is_dir():
        warn(f"проект '{pid}': путь не найден — {project_path}")
        return None
    scope = project.get("memory_scope") or f"project:{pid}"

    entries = {"agentmemory": _agentmemory_entry(env, config, scope)}
    if maind_server:
        entries["maind"] = _maind_entry(env, scope)
    graphify_state = "disabled"
    if with_graphify:
        gcmd = project.get("graphify_command", "graphify-mcp")
        if shutil.which(gcmd):
            entries["graphify"] = _graphify_entry(project_path, gcmd)
            graphify_state = "written"
        else:
            graphify_state = "skipped-not-installed"
            warn(f"проект '{pid}': команда '{gcmd}' не найдена в PATH — пропускаю graphify "
                 f"(код-граф опционален; установите бинарь или задайте graphify_command)")

    written = []
    for _channel, path in _resolve_targets(project_path, targets):
        data, _existed = load_mcp(path)
        changed_any = False
        for name, entry in entries.items():
            data, changed = merge_server(data, name, entry)
            changed_any = changed_any or changed
        if changed_any:
            write_mcp(path, data, dry=dry)
        written.append({"file": str(path.relative_to(project_path)),
                        "servers": list(entries), "changed": changed_any})

    return {"id": pid, "scope": scope, "written": written, "graphify": graphify_state,
            "servers": list(entries), "targets": [w["file"] for w in written]}


def mark_deployed(config, project_id, result):
    """Отметить проект deployed в .maind.json (вызывающий сохраняет через write_config)."""
    proj = get_project(config, project_id)
    if proj is None:
        return config
    proj["deployed"] = True
    proj["deployed_at"] = now_iso()
    proj["mcp"] = {
        "agentmemory": "agentmemory" in result["servers"],
        "maind": "maind" in result["servers"],
        "graphify": result["graphify"] == "written",
        "targets": result["targets"],
        "scope": result["scope"],
    }
    return config


def cmd_deploy(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--all": "bool", "--targets": "str",
                                "--with-graphify": "bool", "--no-maind-server": "bool",
                                "--dry-run": "bool", "--json": "bool"})
    config, _src = load_config(env)
    if opts["project"]:
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"проект не найден в .maind.json: {opts['project']}")
        projects = [proj]
    elif opts["all"]:
        projects = [p for p in listing(env, config) if p.get("enabled", True)]
    else:
        die("укажите --project <id> или --all")

    _, _, url = resolve_ports(env, config)
    if not health(url):
        warn(f"демон памяти не отвечает на {url} — конфиг всё равно пишу "
             f"(поднимите: maind start --only memory)")

    results = []
    for proj in projects:
        res = deploy_project(env, config, proj, targets=opts["targets"] or None,
                             with_graphify=opts["with_graphify"],
                             maind_server=not opts["no_maind_server"], dry=opts["dry_run"])
        if res is None:
            continue
        results.append(res)
        if not opts["dry_run"]:
            config = mark_deployed(config, proj["id"], res)

    if not opts["dry_run"] and results:
        write_config(env, config)

    if opts["json"]:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if not results:
        print("нечего деплоить (нет проектов с существующим local_path)")
        return
    for r in results:
        gf = "" if r["graphify"] == "disabled" else f", graphify:{r['graphify']}"
        print(f"  {r['id']:<18} scope={r['scope']:<24} → {', '.join(r['targets'])} "
              f"({', '.join(r['servers'])}{gf})")
