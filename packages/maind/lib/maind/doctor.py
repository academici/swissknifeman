"""doctor — node environment diagnostics maind."""
import json
import os
import shutil
import sys
from pathlib import Path

from .common import parse_args
from .memory import auth_headers, check_auth, health, resolve_ports, resolve_secret


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
    from core.gitignore_policy import PolicyError, check_project, load_policy

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
    from core.gitignore_policy import PolicyError, recommended_block
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
        print("maind doctor [--quiet] — checking the host environment\n"
              "maind doctor --audit mcp|claude|deny|core|pao|settings|all [--json] — "
              "fleet-audit of optimizations by project (read-only)\n"
              "maind doctor --skill-drift — project-by-design drift breakdown "
              "ecosystem-mcp/ecosystem-setup from the current template\n"
              "maind doctor --channel-drift — project-by-project breakdown of the double channel "
              "skiller (connect+vendor for one bucket)\n"
              "maind doctor --gitignore-drift [--project ID] [--block] [--json] — reconciliation "
              ".gitignore/tracking of each project with a map of service files "
              "(configs/gitignore-policy.json; --block prints the lines for .gitignore)\n"
              "maind doctor --context [--json] — fleet-aggregation of the first footprint "
              "progress (skiller budget --first-turn for each project)")
        return

    # --audit: read-only fleet-report on the completeness of distribution of optimizations for projects
    if opts["audit"]:
        from .analysis.audit import run_audit
        config = {}
        if env.default_config.exists():
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
        if env.default_config.exists():
            try:
                from .config import load_config
                config, _ = load_config(env)
            except SystemExit:
                config = {}
        _context_report(env, config, as_json=opts["json"])
        return

    if opts["gitignore_drift"]:
        config = {}
        if env.default_config.exists():
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

    quiet = opts["quiet"]
    issues = 0

    def check(ok, label, hint=""):
        nonlocal issues
        if not ok:
            issues += 1
        if not quiet or not ok:
            mark = "ok " if ok else "FAIL"
            print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))

    print(f"maind doctor (node: {env.root})")
    check(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]}")
    check(shutil.which("node") is not None, "node in PATH",
          "agent-memory — Node-daemon; install Node.js")

    am = env.root / "node_modules" / ".bin" / "agentmemory"
    check(am.exists(), "agentmemory installed",
          "npm install at the root maind (memory daemon @agentmemory/agentmemory)")
    check(env.memory_config.is_file(), "config/memory/iii-config.yaml in place",
          "maind migrate from-agentmemory <path to .agentmemory>")

    try:
        env.state_dir.mkdir(parents=True, exist_ok=True)
        probe = env.state_dir / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    check(writable, f"{env.state_dir} is writable")

    # .maind.json: validated via load_config (die catch so as not to interrupt doctor)
    config = None
    if env.default_config.exists():
        try:
            from .config import load_config
            config, source = load_config(env)
            check(True, f"node config is valid (source: {source})")
        except SystemExit:
            check(False, "node config is valid", "see validation error above")
    else:
        legacy = env.root / ".projects.json"
        suffix = (" (yes legacy .projects.json — maind migrate from-brain)"
                  if legacy.exists() else " (create from config.example.json)")
        check(True, "config.json missing" + suffix)

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

    print(f"\n{'All checks passed.' if issues == 0 else f'Problems: {issues}'}")
    if issues:
        sys.exit(1)
