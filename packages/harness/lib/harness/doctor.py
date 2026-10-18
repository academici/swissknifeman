"""Internal documentation."""
import hashlib
import json
import os
import sys
from pathlib import Path

from .agentpacks import list_packs
from aicore import MIN_PYTHON
from aicore.util.cli import parse_flags
from aicore.util.term import die
from .mcp import available_mcp

RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"


_RUN_REPORT_FILES = ("run-report.py", "_lib.py", "_usage.py")


_REVIEW_GATE_CHECK_CODES = {"generated-assets": "G1", "plan-check": "G2", "tests-touched": "W1"}


def _review_gate_mode(env_path):
    """Internal documentation."""
    if not env_path.exists():
        return "warn"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("MODE") and "=" in line:
            val = line.split("=", 1)[1].strip().strip("\"'")
            return val if val in ("off", "warn", "strict") else "warn"
    return "warn"


def _review_gate_state(hooks_dir):
    """Internal documentation."""
    rg = hooks_dir / "review-gate"
    if _review_gate_mode(rg / "env.ini") == "off":
        return "disabled (MODE=off)"
    cfg_path = rg / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unconfigured (no-op)"
    checks = cfg.get("checks") or []
    if not cfg.get("check_command") or not checks:
        return "unconfigured (no-op)"
    by_mode = {}
    for c in checks:
        code = _REVIEW_GATE_CHECK_CODES.get(c.get("name", ""), c.get("name", "?"))
        by_mode.setdefault(c.get("mode", "warn"), []).append(code)
    parts = [f"{', '.join(by_mode[m])} ({m})" for m in ("strict", "warn") if by_mode.get(m)]
    return "configured: " + ", ".join(parts) if parts else "unconfigured (no-op)"


def _sha256(path):
    """Internal documentation."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _result(check_id, status, observed, *, category="environment", evidence=None, remediation=None, repair=None):
    doc = {"$schema": RESULT_SCHEMA, "check_id": check_id, "status": status,
           "category": category, "observed": observed}
    if evidence:
        doc["evidence"] = evidence
    if remediation:
        doc["remediation"] = remediation
    if repair:
        doc["repair"] = repair
    return doc


def has_failure(results):
    return any(doc["status"] == "fail" for doc in results)


def render_text(results):
    lines = []
    for doc in results:
        lines.append(f"{doc['status']} {doc['check_id']}: {doc['observed']}")
        if doc.get("remediation"):
            lines.append(f"  remediation: {doc['remediation']}")
    return lines


def _environment_check(env):
    floor = ".".join(str(part) for part in MIN_PYTHON)
    problems = []
    evidence = [f"python3 {sys.version.split()[0]}"]
    if sys.version_info < tuple(MIN_PYTHON):
        problems.append(f"python3 >= {floor} is required")
    cfg = env.configs_dir
    if not cfg.is_dir():
        problems.append(f"configs/claude-code/ is missing: {cfg}")
    presets = sorted(p.stem.split(".", 1)[1] for p in cfg.glob("settings.*.json")) if cfg.is_dir() else []
    mcp_presets = available_mcp(env)
    packs = list_packs(env)
    evidence.append(f"permissions-presets: {', '.join(presets) or 'none'}")
    evidence.append(f"mcp-presets: {', '.join(mcp_presets) or 'none'}")
    evidence.append(f"agent-packs: {', '.join(packs) or 'none'}")
    if cfg.is_dir() and not presets:
        problems.append("no permissions presets")
    if not mcp_presets:
        problems.append("no MCP presets")
    if not env.apply_script.exists():
        problems.append(f"scripts/apply-permissions.sh is missing: {env.apply_script}")
    if not packs:
        problems.append("no agent-packs")
    if problems:
        return _result("harness.environment", "fail", "; ".join(problems), evidence=evidence,
                       remediation="Reinstall the harness module.")
    return _result("harness.environment", "ok", f"python3 >= {floor}, configs, presets and agent-packs present",
                   evidence=evidence)


def _differs(shipped, installed):
    return shipped.is_file() and _sha256(shipped) != _sha256(installed)


def _auto_approve_drift(env, hooks):
    """Code files of the shipped auto-approve hook (and the command logger) that the installed copy lacks or has
    changed; ``env.ini`` and ``config.json`` are the machine's own and are not compared."""
    source = env.configs_dir / "hooks"
    pairs = [(source / "log-bash-command.sh", hooks / "log-bash-command.sh")]
    for pattern in ("auto-approve.sh", "lib/*.sh", "lib/*.py", "modes/*.sh"):
        for shipped in sorted((source / "auto-approve").glob(pattern)):
            pairs.append((shipped, hooks / "auto-approve" / shipped.relative_to(source / "auto-approve")))
    return [str(installed.relative_to(hooks)) for shipped, installed in pairs if _differs(shipped, installed)]


def _hooks_check(env):
    hooks = env.home / ".claude" / "hooks"
    missing = [name for name in ("notify", "auto-approve", "memory") if not (hooks / name).exists()]
    if missing:
        return _result("harness.hooks", "warn", f"hook files not installed: {', '.join(missing)}",
                       category="integration", remediation="harness hooks --global")
    evidence = []
    stale = [f for f in _RUN_REPORT_FILES
             if _sha256(env.configs_dir / "hooks" / "run-report" / f) != _sha256(hooks / "run-report" / f)]
    evidence.append(f"review-gate: {_review_gate_state(hooks)}")
    code_drift = _auto_approve_drift(env, hooks)
    if code_drift:
        return _result("harness.hooks", "warn",
                       f"installed auto-approve hook differs from the shipped one ({', '.join(code_drift)})",
                       category="integration", evidence=evidence, remediation="harness hooks --global")
    config_drift = [name for name in ("config.json",) if _differs(
        env.configs_dir / "hooks" / "auto-approve" / name, hooks / "auto-approve" / name)]
    if config_drift:
        evidence.append("auto-approve/config.json is a local copy that differs from the shipped one "
                        "(kept on purpose; compare it to pick up new deny patterns)")
    if stale:
        return _result("harness.hooks", "warn", f"hook run-report is stale ({', '.join(stale)})",
                       category="integration", evidence=evidence, remediation="harness hooks --global")
    return _result("harness.hooks", "ok", "hook files installed globally (~/.claude/hooks/)",
                   category="integration", evidence=evidence)


def _hooks_env_check(project):
    check = "harness.hooks-env"
    if not (project / ".swissknifeman" / "config.toml").is_file():
        return _result(check, "skip", "the current directory has no .swissknifeman/config.toml", category="config")
    from aicore.config import ConfigError
    from . import hooks_env
    try:
        state = hooks_env.hooks_state(project)
    except ConfigError as error:
        return _result(check, "fail", f"hook modes cannot be resolved: {error}", category="config",
                       remediation="Fix [harness.hooks] in .swissknifeman/config.toml.")
    evidence = [f"legacy: {path}" for path in state["legacy"]]
    repair = {"plan": ["bin/harness", "hooks", "sync", "--target", str(project), "--dry-run"],
              "apply": ["bin/harness", "hooks", "sync", "--target", str(project)]}
    if state["stale"]:
        return _result(check, "warn", f"{hooks_env.CARRIER_REL} does not match the project configuration",
                       category="config", evidence=evidence, remediation="Run: harness hooks sync", repair=repair)
    if state["legacy"]:
        return _result(check, "warn", f"{hooks_env.CARRIER_REL} is current; legacy env.ini files are still read",
                       category="config", evidence=evidence,
                       remediation="Move the modes into [harness.hooks] and run: swissknifeman upgrade")
    return _result(check, "ok", f"{hooks_env.CARRIER_REL} matches the project configuration", category="config")


def _safe_dirs_check(env):
    from .safedirs import state_candidates
    found = [path for path in state_candidates(env) if path.is_file()]
    if not found:
        return _result("harness.safe-dirs", "ok", "no safe-dirs file; the defaults apply", category="state")
    active, rest = found[0], found[1:]
    try:
        document = json.loads(active.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("the root is not an object")
    except (OSError, ValueError) as error:
        return _result("harness.safe-dirs", "fail", f"{active} cannot be read: {error}", category="state",
                       evidence=[f"active: {active}"], remediation="Fix or remove the file.")
    evidence = [f"active: {active}"] + [f"legacy: {path}" for path in rest]
    if active != state_candidates(env)[0]:
        return _result("harness.safe-dirs", "warn", f"safe-dirs is read from {active}, not the current location",
                       category="state", evidence=evidence,
                       remediation="Move it to <config>/harness/safe-dirs.json (swissknifeman upgrade).")
    if rest:
        return _result("harness.safe-dirs", "warn",
                       f"safe-dirs is read from {active}; leftover legacy file(s) are ignored",
                       category="state", evidence=evidence,
                       remediation="Remove the legacy file (swissknifeman upgrade).")
    return _result("harness.safe-dirs", "ok", f"safe-dirs file {active}", category="state", evidence=evidence)


def run_checks(env, project=None):
    """The base doctor checks as ``check-result/v1`` documents (read-only)."""
    project = Path(project or os.getcwd())
    return [_environment_check(env), _hooks_check(env), _hooks_env_check(project), _safe_dirs_check(env)]


def _cmd_doctor_settings(env, opts):
    """Internal documentation."""
    from .settings_audit import (
        Context, build_context, exit_code, load_codex_layers, render_json_obj,
        render_provider_json_obj, render_provider_text, render_text, run_checks,
        run_codex_checks, run_cursor_checks,
    )
    target = opts["target"] or os.getcwd()
    provider = opts["provider"] or None
    if provider not in (None, "claude-code", "codex", "cursor", "grok"):
        die(f"--provider unknown: {provider} (claude-code|codex|cursor|grok)")
    if provider == "codex" and opts["profile"]:
        die("--profile only applies to --provider claude-code")

    if provider in ("codex", "grok"):
        layers = load_codex_layers(env, target, state_dir=".codex" if provider == "codex" else ".grok")
        ctx = Context(layers=layers, values={}, provenance={}, target=Path(target), env=env)
        findings = run_codex_checks(layers)
        if opts["json"]:
            print(json.dumps(render_provider_json_obj(provider, ctx, findings), ensure_ascii=False))
        else:
            print(render_provider_text(provider, ctx, findings))
        sys.exit(exit_code(findings))

    profile_name = opts["profile"] or None
    ctx = build_context(env, target, profile_name=profile_name)
    if provider == "cursor":
        findings = run_cursor_checks(ctx)
        if opts["json"]:
            print(json.dumps(render_provider_json_obj(provider, ctx, findings), ensure_ascii=False))
        else:
            print(render_provider_text(provider, ctx, findings))
        sys.exit(exit_code(findings))
    findings = run_checks(ctx)
    if provider == "claude-code":
        if opts["json"]:
            print(json.dumps(render_provider_json_obj(provider, ctx, findings), ensure_ascii=False))
        else:
            print(render_provider_text(provider, ctx, findings))
        sys.exit(exit_code(findings))
    if opts["json"]:
        print(json.dumps(render_json_obj(ctx, findings), ensure_ascii=False))
    else:
        print(render_text(ctx, findings))
    sys.exit(exit_code(findings))


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {
        "--settings": "bool", "--target": "str", "--json": "bool",
        "--profile": "str", "--provider": "str", "--provider-audit": "bool",
    })
    if opts["help"]:
        print("harness doctor [--json] [--settings [--provider claude-code|codex|cursor|grok] [--target P] "
              "[--json] [--profile NAME] | --provider-audit]\n"
              "  without flag: environment diagnostics harness (presets/script/hooks); --json prints\n"
              "              a list of check-result/v1 documents.\n"
              "  --settings: audit of settings layers of the selected provider\n"
              "              (without --provider is saved legacy-report Claude Code)\n"
              "              (report, --json, exit-code 0 clean / 1 warn / 2 error).")
        return
    if opts["provider"] and not opts["settings"]:
        die("--provider for doctor is only applicable in conjunction with --settings")
    if opts["provider_audit"]:
        from .provider_audit import audit_package
        report = audit_package(env.root)
        print(report.render() if opts["json"] else "harness provider audit: " + ("OK" if report.green else "ERROR"))
        if not opts["json"] and report.diagnostics:
            print("\n".join(report.diagnostics))
        if not report.green:
            sys.exit(2)
        return
    if opts["settings"]:
        _cmd_doctor_settings(env, opts)
        return
    results = run_checks(env)
    if opts["json"]:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("harness doctor:")
        for line in render_text(results):
            print(line)
        print("\nroute evidence: live model - from payload hook/`codex doctor --json`; "
              "effort remains self-attested (the `--actor` declared to `plan.py start`)")
        print("harness: OK" if not has_failure(results) else "harness: there are problems (see fail)")
    if has_failure(results):
        sys.exit(1)
