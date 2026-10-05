"""Internal documentation."""
import hashlib
import json
import os
import sys
from pathlib import Path

from .agentpacks import list_packs
from .common import die, parse_flags
from .mcp import available_mcp


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
        print("harness doctor [--settings [--provider claude-code|codex|cursor|grok] [--target P] "
              "[--json] [--profile NAME] | --provider-audit]\n"
              "  without flag: environment diagnostics harness (presets/script/hooks).\n"
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
    ok = True

    def line(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"  {'✓' if good else '✗'} {msg}")

    print("harness doctor:")
    cfg = env.configs_dir
    line(cfg.is_dir(), f"configs/claude-code/ — {cfg}")
    presets = sorted(p.stem.split(".", 1)[1] for p in cfg.glob("settings.*.json")) \
        if cfg.is_dir() else []
    line(bool(presets), f"permissions-presets: {', '.join(presets) or 'no'}")
    line(bool(available_mcp(env)),
         f"MCP-presets: {', '.join(available_mcp(env)) or 'no'}")
    line(env.apply_script.exists(), f"scripts/apply-permissions.sh — {env.apply_script}")
    line(bool(list_packs(env)), f"agent-packs: {', '.join(list_packs(env)) or 'no'}")

    hooks = env.home / ".claude" / "hooks"
    have = {d: (hooks / d).exists() for d in ("notify", "auto-approve", "memory")}
    if all(have.values()):
        print("  ✓ hook files installed globally (~/.claude/hooks/)")
    else:
        missing = [d for d, v in have.items() if not v]
        print(f"  · hook files not installed: {', '.join(missing)} "
              f"(put: harness hooks --global)")



    rr_src = env.configs_dir / "hooks" / "run-report"
    rr_dst = hooks / "run-report"
    stale = [f for f in _RUN_REPORT_FILES if _sha256(rr_src / f) != _sha256(rr_dst / f)]
    if stale:
        print(f"  · hook run-report rotten ({', '.join(stale)}) — repeat harness hooks --global")

    print(f"  · review-gate: {_review_gate_state(hooks)}")





    print("  · route evidence: live model — from payload hook/`codex doctor --json`; "
          "effort remains self-attested (the `--actor` declared to `plan.py start`)")

    print("\nharness: OK" if ok else "\nharness: there are problems (see ✗)")
