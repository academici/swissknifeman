"""doctor — environment diagnostics."""
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import DB_VERSION, atomic_write_json, harness_bin, is_within, parse_flags, warn
from .state import registry_git_state


def _delegate_settings_doctor(env, opts):
    """Facade `skiller doctor --settings` → `harness doctor --settings` (subprocess).
    NO check logic here (D10, single source of truth in harness): only
    throw stdout (inherited) and return code. harness not found → warn and
    graceful skip (rc 0, like apply_permissions). No output parsing harness."""
    binp = harness_bin(env)
    if binp is None:
        warn("harness not installed - settings-doctor not available "
             "(set: packages/harness/install.sh)")
        return
    cmd = [str(binp), "doctor", "--settings",
           "--target", opts.get("target") or os.getcwd()]
    try:
        result = subprocess.run(cmd, check=False, timeout=30)
    except (subprocess.SubprocessError, OSError) as e:
        warn(f"harness doctor --settings did not start: {e}")
        return
    if result.returncode:
        sys.exit(result.returncode)


def _audit_downstream(env):
    """Hygiene publish-surface onboarded projects: always-loaded layer that Claude Code
    reads in EVERY session of the target project (CLAUDE.md ≤200, scoped/unscoped rules, deny-preset).
    This is the main runtime-token consumption - it is in the TARGET project, not in the registry."""
    print("\nDownstream publish-surface (always-loaded layer in projects):")
    db_file = env.db_file
    projects = []
    if db_file.exists():
        try:
            projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
        except json.JSONDecodeError:
            pass
    seen = 0
    for p in projects:
        pdir = Path(p.get("path", ""))
        if not pdir.is_dir():
            continue
        seen += 1
        name = p.get("id") or pdir.name
        cmd_md = pdir / "CLAUDE.md"
        if not cmd_md.is_file():
            cmd_md = pdir / ".claude" / "CLAUDE.md"
        lines = (len(cmd_md.read_text(encoding="utf-8", errors="ignore").splitlines())
                 if cmd_md.is_file() else 0)
        scoped = unscoped = 0
        rules_dir = pdir / ".claude" / "rules"
        if rules_dir.is_dir():
            for r in sorted(rules_dir.glob("*.md")):
                head = r.read_text(encoding="utf-8", errors="ignore")[:400]
                parts = head.split("---", 2)
                if head.lstrip().startswith("---") and len(parts) >= 3 and "paths:" in parts[1]:
                    scoped += 1
                else:
                    unscoped += 1
        deny = False
        for sf in (pdir / ".claude" / "settings.json",
                   pdir / ".claude" / "settings.local.json"):
            if sf.is_file():
                try:
                    s = json.loads(sf.read_text(encoding="utf-8"))
                    if (s.get("permissions") or {}).get("deny"):
                        deny = True
                except json.JSONDecodeError:
                    pass
        flags = []
        if lines > 200:
            flags.append(f"CLAUDE.md {lines}>200")
        if unscoped:
            flags.append(f"{unscoped} unscoped-rules (always-loaded)")
        if not deny:
            flags.append("no deny-noise preset")
        cursor_skills = pdir / ".cursor" / "skills"
        if cursor_skills.is_dir():
            broken = sorted(p.name for p in cursor_skills.iterdir()
                            if p.is_symlink() and not p.exists())
            if broken:
                sample = ", ".join(broken[:5]) + (" …" if len(broken) > 5 else "")
                flags.append(f"broken .cursor/skills ({len(broken)}): {sample}")
        mark = "ok " if not flags else "warn"
        tail = (" — " + "; ".join(flags)) if flags else ""
        print(f"  [{mark}] {name}: CLAUDE.md={lines} lines, "
              f"rules={scoped} scoped/{unscoped} unscoped, "
              f"deny={'yes' if deny else 'NO'}{tail}")
    if seen == 0:
        print("  (no onboarded projects on disk)")


def _vendor_drift(env):
    """Drift vendor-skills by fleet: registered mode=vendor projects whose set
    has parted ways with the CURRENT registry (add — new skill has appeared, update — sha256 has changed,
    remove — fell out of the config). Dry plan_sync, does not write anything. Connect-only projects
    (without .swissknifeman/config.json) are skipped - the update comes from marketplace
    itself. Returns [(project_name, plan), ...] only for those who have drift."""
    from .config import load_config
    from .publication import build_vendor_distribution_plan
    from .skillset import DEFAULT_SKILLS_PATH, load_skillset_config, plan_sync
    db_file = env.db_file
    if not db_file.exists():
        return []
    try:
        projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
    except json.JSONDecodeError:
        return []
    drifted = []
    for p in projects:
        pdir = Path(p.get("path", ""))
        if not pdir.is_dir():
            continue
        try:
            cfg = load_skillset_config(pdir)
        except SystemExit as exc:
            drifted.append((p.get("id") or pdir.name,
                            {"errors": [str(exc) or type(exc).__name__]}))
            continue
        if cfg is None:
            continue
        name = p.get("id") or pdir.name
        try:
            config = load_config(env, pdir)
            providers = build_vendor_distribution_plan(
                config, pdir, project_id=pdir.name,
                claude_path=cfg.get("skills_path") or DEFAULT_SKILLS_PATH,
                codex_path=".agents/skills")
        except (Exception, SystemExit) as exc:
            drifted.append((name, {"errors": [str(exc) or type(exc).__name__]}))
            continue
        for descriptor in providers:
            provider = descriptor.provider_id
            try:
                skills_path = descriptor.target.relative_to(pdir).as_posix()
                provider_cfg = {**cfg, "skills_path": skills_path, "agent": provider}
                # include_core=True — same default as `skiller sync` (cmd_sync:
                # include_core=not opts["no_core"], default no_core=False). Without
                # this comparison with the registry is false CORE_SKILLS «add»/«remove».
                plan = plan_sync(env, pdir, provider_cfg, include_core=True,
                                 provider=provider)
            except (Exception, SystemExit) as exc:
                plan = {"errors": [str(exc) or type(exc).__name__]}
            if _vendor_plan_has_drift(plan):
                label = f"{name} [{provider}]" if len(providers) > 1 else name
                drifted.append((label, plan))
    return drifted


def _vendor_plan_has_drift(plan):
    """Every state that prevents an ordinary vendor sync from being current."""
    return any(plan.get(field) for field in (
        "add", "update", "managed_drift", "remove", "conflicts", "relocated",
        "provenance_invalid", "errors"))


