"""Вывод и завершение — дословный общий код swissknifeman/maind/brain.

die() здесь — надмножество (с code) обоих исторических вариантов:
swissknifeman вызывал die(msg) → code=1 по умолчанию, поведение не меняется."""
import re
import sys
from datetime import datetime, timezone

_FRAC_RE = re.compile(r"\.(\d+)")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    """ISO-8601 → aware datetime. None при неразборе (без raise).

    py39-safe: `datetime.fromisoformat` до Python 3.11 НЕ принимает суффикс `Z` и
    произвольную дробную точность секунд. Нормализуем ДО парсинга: дробные секунды
    усекаем/дополняем ровно до 6 знаков, хвостовой `Z` → `+00:00`. Naive-результат
    (без offset) считаем UTC. Единый источник вместо расходившихся `strptime(...%SZ)`
    (терял дроби) и `fromisoformat(...Z→+00:00)` (падал на нестандартной дробной части)."""
    if not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    t = _FRAC_RE.sub(lambda m: "." + (m.group(1) + "000000")[:6], t, count=1)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
