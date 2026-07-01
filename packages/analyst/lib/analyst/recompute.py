"""analyst recompute — детерминированный пересчёт confidence + числовая state-machine.

Источник истины — events.ndjson (append-only поток сигналов). recompute читает лог,
затухает по времени, агрегирует S/N и tests, считает confidence (confidence.py) и
двигает состояние ПО ЧИСЛАМ — БЕЗ демона (on-demand), детерминированно и восстановимо
из логов (при фиксированном `--now` снапшот воспроизводим).

Инвариант (P1): `candidate→curated` — ВСЕГДА человек. Здесь при выполненных числовых
порогах curated лишь ПОМЕЧАЕТСЯ «готов» (флаг в audit), но НЕ двигается автоматически.
Демоут — soft (`move_lesson` в deprecated: ре-райт+unlink, файл сохраняется, не удаление).
Авто-переход `ephemeral→candidate` разрешён (машинный тир) при N≥15 & conf≥0.6 & tests≥1.
"""
import json
import os
from datetime import datetime, timezone

from . import confidence as C
from . import lessons
from .common import die, now_iso, parse_args

# ── числовые гейты state-machine (§5) ────────────────────────────────────────
CANDIDATE_MIN_N = 15        # объём наблюдений для авто ephemeral→candidate
CANDIDATE_MIN_CONF = 0.6
CURATED_MIN_N = 50         # числовой порог «готов к curated» (но переход — человек)
CURATED_MIN_CONF = 0.8
CURATED_MIN_PASSRATE = 0.95
DEPRECATE_CONF = 0.6       # просадка ниже → soft-демоут (candidate) / флаг (curated)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ── время (парс timestamp'ов — здесь, чтобы confidence.py оставался чистым) ──
def _parse_ts(ts):
    """ISO 'Z' → aware datetime (UTC). None при неразборе."""
    try:
        return datetime.strptime(ts, _TS_FMT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def day_bucket(ts_event, ts_now):
    """Возраст события в днях (floor, bucket=BUCKET_DAYS), ≥0. Неразбор ts → 0 (защитно)."""
    a, b = _parse_ts(ts_event), _parse_ts(ts_now)
    if a is None or b is None:
        return 0
    secs = (b - a).total_seconds()
    return max(0, int(secs // (C.BUCKET_DAYS * 86400)))


# ── агрегат событий (чистый при заданном now_ts) ─────────────────────────────
def aggregate_events(events, now_ts):
    """Свести события одного урока в скаляры + days_since последнего наблюдения.
    Возвращает {S,N,tests_total,tests_passed,days_since,event_count,last_ts}."""
    S = N = tt = tp = 0
    last_ts = None
    for e in events:
        N += int(e.get("sessions_total", 0) or 0)
        S += int(e.get("sessions_success", 0) or 0)
        tt += int(e.get("tests_total", 0) or 0)
        tp += int(e.get("tests_passed", 0) or 0)
        ts = e.get("ts")
        # ISO-'Z' фикс. ширины → лексикографический max == хронологический
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts
    days = day_bucket(last_ts, now_ts) if last_ts else 0
    return {"S": S, "N": N, "tests_total": tt, "tests_passed": tp,
            "days_since": days, "event_count": len(events), "last_ts": last_ts}


def _passrate(tt, tp):
    return (tp / tt) if tt > 0 else 0.0


def snapshot_fields(agg, conf, now_ts):
    """Аддитивные поля-снапшот для урока (не ломают P1-схему). Детерминированы при now_ts."""
    decay = C.time_decay(agg["days_since"])
    return {
        "sessions_total": agg["N"],
        "sessions_success": agg["S"],
        "tests_total": agg["tests_total"],
        "tests_passed": agg["tests_passed"],
        "S_decayed": round(agg["S"] * decay, 4),
        "N_decayed": round(agg["N"] * decay, 4),
        "confidence": round(conf, 4),
        "confidence_tier": C.tier(conf),
        "recomputed_at": now_ts,
    }


# ── числовая state-machine (чистая: state+числа → решение) ────────────────────
def decide_transition(state, agg, conf):
    """(new_state, action, note) по числам. curated — НЕ авто (только флаг «готов»).

    action ∈ {promote, deprecate, curated-ready, curated-decay, unchanged}."""
    N = agg["N"]
    tt = agg["tests_total"]
    if state == "ephemeral":
        if N >= CANDIDATE_MIN_N and conf >= CANDIDATE_MIN_CONF and tt >= 1:
            return "candidate", "promote", "N≥15 & conf≥0.6 & tests≥1"
        return "ephemeral", "unchanged", ""
    if state == "candidate":
        if conf < DEPRECATE_CONF:
            return "deprecated", "deprecate", f"conf {conf:.2f} < {DEPRECATE_CONF} (soft)"
        pr = _passrate(tt, agg["tests_passed"])
        if N >= CURATED_MIN_N and conf >= CURATED_MIN_CONF and pr >= CURATED_MIN_PASSRATE:
            # инвариант P1: в curated двигает ТОЛЬКО человек — здесь лишь флаг
            return "candidate", "curated-ready", "числа для curated есть — нужен человек"
        return "candidate", "unchanged", ""
    if state == "curated":
        if conf < DEPRECATE_CONF:
            # curated человек-благословлён: не авто-демоутим, помечаем на ревью
            return "curated", "curated-decay", f"conf {conf:.2f} < {DEPRECATE_CONF} — на ревью человека"
        return "curated", "unchanged", ""
    return state, "unchanged", ""


# ── применение (IO) ──────────────────────────────────────────────────────────
def recompute_project(project_path, now_ts, *, dry_run=False):
    """Пересчитать все активные (не deprecated) уроки из events.ndjson. Возвращает
    список результатов. dry_run — только считает, ничего не пишет на диск."""
    events = lessons.read_events(project_path)
    by_id = {}
    for e in events:
        lid = e.get("id")
        if lid:
            by_id.setdefault(lid, []).append(e)

    results = []
    for L, st in lessons.list_lessons(project_path):
        if st == "deprecated":
            continue
        lid = L["id"]
        evs = by_id.get(lid)
        if not evs:
            results.append({"id": lid, "state": st, "action": "no-events",
                            "confidence": None, "tier": None, "note": "нет событий"})
            continue
        agg = aggregate_events(evs, now_ts)
        conf = C.confidence(agg["S"], agg["N"], agg["days_since"])
        new_state, action, note = decide_transition(st, agg, conf)
        results.append({"id": lid, "state": st, "new_state": new_state,
                        "confidence": round(conf, 4), "tier": C.tier(conf),
                        "action": action, "note": note,
                        "N": agg["N"], "S": agg["S"], "days_since": agg["days_since"]})
        if dry_run:
            continue

        # 1) атомарный снапшот в текущем состоянии
        lessons.save_lesson(project_path, dict(L, **snapshot_fields(agg, conf, now_ts)), st)
        # 2) переходы по числам (curated — НЕ здесь)
        if action == "promote":
            lessons.move_lesson(project_path, lid, "candidate")
            lessons.audit_append(project_path, {
                "action": "recompute-promote", "id": lid, "from": st, "to": "candidate",
                "by": "auto", "confidence": round(conf, 4), "note": note})
        elif action == "deprecate":
            lessons.move_lesson(project_path, lid, "deprecated")
            lessons.audit_append(project_path, {
                "action": "recompute-deprecate", "id": lid, "from": st, "to": "deprecated",
                "by": "auto", "confidence": round(conf, 4), "note": note})
        elif action in ("curated-ready", "curated-decay"):
            lessons.audit_append(project_path, {
                "action": "recompute-flag", "id": lid, "state": st, "flag": action,
                "by": "auto", "confidence": round(conf, 4), "note": note})
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_recompute(env, argv):
    """analyst recompute [--now ISO] [--dry-run] [--json]
    — пересчитать confidence уроков из events.ndjson и применить числовую state-machine."""
    opts, _ = parse_args(argv, {"--now": "str", "--project": "str",
                                "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst recompute [--now ISO] [--dry-run] [--json]\n"
              "  Детерминированный пересчёт confidence из events.ndjson + числовая\n"
              "  state-machine: авто ephemeral→candidate; curated — только человек;\n"
              "  просадка → soft-deprecate (файл не удаляется). Демона нет.")
        return
    now_ts = opts["now"] or now_iso()
    if opts["now"] and _parse_ts(now_ts) is None:
        die("--now: ожидается ISO UTC вида 2026-07-01T00:00:00Z")

    ppath = os.getcwd()
    results = recompute_project(ppath, now_ts, dry_run=opts["dry_run"])

    if opts["json"]:
        print(json.dumps({"now": now_ts, "dry_run": opts["dry_run"],
                          "results": results}, ensure_ascii=False, indent=2))
        return

    moved = [r for r in results if r["action"] in ("promote", "deprecate")]
    flags = [r for r in results if r["action"] in ("curated-ready", "curated-decay")]
    print(f"\nanalyst recompute — {len(results)} урок(ов) @ {now_ts}"
          f"{' (dry-run)' if opts['dry_run'] else ''}\n")
    for r in results:
        if r["action"] in ("no-events",):
            continue
        arrow = f" → {r['new_state']}" if r.get("new_state") and r["new_state"] != r["state"] else ""
        print(f"  [{r['tier']} {r['confidence']}] {r['id']} ({r['state']}{arrow})"
              f"  N={r.get('N')} d={r.get('days_since')}"
              f"{('  ⚑ ' + r['note']) if r['action'].startswith('curated') else ''}")
    print()
    if flags:
        print(f"⚑ {len(flags)} готов(ы) к вниманию человека (curated — только человек): "
              "analyst promote <id> --to curated")
    if moved and not opts["dry_run"]:
        print(f"✓ применено переходов: {len(moved)} (см. audit.ndjson)")
    print()