def _audit_vendor_drift(env):
    """Detailed project-by-project drift report vendor-skills (--vendor-drift)."""
    print("\nDrift vendor-skills from the registry (mode=vendor, dry calculation):")
    drifted = _vendor_drift(env)
    if not drifted:
        print("  (all vendor-projects are synchronized with the registry)")
        return
    for name, plan in drifted:
        parts = []
        if plan.get("add"):
            parts.append(f"+{len(plan['add'])} new")
        if plan.get("update"):
            parts.append(f"~{len(plan['update'])} with new version")
        if plan.get("remove"):
            parts.append(f"-{len(plan['remove'])} extra")
        if plan.get("conflicts"):
            parts.append(f"!{len(plan['conflicts'])} conflicts (interrupted sync?)")
        if plan.get("managed_drift"):
            parts.append(f"!{len(plan['managed_drift'])} managed drift")
        if plan.get("relocated"):
            parts.append(f"!{len(plan['relocated'])} relocated")
        if plan.get("provenance_invalid"):
            parts.append("!invalid provenance")
        if plan.get("errors"):
            errors = plan["errors"]
            count = len(errors) if isinstance(errors, (list, tuple, dict, set)) else 1
            parts.append(f"!{count} errors")
        print(f"  [warn] {name}: " + ", ".join(parts)
              + "  (apply: skiller sync — from the project directory)")


def _vendor_drift_summary(env):
    """Compact summary-line for default doctor: how much vendor-projects backlog
    from the registry (new/changed managed-skills). Details — --vendor-drift."""
    drifted = _vendor_drift(env)
    if drifted:
        projects = {name.partition(" [")[0] for name, _plan in drifted}
        print(f"  [warn] vendor-skills: {len(projects)} project(ov) behind the registry "
              "(details: skiller doctor --vendor-drift)")
    else:
        print("  [ok ] vendor-skills: no drift from the registry")


def _downstream_claude_md_summary(env):
    """Compact summary-line for default doctor: how many onboarded projects have
    CLAUDE.md > 200 lines (always-loaded → resident token-spend). Details — --downstream."""
    db_file = env.db_file
    if not db_file.exists():
        return
    try:
        projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
    except json.JSONDecodeError:
        return
    seen = over = 0
    for p in projects:
        pdir = Path(p.get("path", ""))
        if not pdir.is_dir():
            continue
        seen += 1
        cmd_md = pdir / "CLAUDE.md"
        if not cmd_md.is_file():
            cmd_md = pdir / ".claude" / "CLAUDE.md"
        if (cmd_md.is_file()
                and len(cmd_md.read_text(encoding="utf-8", errors="ignore").splitlines()) > 200):
            over += 1
    if not seen:
        return
    if over:
        print(f"  [warn] downstream CLAUDE.md: {over}/{seen} projects > 200 lines "
              "(always-loaded; details: skiller doctor --downstream)")
    else:
        print(f"  [ok ] downstream CLAUDE.md: all {seen} ≤ 200 lines")


_CORE_DONOR_BUCKETS = ("general", "research", "oss-dev")


def detect_core_donor_collisions(catalog, *, enabled):
    """D42 (P1.5, read-only): identities the curated `core` unit shares with a donor bucket
    (`general`/`research`/`oss-dev`) that curated `core` physically copies from.

    `enabled` is an EXPLICIT inventory `{unit_id: bool}` supplied by the caller — this
    function never reads a live provider profile or cache (`~/.codex`, `~/.claude`) and never
    writes one; the CLI passes the worst-case declared set (every unit in `catalog.units` is
    "enabled", matching the D44 cold-detection convention), a test passes a narrow fixture.
    `core`/donor mutual exclusion is a structural fact of the curated bundle (D42 invariant
    ii) — this never repairs it, only names identity/carriers/owner/safe action.
    Returns a tuple of `{identity, carriers, owner, safe_owner_action}` dicts, sorted by
    `(identity, donor)` — [] when nothing overlaps or `core` itself is not enabled."""
    core_unit = next((unit for unit in catalog.units
                      if unit.plugin_id == "core" and unit.kind == "curated"), None)
    if core_unit is None or not enabled.get("core"):
        return ()
    by_id = {skill.semantic_id: skill for skill in catalog.skills}
    core_names = {by_id[member].name for member in core_unit.member_ids if member in by_id}
    findings = []
    for donor in _CORE_DONOR_BUCKETS:
        if not enabled.get(donor):
            continue
        donor_unit = next((unit for unit in catalog.units
                           if unit.plugin_id == donor and unit.kind == "bucket"), None)
        if donor_unit is None:
            continue
        donor_names = {by_id[member].name for member in donor_unit.member_ids if member in by_id}
        for identity in sorted(core_names & donor_names):
            findings.append({
                "identity": identity,
                "carriers": ["unit:core", f"unit:{donor}"],
                "owner": "P1.5",
                "safe_owner_action": (
                    "disable either the curated `core` unit or the "
                    f"`{donor}` bucket for this provider; the plan never writes "
                    "the user-owned enabled set (D42)"),
            })
    return tuple(findings)


def _worst_case_enabled(catalog):
    """Every declared unit is a candidate carrier (D44 cold-detection convention) — never a
    read of a live provider profile/cache."""
    return {unit.plugin_id: True for unit in catalog.units}


def _core_donor_diagnostics(env):
    """Print the D42 read-only diagnostic under the worst-case declared inventory."""
    from .registry import build_catalog, build_registry
    registry, bucket_meta, bucket_dirs = build_registry(env)
    catalog = build_catalog(env, bucket_meta, bucket_dirs, registry)
    findings = detect_core_donor_collisions(catalog, enabled=_worst_case_enabled(catalog))
    print("\nD42 core↔donor mutual exclusion (read-only, worst-case declared set):")
    if not findings:
        print("  [ok ] no core/donor identity overlap in the declared set")
        return
    for item in findings:
        print(f"  [warn] {item['identity']}: carriers={item['carriers']} "
              f"owner={item['owner']} — {item['safe_owner_action']}")


