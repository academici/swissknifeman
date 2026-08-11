#!/usr/bin/env python3
"""run-report · SessionEnd — снять исход прогона из транскрипта и записать на диск.

Универсальный (generic) захват: раз в конце сессии читает transcript_path СТРОЧНО (без
слурпа), извлекает исход ЛЮБОЙ задачи (dev-loop-воркфлоу, тест/линт-прогоны, изменённые
файлы, tool-провалы) и пишет `<cwd>/.claude/runs/<session_id>.json`. Отсюда `maind analyze`
собирает пост-ран отчёт «всё ли сработало». Ничего в dev-loop.js/паках менять не нужно.

После записи отчёта (если DIGEST=on в env.ini) тихо дёргает `analyst digest` subprocess'ом —
замыкает петлю обучения (run-report → кандидат-уроки в ephemeral). Best-effort, не барьер:
нет бинаря analyst / таймаут / любой сбой не мешают завершению сессии. Промоут в память —
по-прежнему человек (инвариант analyst не нарушается: авто-запись только в LOCAL ephemeral).

Дисциплина (verified perplexity-web по офиц. докам Claude Code hooks):
- SessionEnd получает `transcript_path`/`session_id`/`cwd`, НЕ блокирует — идеален для архива;
- транскрипт — first-class артефакт, строчный парс поддерживаем/стабилен к аддитивным правкам;
- хук НЕ барьер: любая ошибка / нет данных / битый stdin → exit 0 без записи.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import parse_events  # noqa: E402

_DEFAULT_KEEP = 30


def _report_root(cwd):
    """Git-root для новых отчётов; вне git сохраняем прежний cwd-path.

    SessionEnd остаётся best-effort: отсутствие git, несуществующий cwd или сбой
    subprocess не меняют его exit-код и не мешают завершению сессии.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        root = result.stdout.strip()
        if result.returncode == 0 and root:
            return root
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def _read_enabled(cwd):
    """ENABLED/RUNS_KEEP/DIGEST из <cwd>/.claude/run-report.env.ini (default on: регистрация
    хука = намерение). Kill-switch без правки settings.json. Возвращает (enabled, keep, digest).
    DIGEST=on (дефолт) — после записи отчёта тихо дёрнуть `analyst digest` (петля обучения)."""
    enabled, keep, digest = True, _DEFAULT_KEEP, True
    if not cwd:
        return enabled, keep, digest
    f = Path(cwd) / ".claude" / "run-report.env.ini"
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return enabled, keep, digest
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
        elif k == "DIGEST":
            digest = v.lower() not in ("off", "0", "false", "no")
    return enabled, keep, digest


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


_TREND_LIMIT = 4000
_TREND_KEEP = 2000


def _prune_trend(f):
    """Ретеншн usage-trend.ndjson: >_TREND_LIMIT строк → атомарно оставить последние
    _TREND_KEEP (tmp рядом + os.replace — не через core.io: хук копируется в ~/.claude/hooks
    без PYTHONPATH монорепо, см. _atomic_write_json выше)."""
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= _TREND_LIMIT:
        return
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text("\n".join(lines[-_TREND_KEEP:]) + "\n", encoding="utf-8")
    os.replace(tmp, f)


def _append_trend(cwd, sid, report):
    """Дописать одну компактную строку тренда токенов/инструментов прогона в
    <cwd>/.claude/analyze/usage-trend.ndjson (SCHEMA=2). Не барьер: любая ошибка молча
    проглатывается, как весь остальной хук — тренд best-effort, а не источник истины."""
    try:
        usage = report.get("usage") or {}
        totals = usage.get("totals") or {}
        by_model = usage.get("by_model") or {}
        agents = usage.get("agents") or []
        main_agent = agents[0] if agents else {}
        analyze_dir = Path(cwd) / ".claude" / "analyze"
        analyze_dir.mkdir(parents=True, exist_ok=True)
        gi = analyze_dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        entry = {
            "ts": report.get("generated_at"),
            "session": sid,
            "in": totals.get("in", 0),
            "out": totals.get("out", 0),
            "cache_read": totals.get("cache_read", 0),
            "cache_creation": totals.get("cache_creation", 0),
            "by_model": {m: {"in": v.get("in", 0), "out": v.get("out", 0)}
                        for m, v in by_model.items() if isinstance(v, dict)},
            "tools_total": (report.get("tools") or {}).get("total", 0),
            "files_changed": len(report.get("files_changed") or []),
            "agents": len(agents),
            "wall_s": main_agent.get("wall_seconds"),
            "retr_chars": (report.get("retrieval") or {}).get("result_chars", 0),
        }
        f = analyze_dir / "usage-trend.ndjson"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _prune_trend(f)
    except Exception:
        pass


def _analyst_bin():
    """Резолв бинаря analyst: ANALYST_BIN → PATH → топология swissknifeman → дефолт-путь.
    Хук копируется в ~/.claude/hooks без PYTHONPATH монорепо, потому digest дёргаем subprocess'ом
    (как memory-хук зовёт maind). None, если не найден — тогда digest тихо пропускается."""
    import shutil
    env_bin = os.environ.get("ANALYST_BIN")
    if env_bin and os.access(env_bin, os.X_OK):
        return env_bin
    found = shutil.which("analyst")
    if found:
        return found
    candidates = []
    topo = Path(os.path.expanduser("~/.swissknifeman/topology.json"))
    try:
        nodes = (json.loads(topo.read_text(encoding="utf-8")) or {}).get("nodes") or {}
        skm = nodes.get("swissknifeman")
        base = skm.get("path") if isinstance(skm, dict) else skm
        if base:
            candidates.append(Path(os.path.expanduser(base)) / "packages/analyst/bin/analyst")
    except Exception:
        pass
    candidates.append(Path(os.path.expanduser(
        "~/projects/packages/swissknifeman/packages/analyst/bin/analyst")))
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def _run_digest(cwd, sid):
    """Тихо дёрнуть `analyst digest --session <sid>` в проекте после записи отчёта: извлечь
    кандидат-уроки в ephemeral (промоут в память по-прежнему человек — инвариант не нарушается).
    Best-effort, НЕ барьер: нет бинаря / таймаут / любой сбой → молча пропускаем (как весь хук)."""
    try:
        import subprocess
        bin_ = _analyst_bin()
        if not bin_:
            return
        subprocess.run([bin_, "digest", "--session", sid],
                       cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30, check=False)
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
    enabled, keep, digest = _read_enabled(cwd)
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
            # transcript_path/cwd — только для SCHEMA=2 (usage-субагенты, protected_writes);
            # файловый объект = ленивый итератор строк, как и раньше
            report = parse_events(fh, transcript_path=tpath, cwd=cwd)
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

    runs_dir = Path(_report_root(cwd)) / ".claude" / "runs"
    try:
        _atomic_write_json(runs_dir / f"{sid}.json", report)
        _prune(runs_dir, keep)
    except Exception:
        sys.exit(0)
    _append_trend(cwd, sid, report)   # best-effort, глотает свои ошибки сама
    if digest:
        _run_digest(cwd, sid)         # петля обучения: run-report → analyst digest → ephemeral
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # хук никогда не ломает завершение сессии
