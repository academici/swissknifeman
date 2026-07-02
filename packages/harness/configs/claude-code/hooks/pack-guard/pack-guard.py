#!/usr/bin/env python3
"""pack-guard · PreToolUse — слой 2 mutation-защиты generated-ассетов agent-packs: ловит
правку ДО того, как она случилась (слой 1 — lock_drift()/`doctor --drift`, постфактум).
Опциональный, по умолчанию НЕ устанавливается: включается явно `harness hooks --target .
--pack-guard warn|strict`. Режимы: off (не ставится) / warn (стерr-предупреждение, не блок) /
strict (блокирует Edit/Write/MultiEdit/NotebookEdit по generated-файлу).

Решение — по `.claude/agent-pack.lock.json` проекта: тот же разбор `packs[].files[].target`
(без `user_owned`), что `_protected_sets()` в ../run-report/_lib.py (осознанный маленький
дубль — автономность хука, PYTHONPATH монорепо в ~/.claude/hooks недоступен).

Дисциплина: хук никогда не роняет сессию — любая ошибка/битый JSON/отсутствие lock →
exit 0 (эквивалент off), НИКОГДА не блокирует из-за внутренней ошибки. Stdlib-only."""
import json
import os
import sys
from pathlib import Path

_DEFAULT_MODE = "off"
_MODES = ("off", "warn", "strict")
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit")


def _read_mode(cwd):
    """MODE из <cwd>/.claude/pack-guard.env.ini (файл пишет `harness hooks --pack-guard`).
    Нет файла / битый / неизвестное значение → off (безопасный дефолт)."""
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
    """abs-путь → имя пака, по `.claude/agent-pack.lock.json`, БЕЗ `user_owned` (их
    редактировать можно свободно — это и есть точка расширения base+overlay, D11)."""
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
    """file_path редактируемого файла по типу инструмента; нерелевантный tool → None."""
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
        sys.exit(0)  # нет lock'а / паков в проекте — нечего защищать

    abs_fp = fp if os.path.isabs(fp) else str(Path(cwd) / fp)
    pack = managed.get(abs_fp)
    if pack is None:
        sys.exit(0)  # файл не под управлением пака (или user_owned) — правь свободно

    msg = (f"pack-guard: файл сгенерирован паком '{pack}' (swissknifeman:generated) — "
           f"не редактируй ядро напрямую: правь оверлей пака или прими изменение через "
           f"'harness agent-packs upgrade': {fp}")
    if mode == "strict":
        sys.stderr.write(msg + "\n")
        sys.exit(2)  # PreToolUse: exit 2 блокирует вызов, stderr — причина
    sys.stderr.write("[warn] " + msg + "\n")
    sys.exit(0)  # warn: предупреждение, не блок


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # хук никогда не ломает сессию