def _provider_distribution_doctor(env, target):
    """Read-only provider-aware delivery preflight; never invokes native Codex."""
    from .config import load_config
    from .connect import prepare_connect_selection
    from .publication import build_connect_distribution_plan, build_vendor_distribution_plan
    from .skillset import DEFAULT_SKILLS_PATH, load_skillset_config
    from core import find_repo_root
    config = load_config(env, target)
    repo_root = find_repo_root(env.root) or env.root
    _core_donor_diagnostics(env)
    print(f"\nProvider distribution (target: {target}):")
    try:
        plugins = prepare_connect_selection(env, target, {}, config)["plugins"]
        connect = build_connect_distribution_plan(config, target, project_id=target.name,
                                                  repo_root=repo_root, plugins=plugins)
        print("  [ok ] marketplace plan: " + ", ".join(item.provider_id for item in connect))
    except SystemExit as exc:
        print(f"  [warn] marketplace plan blocked: {exc}")
    cfg = load_skillset_config(target)
    if cfg is None:
        print("  [ok ] vendor plan: no .swissknifeman/config.json")
        return
    try:
        vendor = build_vendor_distribution_plan(
            config, target, project_id=target.name,
            claude_path=cfg.get("skills_path") or DEFAULT_SKILLS_PATH,
            codex_path=".agents/skills")
        print("  [ok ] vendor plan: " + ", ".join(
            f"{item.provider_id}:{item.target.relative_to(target)}" for item in vendor))
    except SystemExit as exc:
        print(f"  [warn] vendor plan blocked: {exc}")


class EffectiveSourceDoctorError(ValueError):
    """Raised when a diagnostic dict violates the P4.2 record shape (missing key or an
    out-of-vocabulary status) — a composition bug, never a runtime condition to catch."""


EFFECTIVE_SOURCE_SCHEMA_VERSION = "effective-source-doctor/v1"
_DIAGNOSTIC_REQUIRED_KEYS = ("id", "owner", "source", "status", "evidence", "quality",
                             "next_command")
_DIAGNOSTIC_STATUSES = frozenset(("ok", "degraded", "unknown", "n/a"))

_HOOK_REGISTRATIONS = (".codex/hooks.json", ".claude/settings.json")


def build_effective_source_report(diagnostics):
    """Compose the P4.2 read-only effective-source doctor document (schema
    `effective-source-doctor/v1`) from already-gathered diagnostic dicts. Pure: no I/O,
    no ownership/collision arithmetic of its own (that stays sealed in P1's own
    functions, e.g. `run_effective_runtime_gate`) — this only validates the record shape
    Implementation Rules require (semantic owner/source/evidence/quality/next command per
    diagnostic) and folds an overall status. `n/a` counts toward `ok` (a structural fact,
    not a measurement, per the `cache` diagnostic); `degraded`/`unknown` do not."""
    for d in diagnostics:
        missing = [k for k in _DIAGNOSTIC_REQUIRED_KEYS if k not in d]
        if missing:
            raise EffectiveSourceDoctorError(
                f"diagnostic {d.get('id', '?')!r} missing required keys: {missing}")
        if d["status"] not in _DIAGNOSTIC_STATUSES:
            raise EffectiveSourceDoctorError(
                f"diagnostic {d['id']!r} has out-of-vocabulary status {d['status']!r}")
    overall = "ok" if all(d["status"] in ("ok", "n/a") for d in diagnostics) else "degraded"
    return {"schema_version": EFFECTIVE_SOURCE_SCHEMA_VERSION,
            "diagnostics": list(diagnostics), "overall": overall}


def _identity_ownership_diagnostic(env):
    """Active semantic owner + provenance + collisions — reused verbatim from the P1.4
    gate (`run_effective_runtime_gate`), never re-derived: composition, not a second
    ownership engine (Implementation Rules)."""
    try:
        result = run_effective_runtime_gate(env)
    except Exception as exc:  # pragma: no cover — defensive, gate itself is tested elsewhere
        return {
            "id": "identity-ownership", "owner": "P1.1/P1.4 (semantic-identity-ownership-v1.md)",
            "source": "skiller.doctor.run_effective_runtime_gate", "status": "unknown",
            "evidence": {"gap": f"gate did not run: {exc}"},
            "quality": {"completeness": 0.0, "note": "gate raised before producing a result"},
            "next_command": "skiller doctor --effective-runtime",
        }
    collisions = {p: c for p, c in result["collisions_by_provider"].items() if c}
    counts = {p: len(m) for p, m in result["positive_maps"].items()}
    status = "ok" if not collisions else "degraded"
    return {
        "id": "identity-ownership", "owner": "P1.1/P1.4 (semantic-identity-ownership-v1.md)",
        "source": "skiller.doctor.run_effective_runtime_gate", "status": status,
        "evidence": {"identity_counts": counts, "collisions": collisions,
                     "negative_pairs_measured": len(result["negative_pairs"])},
        "quality": {"completeness": 1.0,
                    "note": "cold catalog-wide gate over the declared fixture, not a named subset"},
        "next_command": "skiller doctor --effective-runtime",
    }


def _cache_diagnostic():
    """Cache status is a structural fact (D44), not a measurement: identity/collision
    detection never reads a live provider profile or cache, so neither does this
    diagnostic — printing `ok` here would imply a check that was never run."""
    return {
        "id": "cache",
        "owner": "P1.1 (semantic-identity-ownership-v1.md § Detection is repo-derived and cold, D44)",
        "source": "contract citation — no runtime cache/profile read performed",
        "status": "n/a",
        "evidence": {"note": "carrier detection reads repository sources only "
                             "(marketplace + root projections); a live provider "
                             "cache/profile (~/.codex, ~/.claude) is never read"},
        "quality": {"completeness": 1.0, "note": "structural fact, not a measurement"},
        "next_command": "skiller doctor --effective-runtime",
    }


def _read_json_or_none(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _hook_commands(data):
    """Flatten every literal `command` string out of a hooks.json/settings.json-shaped
    `hooks` block — read-only extraction, no execution, no shell parsing beyond `str`."""
    commands = []
    hooks_block = data.get("hooks", data) if isinstance(data, dict) else {}
    for entries in (hooks_block or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            for h in (entry.get("hooks") or ()):
                cmd = h.get("command") if isinstance(h, dict) else None
                if isinstance(cmd, str):
                    commands.append(cmd)
    return commands


def _command_locality(command, *, repo_root):
    """Best-effort, read-only classification per semantic-identity-ownership-v1.md §
    Hook identities: `repo-local` when the command names a path inside `repo_root`
    (directly, or via `$(git rev-parse --show-toplevel)`); `outside-repo` when it names a
    home-relative path instead. Content of an outside-repo handler is never read
    (`unknown`, never scanned — execution does not read a provider home)."""
    if "show-toplevel" in command or str(repo_root) in command:
        return "repo-local"
    if "~/" in command or "$HOME" in command:
        return "outside-repo"
    return "unknown"


def _hook_ownership_diagnostic(repo_root):
    """Registration source (repo file) × managed owner (`.swissknifeman/provider-
    artifacts.lock.json`) × handler locality — the three answers semantic-identity-
    ownership-v1.md § Hook identities names for a hook identity, computed from
    repository files only. A registration target without a lock record is `unmanaged`,
    never assumed fine."""
    lock_path = repo_root / ".swissknifeman" / "provider-artifacts.lock.json"
    lock = _read_json_or_none(lock_path)
    if lock is None:
        return {
            "id": "hook-ownership",
            "owner": "P0.4 (semantic-identity-ownership-v1.md § Hook identities)",
            "source": str(lock_path), "status": "unknown",
            "evidence": {"gap": f"lock file not found at {lock_path}"},
            "quality": {"completeness": 0.0, "note": "no managed-owner map to cite"},
            "next_command": "harness doctor",
        }
    managed_targets = {r.get("target_path") for r in lock.get("records", ())}
    registrations = {}
    for rel in _HOOK_REGISTRATIONS:
        data = _read_json_or_none(repo_root / rel)
        if data is None:
            continue
        commands = _hook_commands(data)
        registrations[rel] = {
            "managed": rel in managed_targets,
            "commands": [{"command": c, "locality": _command_locality(c, repo_root=repo_root)}
                        for c in commands],
        }
    unmanaged = sorted(rel for rel, r in registrations.items() if not r["managed"])
    status = "ok" if not unmanaged else "degraded"
    return {
        "id": "hook-ownership",
        "owner": "P0.4 (semantic-identity-ownership-v1.md § Hook identities)",
        "source": str(lock_path.relative_to(repo_root)), "status": status,
        "evidence": {"registrations": registrations, "unmanaged": unmanaged},
        "quality": {"completeness": 1.0,
                    "note": "handler content outside the repo is never scanned (D44-style)"},
        "next_command": "harness doctor  # hook lifecycle ownership is P0.4/harness, read-only here",
    }


def _capability_gap_diagnostic(repo_root):
    """Reference/capability coverage is not recomputed live here: no committed measurement
    exists to cite, so the status is a named `unknown`, never a silent "ok"."""
    return {
        "id": "capability-reference-coverage",
        "owner": "semantic identity ownership (record shape)",
        "source": "skiller doctor --provider-distribution", "status": "unknown",
        "evidence": {"gap": "carrier-literal capability coverage has no live measurement in this "
                            "diagnostic; run the provider-distribution preflight"},
        "quality": {"completeness": 0.0, "note": "no live measurement"},
        "next_command": "skiller doctor --provider-distribution",
    }


def _analyst_trace_modules_available():
    """One-way, optional import (mirrors `analyst.doctor`'s own optional `task.plan`
    check): absence of `analyst` degrades this diagnostic, it never raises a trace."""
    try:
        import analyst.metrics as _metrics
        import analyst.trace as _trace
    except Exception:
        return None, None
    return _trace.SCHEMA_VERSION, _metrics.SCHEMA_VERSION


def _trace_quality_diagnostic(repo_root):
    """Trace quality has no generic per-project trace store to query yet, so it is reported
    as a named `unknown` (never rounded to `ok`); the analyst instrument is the live reader."""
    trace_schema, metrics_schema = _analyst_trace_modules_available()
    if not (trace_schema and metrics_schema):
        return {
            "id": "trace-quality", "owner": "unified agent trace",
            "source": "analyst.trace / analyst.metrics (optional, one-way import)",
            "status": "unknown",
            "evidence": {"gap": "analyst package not importable from current PYTHONPATH "
                                "— optional dependency, degrades rather than errors"},
            "quality": {"completeness": 0.0, "note": "instrument not on path"},
            "next_command": "PYTHONPATH=packages/analyst/lib python3 -m analyst doctor",
        }
    return {
        "id": "trace-quality", "owner": "unified agent trace",
        "source": f"{trace_schema}/{metrics_schema}", "status": "unknown",
        "evidence": {"gap": "no per-project trace store reader exists; measure with the analyst doctor"},
        "quality": {"completeness": 0.0, "note": "instrument present, no stored measurement to read"},
        "next_command": "PYTHONPATH=packages/analyst/lib python3 -m analyst doctor",
    }


def gather_effective_source_diagnostics(env, *, repo_root):
    """Assemble the five read-only diagnostics from their own sources — the CLI-facing
    counterpart to `build_effective_source_report`'s pure validation/fold."""
    return [
        _identity_ownership_diagnostic(env),
        _cache_diagnostic(),
        _capability_gap_diagnostic(repo_root),
        _hook_ownership_diagnostic(repo_root),
        _trace_quality_diagnostic(repo_root),
    ]


def _print_effective_source_report(report):
    print("skiller doctor --effective-source:")
    for d in report["diagnostics"]:
        print(f"  [{d['status']}] {d['id']} (owner: {d['owner']})")
        print(f"      source: {d['source']}")
        print(f"      evidence: {d['evidence']}")
        print(f"      next: {d['next_command']}")
    print(f"\noverall: {report['overall']}")


# P1.4 (D51/D62/D63): terminal effective-runtime conformance gate. Cold per-provider
# install/discover of the DECLARED fixture (all repo marketplace units minus exactly the
# three donor buckets `general`/`research`/`oss-dev`, D42-conformant), asserting
# catalog-wide identity uniqueness — never a list of named IDs — plus a negative fixture
# that proves the nine excluded core/donor pairs and the class-B `workflow-craft`
# precondition are diagnosed, not silently dropped. Materialization is confined to a
# caller-owned `tempfile.TemporaryDirectory`; canonical bytes are always read from the
# real `package_root` (never copied into a live profile/cache/home).
_DONOR_BUCKETS = _CORE_DONOR_BUCKETS


def _fixture_catalog(catalog, *, exclude_bucket_ids=_DONOR_BUCKETS):
    """The D51 positive-fixture view: every catalog unit minus exactly the donor buckets.
    Root-bootstrap (private/source-only) never reaches `catalog.units` at all — nothing to
    filter there. A pure data transform: no filesystem access."""
    kept_units = tuple(unit for unit in catalog.units
                       if not (unit.kind == "bucket" and unit.plugin_id in exclude_bucket_ids))
    kept_ids = {member for unit in kept_units for member in unit.member_ids}
    kept_skills = tuple(skill for skill in catalog.skills if skill.semantic_id in kept_ids)
    return dataclasses.replace(catalog, units=kept_units, skills=kept_skills)


def declared_fixture_unit_set(catalog, *, repo_root, package_root=None):
    """D51 declared literal (`artifacts/P1.4/fixture-unit-set.json`, schema v1): the
    positive fixture's exact input, one record per provider. Both providers share one
    provider-neutral catalog, so `units` is identical by construction — the schema still
    carries a record per provider so a future provider-specific catalog can diverge
    without a schema change."""
    fixture = _fixture_catalog(catalog)
    units = sorted({unit.plugin_id for unit in fixture.units} |
                   {sibling.name for sibling in catalog.sibling_plugins})
    from .publication import package_rel
    prefix = package_rel(repo_root, package_root or Path(__file__).resolve().parents[2])
    identity_source = f"{prefix + '/' if prefix else ''}lib/skiller/registry.py::build_catalog"
    per_provider = {
        "codex": {"marketplace": ".agents/plugins/marketplace.json"},
        "claude-code": {"marketplace": ".claude-plugin/marketplace.json"},
    }
    providers = {}
    for provider, extra in per_provider.items():
        providers[provider] = {
            "marketplace": extra["marketplace"],
            "excluded": sorted(_DONOR_BUCKETS),
            "excluded_reason": "d42-donor-bucket",
            "units": units,
            "identity_source": identity_source,
        }
    return {"schema_version": "p1.4-fixture-unit-set/v1", "providers": providers}


def _sibling_identities(repo_root, sibling, *, manifest_name):
    """Read-only, D44-ordered: a sibling package's OWN plugin manifest names its declared
    `skills` root(s) — never a blind recursive walk of the package. Returns the immediate
    subdirectory names that carry a SKILL.md (empty when the manifest declares `commands`
    only, e.g. `task`'s Claude side — commands are a different identity space)."""
    manifest_path = repo_root / sibling.source_path / manifest_name
    if not manifest_path.is_file():
        return ()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    roots = data.get("skills")
    if isinstance(roots, str):
        roots = [roots]
    if not isinstance(roots, list):
        return ()
    identities = set()
    for raw in roots:
        if not isinstance(raw, str):
            continue
        root_dir = (manifest_path.parent.parent / raw).resolve()
        if not root_dir.is_dir():
            continue
        for entry in sorted(root_dir.iterdir()):
            if entry.is_dir() and (entry / "SKILL.md").is_file():
                identities.add(entry.name)
    return tuple(sorted(identities))


def _materialize_repository_bootstrap_sources(*, repo_root, package_root, tmp_root):
    """Copy exactly the bytes `render_repository_bootstrap_projections` reads (class-A
    config + 13 canonical EN-only carriers; class-B canon at its real repo-relative path)
    into `tmp_root`, never the live repo — `render_repository_bootstrap_projections`
    calls `.resolve()` on `package_root`, which would defeat a symlink and silently read
    the real tree, so a real (small) copy is the only way to keep the read genuinely
    cold. Returns the fixture's `package_root` Path."""
    rel_pkg = package_root.relative_to(repo_root)
    fixture_package_root = tmp_root / rel_pkg
    if fixture_package_root.exists():
        return fixture_package_root
    (fixture_package_root / "configs").mkdir(parents=True, exist_ok=True)
    for name in ("repository-bootstrap-skills.json", "publication-versions.json"):
        shutil.copy2(package_root / "configs" / name, fixture_package_root / "configs" / name)
    shutil.copytree(package_root / "skills" / "repository-bootstrap",
                    fixture_package_root / "skills" / "repository-bootstrap")
    workflow_craft_src = package_root / "skills" / "general" / "workflow-craft" / "SKILL.md"
    if workflow_craft_src.is_file():
        dest = fixture_package_root / "skills" / "general" / "workflow-craft" / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workflow_craft_src, dest)
    return fixture_package_root


def build_provider_carrier_map(catalog, *, repo_root, package_root, provider, tmp_root):
    """Cold install+discover of the D51 fixture for ONE provider into `tmp_root` (a
    caller-owned `tempfile.TemporaryDirectory`). Returns `{identity: sorted(carriers)}`.

    Carrier vocabulary: `unit:<plugin_id>` for a bucket/curated/bucket-alias/sibling
    member (identity map read from the generated publication catalog/each unit's own
    declaration — never a recursive source-tree walk, D44); `root:<provider>` for a
    root-bootstrap projection actually materialized for this provider. Bucket/curated
    membership needs no I/O (it is already fully known from the catalog); root-bootstrap
    projections ARE written to `tmp_root` and read back, so the class-A/B generator is
    genuinely exercised cold, not merely trusted in memory."""
    from .publication import render_repository_bootstrap_projections

    fixture = _fixture_catalog(catalog)
    by_id = {skill.semantic_id: skill for skill in fixture.skills}
    carriers: dict[str, set[str]] = {}
    for unit in fixture.units:
        if unit.kind not in ("bucket", "curated", "bucket-alias"):
            continue
        for member in unit.member_ids:
            skill = by_id.get(member)
            if skill is not None:
                carriers.setdefault(skill.name, set()).add(f"unit:{unit.plugin_id}")

    manifest_name = ".codex-plugin/plugin.json" if provider == "codex" else ".claude-plugin/plugin.json"
    for sibling in catalog.sibling_plugins:
        if provider == "codex" and not sibling.codex_supported:
            continue
        for identity in _sibling_identities(repo_root, sibling, manifest_name=manifest_name):
            carriers.setdefault(identity, set()).add(f"unit:{sibling.package}")

    fixture_package_root = _materialize_repository_bootstrap_sources(
        repo_root=repo_root, package_root=package_root, tmp_root=tmp_root)
    bootstrap_artifacts = render_repository_bootstrap_projections(
        repo_root=tmp_root, package_root=fixture_package_root)
    root_provider_key = "claude" if provider == "claude-code" else "codex"
    for artifact in bootstrap_artifacts:
        if artifact.provider != root_provider_key:
            continue
        target = tmp_root / artifact.target if not artifact.target.is_absolute() else artifact.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.managed_bytes)
        # Discover cold, off the materialized fixture disk — not the in-memory artifact.
        if target.is_file():
            carriers.setdefault(target.parent.name, set()).add(f"root:{provider}")

    return {identity: sorted(members) for identity, members in carriers.items()}


def catalog_wide_collisions(carrier_map):
    """Every identity with ≥2 carriers — the whole declared fixture, never a named list."""
    return {identity: carriers for identity, carriers in carrier_map.items()
            if len(carriers) >= 2}


def negative_fixture_diagnostics(catalog, *, repo_root, package_root, tmp_root):
    """The D51 negative fixture: `core` and every donor bucket enabled together. Proves the
    nine core/donor pairs surface as named D42 diagnostics (never silently dropped) and
    that the class-B `workflow-craft` precondition fails closed when its donor bucket
    (`general`) is enabled. Returns `(nine_pairs, workflow_craft_error)`."""
    from .publication import render_repository_bootstrap_projections

    worst_case = _worst_case_enabled(catalog)
    pairs = detect_core_donor_collisions(catalog, enabled=worst_case)
    fixture_package_root = _materialize_repository_bootstrap_sources(
        repo_root=repo_root, package_root=package_root, tmp_root=tmp_root)
    try:
        render_repository_bootstrap_projections(
            repo_root=tmp_root, package_root=fixture_package_root,
            donor_enabled={"general": True})
        workflow_craft_error = None
    except ValueError as exc:
        workflow_craft_error = str(exc)
    return pairs, workflow_craft_error


def reconcile_remediation_collisions(collisions, *, positive_maps, negative_pairs,
                                     terminal_owner_items):
    """D62: classify every FROZEN `remediation-map.json` collision record as exactly one of
    `still-measured` / `resolved` / `unowned-or-unexplained` against the fresh perimeter
    measured by THIS item — never against the frozen snapshot's own point-in-time counters.

    A record whose `classes` include `unit-vs-unit` (a core↔donor-bucket pair) is D42's
    permanent, by-construction diagnostic — it never closes; it classifies `still-measured`
    iff the exact (identity, donor) pair is still among `negative_pairs`. A pure
    `root-vs-unit` record (the 16 deleted root duplicates, or class-B `workflow-craft`)
    classifies `resolved` iff the positive fixture no longer shows it as a live collision
    (root-vs-unit) AND every one of its owner items is terminal; `still-measured` if it is
    still a live collision in the positive fixture; otherwise `unowned-or-unexplained`."""
    negative_index = {(item["identity"], donor) for item in negative_pairs
                      for donor in (carrier.split(":", 1)[1] for carrier in item["carriers"]
                                   if carrier.startswith("unit:") and carrier.split(":", 1)[1] != "core")}
    results = []
    for record in collisions:
        classes = set(record.get("classes", ()))
        owners = [owner["owner_item"] for owner in record.get("owners", ())]
        identity = record["identity"]
        if "unit-vs-unit" in classes:
            donor = next((carrier.split(":", 1)[1] for carrier in record["carriers"]
                         if carrier.startswith("unit:") and carrier.split(":", 1)[1] != "core"), None)
            outcome = "still-measured" if (identity, donor) in negative_index \
                else "unowned-or-unexplained"
        else:
            carriers_now = positive_maps.get(record["provider"], {}).get(identity, [])
            if len(carriers_now) >= 2:
                outcome = "still-measured"
            elif owners and all(owner in terminal_owner_items for owner in owners):
                outcome = "resolved"
            else:
                outcome = "unowned-or-unexplained"
        results.append({"identity": identity, "provider": record["provider"], "outcome": outcome})
    return results


