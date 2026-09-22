"""Internal documentation."""
import json
from pathlib import Path

_DEFAULTS = {"POLICY": "off", "THRESHOLD": "2", "ESCAPE_PREFIX": "~"}


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
        # Task requires explicit invocation, even in legacy consumer catalogs.
        if name.startswith(("/task:", "task:", "skill:task-", "skill:task:")):
            continue
        weight = e.get("weight", 1)
        s = sum(weight for kw in e.get("keywords", []) if kw and kw.lower() in low)
        if s > 0:
            scored.append((name, s))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored
