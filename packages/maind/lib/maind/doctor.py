"""doctor — node environment diagnostics maind."""
import json
import os
import shutil
import sys
from pathlib import Path

from aicore import MIN_PYTHON
from aicore.util.cli import parse_args
from .config import config_available
from .memory import auth_headers, check_auth, health, resolve_ports, resolve_secret


RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"


def _result(check_id, status, observed, *, category, evidence=None, remediation=None, repair=None):
    doc = {"$schema": RESULT_SCHEMA, "check_id": check_id, "status": status,
           "category": category, "observed": observed}
    if evidence:
        doc["evidence"] = evidence
    if remediation:
        doc["remediation"] = remediation
    if repair:
        doc["repair"] = repair
    return doc


def _can_write(path):
    """True when ``path`` (or its nearest existing parent, when it does not exist yet) is writable.
    Looks at permissions only: nothing is created, written or removed."""
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe.is_dir() and os.access(str(probe), os.W_OK | os.X_OK)


def _load_quietly(env):
    """(config, source, warnings, error): ``load_config`` with its warnings and ``die`` captured."""
    import contextlib
    import io
    from .config import load_config
    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured):
            config, source = load_config(env)
    except SystemExit:
        lines = [l.strip() for l in captured.getvalue().splitlines() if l.strip()]
        return None, None, [], (lines[-1] if lines else "invalid configuration")
    return config, source, [l.strip() for l in captured.getvalue().splitlines() if l.strip()], None


def _environment_result(env):
    floor = ".".join(str(part) for part in MIN_PYTHON)
    agentmemory = env.root / "node_modules" / ".bin" / "agentmemory"
    evidence = [f"python3 {sys.version.split()[0]}", f"state_dir: {env.state_dir}",
                "node: " + ("found" if shutil.which("node") else "not found"),
                "agentmemory: " + ("installed" if agentmemory.exists() else "not installed")]
    if sys.version_info < tuple(MIN_PYTHON):
        return _result("maind.environment", "fail", f"python3 {sys.version.split()[0]} is older than {floor}",
                       category="environment", evidence=evidence, remediation=f"Install python3 >= {floor}.")
    if not _can_write(env.state_dir):
        return _result("maind.environment", "fail", f"the state directory {env.state_dir} cannot be created or written",
                       category="environment", evidence=evidence, remediation=f"Make {env.state_dir} writable.")
    return _result("maind.environment", "ok", f"python3 >= {floor}, state directory {env.state_dir} is writable",
                   category="environment", evidence=evidence)


def _config_results(env):
    """(config check, registry check, loaded config or None)."""
    config, source, notices, error = _load_quietly(env)
    if error:
        fail = "the node configuration is invalid: " + error
        return (_result("maind.config", "fail", fail, category="config",
                        remediation="Fix the named file or run: aicore config explain maind"),
                _result("maind.registry", "fail", fail, category="state", remediation="Fix the named file."),
                None)
    legacy_notices = [n for n in notices if "MAIND_LEGACY_CONFIG" in n]
    if any("ignored because [maind] is set" in n for n in legacy_notices):
        config_check = _result("maind.config", "warn",
                               "legacy node file settings are ignored because [maind] is set", category="config",
                               evidence=legacy_notices,
                               remediation="Run: swissknifeman upgrade (removes the legacy file)")
    elif any("reading settings" in n for n in legacy_notices):
        config_check = _result("maind.config", "warn", "settings are read from the legacy node file", category="config",
                               evidence=legacy_notices, remediation="Run: swissknifeman upgrade")
    else:
        config_check = _result("maind.config", "ok", "the [maind] settings resolve", category="config")
    if source == "empty":
        registry_check = _result("maind.registry", "skip", "no registry source exists yet", category="state")
    elif source != "config":
        registry_check = _result("maind.registry", "warn", f"the registry is read from a legacy source ({source})",
                                 category="state", remediation="Run: swissknifeman upgrade")
    else:
        registry_check = _result("maind.registry", "ok",
                                 f"registry.json is valid ({len(config.get('projects') or [])} projects)",
                                 category="state", evidence=[f"path: {env.registry_file}"])
    return config_check, registry_check, config


