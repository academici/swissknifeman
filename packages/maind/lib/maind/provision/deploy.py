"""maind deploy — provisioning: roll out MCP-hub servers for projects («clone network»).

From config.json enter in MCP-config of each project hub servers (agent-memory + maind),
with scope project:<id>. Non-destructive merger (mcpconfig: upsert + a backup under .swissknifeman/backups), idempotent, opt-in.
The daemon is not required - we write the client config even when the daemon is turned off (with warning).
Code graph (engine Serena) optional: --with-code (legacy --with-graphify), and only if the binary
engine is installed in PATH (otherwise warn-and-skip). Politics - from section code_graph config."""
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from aicore.provider.values import ProviderId
from aicore.artifacts.lock import LOCK_RELATIVE_PATH, apply_plan
from aicore.util.partners import PartnerUnavailable
from .. import codegraph, harness_link, pplxweb
from aicore.util.term import die, now_iso, warn
from aicore.util.cli import parse_args
from aicore.config import ConfigError
from ..config import (PROJECT_LEGACY_CARRIER, PROJECT_TOML_CARRIER, load_config,
                      resolve_provider_config, toml_project_providers)
from ..mcpconfig import (MCP_FILES, MCPConfigError, load_mcp, mcp_path,
                        merge_server, reconcile_gitignore, remove_server,
                        write_example, write_mcp)
from ..memory import health, resolve_ports
from ..projects import get as get_project
from ..projects import listing, write_registry
from ..provider_deploy import (generate_conformance_report, plan_provider_artifacts,
                               plan_provider_deploy,
                               plan_d104_bootstrap_transfer, project_provider_preflight,
                               bootstrap_transfer_projection, plan_d108_operation,
                               apply_d108_operation, SemanticServer, semantic_servers,
                               warn_legacy_providers)


@dataclass(frozen=True)
class ProviderProjectionContext:
    """P1 selection and P5 projections resolved once for a project operation."""
    providers: tuple
    effective_providers: tuple
    projections: tuple


def provider_operation_green(result):
    """A refused D104 bootstrap makes the whole deploy non-green, not its provider row."""
    provider_plan = result.get("provider_plan")
    bootstrap = result.get("bootstrap_transfer") or {}
    return ((provider_plan is None or provider_plan.green)
            and bootstrap.get("status") != "refused")


def _provider_projections(env, config, project):
    """Legacy compatibility projection over the public one-resolution seam."""
    return provider_projection_context(env, config, project).projections


def _load_project_provider_config(project):
    """Load the project provider selection from its active carrier.

    Returns ``(providers, carrier)``: the ``[aicore.providers]`` table of the project layer when it
    sets a selection, else the legacy regular ``.swissknife.json#/providers`` of the exact
    registered root (one MAIND_LEGACY_PROVIDERS warning), else ``(None, <legacy carrier>)``."""
    local_path = project.get("local_path")
    if not local_path:
        return None, PROJECT_LEGACY_CARRIER
    root = Path(os.path.expanduser(local_path))
    try:
        from_toml = toml_project_providers(root)
    except ConfigError as exc:
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_INVALID") from exc
    if from_toml is not None:
        return from_toml, PROJECT_TOML_CARRIER
    providers = _load_legacy_project_providers(root)
    if providers is not None:
        warn_legacy_providers(root / PROJECT_LEGACY_CARRIER)
    return providers, PROJECT_LEGACY_CARRIER


def _load_legacy_project_providers(root):
    """Load the exact registered root's regular legacy project provider carrier."""
    carrier = root / PROJECT_LEGACY_CARRIER
    try:
        carrier_stat = carrier.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_INVALID") from exc
    if stat.S_ISLNK(carrier_stat.st_mode) or not stat.S_ISREG(carrier_stat.st_mode):
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_UNSAFE")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(carrier, flags)
    except OSError as exc:
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_UNSAFE") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_UNSAFE")
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = None
            payload = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_INVALID") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_INVALID")
    providers = payload.get("providers")
    if providers is None:
        return None
    if not isinstance(providers, dict):
        raise ValueError("MAIND_PROJECT_PROVIDER_CONFIG_INVALID")
    return providers


