"""maind deploy — провижининг: раскатать MCP-серверы хаба на проекты («клонировать сеть»).

Из config.json вписываем в MCP-конфиг каждого проекта серверы хаба (agent-memory + maind),
со scope project:<id>. Слияние недеструктивное (mcpconfig: upsert + .bak), идемпотентное, opt-in.
Демон не обязателен — пишем клиентский конфиг и при выключенном демоне (с предупреждением).
Код-граф (движок Serena) опционален: --with-code (legacy --with-graphify), и только если бинарь
движка установлен в PATH (иначе warn-and-skip). Политика — из секции code_graph конфига."""
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import codegraph, pplxweb
from ..common import die, now_iso, parse_args, warn
from ..config import load_config, resolve_provider_config
from ..mcpconfig import (MCP_FILES, MCPConfigError, load_mcp, mcp_path,
                        merge_server, reconcile_gitignore, remove_server,
                        write_example, write_mcp)
from ..memory import health, resolve_ports
from ..projects import get as get_project
from ..projects import listing, write_config
from ..provider_deploy import (apply_provider_artifacts, generate_conformance_report,
                               plan_provider_artifacts, plan_provider_deploy,
                               semantic_servers)


@dataclass(frozen=True)
class ProviderProjectionContext:
    """P1 selection and P5 projections resolved once for a project operation."""
    providers: tuple
    effective_providers: tuple
    projections: tuple


def _provider_projections(env, config, project):
    """Legacy compatibility projection over the public one-resolution seam."""
    return provider_projection_context(env, config, project).projections


def provider_projection_context(env, config, project):
    """Public P6 seam: one effective-provider resolution and P5 projections."""
    harness_root = Path(env.root).parent / "harness"
    if not harness_root.is_dir():
        harness_root = Path(__file__).resolve().parents[3].parent / "harness"
    harness_lib = str(harness_root / "lib")
    if harness_lib not in sys.path:
        sys.path.insert(0, harness_lib)
    from core import ProviderConfigCatalog, ProviderId
    from harness.mcp import load_mcp_catalog, plan_mcp_projection
    resolved = resolve_provider_config(
        config, ProviderConfigCatalog("1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX), (), ()),
        project["id"])
    if resolved.selection is None:
        codes = ",".join(item.code for item in resolved.diagnostics)
        raise ValueError(codes or "MAIND_PROVIDER_RESOLUTION_INVALID")
    effective_providers = tuple(row for row in resolved.selection if row.enabled)
    providers = tuple(row.provider_id for row in effective_providers)
    if not providers:
        raise ValueError("MAIND_PROVIDER_DISABLED")
    catalog = load_mcp_catalog(harness_root / "configs/common/mcp/catalog.json")
    projections = tuple(plan_mcp_projection(
        catalog, provider_id=provider,
        bindings_path=harness_root / "configs" / provider.value / "mcp/bindings.json",
        selected=(), trusted=True) for provider in providers)
    return ProviderProjectionContext(providers, effective_providers, projections)


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


def provider_semantic_inventory(env, config, project, *, with_code, maind_server,
                                with_agentmemory):
    """Caller-owned server descriptors; P5 supplies provider projections separately."""
    scope = project.get("memory_scope") or f"project:{project['id']}"
    st = codegraph.settings(config)
    if with_code is None:
        with_code = codegraph.enabled(project, st)
    code = None
    if with_code:
        code = _code_entry(Path(os.path.expanduser(project["local_path"])),
                           codegraph.command(project, st), codegraph.cmd_args(project, st))
    pw = pplxweb.settings(config)
    perplexity = pplxweb.entry(project, pw) if pplxweb.enabled(project, pw) else None
    return semantic_servers(maind=_maind_entry(scope) if maind_server else None,
                            agentmemory=_agentmemory_entry(env, config, scope) if with_agentmemory else None,
                            codegraph=code, perplexity=perplexity)


def deploy_project(env, config, project, *, targets=None, with_code=None,
                   maind_server=True, with_agentmemory=False, dry=False,
                   provider_projections=None, provider_repair=False):
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
    provider_plan = None
    provider_changed = False
    if provider_projections is not None:
        provider_plan = plan_provider_deploy(
            provider_projections,
            provider_semantic_inventory(env, config, project, with_code=with_code,
                                        maind_server=maind_server,
                                        with_agentmemory=with_agentmemory))
        provider_check = plan_provider_artifacts(project_path, provider_plan, repair=provider_repair)
        if provider_check["severity"] == "error":
            raise ValueError("MAIND_PROVIDER_DEPLOY_REFUSED")
        provider_changed = any(
            getattr(action.action, "value", action.action) != "noop"
            for action in provider_check["plan"].actions)
        if not dry:
            apply_provider_artifacts(project_path, provider_plan, repair=provider_repair)
    emit_example = bool((config.get("mcp") or {}).get("emit_example"))  # opt-in: .example + .gitignore

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

    pw = pplxweb.settings(config)                            # hub-managed perplexity-web
    if pplxweb.enabled(project, pw):                         # opt-in: mcp.perplexity_web.enabled
        entries[pplxweb.server_name(pw)] = pplxweb.entry(project, pw)

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
        if emit_example:                                     # портируемый .example + гигиена .gitignore
            write_example(path, data, project_path, dry=dry)
            reconcile_gitignore(project_path, rel, dry=dry)
        written.append({"file": rel, "servers": list(entries), "changed": changed_any})

    return {"id": pid, "scope": scope, "written": written, "skipped": skipped,
            "code": code_state, "code_server": codegraph.server_name(project, st),
            "servers": list(entries), "targets": [w["file"] for w in written],
            "provider_plan": provider_plan, "provider_changed": provider_changed}


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
        "perplexity_web": pplxweb.server_name(pplxweb.settings(config)) in result["servers"],
        "targets": result["targets"],
        "scope": result["scope"],
    }
    provider_plan = result.get("provider_plan")
    if provider_plan is not None:
        proj["provider_deploy"] = {
            row.provider_id.value: {
                "status": row.status,
                "target_scope": row.target_scope,
                "target_path": row.target_path,
                "server_ids": list(row.server_ids),
                "diagnostic": row.diagnostic,
                "provenance": {
                    "source_path": row.artifact.provenance.canonical_sources[0].path,
                    "content_hash": row.artifact.provenance.canonical_sources[0].content_hash,
                } if row.artifact is not None else None,
            }
            for row in provider_plan.results
        }
    return config


def cmd_deploy(env, argv):
    opts, _ = parse_args(argv, {"--project": "str", "--all": "bool", "--targets": "str",
                                "--with-code": "bool", "--with-graphify": "bool",
                                "--no-maind-server": "bool", "--with-agentmemory": "bool",
                                "--dry-run": "bool", "--json": "bool",
                                "--conformance": "str", "--repair": "bool"})
    if opts["conformance"]:
        harness_configs = Path(env.root).parent / "harness/configs"
        plan = generate_conformance_report(harness_configs, opts["conformance"])
        print(f"provider deploy conformance: {len(plan.results)} provider rows")
        return
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
        projections = _provider_projections(env, config, proj)
        res = deploy_project(env, config, proj, targets=opts["targets"] or None,
                             with_code=with_code, with_agentmemory=opts["with_agentmemory"],
                             maind_server=not opts["no_maind_server"], dry=opts["dry_run"],
                             provider_projections=projections, provider_repair=opts["repair"])
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