def run_effective_runtime_gate(env, *, terminal_owner_items=("P1.2", "P1.3", "P1.5")):
    """Orchestrate the full P1.4 gate: declared fixture → cold positive install/discover per
    provider (catalog-wide collisions + undeclared-root completeness) → negative fixture
    (D42 nine pairs + class-B precondition) → D62 reconciliation against the frozen
    `remediation-map.json`. Returns a plain dict — the CLI/tests decide what to print or
    persist; this function never writes outside the `tempfile.TemporaryDirectory` it owns."""
    from core import find_repo_root
    from .registry import build_catalog, build_registry
    from .publication import assert_root_bootstrap_set_completeness

    root = env.root
    repo_root = find_repo_root(root) or root
    registry, bucket_meta, bucket_dirs = build_registry(env)
    catalog = build_catalog(env, bucket_meta, bucket_dirs, registry)

    fixture_unit_set = declared_fixture_unit_set(catalog, repo_root=repo_root, package_root=root)

    positive_maps = {}
    collisions_by_provider = {}
    undeclared_by_provider = {}
    for provider in ("codex", "claude-code"):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            carrier_map = build_provider_carrier_map(
                catalog, repo_root=repo_root, package_root=root,
                provider=provider, tmp_root=tmp_root)
            positive_maps[provider] = carrier_map
            collisions_by_provider[provider] = catalog_wide_collisions(carrier_map)
            root_artifacts = [
                type("A", (), {"provider": "claude" if provider == "claude-code" else "codex",
                               "identity": identity})()
                for identity, carriers in carrier_map.items()
                if any(c == f"root:{provider}" for c in carriers)]
            undeclared_by_provider[provider] = assert_root_bootstrap_set_completeness(
                tmp_root, root_artifacts)

    with tempfile.TemporaryDirectory() as tmp:
        negative_pairs, workflow_craft_error = negative_fixture_diagnostics(
            catalog, repo_root=repo_root, package_root=root, tmp_root=Path(tmp))

    return {
        "fixture_unit_set": fixture_unit_set,
        "positive_maps": positive_maps,
        "collisions_by_provider": collisions_by_provider,
        "undeclared_by_provider": undeclared_by_provider,
        "negative_pairs": negative_pairs,
        "workflow_craft_precondition_error": workflow_craft_error,
    }


