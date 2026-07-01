"""Хранилище уроков analyst — файловый стор со скалярами, провенансом и аудитом.

Per-project раскладка (LOCAL, приватность-по-каталогам из ECC):
    <project>/.claude/analyst/
      lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
      audit.ndjson        # append-only: кто/когда/что промоутил (провенанс)

Инварианты (data-integrity):
- запись урока — атомарна (core.atomic_write_json: tmp + os.replace);
- переход состояния — атомарный ре-райт в новый каталог + unlink старого (урок не двоится);
- аудит — append-only ndjson (не перезаписывается, только дописывается);
- урок несёт только СКАЛЯРЫ (переносимо, детерминированно); сырьё/секреты внутрь не кладём.

Confidence-арифметика (Beta/decay) и state-machine-гейты по числам — фаза P3; здесь MVP
хранит счётчики-сырьё (sessions_total/…), переходы делает человек через `analyst promote`."""
import hashlib
import json
import os
from pathlib import Path

from .common import atomic_write_json, now_iso, safe_load_json, sanitize

STATES = ("ephemeral", "candidate", "curated", "deprecated")
KINDS = ("heuristic", "procedure", "gotcha")

# Порядок «активности»: активные уроки, против которых считаем diff/дубли (не deprecated).
ACTIVE_STATES = ("curated", "candidate", "ephemeral")


# ── пути ─────────────────────────────────────────────────────────────────────
def project_dir(project_path):
    """<project>/.claude/analyst — корень per-project стора уроков."""
    return Path(os.path.expanduser(str(project_path))) / ".claude" / "analyst"


def lessons_dir(project_path):
    return project_dir(project_path) / "lessons"


def state_dir(project_path, state):
    if state not in STATES:
        raise ValueError(f"неизвестное состояние: {state}")
    return lessons_dir(project_path) / state


def audit_path(project_path):
    return project_dir(project_path) / "audit.ndjson"


def events_path(project_path):
    """<project>/.claude/analyst/events.ndjson — append-only поток сигналов confidence.
    Отдельно от audit.ndjson (тот — провенанс переходов); здесь — скаляры наблюдений
    (sessions_total/success, tests_total/passed), из которых recompute восстановим."""
    return project_dir(project_path) / "events.ndjson"


