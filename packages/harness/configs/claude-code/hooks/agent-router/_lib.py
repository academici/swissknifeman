"""agent-router · общие примитивы для router.py (UserPromptSubmit) и session-policy.py
(SessionStart). Stdlib-only. Хуки автономны в ~/.claude/hooks — маленький дубль тут
осознан (импорт пакета harness в момент работы хука недоступен).

Никогда не бросай наружу: вызывающий хук оборачивает всё в try/except → exit 0.
"""
import json
from pathlib import Path

_DEFAULTS = {"POLICY": "propose", "THRESHOLD": "2", "ESCAPE_PREFIX": "~"}


def read_env(cfg_dir, cwd):
    """POLICY/THRESHOLD/ESCAPE_PREFIX. Порядок: глобальный env.ini рядом с хуком, затем
    project-local <cwd>/.claude/agent-router.env.ini (project перебивает по ключу)."""
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
    """Per-project <cwd>/.claude/agent-router.config.json если валиден, иначе глобальный
    config.json рядом с хуком (fallback: политика + 5 /task:*)."""
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
    """Сумма весов по вхождению ключевых слов (lowercase substring). Возвращает
    [(name, score), …] со score>0 по убыванию. Детерминированно (idempotent)."""
    low = text.lower()
    scored = []
    for e in entries:
        name = e.get("name")
        if not name:
            continue
        weight = e.get("weight", 1)
        s = sum(weight for kw in e.get("keywords", []) if kw and kw.lower() in low)
        if s > 0:
            scored.append((name, s))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored
