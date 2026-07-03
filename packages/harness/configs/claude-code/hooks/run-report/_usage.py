"""usage — единый транскрипт-парсер usage-метрик Claude Code (JSONL-транскрипты).

САМОДОСТАТОЧНЫЙ модуль: импортирует ТОЛЬКО stdlib, ни одного «from core...»/«from .».
Причина — файл копируется байт-в-байт в хук (~/.claude/hooks/run-report/_usage.py),
где PYTHONPATH монорепо недоступен; любой относительный импорт сломает хук молча.
Поэтому здесь осознанный дубль потоковой JSONL-дисциплины из core.io.read_ndjson_iter.

СЕМАНТИКА СУММ: суммы input-токенов — это BILLABLE-объём (каждый API-вызов оплачивает
свой вход заново, включая повтор истории), а НЕ размер контекста. Сумма по длинному
диалогу многократно превышает контекст-окно — это нормально и ожидаемо.

Все функции — чистые, потоковые и толерантные к битым/неожиданным событиям:
исключений наружу не бросают (мусор в транскрипте не должен ронять отчёт)."""
from datetime import datetime
from pathlib import Path
import json

# Обрезка label — первая строка user-текста бывает целым промптом на экраны.
LABEL_MAX = 80


def _int(v):
    """Токен-счётчик из события: только настоящие числа, иначе 0 — в транскриптах
    попадаются null/строки, а += с ними уронил бы весь разбор."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _iter_content(msg):
    """content бывает списком блоков, строкой или отсутствует — наружу только список."""
    c = msg.get("content") if isinstance(msg, dict) else None
    return c if isinstance(c, list) else []


def _first_line(txt):
    """Первая непустая строка текста, обрезанная до LABEL_MAX (человекочитаемая метка)."""
    if not isinstance(txt, str):
        return None
    for ln in txt.strip().splitlines():
        ln = ln.strip()
        if ln:
            return ln[:LABEL_MAX]
    return None


def new_acc():
    """Пустой аккумулятор одного агента/транскрипта (мутируется feed_event)."""
    return {
        "model": None, "models": set(),
        "in": 0, "out": 0, "cache_read": 0, "cache_creation": 0,
        "msgs": 0, "thinking_chars": 0, "text_chars": 0, "tool_errors": 0,
        "ts_min": None, "ts_max": None,
        "first_user_text": None,
    }


def feed_event(acc, ev):
    """Скормить одно распарсенное JSONL-событие в аккумулятор. Толерантна к любой
    структуре: не-dict/битое событие молча пропускается (мусор не роняет отчёт)."""
    if not isinstance(ev, dict):
        return
    ts = ev.get("timestamp")
    # ISO-таймстемпы Claude Code монотонны по алфавиту — сравниваем лексикографически,
    # без парсинга дат на каждом событии (парсим один раз в finish).
    if isinstance(ts, str) and ts:
        if acc["ts_min"] is None or ts < acc["ts_min"]:
            acc["ts_min"] = ts
        if acc["ts_max"] is None or ts > acc["ts_max"]:
            acc["ts_max"] = ts
    m = ev.get("message")
    if not isinstance(m, dict):
        return
    etype = ev.get("type")
    if etype == "assistant":
        acc["msgs"] += 1
        model = m.get("model")
        if isinstance(model, str) and model:
            acc["model"] = model          # последняя модель — «текущая» агента
            acc["models"].add(model)
        u = m.get("usage")
        if isinstance(u, dict):
            acc["in"] += _int(u.get("input_tokens"))
            acc["out"] += _int(u.get("output_tokens"))
            acc["cache_read"] += _int(u.get("cache_read_input_tokens"))
            acc["cache_creation"] += _int(u.get("cache_creation_input_tokens"))
        for b in _iter_content(m):
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype == "thinking":
                t = b.get("thinking")
                acc["thinking_chars"] += len(t) if isinstance(t, str) else 0
            elif btype == "text":
                t = b.get("text")
                acc["text_chars"] += len(t) if isinstance(t, str) else 0
    elif etype == "user":
        # tool_result с is_error приходят user-событиями — считаем отказы инструментов
        for b in _iter_content(m):
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                acc["tool_errors"] += 1
        if acc["first_user_text"] is None:
            c = m.get("content")
            got = _first_line(c) if isinstance(c, str) else None
            if got is None:
                for b in _iter_content(m):
                    if isinstance(b, dict) and b.get("type") == "text":
                        got = _first_line(b.get("text"))
                        if got:
                            break
            if got:
                acc["first_user_text"] = got


def _parse_iso(s):
    """datetime из ISO-строки; None при любом мусоре (защита — не роняем агрегат)."""
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _wall_seconds(ts_min, ts_max):
    """Длительность агента по крайним таймстемпам; None, когда посчитать нельзя."""
    a, b = _parse_iso(ts_min), _parse_iso(ts_max)
    if a is None or b is None:
        return None
    try:
        return max(0.0, (b - a).total_seconds())
    except TypeError:
        # naive и aware datetime не вычитаются — смешанные форматы в одном файле
        return None


def finish(acc, label=None):
    """Финализировать аккумулятор в агрегат агента. label: явный аргумент важнее
    автоматической метки (первая строка первого user-текста)."""
    lbl = label if label is not None else acc.get("first_user_text")
    return {
        "label": lbl,
        "model": acc.get("model"),
        "models": sorted(acc.get("models") or ()),
        "in": acc.get("in", 0),
        "out": acc.get("out", 0),
        "cache_read": acc.get("cache_read", 0),
        "cache_creation": acc.get("cache_creation", 0),
        "msgs": acc.get("msgs", 0),
        "thinking_chars": acc.get("thinking_chars", 0),
        "text_chars": acc.get("text_chars", 0),
        "tool_errors": acc.get("tool_errors", 0),
        "wall_seconds": _wall_seconds(acc.get("ts_min"), acc.get("ts_max")),
    }


def merge(agents):
    """Слить агрегаты агентов (результаты finish) в сводку прогона:
    totals + разбивка by_model + cache_hit (доля кэш-чтений во «свежем» входе;
    None, когда входа не было — деление на ноль не маскируем нулём)."""
    totals = {"in": 0, "out": 0, "cache_read": 0, "cache_creation": 0}
    by_model = {}
    for a in agents:
        if not isinstance(a, dict):
            continue
        for k in totals:
            totals[k] += _int(a.get(k))
        model = a.get("model") or "?"
        bm = by_model.setdefault(
            model, {"in": 0, "out": 0, "cache_read": 0, "cache_creation": 0, "msgs": 0})
        for k in ("in", "out", "cache_read", "cache_creation", "msgs"):
            bm[k] += _int(a.get(k))
    denom = totals["cache_read"] + totals["in"]
    hit = (totals["cache_read"] / denom) if denom else None
    return {"totals": totals, "by_model": by_model, "cache_hit": hit}


def similar_ratio(a, b):
    """Похожесть двух текстов по множествам токенов (Жаккар): слова lower длиной >=2,
    |A∩B|/|A∪B|. Пустые множества → 0.0 (а не 1.0 — «оба пустые» не значит «похожи»)."""
    def toks(s):
        return {w for w in str(s or "").lower().split() if len(w) >= 2}
    ta, tb = toks(a), toks(b)
    union = ta | tb
    if not union:
        return 0.0
    return len(ta & tb) / len(union)


def iter_jsonl(path):
    """Потоковый JSONL-итератор: пустые/битые строки и не-dict записи пропускаются,
    errors='replace' — битый байт не роняет чтение; нет файла → пустой генератор.
    Осознанный дубль core.io.read_ndjson_iter (см. docstring модуля: без PYTHONPATH)."""
    p = Path(path)
    if not p.is_file():
        return
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except (ValueError, TypeError):
                    continue
                if isinstance(rec, dict):
                    yield rec
    except OSError:
        return
