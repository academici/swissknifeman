"""analyst doctor — package environment diagnostics (read-only, without external calls).

Checks: python3, package availability `core` on PYTHONPATH (general foundation), availability
CLI `maind` (is needed for surfacing curated-lessons in memory - optional, only warn) and
`task.route_evidence` (route/budget evidence — optional, analyst does not depend on
`task` hard)."""
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
    """P2.4: optional marker that
    `task.route_evidence` (normalized route/budget evidence) is visible from the current
    PYTHONPATH — analyst does not depend on `task` hard, like from `maind`."""
    try:
        from task import route_evidence  # noqa: F401
        return True
    except Exception:
        return False


def cmd_doctor(env, argv):
    """analyst doctor — environment diagnostics (python/core/maind)."""
    opts, _ = parse_args(argv, {"--json": "bool"})
    if opts["help"]:
        print("analyst doctor [--json] — diagnostics of the package environment.")
        return

    py_ok = sys.version_info >= (3, 8)
    core_ok = _check_core()
    maind_bin = shutil.which("maind")
    route_evidence_ok = _check_route_evidence()

    checks = {
        "python>=3.8": py_ok,
        "core (common foundation on PYTHONPATH)": core_ok,
        "maind (surfacing curated to memory, opt.)": bool(maind_bin),
        "task.route_evidence (route/budget evidence, opt.)": route_evidence_ok,
    }
    ok = py_ok and core_ok  # maind — optional, does not lower the verdict

    if opts["json"]:
        import json
        print(json.dumps({"ok": ok, "checks": checks,
                          "maind_bin": maind_bin}, ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst doctor — {env.root}\n")
    for name, val in checks.items():
        icon = "✓" if val else ("·" if "opt" in name else "✗")
        print(f"  {icon} {name}")
    print()
    if not ok:
        print("Required environment missing (python3.8+ and package core).", file=sys.stderr)
        raise SystemExit(1)
    print("The environment is ready.")
