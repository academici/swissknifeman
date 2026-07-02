"""doctor — диагностика окружения harness (пресеты, скрипт, файлы хуков)."""
import hashlib
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


def cmd_doctor(env, argv):
    opts = parse_flags(argv, {})
    if opts["help"]:
        print("harness doctor")
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
