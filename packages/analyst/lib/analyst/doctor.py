"""analyst doctor — package environment diagnostics (read-only, without external calls).

Checks: python3, availability of the `maind` CLI (needed for surfacing curated lessons in
memory - optional, only warn) and of the `planner` command (optional, analyst does not depend
on `planner` hard). Partners are found by `aicore.util.partners`; none is imported."""
import sys

from aicore.util.cli import parse_args
from aicore.util.partners import partner_command


def cmd_doctor(env, argv):
    """analyst doctor — environment diagnostics (python/maind/planner)."""
    opts, _ = parse_args(argv, {"--json": "bool"})
    if opts["help"]:
        print("analyst doctor [--json] — diagnostics of the package environment.")
        return

    py_ok = sys.version_info >= (3, 8)
    maind_cmd = partner_command("maind", legacy_env=("MAIND_BIN",))
    maind_bin = maind_cmd[0] if maind_cmd else None
    planner_ok = partner_command("planner") is not None

    checks = {
        "python>=3.8": py_ok,
        "maind (surfacing curated to memory, optional)": bool(maind_bin),
        "planner (optional)": planner_ok,
    }
    ok = py_ok  # maind and planner are optional, they do not lower the verdict

    if opts["json"]:
        import json
        print(json.dumps({"ok": ok, "checks": checks,
                          "maind_bin": maind_bin}, ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst doctor — {env.root}\n")
    for name, val in checks.items():
        icon = "✓" if val else ("·" if "optional" in name else "✗")
        print(f"  {icon} {name}")
    print()
    if not ok:
        print("Required environment missing (python3.8+).", file=sys.stderr)
        raise SystemExit(1)
    print("The environment is ready.")
