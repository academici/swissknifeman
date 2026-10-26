"""Fleet-audit of optimizations for registered projects (read-only, fail-soft).

Hub control surface: shows WHERE distribution of optimizations is incomplete -
- mcp:    active MCP-project servers (+ revision candidates: each schema
          is loaded into EVERY request, see context-economy §MCP-audit);
- claude: size CLAUDE.md (>200 lines - constant tax on session context);
- deny:   is there permissions.deny (garbage block _ide_helper/*.lock from context);
- core:   have we arrived? CORE-token saving skills + default command plugins
          (task → /planner:*) — gives them away skiller connect into each project;
- pao:    php/laravel-project (PHP≥8.3) without installed `laravel/pao` (and without
          committed opt-out) — token-saving output PHP-tests/analysis
          doesn't work (see SKM-AUDIT-004 P6, `..pao`);
- settings: settings-linter conflict Claude Code by layers (`harness doctor
          --settings --json`, subprocess to the neighbor - D10 SKM-ROADMAP-005 P1) —
          per-project doctor doesn't look at the entire fleet at once, he looks here.

Doesn't write anything to disk - only reads project files. List source -
projects.listing (same model as projects/status)."""
import json
import os
from pathlib import Path

from .. import codegraph
from .. import pao
from ..mcpconfig import MCP_FILES
from ..mcp_parity import analyze as mcp_parity_analyze
from ..codegraph_usage import fleet_summary, format_project_line, usage_note
from ..mcp_runtime import runtime_summary, scan_runtime
from ..projects import listing

DIMS = ("mcp", "claude", "deny", "core", "pao", "settings")
CLAUDE_MD_WARN = 200  # landmark Anthropic (context-economy axis 1)
CORE_SKILLS = ("context-economy", "anti-drift", "compact-responses",
               "session-handoff", "gh-review")
# Curated connect-plugin that carries smoothly CORE_SKILLS (mirror skiller CORE_PLUGIN).
CORE_PLUGIN = "core"
# CORE can be reached by THREE channels: vendor → physical. files; connect → core@ (current
# default) or legacy-buckets general/oss-dev. Everyone's Bucket CORE-skill (legacy):
CORE_SKILL_BUCKET = {
    "context-economy": "general", "anti-drift": "general",
    "compact-responses": "general", "session-handoff": "general",
    "gh-review": "oss-dev",
}
# Command plugins that skiller connect distributes to EVERY project by default
# (mirror skiller.config.DEFAULT_COMMAND_PLUGINS; duplicate locally - maind will not import skiller).
# They arrive ONLY connect-channel (marketplace-plugin) → key enabledPlugins '<name>@<marketplace>'.
DEFAULT_COMMAND_PLUGINS = ("planner",)
# Servers that maind rolls out normally - not candidates for revision.
HUB_MCP = {"agentmemory", "maind"}


def _expected_mcp_servers(env, config, project, code_st):
    """Semantic inventory IDs the hub would deploy for this project (fail-soft)."""
    if config is None:
        return ()
    try:
        from ..provision.deploy import provider_semantic_inventory
        rows = provider_semantic_inventory(
            env, config, project, with_code=None, maind_server=True,
            with_agentmemory=False)
        return tuple(row.id for row in rows)
    except (ValueError, KeyError, TypeError):
        return ()


def _mcp_parity_summary(parity):
    parts = []
    for drift in parity.get("drifts") or []:
        left = drift["left"]
        right = drift["right"]
        if drift["only_left"]:
            parts.append(f"{left}−{right}:{','.join(drift['only_left'])}")
        if drift["only_right"]:
            parts.append(f"{right}−{left}:{','.join(drift['only_right'])}")
    if parity.get("settings_dup"):
        parts.append("settings_dup:" + ",".join(parity["settings_dup"]))
    if parity.get("undeclared"):
        parts.append("undeclared:" + ",".join(parity["undeclared"]))
    return "; ".join(parts)


def _mcp_servers(path):
    """All names MCP-project servers for all configs (dedup, fail-soft)."""
    names = set()
    for rel in MCP_FILES.values():
        f = path / rel
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            names |= set((data.get("mcpServers") or {}).keys())
    return sorted(names)


def _claude_md_lines(path):
    f = path / "CLAUDE.md"
    if not f.is_file():
        return None
    try:
        return f.read_text(encoding="utf-8").count("\n") + 1
    except OSError:
        return None


def _deny_present(path):
    """permissions.deny is non-empty in any of the .claude/settings(.local).json."""
    for name in ("settings.json", "settings.local.json"):
        f = path / ".claude" / name
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and (data.get("permissions") or {}).get("deny"):
            return True
    return False


def _lock_skill_names(lock_skills):
    """Names from skills-lock.json::skills — dict {name: entry} or list [{name, ...}]."""
    if not lock_skills:
        return set()
    if isinstance(lock_skills, list):
        return {s.get("name") for s in lock_skills if s.get("name")}
    if isinstance(lock_skills, dict):
        return set(lock_skills.keys())
    return set()


def _present_skills(path):
    """Names of installed skills: skills-lock.json + directories .claude/.ai skills."""
    names = set()
    lock = path / "skills-lock.json"
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            names |= _lock_skill_names(data.get("skills"))
        except (json.JSONDecodeError, OSError):
            pass
    for base in (path / ".claude" / "skills", path / ".ai" / "skills"):
        if base.is_dir():
            names |= {d.name for d in base.iterdir() if d.is_dir()}
    return names


def _enabled_buckets(path):
    """Bucket plugins included in .claude/settings(.local).json (connect-channel).
    Keys enabledPlugins of the form '<bucket>@<marketplace>' → bucket name."""
    buckets = set()
    for name in ("settings.json", "settings.local.json"):
        f = path / ".claude" / name
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            for key, on in (data.get("enabledPlugins") or {}).items():
                if on:
                    buckets.add(key.split("@")[0])
    return buckets


def _settings_status(config, path):
    """Fail-soft call `harness doctor --settings --json` by project (subprocess to
    neighbor - maind harness does NOT import, D10). Returns {"error", "warn", "info"}
    or string "unavailable" (harness not found / fell / gave not-JSON) — measurement
    has no right to drop fleet-audit."""
    import subprocess

    from ..provision.orchestrate import _sibling_bin
    if config is None:
        return "unavailable"
    try:
        harness_bin = _sibling_bin(config, "harness")
    except SystemExit:
        return "unavailable"
    try:
        r = subprocess.run(
            [str(harness_bin), "doctor", "--settings", "--target", str(path), "--json"],
            capture_output=True, text=True, timeout=20, check=False)
        data = json.loads(r.stdout)
        counts = data["counts"]
        return {"error": int(counts["error"]), "warn": int(counts["warn"]),
                "info": int(counts["info"])}
    except (subprocess.SubprocessError, ValueError, OSError, KeyError, TypeError):
        return "unavailable"


def audit_project(env, project, dims, code_st, config=None):
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    row = {"id": pid, "path": local}
    if not path or not path.is_dir():
        row["status"] = "missing-path"
        return row
    row["status"] = "ok"
    if "mcp" in dims:
        servers = _mcp_servers(path)
        expected = _expected_mcp_servers(env, config, project, code_st)
        known = HUB_MCP | {codegraph.server_name(project, code_st)} | set(expected)
        code_providers = project.get("code_providers")
        excluded = {}
        if isinstance(code_providers, list):
            allowed = set(code_providers)
            code_server = codegraph.server_name(project, code_st)
            # Provider-specific code-graph opt-outs make literal server-set parity
            # misleading. Exclude this server from the parity comparison when the
            # project intentionally limits it to a subset of provider surfaces.
            if not {"claude-code", "codex", "cursor"}.issubset(allowed):
                code_ids = {code_server, "codegraph"}
                excluded = {surface: code_ids
                            for surface in ("claude", "codex", "cursor")}
        parity = mcp_parity_analyze(path, expected,
                                    excluded_ids_by_surface=excluded)
        row["mcp"] = {"servers": servers,
                      "review": [s for s in servers if s not in known],
                      "parity": parity}
    if "claude" in dims:
        row["claude_md_lines"] = _claude_md_lines(path)
    if "deny" in dims:
        row["deny"] = _deny_present(path)
    if "core" in dims:
        present = _present_skills(path)          # vendor: physical. files
        enabled = _enabled_buckets(path)         # connect: bucket/command plugins
        core_via_connect = CORE_PLUGIN in enabled
        row["core"] = {
            "missing": [s for s in CORE_SKILLS
                        if s not in present and not core_via_connect
                        and CORE_SKILL_BUCKET.get(s) not in enabled],
            # Command plugins (task) only reach connect-channel → checking enabledPlugins.
            "missing_cmds": [c for c in DEFAULT_COMMAND_PLUGINS if c not in enabled],
        }
    if "pao" in dims:
        row["pao"] = pao.status(project, path)
    if "settings" in dims:
        row["settings"] = _settings_status(config, path)
    return row


