"""analyst review — показать уроки по состояниям + structured diff против активных.

Read-only человеко-обзор перед промоутом: группирует уроки по state, а для каждого
показывает похожие активные уроки (Jaccard, stdlib) — чтобы человек видел дубли/конфликты
до продвижения (mem0-таксономия ADD/UPDATE/NOOP считается на глаз в MVP; авто-резолв — P3)."""
import json
import os

from . import lessons
from .common import die, parse_args


def build_review(project_path, state=None):
    """{state: [{lesson, similar, consolidation}]} по одному состоянию или по всем.
    consolidation — mem0-рекомендация ADD/UPDATE/NOOP/CONFLICT (человеку, не авто-резолв)."""
    groups = {st: [] for st in lessons.STATES}
    for L, st in lessons.list_lessons(project_path, state):
        sim = lessons.similar_lessons(
            project_path, L.get("trigger", ""), L.get("action", ""),
            states=lessons.ACTIVE_STATES, threshold=0.4, exclude_id=L.get("id"))
        cons = lessons.classify_consolidation(L.get("trigger", ""), L.get("action", ""), sim)
        groups[st].append({"lesson": L, "similar": sim, "consolidation": cons})
    return groups


def _print_human(groups, only_state=None):
    states = (only_state,) if only_state else lessons.STATES
    total = sum(len(groups[st]) for st in states)
    print(f"\nanalyst review — {total} урок(ов)"
          f"{f' в состоянии {only_state}' if only_state else ''}\n")
    if not total:
        print("  Пусто. Собери кандидатов: analyst digest\n")
        return
    for st in states:
        entries = groups.get(st) or []
        if not entries:
            continue
        print(f"── {st}  ({len(entries)})  " + "─" * max(2, 40 - len(st)))
        for e in entries:
            L = e["lesson"]
            print(f"  [{L.get('kind', '?')}] {L.get('id')}")
            print(f"    trigger: {L.get('trigger', '')}")
            print(f"    action:  {L.get('action', '')}")
            ev = ", ".join(L.get("evidence") or []) or "—"
            print(f"    evidence: {ev}   scope: {L.get('scope', '?')}   source: {L.get('source', '?')}")
            conf = L.get("confidence")
            if conf is not None:
                print(f"    confidence: {conf} ({L.get('confidence_tier', '?')})"
                      f"   S/N: {L.get('S_decayed', '?')}/{L.get('N_decayed', '?')}")
            cons = e.get("consolidation") or {}
            if cons.get("action") and cons["action"] != "ADD":
                mark = "⚠ CONFLICT (flag-and-ask)" if cons["action"] == "CONFLICT" else cons["action"]
                print(f"    → {mark}: {cons.get('reason', '')}")
            for sl, sst, score in e["similar"][:3]:
                print(f"    ≈ похоже ({score}) на {sl.get('id')} [{sst}]")
        print()
    if not only_state:
        print("Промоут (человек): analyst promote <id> [--to candidate|curated]   ·   "
              "демоут: analyst deprecate <id>\n")


def _json_ready(groups, only_state=None):
    states = (only_state,) if only_state else lessons.STATES
    out = {}
    for st in states:
        out[st] = [{
            "lesson": e["lesson"],
            "consolidation": e.get("consolidation"),
            "similar": [{"id": sl.get("id"), "state": sst, "score": score}
                        for sl, sst, score in e["similar"]],
        } for e in (groups.get(st) or [])]
    return out


def cmd_review(env, argv):
    """analyst review [--state ephemeral|candidate|curated|deprecated] [--json]
    — уроки по состояниям + diff против активных (read-only)."""
    opts, _ = parse_args(argv, {"--state": "str", "--project": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst review [--state STATE] [--json]\n"
              "  Показать уроки по состояниям + похожие активные (Jaccard). Read-only.")
        return
    state = opts["state"] or None
    if state and state not in lessons.STATES:
        die(f"неизвестное состояние: {state} (допустимо: {', '.join(lessons.STATES)})")
    ppath = os.getcwd()
    groups = build_review(ppath, state)
    if opts["json"]:
        print(json.dumps(_json_ready(groups, state), ensure_ascii=False, indent=2))
    else:
        _print_human(groups, state)
