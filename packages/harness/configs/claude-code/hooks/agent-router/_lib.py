"""Internal documentation."""
import json
from pathlib import Path

_DEFAULTS = {"POLICY": "off", "THRESHOLD": "2", "ESCAPE_PREFIX": "~"}


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


def read_env(cfg_dir, cwd):
    """Internal documentation."""
    vals = dict(_DEFAULTS)
    files = [Path(cfg_dir) / "env.ini"]
    if cwd:
        files.append(Path(cwd) / ".claude" / "agent-router.env.ini")
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in vals:
                vals[k] = v.strip()
    if cwd:
        carried = _carrier(cwd, "AGENT_ROUTER_POLICY")
        if carried is not None:
            vals["POLICY"] = carried
    return vals


def load_catalog(cfg_dir, cwd):
    """Internal documentation."""
    if cwd:
        p = Path(cwd) / ".claude" / "agent-router.config.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        return json.loads((Path(cfg_dir) / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def score_entries(text, entries):
    """Internal documentation."""
    low = text.lower()
    scored = []
    for e in entries:
        name = e.get("name")
        if not name:
            continue
        # planner requires explicit invocation, even in legacy consumer catalogs.
        # Compatibility alias: remove in the next minor release (the `task` spellings).
        if name.startswith(("/planner:", "planner:", "skill:planner-", "skill:planner:",
                            "/task:", "task:", "skill:task-", "skill:task:")):
            continue
        weight = e.get("weight", 1)
        s = sum(weight for kw in e.get("keywords", []) if kw and kw.lower() in low)
        if s > 0:
            scored.append((name, s))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored
