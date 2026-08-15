#!/usr/bin/env python3
"""Internal documentation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import load_catalog, read_env, score_entries  # noqa: E402


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    text = payload.get("user_input") or payload.get("prompt") or ""
    if not isinstance(text, str) or not text.strip():
        sys.exit(0)
    cwd = payload.get("cwd")
    cfg_dir = Path(__file__).resolve().parent

    try:
        env = read_env(cfg_dir, cwd)
    except Exception:
        sys.exit(0)
    if env.get("POLICY") == "off":
        sys.exit(0)

    esc = env.get("ESCAPE_PREFIX", "~")
    if esc and text.lstrip().startswith(esc):
        sys.exit(0)

    try:
        threshold = int(env.get("THRESHOLD", "2"))
    except (TypeError, ValueError):
        threshold = 2

    try:
        cat = load_catalog(cfg_dir, cwd)
        entries = ((cat.get("commands") or []) + (cat.get("agents") or [])
                   + (cat.get("skills") or []))
        scored = score_entries(text, entries)
    except Exception:
        sys.exit(0)

    if not scored or scored[0][1] < threshold:
        sys.exit(0)

    top_name, top_score = scored[0]
    runners = ", ".join(f"{n} ({s})" for n, s in scored[1:3])
    tmpl = cat.get("hint_template") or \
        "[intent-router] bias (non-authoritative): top={name} score={score}{runners}"
    try:
        hint = tmpl.format(name=top_name, score=top_score,
                           runners=(f"; runners-up: {runners}" if runners else ""))
    except Exception:
        sys.exit(0)

    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                  "additionalContext": hint},
           "suppressOutput": True}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
