"""doctor — диагностика окружения harness (пресеты, скрипт, файлы хуков)."""
from .agentpacks import list_packs
from .common import parse_flags
from .mcp import available_mcp


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

    print("\nharness: OK" if ok else "\nharness: есть проблемы (см. ✗)")