def _effective_carrier_set_document(gate_result, *, commit_sha):
    """`artifacts/P1.4/effective-carrier-set.json` (D62 schema v1): the post-remediation
    identity→carriers map, one record per provider, on a named commit."""
    fixture_unit_set = "fixture-unit-set.json"
    providers = {}
    for provider, carrier_map in gate_result["positive_maps"].items():
        providers[provider] = {
            "fixture_unit_set": fixture_unit_set,
            "identities": [{"identity": identity, "carriers": carriers}
                          for identity, carriers in sorted(carrier_map.items())],
        }
    return {"schema_version": "p1.4-effective-carrier-set/v1",
            "measured_at_commit": commit_sha, "providers": providers}


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {"--downstream": "bool", "--vendor-drift": "bool",
                              "--settings": "bool", "--provider-distribution": "bool",
                              "--context": "bool", "--provider": "str",
                              "--effective-runtime": "bool", "--fixture-out": "str",
                              "--carrier-out": "str", "--target": "str",
                              "--effective-source": "bool", "--json": "bool"})
    if opts["help"]:
        print("skiller doctor [--downstream] [--vendor-drift] [--settings [--target P]]\n"
              "  --downstream:   hygiene publish-surface onboarded projects "
              "(CLAUDE.md ≤200, scoped/unscoped rules, deny-preset).\n"
              "  --vendor-drift: by design drift vendor-skills from the registry "
              "(new/changed managed-skills; dry calculation).\n"
              "  --provider-distribution: read-only preflight Claude/Codex delivery; "
              "does not start native installer.\n"
              "  --context [--provider claude-code|codex|cursor|grok] [--target P]: "
              "provider-aware first-turn footprint; Codex reads its effective native "
              "prompt inventory and reports duplicate skills / plugins outside policy.\n"
              "  --effective-runtime [--fixture-out F] [--carrier-out F]: P1.4 cold "
              "install/discover conformance gate (declared fixture, catalog-wide "
              "uniqueness, D42 negative fixture); opt. record declared-literal/carrier-set.\n"
              "  --effective-source [--json]: read-only composed effective-source doctor "
              "(active semantic owner/provenance/collisions, cache, capability/reference "
              "coverage, hook ownership, trace-quality — versioned JSON with --json).\n"
              "  --settings:     settings audit Claude Code (facade → harness "
              "doctor --settings).")
        return
    if opts.get("settings"):
        _delegate_settings_doctor(env, opts)
        return
    if opts.get("context"):
        from .budget import first_turn_report, format_first_turn_report
        from .config import resolve_target
        provider = opts.get("provider") or "claude-code"
        if provider not in {"claude-code", "codex", "cursor", "grok"}:
            raise SystemExit("--provider: expected claude-code|codex|cursor|grok")
        target, _ = resolve_target(env, opts)
        report = first_turn_report(env, target, provider=provider)
        skills = report["sources"]["skills"]
        diagnostics = []
        if skills.get("duplicates"):
            diagnostics.append({
                "code": "SKILL_DUPLICATE_NAME",
                "names": [row["name"] for row in skills["duplicates"]],
            })
        if skills.get("enabled_outside_project_policy"):
            diagnostics.append({
                "code": "CODEX_PLUGIN_ENABLED_OUTSIDE_PROJECT_POLICY",
                "plugins": skills["enabled_outside_project_policy"],
            })
        if skills.get("desired_plugins_not_effective"):
            diagnostics.append({
                "code": "CODEX_DESIRED_PLUGIN_NOT_EFFECTIVE",
                "plugins": skills["desired_plugins_not_effective"],
            })
        report["diagnostics"] = diagnostics
        report["status"] = ("degraded" if diagnostics or
                            report.get("measurement_status") == "incomplete" else "ok")
        if opts.get("json"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_first_turn_report(report))
            for diagnostic in diagnostics:
                values = diagnostic.get("names", diagnostic.get("plugins", []))
                print(f"{diagnostic['code']}: {', '.join(values)}")
        return
    if opts.get("effective_source"):
        from core import find_repo_root
        repo_root = find_repo_root(env.root) or env.root
        diagnostics = gather_effective_source_diagnostics(env, repo_root=repo_root)
        report = build_effective_source_report(diagnostics)
        if opts.get("json"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_effective_source_report(report)
        return
    if opts.get("provider_distribution"):
        from .config import resolve_target
        target, _ = resolve_target(env, opts)
        _provider_distribution_doctor(env, target)
        return
    if opts.get("effective_runtime"):
        result = run_effective_runtime_gate(env)
        failures = []
        for provider in ("codex", "claude-code"):
            for identity, carriers in result["collisions_by_provider"][provider].items():
                failures.append(f"{provider}: {identity} has ≥2 carriers: {carriers}")
            failures.extend(f"{provider}: {msg}" for msg in result["undeclared_by_provider"][provider])
        print("skiller doctor --effective-runtime:")
        print(f"  positive fixture: codex {len(result['positive_maps']['codex'])} identities, "
              f"claude-code {len(result['positive_maps']['claude-code'])} identities")
        print(f"  negative fixture: {len(result['negative_pairs'])} D42 pairs, "
              f"workflow-craft precondition error: "
              f"{'yes' if result['workflow_craft_precondition_error'] else 'NO (BUG)'}")
        if opts.get("fixture_out"):
            atomic_write_json(Path(opts["fixture_out"]), result["fixture_unit_set"])
        if opts.get("carrier_out"):
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=env.root,
                                 capture_output=True, text=True, check=False).stdout.strip()
            atomic_write_json(Path(opts["carrier_out"]),
                              _effective_carrier_set_document(result, commit_sha=sha or "unknown"))
        if failures:
            print("  FAILURES:")
            for item in failures:
                print(f"    - {item}")
            sys.exit(1)
        print("  OK — 0 catalog-wide collisions, 0 undeclared root directories")
        return
    root = env.root
    issues = 0

    def check(ok, label, hint=""):
        nonlocal issues
        mark = "ok " if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {hint}" if hint and not ok else ""))
        if not ok:
            issues += 1

    print(f"skiller doctor (registry: {root})")
    check(sys.version_info >= (3, 8), f"python3 {sys.version.split()[0]}")

    link = Path(os.path.expanduser("~/.local/bin/skiller"))
    resolved = Path(os.path.realpath(link)) if link.exists() else None
    check(resolved is not None and is_within(resolved, root),
          f"symlink {link}",
          "restart install.sh from the registry repository")
    on_path = any(Path(p or ".").resolve() == link.parent.resolve()
                  for p in os.environ.get("PATH", "").split(os.pathsep))
    check(on_path, f"{link.parent} in PATH",
          'add: export PATH="$HOME/.local/bin:$PATH"')

    db_file = env.db_file
    if db_file.exists():
        try:
            db = json.loads(db_file.read_text(encoding="utf-8"))
            check(db.get("version", 1) <= DB_VERSION,
                  f"projects.json (entries: {len(db.get('projects', []))})",
                  "version newer than supported - git pull in the registry")
            stale = [p for p in db.get("projects", [])
                     if not Path(p["path"]).is_dir()]
            check(not stale,
                  "records projects.json point to existing directories",
                  f"{len(stale)} obsolete - skiller list --prune")
        except json.JSONDecodeError:
            check(False, "projects.json is parsed",
                  "broken JSON — the next entry will recreate the file")
    else:
        check(True, "projects.json missing (will be created the first time connect/vendor)")

    sha, dirty = registry_git_state(env)
    check(sha is not None, "registry - git-repository")
    if sha:
        check(not dirty, f"registry is clean (HEAD {sha})",
              "there are uncommitted skill changes - marketplace sees "
              "commits only")
    profiles = sorted((root / "profiles").glob("*.json"))
    bad = []
    for p in profiles:
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            bad.append(p.name)
    check(profiles and not bad, f"profiles are loading ({len(profiles)})",
          f"broken: {', '.join(bad)}")

    # harness (environment Claude Code — permissions/MCP/hooks) — OPTIONAL
    # dependency: apply_permissions/_run_harness graceful-skip'if it's not there
    # (standalone-layout / not installed). Previously doctor didn't look at all
    # harness — «not installed» and «installed but broken» (broken binary/venv/etc.)
    # were indistinguishable: connect/integrate quietly lost permissions-presets, and doctor
    # reported «All checks passed» (audit Doc-1). Absence - NOT FAIL (this
    # optional package); broken if present - FAIL.
    hbin = harness_bin(env)
    if hbin is None:
        print("  [ok ] harness not installed - optional (permissions/MCP/hooks "
              "do not apply; installation: packages/harness/install.sh)")
    else:
        try:
            r = subprocess.run([str(hbin), "--help"], capture_output=True,
                               text=True, timeout=10, check=False)
            check(r.returncode == 0, f"harness is being executed ({hbin})",
                  f"exit {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")
        except subprocess.TimeoutExpired:
            check(False, f"harness is being executed ({hbin})", "timeout exceeded 10s")
        except OSError as e:
            check(False, f"harness is being executed ({hbin})", str(e))

    # JSON-config schemes (schema/*.json) — DX-artifact (IntelliSense). Runtime-
    # manual validation (CONFIG_KEYS/SKILLSET_KEYS); scheme should not diverge from
    # code, otherwise the editor suggests something other than what it accepts skiller. Same gate
    # holds tests/test_schema.py; doctor gives it as an interactive check.
    from .common import CONFIG_KEYS
    from .skillset import SKILLSET_KEYS
    for fname, keys, label in (
            ("swissknife.schema.json", CONFIG_KEYS, ".swissknife.json"),
            ("swissknifeman-config.schema.json", SKILLSET_KEYS,
             ".swissknifeman/config.json")):
        sf = root / "schema" / fname
        if not sf.is_file():
            check(False, f"diagram {fname}", "no file in schema/")
            continue
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("schema root must be an object")
            props = set(data.get("properties", {}))
        except (json.JSONDecodeError, ValueError) as e:
            check(False, f"diagram {fname} is parsed", str(e))
            continue
        check(props == set(keys), f"diagram {fname} ⇄ keys {label}",
              f"separated: extra ones in the scheme {sorted(props - set(keys))}, "
              f"not in the schema {sorted(set(keys) - props)} — update schema/{fname}")
        # Doc-2: key names aren't the only thing that can diverge. Property TYPE
        # in the schema (string/array/…) — also a contract with CONFIG_KEYS/SKILLSET_KEYS; before
        # doctor checked only names ("⇄ keys OK"), silently overlooking the discrepancy
        # type (test test_schema.py::test_property_types_align_with_python catches it,
        # but doctor falsely reassured interactive "OK").
        json_type = {str: "string", list: "array", int: "integer",
                    dict: "object", bool: "boolean"}
        props_data = data.get("properties", {})
        type_mismatches = []
        for k, t in keys.items():
            if k not in props_data:
                continue
            if isinstance(t, tuple):
                # Multi-type (memory_brain = (str, dict)) → in the schema oneOf; check,
                # that the members cover exactly the expected JSON-types.
                members = {b.get("type") for b in props_data[k].get("oneOf", [])}
                want = {json_type.get(x) for x in t}
                if members != want:
                    type_mismatches.append(
                        f"{k}: diagram oneOf={sorted(m for m in members if m)} code={sorted(want)}")
            elif props_data[k].get("type") != json_type.get(t):
                type_mismatches.append(
                    f"{k}: diagram={props_data[k].get('type')} code={json_type.get(t)}")
        check(not type_mismatches, f"diagram {fname} ⇄ types {label}",
              f"types diverged: {'; '.join(type_mismatches)} — update schema/{fname}")

    # freshness hubs: stamp <!-- swissknifeman:registry sha=… --> in the project hub
    # check with the current one sha registry (same calculation as in generate-hub.sh). Projects
    # without stamp (old hub) — skip: they will receive a stamp during the next regeneration.
    reg_skills = root / "skills.json"
    if reg_skills.is_file():
        reg_sha = hashlib.sha256(reg_skills.read_bytes()).hexdigest()[:12]
        pat = re.compile(r"swissknifeman:registry sha=([0-9a-f]+)")
        projects = []
        if db_file.exists():
            try:
                projects = json.loads(db_file.read_text(encoding="utf-8")).get("projects", [])
            except json.JSONDecodeError:
                projects = []
        stale_hubs = []
        for p in projects:
            pdir = Path(p["path"])
            if not pdir.is_dir():
                continue
            for cand in (pdir / ".ai/guidelines/swissknifeman-hub.md", pdir / "CLAUDE.md"):
                if not cand.is_file():
                    continue
                m = pat.search(cand.read_text(encoding="utf-8", errors="ignore"))
                if m:
                    if m.group(1) != reg_sha:
                        stale_hubs.append(pdir.name)
                    break
        check(not stale_hubs, f"project hubs are fresh (registry sha {reg_sha})",
              f"{len(stale_hubs)} is deprecated(and): {', '.join(stale_hubs)} — regenerate "
              "(skiller update / generate-hub.sh)")

    if opts.get("downstream"):
        _audit_downstream(env)
    else:
        _downstream_claude_md_summary(env)

    if opts.get("vendor_drift"):
        _audit_vendor_drift(env)
    else:
        _vendor_drift_summary(env)

    print(f"\n{'All checks passed.' if issues == 0 else f'Problems: {issues}'}")
    if issues:
        sys.exit(1)