# ── схема урока ──────────────────────────────────────────────────────────────
def make_lesson_id(trigger, action, session=""):
    """Детерминированный id: slug(trigger) + короткий хэш(trigger|action|session).
    Хэш даёт уникальность при совпадающих slug'ах; детерминизм — тестируемость."""
    slug = sanitize(trigger)[:48] or "lesson"
    h = hashlib.sha1(f"{trigger}\x00{action}\x00{session}".encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{h}"


def new_lesson(*, trigger, action, kind="heuristic", scope, session_id="",
               project="", detector="", evidence=None, source="digest",
               tests_total=0, tests_passed=0):
    """Собрать словарь урока (скаляры + провенанс). state всегда 'ephemeral' на входе."""
    if kind not in KINDS:
        raise ValueError(f"неизвестный kind: {kind}")
    trigger = " ".join((trigger or "").split()).strip()
    action = " ".join((action or "").split()).strip()
    ts = now_iso()
    return {
        "id": make_lesson_id(trigger, action, session_id),
        "kind": kind,
        "trigger": trigger,
        "action": action,
        "evidence": list(evidence or []),
        "created_at": ts,
        "last_used_at": ts,
        "sessions_total": 1,
        "sessions_success": 0,
        "tests_total": int(tests_total),
        "tests_passed": int(tests_passed),
        "state": "ephemeral",
        "scope": scope,
        "source": source,
        "supersedes": None,
        "provenance": {"session_id": session_id, "project": project, "detector": detector},
    }


# ── чтение ───────────────────────────────────────────────────────────────────
def _iter_state(project_path, state):
    d = state_dir(project_path, state)
    if not d.is_dir():
        return
    for p in sorted(d.glob("*.json")):
        rec = safe_load_json(p, None)
        if isinstance(rec, dict):
            yield rec


def list_lessons(project_path, state=None):
    """[(lesson, state)] по одному состоянию или по всем (в порядке STATES)."""
    states = (state,) if state else STATES
    out = []
    for st in states:
        for rec in _iter_state(project_path, st):
            out.append((rec, st))
    return out


def find_lesson(project_path, lesson_id):
    """(lesson, state) первого совпадения по id (порядок STATES) или (None, None)."""
    for st in STATES:
        p = state_dir(project_path, st) / f"{lesson_id}.json"
        if p.is_file():
            rec = safe_load_json(p, None)
            if isinstance(rec, dict):
                return rec, st
    return None, None


# ── запись / переходы ────────────────────────────────────────────────────────
def save_lesson(project_path, lesson, state=None):
    """Атомарно записать урок в каталог его состояния (или state-override).
    Возвращает путь. Дубли по id внутри одного состояния перезаписываются (идемпотентно)."""
    st = state or lesson.get("state") or "ephemeral"
    lesson = dict(lesson, state=st)
    dst = state_dir(project_path, st) / f"{lesson['id']}.json"
    atomic_write_json(dst, lesson)
    return dst


def add_candidate(project_path, lesson):
    """Записать кандидат-урок из digest в ephemeral, если такого id там ещё нет.
    Возвращает (lesson, created: bool). Уже существует в ЛЮБОМ состоянии → не трогаем."""
    existing, _st = find_lesson(project_path, lesson["id"])
    if existing is not None:
        return existing, False
    save_lesson(project_path, lesson, "ephemeral")
    return lesson, True


def move_lesson(project_path, lesson_id, new_state):
    """Атомарно перевести урок в new_state: ре-райт в новый каталог + unlink старого
    (урок не двоится между состояниями). Возвращает (lesson, old_state, new_state).
    die-семантики нет — вызывающий проверяет None."""
    if new_state not in STATES:
        raise ValueError(f"неизвестное состояние: {new_state}")
    lesson, old_state = find_lesson(project_path, lesson_id)
    if lesson is None:
        return None, None, None
    if old_state == new_state:
        return lesson, old_state, new_state
    lesson = dict(lesson, state=new_state, last_used_at=now_iso())
    save_lesson(project_path, lesson, new_state)
    old_path = state_dir(project_path, old_state) / f"{lesson_id}.json"
    try:
        old_path.unlink(missing_ok=True)
    except OSError:
        pass
    return lesson, old_state, new_state


# ── аудит (append-only провенанс) ────────────────────────────────────────────
def audit_append(project_path, record):
    """Дописать одну запись в audit.ndjson (append-only, никогда не перезаписываем).
    Добавляет ts, если его нет. Создаёт каталог. Дозапись — открытие в 'a'."""
    rec = dict(record)
    rec.setdefault("ts", now_iso())
    path = audit_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return rec


def read_audit(project_path):
    """Список записей audit.ndjson (пропускает битые строки). [] если нет файла."""
    return _read_ndjson(audit_path(project_path))


def _read_ndjson(path):
    """Разбор ndjson-файла в список dict'ов (битые/пустые строки пропускаются)."""
    if not path.is_file():
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except (ValueError, TypeError):
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


# ── events (append-only поток сигналов confidence) ───────────────────────────
def event_append(project_path, record):
    """Дописать событие-сигнал в events.ndjson (append-only, только дозапись).
    Добавляет ts, если его нет. Из этого лога recompute восстанавливает confidence."""
    rec = dict(record)
    rec.setdefault("ts", now_iso())
    path = events_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return rec


def read_events(project_path):
    """Список событий events.ndjson (пропускает битые строки). [] если нет файла."""
    return _read_ndjson(events_path(project_path))


# ── похожесть (Jaccard, stdlib) ──────────────────────────────────────────────
_WORD_RE = None


def _tokens(text):
    """Множество токенов (lower, только буквенно-цифровые слова ≥3 символов)."""
    import re
    global _WORD_RE
    if _WORD_RE is None:
        _WORD_RE = re.compile(r"[a-zа-я0-9]{3,}")
    return set(_WORD_RE.findall((text or "").lower()))


def jaccard(a, b):
    """Жаккар по токенам двух строк. 0.0 если оба пусты."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def similar_lessons(project_path, trigger, action, *, states=ACTIVE_STATES,
                    threshold=0.4, exclude_id=None):
    """[(lesson, state, score)] активных уроков, похожих на (trigger+action) по Jaccard
    ≥ threshold, по убыванию score. Для diff в review и дедупа при промоуте."""
    query = f"{trigger} {action}"
    out = []
    for st in states:
        for rec in _iter_state(project_path, st):
            if exclude_id and rec.get("id") == exclude_id:
                continue
            score = jaccard(query, f"{rec.get('trigger', '')} {rec.get('action', '')}")
            if score >= threshold:
                out.append((rec, st, round(score, 3)))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


# ── консолидация (mem0-таксономия, в human-gate) ─────────────────────────────
# Пороги по паре (сходство trigger, сходство action) — чистая эвристика (stdlib):
CONSOLIDATE_TRIGGER_HIGH = 0.6   # «та же ситуация»
CONSOLIDATE_ACTION_HIGH = 0.6    # «то же действие»
CONSOLIDATE_ACTION_LOW = 0.2     # действия расходятся → противоречие


def classify_consolidation(trigger, action, similar):
    """mem0-таксономия для кандидата против похожих активных уроков (авто-резолва НЕТ —
    только рекомендация человеку). similar: [(lesson, state, score)] из similar_lessons.

    Возвращает {"action": ADD|UPDATE|NOOP|CONFLICT, "target": id|None, "reason": str}:
      NOOP     — дубликат (та же ситуация И то же действие);
      CONFLICT — противоречие (та же ситуация, действие расходится) → flag-and-ask;
      UPDATE   — уточняет существующий (та же ситуация, действие эволюционировало);
      ADD      — новое знание (нет близких / только слабо связанные).
    """
    best = None  # (trigger_sim, action_sim, lesson, state) с макс. trigger_sim
    for L, st, _score in similar:
        tsim = jaccard(trigger, L.get("trigger", ""))
        asim = jaccard(action, L.get("action", ""))
        if best is None or tsim > best[0]:
            best = (tsim, asim, L, st)
    if best is None:
        return {"action": "ADD", "target": None, "reason": "похожих активных нет"}
    tsim, asim, L, st = best
    tid = L.get("id")
    if tsim >= CONSOLIDATE_TRIGGER_HIGH and asim >= CONSOLIDATE_ACTION_HIGH:
        return {"action": "NOOP", "target": tid, "reason": f"дубликат {tid} [{st}]"}
    if tsim >= CONSOLIDATE_TRIGGER_HIGH and asim < CONSOLIDATE_ACTION_LOW:
        return {"action": "CONFLICT", "target": tid,
                "reason": f"та же ситуация, иное действие → конфликт с {tid} [{st}]"}
    if tsim >= CONSOLIDATE_TRIGGER_HIGH:
        return {"action": "UPDATE", "target": tid, "reason": f"уточняет {tid} [{st}]"}
    return {"action": "ADD", "target": tid, "reason": f"связан с {tid} [{st}], но новое"}