def _memory_result(env, config):
    if config is None:
        return _result("maind.memory", "skip", "the configuration was not loaded", category="integration")
    http_port, stream_port, url = resolve_ports(env, config)
    evidence = [f"url: {url}", f"ports: http {http_port}, stream {stream_port}"]
    if not health(url):
        return _result("maind.memory", "warn", f"the memory daemon does not respond at {url}", category="integration",
                       evidence=evidence, remediation="Run: maind start --only memory")
    headers = auth_headers(resolve_secret(env, config))
    if headers and check_auth(url, headers) is False:
        return _result("maind.memory", "warn", "the memory daemon responds but rejects the configured secret",
                       category="integration", evidence=evidence,
                       remediation="Check memory.secret_file or AGENTMEMORY_SECRET.")
    return _result("maind.memory", "ok", f"the memory daemon responds at {url}", category="integration",
                   evidence=evidence)


def _mcp_result():
    from . import mcp
    try:
        digest = mcp.tools_digest()
    except Exception as error:  # a broken tool table must not break the doctor
        return _result("maind.mcp", "fail", f"the MCP server cannot describe its tools: {type(error).__name__}",
                       category="integration", remediation="Reinstall maind.")
    return _result("maind.mcp", "ok", f"the MCP server describes {len(mcp.TOOLS)} tools", category="integration",
                   evidence=[f"tools_digest={digest}",
                             "protocol_versions=" + ",".join(mcp.SUPPORTED_PROTOCOL_VERSIONS)])


def _health_result(env, config):
    check = "maind.health"
    if config is None:
        return _result(check, "skip", "the configuration was not loaded", category="integration")
    from . import projects as projects_mod
    try:
        project = projects_mod.match_cwd(env, config)
    except Exception:
        project = None
    if project is None:
        return _result(check, "skip", "the current directory is not a registered project", category="integration")
    from .health import health_report
    try:
        report = health_report(env, config, project)
    except (Exception, SystemExit) as error:
        return _result(check, "warn", f"the health of {project['id']} cannot be determined: {type(error).__name__}",
                       category="integration")
    if report["status"] == "connected":
        return _result(check, "ok", f"project {report['id']} is connected", category="integration")
    pid = report["id"]
    return _result(check, "warn", f"project {pid} is {report['status']}", category="integration",
                   evidence=list(report["hints"]),
                   remediation=f"Run: maind health --project {pid} --plan-repair, then --apply-repair",
                   repair={"plan": ["bin/maind", "health", "--project", pid, "--plan-repair"],
                           "apply": ["bin/maind", "health", "--project", pid, "--apply-repair"]})


def run_checks(env):
    """The doctor checks as ``check-result/v1`` documents. Nothing is written."""
    config_check, registry_check, config = _config_results(env)
    return [_environment_result(env), config_check, registry_check, _memory_result(env, config),
            _mcp_result(), _health_result(env, config)]


def render_lines(results):
    lines = []
    for doc in results:
        lines.append(f"{doc['status']} {doc['check_id']}: {doc['observed']}")
        if doc.get("remediation"):
            lines.append(f"  remediation: {doc['remediation']}")
    return lines


def provider_trust_report(env, config):
    """Read-only provider trust aggregate for enabled projects."""
    from .provision.sync import contexts
    from .provision.workspace import norm_path, provider_trust, trusted_dirs
    trusted = trusted_dirs(env)
    rows = []
    for context in contexts(env, config, [p for p in config.get("projects") or []
                                           if p.get("enabled", True)]):
        path = context.get("local_path")
        rows.extend({"project_id": context.id, **row} for row in provider_trust(
            context, trusted=bool(path and norm_path(path) in trusted)))
    return rows


def _skill_drift(env, config):
    """Drift managed-skills maind (ecosystem-mcp/ecosystem-setup) by fleet enabled-
    projects: dry run of both providers (mode=auto, dry=True) — state != 'fresh'
    means the skill is missing OR the template is in maind has since been updated (is deprecated). Nothing
    does not write; real rolling out - `maind sync --only ecosystem-skill,setup-skill`."""
    from .federation import _enabled_projects
    from .provision.skilldoc import apply_ecosystem_skill, apply_setup_skill
    drifted = []
    for p in _enabled_projects(config):
        local = p.get("local_path")
        if not local or not Path(os.path.expanduser(local)).is_dir():
            continue
        for fn, label in ((apply_ecosystem_skill, "ecosystem-mcp"),
                          (apply_setup_skill, "ecosystem-setup")):
            try:
                res = fn(env, config, p, "auto", True)
            except Exception:
                continue
            if res.get("state") not in {"fresh", "foreign-owner"}:
                drifted.append((p.get("id"), label, res["state"]))
    return drifted