def provider_projection_context(env, config, project):
    """Public P6 seam: one effective-provider resolution and P5 projections."""
    project_config, project_carrier = _load_project_provider_config(project)
    resolved = resolve_provider_config(
        config, None, project["id"], project_config=project_config,
        project_carrier=project_carrier)
    if resolved.selection is None:
        codes = ",".join(item.code for item in resolved.diagnostics)
        raise ValueError(codes or "MAIND_PROVIDER_RESOLUTION_INVALID")
    effective_providers = tuple(row for row in resolved.selection if row.enabled)
    providers = tuple(row.provider_id for row in effective_providers)
    if not providers:
        raise ValueError("MAIND_PROVIDER_DISABLED")
    try:
        projections = harness_link.base_projections(providers)
    except PartnerUnavailable as error:
        # No harness: the provider steps are skipped, the legacy hub servers still deploy.
        warn(str(error))
        projections = ()
    return ProviderProjectionContext(providers, effective_providers, projections)


def _agentmemory_entry(env, config, scope):
    _, _, url = resolve_ports(env, config)
    bin_path = env.root / "node_modules" / ".bin" / "agentmemory"
    return {"command": str(bin_path), "args": ["mcp"],
            "env": {"AGENTMEMORY_URL": url, "AGENTMEMORY_NAMESPACE": scope}}


def _maind_entry(scope):
    # MCP clients execute command directly, without shell parameter expansion.  The installer
    # places `maind` on PATH, so the bare command is portable for Claude Code and Codex.
    return {"command": "maind",
            "args": ["mcp", "--scope", scope]}


def _code_entry(project_path, command, args):
    """MCP-project code graph server (default Serena). Placeholder {root} in args →
    project path. command/args/server name - from policy code_graph + per-project override."""
    root = str(project_path)
    return {"command": command, "args": [a.replace("{root}", root) for a in args]}


def _resolve_targets(project_path, opt_targets):
    """[(channel, path)]: .mcp.json always; .cursor/mcp.json if available .cursor/ or specified explicitly."""
    if opt_targets:
        channels = [c.strip() for c in opt_targets.split(",") if c.strip()]
    else:
        channels = ["claude"]
        if (project_path / ".cursor").is_dir():
            channels.append("cursor")
    out = []
    for ch in channels:
        if ch not in MCP_FILES:
            die(f"unknown target: {ch} (claude|cursor|vscode)")
        out.append((ch, mcp_path(project_path, ch)))
    return out


def provider_semantic_inventory(env, config, project, *, with_code, maind_server,
                                with_agentmemory, d108=False):
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
    rows = semantic_servers(maind=_maind_entry(scope) if maind_server else None,
                            agentmemory=_agentmemory_entry(env, config, scope) if with_agentmemory else None,
                            codegraph=code, perplexity=perplexity)
    if d108:
        # D114: only the sealed D108 candidate serializes configured MCP identities.
        # Ordinary provider inventory retains its stable internal role labels.
        names = {"codegraph": codegraph.server_name(project, st),
                 "perplexity": pplxweb.server_name(pw)}
        rows = tuple(SemanticServer(names.get(row.id, row.id), row.binding, row.required)
                     for row in rows)
    extra = (project.get("mcp") or {}).get("extra_servers") or {}
    if not isinstance(extra, dict) or any(not isinstance(value, dict)
                                          for value in extra.values()):
        raise ValueError("MAIND_SEMANTIC_SERVER_INVALID")
    extra_rows = tuple(SemanticServer(str(server_id), dict(extra[server_id]))
                       for server_id in sorted(extra))
    if len({row.id for row in rows + extra_rows}) != len(rows) + len(extra_rows):
        raise ValueError("MAIND_SEMANTIC_SERVER_DUPLICATE")
    return rows + extra_rows


