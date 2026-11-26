#!/usr/bin/env python3
"""PostToolUse: after a plan JSON edit run `plan.py check`, then `plan.py render`."""
import json
import os
import subprocess
import sys
from pathlib import Path

_EDIT_TOOLS = ("Edit", "Write", "MultiEdit")
_MAX_ISSUES = 5


def _carrier(cwd, key):
    """Value of `key` in the committed carrier .swissknifeman/hooks.env (provider key first)."""
    try:
        text = (Path(cwd) / ".swissknifeman" / "hooks.env").read_text(encoding="utf-8")
    except Exception:
        return None
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            found[k.strip()] = v.strip()
    return found.get(key + "__CLAUDE_CODE", found.get(key))


def _enabled(cwd):
    carried = _carrier(cwd, "PLAN_REGEN_MODE")
    if carried is not None:
        return carried.lower() == "on"
    try:
        text = (Path(cwd) / ".claude" / "plan-regen.env.ini").read_text(encoding="utf-8")
    except Exception:
        return False
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "MODE":
            return value.strip().lower() == "on"
    return False


def _plan_dir(path):
    for directory in Path(os.path.normpath(path)).parents:
        if (directory / "plan.json").is_file():
            return directory
    return None


def _plan_cli(cwd):
    explicit = os.environ.get("TASK_PLAN_CLI") or os.environ.get("PLANNER_PLAN_PY")
    root = os.environ.get("PLANNER_ROOT")
    candidates = ([Path(explicit)] if explicit else []) + (
        [Path(root) / "scripts" / "plan.py"] if root else []) + [
        Path(cwd) / "packages" / "planner" / "scripts" / "plan.py"]
    return next((item for item in candidates if item.is_file()), None)


def _run(cli, *args):
    return subprocess.run([sys.executable, str(cli), *args], capture_output=True, text=True,
                          timeout=60, check=False)


def _blocking_issues(result):
    """Check errors other than stale views: render exists to repair exactly those."""
    try:
        report = json.loads(result.stdout)
    except ValueError:
        return [(result.stderr or result.stdout).strip()[:300] or "plan.py check failed"]
    return ["%s: %s" % (item.get("where"), item.get("message"))
            for item in report.get("issues") or []
            if item.get("level") == "error" and item.get("code") != "stale_view"]


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict) or payload.get("tool_name") not in _EDIT_TOOLS:
        sys.exit(0)
    cwd = payload.get("cwd") or os.getcwd()
    tool_input = payload.get("tool_input")
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not _enabled(cwd) or not isinstance(path, str) or not path.endswith(".json"):
        sys.exit(0)
    absolute = path if os.path.isabs(path) else str(Path(cwd) / path)
    plan_dir = _plan_dir(absolute)
    cli = _plan_cli(cwd)
    if plan_dir is None or cli is None:
        sys.exit(0)
    check = _run(cli, "check", str(plan_dir), "--json")
    issues = _blocking_issues(check) if check.returncode != 0 else []
    if issues:
        sys.stderr.write("plan-regen: plan.py check failed for %s:\n%s\n"
                         % (plan_dir, "\n".join(issues[:_MAX_ISSUES])))
        sys.exit(2)
    render = _run(cli, "render", str(plan_dir))
    if render.returncode != 0:
        sys.stderr.write("plan-regen: plan.py render failed: %s\n" % render.stderr.strip()[:300])
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
