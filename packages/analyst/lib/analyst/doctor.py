"""analyst doctor — диагностика окружения пакета (read-only, без внешних вызовов).

Проверяет: python3, наличие пакета `core` на PYTHONPATH (общий фундамент), доступность
CLI `maind` (нужен для surfacing curated-уроков в память — необязателен, только warn)."""
import shutil
import sys

from .common import parse_args


def _check_core():
    try:
        import core  # noqa: F401
        return True
    except Exception:
        return False


def cmd_doctor(env, argv):
    """analyst doctor — диагностика окружения (python/core/maind)."""
    opts, _ = parse_args(argv, {"--json": "bool"})
    if opts["help"]:
        print("analyst doctor [--json] — диагностика окружения пакета.")
        return

    py_ok = sys.version_info >= (3, 8)
    core_ok = _check_core()
    maind_bin = shutil.which("maind")

    checks = {
        "python>=3.8": py_ok,
        "core (общий фундамент на PYTHONPATH)": core_ok,
        "maind (surfacing curated в память, опц.)": bool(maind_bin),
    }
    ok = py_ok and core_ok  # maind — опционально, не роняет вердикт

    if opts["json"]:
        import json
        print(json.dumps({"ok": ok, "checks": checks,
                          "maind_bin": maind_bin}, ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst doctor — {env.root}\n")
    for name, val in checks.items():
        icon = "✓" if val else ("·" if "опц" in name else "✗")
        print(f"  {icon} {name}")
    print()
    if not ok:
        print("Не хватает обязательного окружения (python3.8+ и пакет core).", file=sys.stderr)
        raise SystemExit(1)
    print("Окружение готово.")
