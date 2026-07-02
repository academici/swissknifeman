"""analyst status / compact — видимость стора и детерминированная редукция events-лога.

`status` — read-only сводка (счётчики по состояниям, даты последнего digest/recompute,
curated-ready, promote_failed). `compact` — свести старые события `events.ndjson` в один
snapshot-event на урок, сохранив суммы (S/N/tests) и МАКС ts группы, чтобы `recompute` до и
после давал ТУ ЖЕ confidence (агрегат зависит только от сумм и возраста последнего события)."""
import json
import os

from . import lessons
from . import recompute as R
from .common import atomic_write_text, die, parse_args, parse_iso


# ── status ────────────────────────────────────────────────────────────────────
def _is_curated_ready(lesson, curated_min_n=None):
    """Кандидат набрал ЧИСЛА для curated (порог recompute)? Переход — всё равно человек.
    curated_min_n — эффективный (адаптивный) порог; None → статический CURATED_MIN_N."""
    conf = lesson.get("confidence")
    if conf is None:
        return False
    if curated_min_n is None:
        curated_min_n = R.CURATED_MIN_N
    n = int(lesson.get("sessions_total", 0) or 0)
    tt = int(lesson.get("tests_total", 0) or 0)
    tp = int(lesson.get("tests_passed", 0) or 0)
    pr = (tp / tt) if tt > 0 else 0.0
    return (n >= curated_min_n and conf >= R.CURATED_MIN_CONF
            and pr >= R.CURATED_MIN_PASSRATE)


def _last_ts(records, pred):
    """Максимальный (по разобранному времени) ts среди записей, удовлетворяющих pred. None — нет."""
    best = None
    for r in records:
        if not pred(r):
            continue
        ts = r.get("ts")
        dt = parse_iso(ts) if ts else None
        if dt is not None and (best is None or dt > best[0]):
            best = (dt, ts)
    return best[1] if best else None


def build_status(project_path):
    """Сводка стора уроков (read-only, без мутаций). Даты — из append-only audit.ndjson."""
    counts = {st: 0 for st in lessons.STATES}
    promote_failed = 0
    curated_ready = 0
    events = lessons.read_events(project_path)
    # адаптивный порог curated — тот же, что применил бы recompute (активность проекта)
    project_sessions = sum(int(e.get("sessions_total", 0) or 0) for e in events)
    _, cur_min = R.adaptive_thresholds(project_sessions)
    for L, st in lessons.list_lessons(project_path):
        counts[st] += 1
        if L.get("promote_failed"):
            promote_failed += 1
        if st == "candidate" and _is_curated_ready(L, cur_min):
            curated_ready += 1
    audit = lessons.read_audit(project_path)
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "curated_ready": curated_ready,
        "promote_failed": promote_failed,
        "events": len(events),
        "last_digest": _last_ts(audit, lambda a: a.get("action") == "digest"),
        "last_recompute": _last_ts(
            audit, lambda a: str(a.get("action", "")).startswith("recompute")),
    }


def cmd_status(env, argv):
    """analyst status [--json] — сводка стора уроков (read-only, без мутаций)."""
    opts, _ = parse_args(argv, {"--project": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst status [--json]\n"
              "  Read-only сводка: счётчики по состояниям, curated-ready, promote_failed,\n"
              "  число событий, даты последнего digest/recompute. Ничего не меняет.")
        return
    st = build_status(os.getcwd())
    if opts["json"]:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return
    c = st["counts"]
    print(f"\nanalyst status — {st['total']} урок(ов)\n")
    for state in lessons.STATES:
        print(f"  {state:<11} {c[state]}")
    print(f"\n  curated-ready:  {st['curated_ready']}  (числа есть — нужен человек)")
    print(f"  promote_failed: {st['promote_failed']}"
          + ("  → досыл: analyst promote --retry-failed" if st["promote_failed"] else ""))
    print(f"  события:        {st['events']}")
    print(f"  последний digest:    {st['last_digest'] or '—'}")
    print(f"  последний recompute: {st['last_recompute'] or '—'}\n")


# ── compact ─────────────────────────────────────────────────────────────────
def compact_events(events, before_dt):
    """Свести события с `ts < before_dt` (или ВСЕ при before_dt=None) в один snapshot-event
    на урок. Сохраняет суммы (S/N/tests) и МАКС ts группы → recompute даёт ту же confidence.
    События без id / без разбираемого ts / с `ts >= before_dt` остаются как есть.
    Возвращает (new_events, {compacted, snapshots, kept}). Чистая (без I/O)."""
    old_by_id = {}
    kept = []
    for e in events:
        lid = e.get("id")
        ts = e.get("ts")
        dt = parse_iso(ts) if ts else None
        eligible = bool(lid) and dt is not None and (before_dt is None or dt < before_dt)
        if not eligible:
            kept.append(e)
            continue
        old_by_id.setdefault(lid, []).append((dt, e))
    snapshots = []
    for lid, items in old_by_id.items():
        _max_dt, max_e = max(items, key=lambda it: it[0])
        snapshots.append({
            "id": lid, "source": "compact", "ts": max_e.get("ts"),
            "sessions_total": sum(int(e.get("sessions_total", 0) or 0) for _, e in items),
            "sessions_success": sum(int(e.get("sessions_success", 0) or 0) for _, e in items),
            "tests_total": sum(int(e.get("tests_total", 0) or 0) for _, e in items),
            "tests_passed": sum(int(e.get("tests_passed", 0) or 0) for _, e in items),
            "compacted": True, "compacted_count": len(items),
        })
    new_events = kept + snapshots
    new_events.sort(key=lambda e: (e.get("ts") or ""))
    return new_events, {"compacted": sum(len(v) for v in old_by_id.values()),
                        "snapshots": len(snapshots), "kept": len(kept)}


def cmd_compact(env, argv):
    """analyst compact [--before ISO] [--dry-run] [--json] — свести старые события в snapshot."""
    opts, _ = parse_args(argv, {"--before": "str", "--project": "str",
                                "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst compact [--before ISO] [--dry-run] [--json]\n"
              "  Свести события events.ndjson (старше --before, или ВСЕ) в один snapshot\n"
              "  на урок. Суммы и возраст последнего события сохраняются → recompute даёт\n"
              "  ту же confidence. --dry-run — только показать, ничего не писать.")
        return
    before_dt = None
    if opts["before"]:
        before_dt = parse_iso(opts["before"])
        if before_dt is None:
            die("--before: ожидается ISO UTC вида 2026-07-01T00:00:00Z")
    ppath = os.getcwd()
    events = lessons.read_events(ppath)
    new_events, stats = compact_events(events, before_dt)

    if opts["json"]:
        print(json.dumps({"before": opts["before"] or None, "dry_run": opts["dry_run"],
                          **stats, "events_after": len(new_events)},
                         ensure_ascii=False, indent=2))
    if stats["compacted"] == 0:
        if not opts["json"]:
            print("Компактить нечего (нет подходящих событий).")
        return
    if opts["dry_run"]:
        if not opts["json"]:
            print(f"[dry-run] свернулось бы {stats['compacted']} событий → "
                  f"{stats['snapshots']} snapshot; осталось бы всего {len(new_events)}.")
        return

    content = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in new_events)
    atomic_write_text(lessons.events_path(ppath), content)
    lessons.audit_append(ppath, {"action": "compact", "before": opts["before"] or None,
                                 **stats, "events_after": len(new_events)})
    if not opts["json"]:
        print(f"Свёрнуто {stats['compacted']} событий → {stats['snapshots']} snapshot. "
              f"events.ndjson: {len(new_events)} записей.")
