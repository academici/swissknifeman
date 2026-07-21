"""doctor — диагностика окружения harness (пресеты, скрипт, файлы хуков) + аудит
настроек Claude Code (`--settings`, settings-doctor).

Две НЕсмешиваемые ветки: без флага — диагностика окружения самого harness (пресеты,
apply-скрипт, файлы хуков); с `--settings` — аудит слоёв настроек Claude Code
целевого проекта (движок `settings_audit`), с человекочитаемым отчётом или единым
JSON-документом и exit-code 0/1/2. Ветки не пересекаются в выводе (ранний return)."""
import hashlib
import json
import os
import sys
from pathlib import Path

from .agentpacks import list_packs
from .common import parse_flags
from .mcp import available_mcp

# run-report SCHEMA=2: файлы хука, чью свежесть сверяем против источника в репо.
_RUN_REPORT_FILES = ("run-report.py", "_lib.py", "_usage.py")


def _sha256(path):
    """sha256 файла или None (нет файла/не читается) — для сравнения «свежести»."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _cmd_doctor_settings(env, opts):
    """Ветка `--settings`: аудит слоёв настроек Claude Code целевого проекта.
    Отдельная от диагностики окружения harness (ранний return в `cmd_doctor`) —
    два разных вывода не смешиваются. exit-code 0/1/2 по составу находок; `--json`
    печатает РОВНО один JSON-документ (контракт для fleet-скана P1.6)."""
    from .settings_audit import build_context, exit_code, render_json_obj, render_text, run_checks
    target = opts["target"] or os.getcwd()
    profile_name = opts["profile"] or None
    ctx = build_context(env, target, profile_name=profile_name)
    findings = run_checks(ctx)
    if opts["json"]:
        # Единственный вывод в stdout — иначе fleet-скан P1.6 (json.loads) падает.
        print(json.dumps(render_json_obj(ctx, findings), ensure_ascii=False))
    else:
        print(render_text(ctx, findings))
    sys.exit(exit_code(findings))


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {
        "--settings": "bool", "--target": "str", "--json": "bool",
        "--profile": "str", "--provider-audit": "bool",
    })
    if opts["help"]:
        print("harness doctor [--settings [--target P] [--json] [--profile NAME] | --provider-audit]\n"
              "  без флага:  диагностика окружения harness (пресеты/скрипт/хуки).\n"
              "  --settings: аудит слоёв настроек Claude Code целевого проекта\n"
              "              (отчёт, --json, exit-code 0 чисто / 1 warn / 2 error).")
        return
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
    line(bool(presets), f"permissions-пресеты: {', '.join(presets) or 'нет'}")
    line(bool(available_mcp(env)),
         f"MCP-пресеты: {', '.join(available_mcp(env)) or 'нет'}")
    line(env.apply_script.exists(), f"scripts/apply-permissions.sh — {env.apply_script}")
    line(bool(list_packs(env)), f"agent-packs: {', '.join(list_packs(env)) or 'нет'}")

    hooks = env.home / ".claude" / "hooks"
    have = {d: (hooks / d).exists() for d in ("notify", "auto-approve", "memory")}
    if all(have.values()):
        print("  ✓ файлы хуков установлены глобально (~/.claude/hooks/)")
    else:
        missing = [d for d, v in have.items() if not v]
        print(f"  · файлы хуков не установлены: {', '.join(missing)} "
              f"(поставить: harness hooks --global)")

    # run-report SCHEMA=2: установленный хук может протухнуть (правки configs/ не долетели
    # до ~/.claude/hooks — apply-permissions.sh --global копирует, а не симлинкует).
    rr_src = env.configs_dir / "hooks" / "run-report"
    rr_dst = hooks / "run-report"
    stale = [f for f in _RUN_REPORT_FILES if _sha256(rr_src / f) != _sha256(rr_dst / f)]
    if stale:
        print(f"  · хук run-report протух ({', '.join(stale)}) — повтори harness hooks --global")

    print("\nharness: OK" if ok else "\nharness: есть проблемы (см. ✗)")