def deploy_project(env, config, project, *, targets=None, with_code=None,
                   maind_server=True, with_agentmemory=False, dry=False,
                   provider_projections=None, provider_repair=False, d108=False):
    """Roll out the hub servers into one project. with_code=None → is taken from the policy/project fields
    (code|graphify). Project memory - via server `maind` (insulation by scope on the side maind);
    raw-server `agentmemory` DOES NOT roll out (he writes by scope-marker → invisible to
    scoped-recall) and REMOVED from .mcp.json, if left over from old deployments. Returns
    result-dict or None (pass)."""
    pid = project["id"]
    local = project.get("local_path")
    if not local:
        warn(f"project '{pid}': no local_path — skipping")
        return None
    project_path = Path(os.path.expanduser(local))
    if not project_path.is_dir():
        warn(f"project '{pid}': path not found - {project_path}")
        return None
    scope = project.get("memory_scope") or f"project:{pid}"
    if provider_projections is not None or d108:
        if not harness_link.available():
            warn(f"project '{pid}': PARTNER_UNAVAILABLE: harness not found (set SKM_HARNESS_ROOT "
                 f"or put harness on PATH) — provider projection skipped")
            provider_projections, d108 = None, False
        elif provider_projections is not None and not provider_projections:
            provider_projections = None      # no projections: reported where they were requested
    provider_plan = None
    provider_changed = False
    bootstrap_transfer = None
    bootstrap_projection = None
    if provider_projections is not None or d108:
        inventory = provider_semantic_inventory(
            env, config, project, with_code=with_code, maind_server=maind_server,
            with_agentmemory=with_agentmemory, d108=d108)
        if d108:
            d108_root = project_path.resolve()
            operation = plan_d108_operation(
                d108_root, config, pid, inventory,
                expected_root=d108_root)
            provider_plan = operation.deploy
            bootstrap_transfer = operation.transfer
            bootstrap_projection = bootstrap_transfer_projection("admitted", bootstrap_transfer)
            provider_changed = operation.carrier.changed or any(
                getattr(action.action, "value", action.action) != "noop"
                for action in operation.chained_plan.actions)
            if not dry:
                apply_d108_operation(project_path, operation)
        else:
            exclusions = {}
            code_providers = project.get("code_providers")
            if with_code is not False and isinstance(code_providers, list):
                allowed_code = set(code_providers)
                for projection in provider_projections:
                    provider_id = projection.provider_id.value
                    if provider_id not in allowed_code:
                        exclusions[provider_id] = ("codegraph",)
            provider_plan = plan_provider_deploy(
                provider_projections, inventory,
                excluded_server_ids_by_provider=exclusions)
        if d108:
            ordinary_check = {"severity": "green", "plan": operation.chained_plan}
        else:
        # This ordinary P2 check deliberately does not include transfer artifacts: their
        # pre-transfer state does not exist yet and must not manufacture a staged green.
            ordinary_check = plan_provider_artifacts(project_path, provider_plan,
                                                     repair=provider_repair)
        has_codex = any(projection.provider_id.value == "codex"
                        for projection in provider_projections)
        bootstrap_root = project_path / ".codex/hooks.json"
        bootstrap_lock = project_path / LOCK_RELATIVE_PATH
        bootstrap_handler = project_path / ".codex/hooks/lifecycle.py"
        # A completed transfer has both its lock and handler, so second-run behavior stays
        # on the ordinary managed path. Every incomplete candidate still asks the P2 oracle.
        if not d108 and has_codex and bootstrap_root.is_file() and (
                not bootstrap_lock.exists() or not bootstrap_handler.is_file()):
            try:
                bootstrap_transfer = plan_d104_bootstrap_transfer(project_path)
            except ValueError:
                bootstrap_projection = bootstrap_transfer_projection(
                    "refused", diagnostic="MAIND_PROVIDER_DEPLOY_REFUSED")
            else:
                refused = any(getattr(action.action, "value", action.action) == "refuse"
                              for action in bootstrap_transfer.plan.actions)
                bootstrap_projection = bootstrap_transfer_projection(
                    "refused" if refused else "admitted", bootstrap_transfer,
                    "MAIND_PROVIDER_DEPLOY_REFUSED" if refused else None)
        elif not d108:
            bootstrap_projection = bootstrap_transfer_projection("not-selected")

        provider_check = ordinary_check
        provider_plan = project_provider_preflight(provider_plan, ordinary_check)
        refused = (bootstrap_projection["status"] == "refused"
                   or ordinary_check["severity"] == "error")
        if not refused and not d108:
            provider_changed = any(
                getattr(action.action, "value", action.action) != "noop"
                for action in ordinary_check["plan"].actions)
            if bootstrap_transfer is not None:
                provider_changed = provider_changed or any(
                    getattr(action.action, "value", action.action) != "noop"
                    for action in bootstrap_transfer.plan.actions)
            if not dry and bootstrap_transfer is not None:
                apply_plan(project_path, bootstrap_transfer.plan)
                # Replan only after the admitted transfer has actually completed. This
                # preserves the initial no-write refusal gate and catches a changed root
                # before any ordinary provider artifact is applied.
                provider_check = plan_provider_artifacts(
                    project_path, provider_plan, repair=provider_repair,
                    extra_artifacts=bootstrap_transfer.artifacts)
                if provider_check["severity"] == "error":
                    raise ValueError("MAIND_PROVIDER_DEPLOY_REFUSED")
            if not dry:
                apply_plan(project_path, provider_check["plan"])
    # default-on (P2.4): merge_defaults already set up EMIT_EXAMPLE_DEFAULT, if the key
    # is not specified - here we only read the total, opt-out `false` in config.json respected.
    emit_example = bool((config.get("mcp") or {}).get("emit_example"))

    st = codegraph.settings(config)
    if with_code is None:
        with_code = codegraph.enabled(project, st)
    entries = {}
    if maind_server:
        entries["maind"] = _maind_entry(scope)               # memory via maind (insulation)
    if with_agentmemory:                                     # legacy/opt-in raw-server
        entries["agentmemory"] = _agentmemory_entry(env, config, scope)
    drop = [] if with_agentmemory else ["agentmemory"]       # clean raw-server from old .mcp.json
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
            warn(f"project '{pid}': command '{gcmd}' code-graph not found in PATH — skipping "
                 f"(set e.g. uvx for Serena, or set code_command)")

    pw = pplxweb.settings(config)                            # hub-managed perplexity-web
    if pplxweb.enabled(project, pw):                         # opt-in: mcp.perplexity_web.enabled
        entries[pplxweb.server_name(pw)] = pplxweb.entry(project, pw)

    written = []
    skipped = []
    legacy_targets = () if provider_plan is not None else _resolve_targets(project_path, targets)
    for _channel, path in legacy_targets:
        rel = str(path.relative_to(project_path))
        try:
            data, _existed = load_mcp(path)
        except MCPConfigError as e:
            # Broken config of ONE channel (e.g. .cursor/mcp.json) should not fall all
            # deployment/sync — do not touch the file, warn and move on to the next channel.
            warn(f"project '{pid}': {e} — channel skipped")
            skipped.append(rel)
            continue
        changed_any = False
        for name, entry in entries.items():
            data, changed = merge_server(data, name, entry)
            changed_any = changed_any or changed
        for name in drop:                                    # remove obsolete raw-server
            data, changed = remove_server(data, name)
            changed_any = changed_any or changed
        if changed_any:
            write_mcp(path, data, dry=dry)
        if emit_example:                                     # portable .example + hygiene .gitignore
            write_example(path, data, project_path, dry=dry)
            reconcile_gitignore(project_path, rel, dry=dry)
        written.append({"file": rel, "servers": list(entries), "changed": changed_any})

    if provider_plan is not None:
        written = [{"file": row.target_path, "servers": list(row.server_ids),
                    "changed": provider_changed} for row in provider_plan.results
                   if row.status == "planned"]
        # provider-managed .example + .gitignore (P2.4, D91): predicate — emit_example
        # enabled, operation not refused, string "planned", channel claude-code; bytes
        # .example — from row.rendered (the same render that hit the target), there is no second render.
        if emit_example and not refused:
            for row in provider_plan.results:
                if row.status == "planned" and row.provider_id is ProviderId.CLAUDE_CODE:
                    example_data = json.loads(row.rendered.decode("utf-8"))
                    write_example(project_path / row.target_path, example_data,
                                 project_path, dry=dry)
                    reconcile_gitignore(project_path, row.target_path, dry=dry)

    return {"id": pid, "scope": scope, "written": written, "skipped": skipped,
            "code": code_state, "code_server": codegraph.server_name(project, st),
            "servers": list(entries), "targets": [w["file"] for w in written],
            "provider_plan": provider_plan, "provider_changed": provider_changed,
            "bootstrap_transfer": bootstrap_projection}