def _skill_drift_report(env, config, detail):
    """detail=False: one summary-line for default doctor. detail=True: by design
    breakdown (--skill-drift)."""
    drifted = _skill_drift(env, config)
    if not detail:
        if drifted:
            projects = sorted({pid for pid, _, _ in drifted})
            print(f"  [warn] managed-skills (ecosystem-mcp/setup): {len(projects)} "
                  "project(ov) behind the template (details: maind doctor --skill-drift)")
        else:
            print("  [ok ] managed-skills (ecosystem-mcp/setup): no drift from template")
        return
    print("\nDrift managed-skills maind (ecosystem-mcp/ecosystem-setup, dry calculation):")
    if not drifted:
        print("  (all enabled-projects are synchronized with current templates)")
        return
    by_project = {}
    for pid, label, state in drifted:
        by_project.setdefault(pid, []).append(f"{label}:{state}")
    for pid, items in sorted(by_project.items()):
        print(f"  [warn] {pid}: " + ", ".join(items)
              + "  (apply: maind sync --project " + pid + " --only ecosystem-skill,setup-skill)")


def _channel_overlap(env, config):
    """Duplicate channel skiller (the bucket is distributed AT THE SAME TIME plugin'ohm (connect) and
    vendor) by fleet enabled-projects: dry `skiller status --json` for each -
    detector lives in skiller (`channel_overlap`), doctor only aggregates by fleet
    (field-feedback: found manually on agelto/azguard/dterema — is now on the radar
    itself). Returns [(project_id, [bucket, …])]."""
    import json
    import subprocess

    from .federation import _enabled_projects
    from .provision.orchestrate import _sibling_bin
    try:
        skm_bin = _sibling_bin(config, "swissknifeman")
    except SystemExit:
        return []
    overlaps = []
    for p in _enabled_projects(config):
        local = p.get("local_path")
        if not local or not Path(os.path.expanduser(local)).is_dir():
            continue
        try:
            r = subprocess.run([str(skm_bin), "status", "--target", local, "--json"],
                               capture_output=True, text=True, timeout=15, check=False)
            data = json.loads(r.stdout)
        except (subprocess.SubprocessError, ValueError, OSError):
            continue
        overlap = data.get("channel_overlap") or []
        if overlap:
            overlaps.append((p.get("id"), overlap))
    return overlaps


def _channel_hygiene_report(env, config, detail):
    """detail=False: one summary-string. detail=True (--channel-drift): by design
    breakdown of channel takes."""
    overlaps = _channel_overlap(env, config)
    if not detail:
        if overlaps:
            print(f"  [warn] duplicate channel skiller (connect+vendor): {len(overlaps)} "
                  "project(ov) give out skills twice (details: maind doctor --channel-drift)")
        else:
            print("  [ok ] duplicate channel skiller (connect+vendor): not found")
        return
    print("\nDuplicate channel skiller (bucket AT THE SAME TIME plugin+vendor, dry request):")
    if not overlaps:
        print("  (not found in any enabled-project)")
        return
    for pid, buckets in overlaps:
        print(f"  [warn] {pid}: {' '.join(buckets)}  (clean: skiller connect "
              "--target <path> --cleanup-vendored — plus separately manually if "
              "vendor via .swissknifeman/config.json, not legacy .swissknife.json)")


def _gitignore_drift(config, only=None):
    """Verification of each enabled-project with map `configs/gitignore-policy.json` (read-only):
    what should be in the .gitignore, and what to commit. Returns [(project_id, findings)]."""
    from aicore.state.gitignore import PolicyError, check_project, load_policy

    from .federation import _enabled_projects
    policy = load_policy()
    rows = []
    for p in _enabled_projects(config):
        if only and p.get("id") != only:
            continue
        local = p.get("local_path")
        path = Path(os.path.expanduser(local)) if local else None
        if not path or not path.is_dir():
            continue
        try:
            rows.append((p.get("id"), check_project(path, policy), policy))
        except PolicyError:
            continue
    return rows


