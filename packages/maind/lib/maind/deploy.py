"""maind deploy — провижининг: раскатать MCP-серверы хаба на проекты («клонировать сеть»).

Из config.json вписываем в MCP-конфиг каждого проекта серверы хаба (agent-memory + maind),
со scope project:<id>. Слияние недеструктивное (mcpconfig: upsert + .bak), идемпотентное, opt-in.
Демон не обязателен — пишем клиентский конфиг и при выключенном демоне (с предупреждением).
Код-граф (движок Serena) опционален: --with-code (legacy --with-graphify), и только если бинарь
движка установлен в PATH (иначе warn-and-skip). Политика — из секции code_graph конфига."""
import json
import os
import shutil
from pathlib import Path

from . import codegraph
from .common import die, now_iso, parse_args, warn
from .config import load_config
from .mcpconfig import (MCP_FILES, MCPConfigError, load_mcp, mcp_path,
                        merge_server, remove_server, write_mcp)
from .memory import health, resolve_ports
from .projects import get as get_project
from .projects import listing, write_config


def _agentmemory_entry(env, config, scope):
    _, _, url = resolve_ports(env, config)
    bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
    return {"command": str(bin_path), "args": ["mcp"],
            "env": {"AGENTMEMORY_URL": url, "AGENTMEMORY_NAMESPACE": scope}}


def _maind_entry(scope):
    # Индирекция вместо абсолютного пути: `${MAIND_BIN:-maind}` раскрывается Claude Code из
    # ОКРУЖЕНИЯ процесса (проектный .env он не читает) → дефолт `maind` резолвится по PATH
    # (~/.local/bin кладёт install.sh). Тот же MAIND_BIN, что у health-хуков. Переносимо на
    # другую машину/CI и при переносе репо — в .mcp.json не остаётся захардкоженного /home/...
    return {"command": "${MAIND_BIN:-maind}",
            "args": ["mcp", "--scope", scope]}


def _code_entry(project_path, command, args):
    """MCP-сервер код-графа проекта (по умолчанию Serena). Плейсхолдер {root} в args →
    путь проекта. command/args/имя сервера — из политики code_graph + per-project override."""
    root = str(project_path)
    return {"command": command, "args": [a.replace("{root}", root) for a in args]}


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


def deploy_project(env, config, project, *, targets=None, with_code=None,
                   maind_server=True, with_agentmemory=False, dry=False):
    """Раскатать серверы хаба в один проект. with_code=None → берётся из политики/полей проекта
    (code|graphify). Память проекта — через сервер `maind` (изоляция по scope на стороне maind);
    raw-сервер `agentmemory` НЕ раскатывается (он пишет мимо scope-маркера → невидимо для
    scoped-recall) и УДАЛЯЕТСЯ из .mcp.json, если остался от старых деплоев. Возвращает
    result-dict или None (пропуск)."""
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

    st = codegraph.settings(config)
    if with_code is None:
        with_code = codegraph.enabled(project, st)
    entries = {}
    if maind_server:
        entries["maind"] = _maind_entry(scope)               # память через maind (изоляция)
    if with_agentmemory:                                     # legacy/opt-in raw-сервер
        entries["agentmemory"] = _agentmemory_entry(env, config, scope)
    drop = [] if with_agentmemory else ["agentmemory"]       # чистим raw-сервер из старых .mcp.json
    code_state = "disabled"
    if with_code:
        gcmd = codegraph.command(project, st)
        gargs = codegraph.cmd_args(project, st)
        gname = codegraph.server_name(project, st)
        if shutil.which(gcmd):
            entries[gname] = _code_entry(project_path, gcmd, gargs)
            code_state = "written"
        else:
            code_state = "skipped-not-installed"
            warn(f"проект '{pid}': команда '{gcmd}' код-графа не найдена в PATH — пропускаю "
                 f"(установите, напр. uvx для Serena, или задайте code_command)")

    written = []
    skipped = []
    for _channel, path in _resolve_targets(project_path, targets):
        rel = str(path.relative_to(project_path))
        try:
            data, _existed = load_mcp(path)
        except MCPConfigError as e:
            # Битый конфиг ОДНОГО канала (напр. .cursor/mcp.json) не должен валить весь
            # деплой/sync — файл не трогаем, предупреждаем и идём к следующему каналу.
            warn(f"проект '{pid}': {e} — канал пропущен")
            skipped.append(rel)
            continue
        changed_any = False
        for name, entry in entries.items():
            data, changed = merge_server(data, name, entry)
            changed_any = changed_any or changed
        for name in drop:                                    # снять устаревший raw-сервер
            data, changed = remove_server(data, name)
            changed_any = changed_any or changed
        if changed_any:
            write_mcp(path, data, dry=dry)
        written.append({"file": rel, "servers": list(entries), "changed": changed_any})

    return {"id": pid, "scope": scope, "written": written, "skipped": skipped,
            "code": code_state, "code_server": codegraph.server_name(project, st),
            "servers": list(entries), "targets": [w["file"] for w in written]}


def mark_deployed(config, project_id, result):
    """Отметить проект deployed в config.json (вызывающий сохраняет через write_config)."""
    proj = get_project(config, project_id)
    if proj is None:
        return config
    proj["deployed"] = True
    proj["deployed_at"] = now_iso()
    proj["mcp"] = {
        "agentmemory": "agentmemory" in result["servers"],
        "maind": "maind" in result["servers"],
        "code": result["code"] == "written",
        "code_server": result.get("code_server"),
        "targets": result["targets"],
        "scope": result["scope"],
    }
    return config


def cmd_deploy(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--all": "bool", "--targets": "str",
                                "--with-code": "bool", "--with-graphify": "bool",
                                "--no-maind-server": "bool", "--with-agentmemory": "bool",
                                "--dry-run": "bool", "--json": "bool"})
    config, _src = load_config(env)
    if opts["project"]:
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"проект не найден в config.json: {opts['project']}")
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
        # флаг (--with-code|--with-graphify) форсит код-граф; иначе None → из конфига проекта
        with_code = True if (opts["with_code"] or opts["with_graphify"]) else None
        res = deploy_project(env, config, proj, targets=opts["targets"] or None,
                             with_code=with_code, with_agentmemory=opts["with_agentmemory"],
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
        gf = "" if r["code"] == "disabled" else f", code:{r['code']}"
        sk = f"  ⚠ пропущено битых: {', '.join(r['skipped'])}" if r.get("skipped") else ""
        print(f"  {r['id']:<18} scope={r['scope']:<24} → {', '.join(r['targets'])} "
              f"({', '.join(r['servers'])}{gf}){sk}")