def mark_deployed(config, project_id, result):
    """Mark project deployed in the registry (caller saves via write_registry)."""
    proj = get_project(config, project_id)
    if proj is None:
        return config
    proj["deployed"] = True
    proj["deployed_at"] = now_iso()
    prev_mcp = proj.get("mcp") or {}
    extra_servers = prev_mcp.get("extra_servers")
    proj["mcp"] = {
        "agentmemory": "agentmemory" in result["servers"],
        "maind": "maind" in result["servers"],
        "code": result["code"] == "written",
        "code_server": result.get("code_server"),
        "perplexity_web": pplxweb.server_name(pplxweb.settings(config)) in result["servers"],
        "targets": result["targets"],
        "scope": result["scope"],
    }
    if extra_servers:
        proj["mcp"]["extra_servers"] = extra_servers
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
        try:
            plan = generate_conformance_report(opts["conformance"])
        except PartnerUnavailable as error:
            die(str(error))
        print(f"provider deploy conformance: {len(plan.results)} provider rows")
        return
    config, _src = load_config(env)
    if opts["project"]:
        proj = get_project(config, opts["project"])
        if proj is None:
            die(f"project not found in config.json: {opts['project']}")
        projects = [proj]
    elif opts["all"]:
        projects = [p for p in listing(env, config) if p.get("enabled", True)]
    else:
        die("specify --project <id> or --all")

    _, _, url = resolve_ports(env, config)
    if not health(url):
        warn(f"memory daemon not responding to {url} — I’m still writing the config "
             f"(raise: maind start --only memory)")

    results = []
    config_changed = False
    for proj in projects:
        # flag (--with-code|--with-graphify) force code graph; otherwise None → from the project config
        with_code = True if (opts["with_code"] or opts["with_graphify"]) else None
        projections = _provider_projections(env, config, proj)
        res = deploy_project(env, config, proj, targets=opts["targets"] or None,
                             with_code=with_code, with_agentmemory=opts["with_agentmemory"],
                             maind_server=not opts["no_maind_server"], dry=opts["dry_run"],
                             provider_projections=projections, provider_repair=opts["repair"])
        if res is None:
            continue
        results.append(res)
        if not opts["dry_run"] and provider_operation_green(res):
            config = mark_deployed(config, proj["id"], res)
            config_changed = True

    if not opts["dry_run"] and config_changed:
        write_registry(env, config)

    if opts["json"]:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if not results:
        print("nothing to deploy (no projects with existing local_path)")
        return
    for r in results:
        gf = "" if r["code"] == "disabled" else f", code:{r['code']}"
        sk = f"  ⚠ missing bits: {', '.join(r['skipped'])}" if r.get("skipped") else ""
        print(f"  {r['id']:<18} scope={r['scope']:<24} → {', '.join(r['targets'])} "
              f"({', '.join(r['servers'])}{gf}){sk}")
