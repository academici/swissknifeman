#!/usr/bin/env python3
"""Internal documentation."""
import json
import os
import sys
from pathlib import Path

_DEFAULT_MODE = "off"
_MODES = ("off", "warn", "strict")
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit")


def _read_mode(cwd):
    """Internal documentation."""
    if not cwd:
        return _DEFAULT_MODE
    f = Path(cwd) / ".claude" / "pack-guard.env.ini"
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return _DEFAULT_MODE
    mode = _DEFAULT_MODE
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if k == "MODE":
            v = v.lower()
            mode = v if v in _MODES else _DEFAULT_MODE
    return mode


def _managed_files(cwd):
    """Internal documentation."""
    result = {}
    if not cwd:
        return result
    base = Path(cwd)
    try:
        lock = json.loads((base / ".claude" / "agent-pack.lock.json").read_text(encoding="utf-8"))
    except Exception:
        return result
    packs = lock.get("packs") if isinstance(lock, dict) else None
    if not isinstance(packs, dict):
        return result
    for pack_name, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        for f in pack.get("files") or []:
            if isinstance(f, dict) and f.get("target") and not f.get("user_owned"):
                result[str(base / f["target"])] = pack_name
    return result


def _target_path(tool_name, tool_input):
    """Internal documentation."""
    if not isinstance(tool_input, dict):
        return None
    if tool_name in _EDIT_TOOLS:
        fp = tool_input.get("file_path")
        return fp if isinstance(fp, str) and fp else None
    if tool_name == "NotebookEdit":
        fp = tool_input.get("notebook_path")
        return fp if isinstance(fp, str) and fp else None
    return None


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    cwd = payload.get("cwd") or os.getcwd()
    mode = _read_mode(cwd)
    if mode == "off":
        sys.exit(0)

    fp = _target_path(payload.get("tool_name"), payload.get("tool_input"))
    if not fp:
        sys.exit(0)

    managed = _managed_files(cwd)
    if not managed:
        sys.exit(0)

    abs_fp = fp if os.path.isabs(fp) else str(Path(cwd) / fp)
    pack = managed.get(abs_fp)
    if pack is None:
        sys.exit(0)

    msg = (f"pack-guard: файл сгенерирован паком '{pack}' (swissknifeman:generated) — "
           f"не редактируй ядро напрямую: правь оверлей пака или прими изменение через "
           f"'harness agent-packs upgrade': {fp}")
    if mode == "strict":
        sys.stderr.write(msg + "\n")
        sys.exit(2)
    sys.stderr.write("[warn] " + msg + "\n")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