def _gitignore_drift_report(config, detail, *, only=None, as_json=False, block=False):
    """detail=False: one summary-line for default doctor. detail=True
    (--gitignore-drift): by project breakdown, --json, --block (ready lines .gitignore)."""
    from aicore.state.gitignore import PolicyError, recommended_block
    try:
        rows = _gitignore_drift(config, only)
    except PolicyError as exc:
        print(f"  [warn] map gitignore not available: {exc}")
        return
    errors = {pid: [f for f in found if f["level"] == "error"] for pid, found, _ in rows}
    if as_json:
        print(json.dumps({"projects": [{"id": pid, "findings": found} for pid, found, _ in rows]},
                         ensure_ascii=False, indent=2))
        return
    if not detail:
        bad = sorted(pid for pid, errs in errors.items() if errs)
        if bad:
            print(f"  [warn] .gitignore ↔ service file map: {len(bad)} project(ov) diverge "
                  "(details: maind doctor --gitignore-drift)")
        else:
            print("  [ok ] .gitignore ↔ service file map: no discrepancies")
        return
    print("\nDiscrepancies .gitignore with service file map (configs/gitignore-policy.json):")
    clean = True
    for pid, found, policy in rows:
        problems = [f for f in found if f["level"] != "info"]
        if not problems:
            continue
        clean = False
        print(f"  {pid}: {len([f for f in problems if f['level'] == 'error'])} errors, "
              f"{len([f for f in problems if f['level'] == 'warn'])} warnings")
        for f in problems:
            print(f"    [{f['level']:<5}] {f['code']}: {f['path']} — {f['fix']}")
        if block:
            lines = recommended_block(found, policy)
            if lines:
                print("    # add to .gitignore:")
                for line in lines:
                    print(f"    {line}")
    if clean:
        print("  (there are no discrepancies in any enabled-project)")


def _fleet_context(env, config):
    """First move footprint fleet aggregation: cycle by registered-projects → subprocess
    `skiller budget --first-turn --target <path> --json` — token-math
    remains ONLY in skiller, maind only consumes ready JSON (without a double,
    without cross-imports - pattern doctor --audit settings, D10). Fail-soft: unavailable
    skiller / broken pin / missing local_path for the project → context='n/a',
    fleet scan continues."""
    import json
    import subprocess

    from .federation import _enabled_projects
    from .provision.orchestrate import _sibling_bin
    try:
        skm_bin = _sibling_bin(config, "swissknifeman")
    except SystemExit:
        skm_bin = None
    rows = []
    for p in _enabled_projects(config):
        pid = p.get("id")
        local = p.get("local_path")
        path = Path(os.path.expanduser(local)) if local else None
        if not path or not path.is_dir() or skm_bin is None:
            rows.append({"id": pid, "context": "n/a"})
            continue
        try:
            r = subprocess.run(
                [str(skm_bin), "budget", "--first-turn", "--target", str(path), "--json"],
                capture_output=True, text=True, timeout=20, check=False)
            data = json.loads(r.stdout)
            rows.append({"id": pid,
                        "context": {"total": data["total"], "verdict": data["verdict"]}})
        except (subprocess.SubprocessError, ValueError, OSError, KeyError, TypeError):
            rows.append({"id": pid, "context": "n/a"})
    return rows


def _context_report(env, config, as_json):
    import json
    rows = _fleet_context(env, config)
    if as_json:
        print(json.dumps({"projects": rows}, ensure_ascii=False, indent=2))
        return
    print(f"maind doctor --context (footprint of the first move) — projects: {len(rows)}")
    if not rows:
        print("  no projects - config.json is empty or missing")
        return
    for r in rows:
        ctx = r["context"]
        if ctx == "n/a":
            print(f"  {r['id']:<18} context·n/a")
        else:
            print(f"  {r['id']:<18} context={ctx['total']} {ctx['verdict']}")


