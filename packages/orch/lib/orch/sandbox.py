"""Whether the provider sandboxes can start on this machine.

Claude Code (Bash tool) and Codex confine tool commands with bubblewrap in user and network namespaces, plus ``socat``
for the Claude network proxy. Ubuntu 24.04 and later refuse unprivileged user namespaces to a program without an AppArmor
profile, so the sandbox may be installed and still not start. ``probe`` only reads the PATH and runs ``bwrap … true``; it
changes nothing. The sandbox restricts the commands of a role, never the agent process itself (its model API stays
reachable), so a declared ``network: none`` is intent that this probe makes visible, not a guarantee of the process.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

TIMEOUT_S = 10
BWRAP_TRY = ["--ro-bind", "/", "/", "--unshare-user", "--unshare-net", "--dev", "/dev", "--proc", "/proc", "true"]

_cached: dict | None = None


def probe(refresh: bool = False) -> dict:
    """``{"available": bool, "reason": str | None, "checked": [{"name", "ok", "detail"}]}``, cached for the process."""
    global _cached
    if _cached is None or refresh:
        _cached = _probe()
    return _cached


def _probe() -> dict:
    if not sys.platform.startswith("linux"):
        # macOS uses Seatbelt, which needs no helper; the provider's own failIfUnavailable covers a start failure.
        checked = [{"name": "platform", "ok": True, "detail": f"{sys.platform}: the provider sandbox needs no bubblewrap"}]
        return {"available": True, "reason": None, "checked": checked}
    checked = []
    for name in ("bwrap", "socat"):
        found = shutil.which(name)
        checked.append({"name": name, "ok": bool(found), "detail": found or f"{name} not found on PATH"})
    if checked[0]["ok"]:
        checked.append(_try_namespaces(checked[0]["detail"]))
    failed = next((row for row in checked if not row["ok"]), None)
    return {"available": failed is None, "reason": failed["detail"] if failed else None, "checked": checked}


def _try_namespaces(bwrap: str) -> dict:
    name = "bwrap-user-net-namespaces"
    try:
        done = subprocess.run([bwrap, *BWRAP_TRY], capture_output=True, text=True, errors="replace",
                              timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"name": name, "ok": False, "detail": f"bwrap did not finish in {TIMEOUT_S} s"}
    except OSError as error:
        return {"name": name, "ok": False, "detail": f"bwrap cannot start: {error}"}
    if done.returncode == 0:
        return {"name": name, "ok": True, "detail": "user and network namespaces start"}
    lines = (done.stderr or "").strip().splitlines()
    return {"name": name, "ok": False, "detail": lines[0] if lines else f"bwrap exited {done.returncode}"}
