#!/usr/bin/env python3
"""run-report · SessionEnd — снять исход прогона из транскрипта и записать на диск.

Универсальный (generic) захват: раз в конце сессии читает transcript_path СТРОЧНО (без
слурпа), извлекает исход ЛЮБОЙ задачи (dev-loop-воркфлоу, тест/линт-прогоны, изменённые
файлы, tool-провалы) и пишет `<cwd>/.claude/runs/<session_id>.json`. Отсюда `maind analyze`
собирает пост-ран отчёт «всё ли сработало». Ничего в dev-loop.js/паках менять не нужно.

Дисциплина (verified perplexity-web по офиц. докам Claude Code hooks):
- SessionEnd получает `transcript_path`/`session_id`/`cwd`, НЕ блокирует — идеален для архива;
- транскрипт — first-class артефакт, строчный парс поддерживаем/стабилен к аддитивным правкам;
- хук НЕ барьер: любая ошибка / нет данных / битый stdin → exit 0 без записи.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import parse_events  # noqa: E402

_DEFAULT_KEEP = 30


def _read_enabled(cwd):
    """ENABLED из <cwd>/.claude/run-report.env.ini (default on: регистрация хука = намерение).
    Kill-switch без правки settings.json. Возвращает (enabled: bool, keep: int)."""
    enabled, keep = True, _DEFAULT_KEEP
    if not cwd:
        return enabled, keep
    f = Path(cwd) / ".claude" / "run-report.env.ini"
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return enabled, keep
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if k == "ENABLED":
            enabled = v.lower() not in ("off", "0", "false", "no")
        elif k == "RUNS_KEEP":
            try:
                keep = max(1, int(v))
            except ValueError:
                pass
    return enabled, keep


def _ensure_gitignore(runs_dir):
    """runs/ — эфемерные машинно-локальные артефакты: делаем каталог само-игнорируемым
    (`.gitignore` = `*`), чтобы run-report'ы не засоряли git status проекта (и не ломали
    'dirty tree' в maind analyze). Идемпотентно, ошибки глотаем."""
    gi = runs_dir / ".gitignore"
    try:
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
    except OSError:
        pass


def _atomic_write_json(path, data):
    """tmp рядом + os.replace — краш в момент записи не оставит полу-JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _prune(runs_dir, keep):
    """Оставить keep самых свежих run-*.json (ретеншн; ошибки глотаем)."""
    try:
        files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[keep:]:
            p.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    cwd = payload.get("cwd") or os.getcwd()
    enabled, keep = _read_enabled(cwd)
    if not enabled:
        sys.exit(0)

    tpath = payload.get("transcript_path")
    if not tpath or not isinstance(tpath, str):
        sys.exit(0)
    tpath = os.path.expanduser(tpath)
    if not os.path.isfile(tpath):
        sys.exit(0)

    sid = payload.get("session_id") or "session"
    sid = "".join(c for c in str(sid) if c.isalnum() or c in "-_") or "session"

    try:
        with open(tpath, encoding="utf-8", errors="replace") as fh:
            report = parse_events(fh)           # файловый объект = ленивый итератор строк
    except Exception:
        sys.exit(0)

    report["session_id"] = sid
    report["cwd"] = cwd
    report["reason"] = payload.get("reason") or ""
    try:
        from datetime import datetime, timezone
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
    except Exception:
        report["generated_at"] = None

    runs_dir = Path(cwd) / ".claude" / "runs"
    try:
        _atomic_write_json(runs_dir / f"{sid}.json", report)
        _prune(runs_dir, keep)
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # хук никогда не ломает завершение сессии