def cmd_doctor(env, argv):
    opts, _ = parse_args(argv, {"--quiet": "bool", "--audit": "str", "--json": "bool",
                                "--skill-drift": "bool", "--channel-drift": "bool",
                                "--context": "bool", "--provider-trust": "bool",
                                "--gitignore-drift": "bool", "--project": "str", "--block": "bool"})
    if opts["help"]:
        print("maind doctor [--quiet] [--json] — checking the host environment; --json prints a list of "
              "check-result/v1 documents (maind.environment, .config, .registry, .memory, .mcp, .health)\n"
              "maind doctor --audit mcp|claude|deny|core|pao|settings|all [--json] — "
              "fleet-audit of optimizations by project (read-only)\n"
              "maind doctor --skill-drift — project-by-design drift breakdown "
              "ecosystem-mcp/ecosystem-setup from the current template\n"
              "maind doctor --channel-drift — project-by-project breakdown of the double channel "
              "skiller (connect+vendor for one bucket)\n"
              "maind doctor --gitignore-drift [--project ID] [--block] [--json] — reconciliation "
              ".gitignore/tracking of each project with a map of service files "
              "(configs/gitignore-policy.json; --block prints the lines for .gitignore; "
              "maind sync provisioner gitignore appends them)\n"
              "maind doctor --context [--json] — fleet-aggregation of the first footprint "
              "progress (skiller budget --first-turn for each project)")
        return

    # --audit: read-only fleet-report on the completeness of distribution of optimizations for projects
    if opts["audit"]:
        from .analysis.audit import run_audit
        config = {}
        if config_available(env):
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        run_audit(env, config, opts["audit"], as_json=opts["json"])
        return

    # --context: read-only fleet-first move footprint aggregation (subprocess → skiller)
    if opts["context"]:
        config = {}
        if config_available(env):
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        _context_report(env, config, as_json=opts["json"])
        return

    if opts["gitignore_drift"]:
        config = {}
        if config_available(env):
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        _gitignore_drift_report(config, True, only=opts["project"], as_json=opts["json"],
                                block=opts["block"])
        return

    if opts["provider_trust"]:
        from .config import load_config
        config, _src = load_config(env)
        rows = provider_trust_report(env, config)
        if opts["json"]:
            print(json.dumps({"providers": rows, "non_green": sum(not row["green"] for row in rows)}, ensure_ascii=False))
        else:
            print(f"provider trust: non-green={sum(not row['green'] for row in rows)}")
            for row in rows:
                print(f"  {row['project_id']} {row['provider_id']}: " + ("ok" if row["green"] else ", ".join(row["diagnostics"])))
        return

    if opts["json"]:
        results = run_checks(env)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if any(doc["status"] == "fail" for doc in results):
            sys.exit(1)
        return

    quiet = opts["quiet"]
    issues = 0
    check_lines = [] if quiet else render_lines(run_checks(env))  # first: legacy warnings are printed once

    def check(ok, label, hint=""):
        nonlocal issues
        if not ok:
            issues += 1
        if not quiet or not ok:
            mark = "ok " if ok else "FAIL"
            print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))

    print(f"maind doctor (node: {env.root})")
    floor = ".".join(str(part) for part in MIN_PYTHON)
    check(sys.version_info >= tuple(MIN_PYTHON), f"python3 {sys.version.split()[0]} (>= {floor})")
    check(shutil.which("node") is not None, "node in PATH",
          "agent-memory — Node-daemon; install Node.js")

    am = env.root / "node_modules" / ".bin" / "agentmemory"
    check(am.exists(), "agentmemory installed",
          "npm install at the root maind (memory daemon @agentmemory/agentmemory)")
    check(env.memory_config.is_file(), "config/memory/iii-config.yaml in place",
          "maind migrate from-agentmemory <path to .agentmemory>")

    writable = _can_write(env.state_dir)
    check(writable, f"{env.state_dir} is writable")

    # node config (registry + settings): validated via load_config (die catch so as not to interrupt doctor)
    config = None
    if config_available(env):
        try:
            from .config import load_config
            config, source = load_config(env)
            check(True, f"node config is valid (source: {source})")
        except SystemExit:
            check(False, "node config is valid", "see validation error above")
    else:
        legacy = env.root / ".projects.json"
        suffix = (" (yes legacy .projects.json — maind migrate from-brain)"
                  if legacy.exists() else " (copy configs/registry.example.json)")
        check(True, "registry missing" + suffix)

    if config:
        _skill_drift_report(env, config, detail=opts.get("skill_drift"))
        _channel_hygiene_report(env, config, detail=opts.get("channel_drift"))
        _gitignore_drift_report(config, False)
        from .codegraph import check_schema_connectivity
        schema_issues = check_schema_connectivity(config)
        check(not schema_issues, "pin Serena/schema .serena/project.yml connected",
              "; ".join(schema_issues))

    # memory ports - on allowed ports (env/config), informative
    if not quiet:
        http_port, stream_port, url = resolve_ports(env, config)
        up = health(url)
        if not up:
            print(f"  [info] memory {url} — not running (maind start --only memory)")
        else:
            # /agentmemory/health ALWAYS public (even with a secret) — «replies» doesn't mean
            # «our calls are authorized»; distinguished by an explicit protected probe (findings §2).
            headers = auth_headers(resolve_secret(env, config)) if config else None
            auth = check_auth(url, headers) if headers else None
            detail = "responds but is unauthorized (401) — check memory.secret_file/AGENTMEMORY_SECRET" \
                if auth is False else "replies"
            print(f"  [info] memory {url} — {detail}")
        print(f"  [info] ports: http :{http_port}, stream :{stream_port} "
              "(override via .env AGENTMEMORY_PORT/STREAM_PORT)")

    if not quiet:
        print()
        for line in check_lines:
            print(line)

    print(f"\n{'All checks passed.' if issues == 0 else f'Problems: {issues}'}")
    if issues:
        sys.exit(1)