def run_audit(env, config, dim, as_json=False):
    """dim ∈ mcp|claude|deny|core|all (or empty → all). Prints a report."""
    dims = DIMS if dim in (None, "", "all") else (dim,)
    bad = [d for d in dims if d not in DIMS]
    if bad:
        from aicore.util.term import die
        die(f"--audit: {', '.join(bad)} (available: {', '.join(DIMS)}, all)")
    code_st = codegraph.settings(config)
    projs = listing(env, config)
    rows = [audit_project(env, p, dims, code_st, config) for p in projs]
    runtime = scan_runtime() if "mcp" in dims else None
    code_usage = fleet_summary(projs) if "mcp" in dims else None
    if as_json:
        payload = {"dims": list(dims), "projects": rows}
        if runtime is not None:
            payload["mcp_runtime"] = runtime
        if code_usage is not None:
            payload["codegraph_usage"] = code_usage
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"maind audit ({', '.join(dims)}) — projects: {len(rows)}")
    if not rows:
        print("  no projects - config.json is empty or missing")
        return
    for r in rows:
        if r.get("status") == "missing-path":
            print(f"  {r['id']:<18} [missing-path] {r.get('path')}")
            continue
        parts = []
        if "mcp" in dims:
            review = r["mcp"]["review"]
            parity_note = _mcp_parity_summary(r["mcp"].get("parity") or {})
            seg = f"mcp={len(r['mcp']['servers'])}"
            if parity_note:
                seg += f"⚠(parity: {parity_note})"
            elif review:
                seg += f"⚠(revision: {', '.join(review)})"
            parts.append(seg)
        if "claude" in dims:
            n = r["claude_md_lines"]
            seg = "claude.md=" + ("—" if n is None else str(n))
            if n and n > CLAUDE_MD_WARN:
                seg += f"⚠>{CLAUDE_MD_WARN}"
            parts.append(seg)
        if "deny" in dims:
            parts.append("deny" + ("✓" if r["deny"] else "✗"))
        if "core" in dims:
            miss = r["core"]["missing"]
            seg = "core✓" if not miss else f"core⚠(no: {', '.join(miss)})"
            miss_cmds = r["core"].get("missing_cmds") or []
            if miss_cmds:
                seg += " cmd⚠(no: " + ", ".join("/" + c + ":*" for c in miss_cmds) + ")"
            parts.append(seg)
        if "pao" in dims:
            st = r["pao"]
            parts.append({"installed": "pao✓",
                          "missing": "pao⚠(missing: composer require laravel/pao --dev)",
                          }.get(st, f"pao·{st}"))
        if "settings" in dims:
            st = r["settings"]
            if st == "unavailable":
                parts.append("settings·n/a")
            elif st["error"] == 0 and st["warn"] == 0:
                parts.append("settings✓")
            else:
                parts.append(f"settings⚠(err:{st['error']} warn:{st['warn']})")
        print(f"  {r['id']:<18} " + "  ".join(parts))
    if runtime is not None:
        note = runtime_summary(runtime)
        if note:
            print(f"  [host] mcp-runtime⚠ {note}")
        elif runtime.get("duplicates") or runtime.get("heavy"):
            print("  [host] mcp-runtime: ok")
    if code_usage is not None:
        print(f"  [fleet] codegraph-usage {usage_note(code_usage)}")
        code_on = {p["id"]: bool(p.get("code") or p.get("graphify")) for p in projs}
        idle = []
        for row in code_usage.get("projects") or []:
            line = format_project_line(row, code_on.get(row["id"], False))
            if line and " idle" in line:
                idle.append(row["id"])
        if idle:
            print(f"  [fleet] codegraph-idle {', '.join(idle[:8])}"
                  + ("…" if len(idle) > 8 else ""))
