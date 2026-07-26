"""analyst doctor — диагностика окружения пакета (read-only, без внешних вызовов).

Проверяет: python3, наличие пакета `core` на PYTHONPATH (общий фундамент), доступность
CLI `maind` (нужен для surfacing curated-уроков в память — необязателен, только warn) и
`task.route_evidence` (P2.4 route/budget evidence — опционально, analyst не зависит от
`task` жёстко)."""
import shutil
import sys

from .common import parse_args


def _check_core():
    try:
        import core  # noqa: F401
        return True
    except Exception:
        return False


def _check_route_evidence():
    """P2.4 (plans/2026.07.24-AGENT-RELIABILITY): опциональный маркер того, что
    `task.route_evidence` (нормализованное route/budget evidence) виден с текущего
    PYTHONPATH — analyst не зависит от `task` жёстко, как и от `maind`."""
    try:
        from task import route_evidence  # noqa: F401
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
    route_evidence_ok = _check_route_evidence()

    checks = {
        "python>=3.8": py_ok,
        "core (общий фундамент на PYTHONPATH)": core_ok,
        "maind (surfacing curated в память, опц.)": bool(maind_bin),
        "task.route_evidence (route/budget evidence, опц.)": route_evidence_ok,
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
