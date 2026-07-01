"""analyst promote / deprecate — человеко-гейт жизненного цикла урока.

Инвариант (research/analyst-self-learning-system.md §5/§6): переход в CURATED — ВСЕГДА явное
согласие человека (confirm на tty либо --yes на CLI = осознанный ввод). Авто-запись запрещена.
Каждый переход — запись в audit.ndjson (append-only провенанс). При выходе в curated урок
всплывает в память mAInd (subprocess, graceful: демон лёг / нет CLI → урок остаётся на диске,
surfacing повторим позже — промоут на диске не откатывается).

Confidence-гейты по числам (N≥15/conf≥0.6 …) и mem0 auto-резолв — фаза P3; в MVP переход
делает человек осознанно."""
import os
import shutil

from . import lessons
from .common import confirm, die, parse_args, run_cmd, warn

# Конвейер продвижения (deprecated — отдельным `deprecate`, не в этом порядке).
ORDER = ("ephemeral", "candidate", "curated")


def _next_state(cur):
    i = ORDER.index(cur)
    return ORDER[i + 1] if i + 1 < len(ORDER) else None


# ── surfacing в память mAInd (graceful) ──────────────────────────────────────
def _resolve_maind_bin(env):
    """MAIND_BIN → PATH → <monorepo>/packages/maind/bin/maind. None если не найден."""
    override = os.environ.get("MAIND_BIN")
    if override:
        p = os.path.expanduser(override)
        return p if os.path.exists(p) else None
    which = shutil.which("maind")
    if which:
        return which
    cand = env.monorepo_root / "packages" / "maind" / "bin" / "maind"
    return str(cand) if cand.exists() else None


def _fact_text(lesson):
    """Абстрагированный факт для памяти: trigger→action + указатель на evidence.
    БЕЗ кода/сырья/секретов — их человек отфильтровал на review перед промоутом в curated."""
    ev = ", ".join(lesson.get("evidence") or [])
    kind = lesson.get("kind", "lesson")
    text = f"[analyst:{kind}] {lesson.get('trigger', '')} → {lesson.get('action', '')}"
    return text + (f" (evidence: {ev})" if ev else "")


def surface_to_memory(env, lesson):
    """Всплыть урок в память mAInd (scope урока). {ok, reason}. Никогда не бросает —
    surfacing опционален, промоут уже зафиксирован на диске."""
    binp = _resolve_maind_bin(env)
    if not binp:
        return {"ok": False, "reason": "CLI maind не найден (surfacing опционален)"}
    scope = lesson.get("scope") or "global"
    try:
        res = run_cmd([binp, "memory", "remember", "--scope", scope,
                       "--type", "analyst-lesson", _fact_text(lesson)],
                      capture=True, check=False, timeout=20)
    except SystemExit as e:            # run_cmd die (не найден/таймаут/OSError) — деградируем
        return {"ok": False, "reason": f"запуск maind не удался: {e}"}
    if res.returncode == 0:
        return {"ok": True, "reason": ""}
    tail = (res.stderr or res.stdout or "ненулевой код").strip()[:160]
    return {"ok": False, "reason": tail}


# ── promote ──────────────────────────────────────────────────────────────────
def cmd_promote(env, argv):
    """analyst promote <id> [--to candidate|curated] [--yes] [--supersedes ID] [--force]
    — продвинуть урок вперёд по конвейеру. Переход в curated требует согласия человека."""
    opts, pos = parse_args(argv, {"--to": "str", "--yes": "bool", "--supersedes": "str",
                                  "--force": "bool", "--project": "str", "--json": "bool"},
                           max_pos=1)
    if opts["help"] or not pos:
        print("analyst promote <id> [--to candidate|curated] [--yes] [--supersedes ID] [--force]\n"
              "  ephemeral→candidate→curated. Переход в curated — только с согласия человека\n"
              "  (confirm на tty либо --yes); curated всплывает в память mAInd.\n"
              "  Противоречие с активным уроком → flag-and-ask (реши --supersedes ID | --force).")
        return
    lid = pos[0]
    ppath = os.getcwd()
    lesson, cur = lessons.find_lesson(ppath, lid)
    if lesson is None:
        die(f"урок не найден: {lid} (см. analyst review)")
    if cur == "deprecated":
        die("урок деприкейтнут — промоут из deprecated в MVP не поддержан")

    # mem0-консолидация: противоречие с активным → flag-and-ask (авто-резолв запрещён)
    sim = lessons.similar_lessons(ppath, lesson.get("trigger", ""), lesson.get("action", ""),
                                  states=lessons.ACTIVE_STATES, threshold=0.4, exclude_id=lid)
    cons = lessons.classify_consolidation(lesson.get("trigger", ""), lesson.get("action", ""), sim)
    if cons["action"] == "CONFLICT" and not opts["force"] and not opts["supersedes"]:
        print(f"⚠ Конфликт: {cons['reason']}")
        print("flag-and-ask — авто-резолв запрещён. Реши явно:\n"
              f"  analyst promote {lid} --supersedes {cons['target']}   # soft-деприкейт старого\n"
              f"  analyst promote {lid} --force                          # проигнорировать конфликт")
        return

    target = opts["to"] or _next_state(cur)
    if target is None:
        die(f"урок уже в '{cur}' — продвигать некуда")
    if target not in ORDER:
        die(f"--to допускает: {', '.join(ORDER)}")
    if ORDER.index(target) <= ORDER.index(cur):
        die(f"нельзя понизить/оставить: {cur}→{target} (демоут: analyst deprecate {lid})")

    # человеко-гейт: выход в curated — всегда явное согласие
    if target == "curated" and not opts["yes"]:
        if not confirm(f"Продвинуть в CURATED (попадёт в память mAInd) урок {lid}?"):
            print("Отменено — переход в curated требует согласия человека (--yes или подтверждение).")
            return

    moved, old, new = lessons.move_lesson(ppath, lid, target)
    lessons.audit_append(ppath, {"action": "promote", "id": lid, "from": old, "to": new,
                                 "by": "human", "consent": "yes" if opts["yes"] else "confirm"})
    # событие-сигнал: человек подтвердил урок → положительное наблюдение для confidence
    # (append-only; recompute учтёт это при пересчёте S/N).
    lessons.event_append(ppath, {"id": lid, "source": "promote",
                                 "sessions_total": 1, "sessions_success": 1})
    print(f"✓ {lid}: {old} → {new}")

    # supersedes: soft-invalidate замещаемого урока (temporal-ranking, НЕ физ.удаление).
    if opts["supersedes"]:
        old_id = opts["supersedes"]
        sup, sst = lessons.find_lesson(ppath, old_id)
        if sup is None:
            warn(f"--supersedes: урок {old_id} не найден — метка supersedes не проставлена")
        else:
            moved = dict(moved, supersedes=old_id)
            lessons.save_lesson(ppath, moved, new)
            if sst != "deprecated":
                lessons.save_lesson(ppath, dict(sup, superseded_by=lid,
                                                superseded_at=lessons.now_iso()), sst)
                lessons.move_lesson(ppath, old_id, "deprecated")
                lessons.audit_append(ppath, {"action": "supersede", "id": old_id,
                                             "by": lid, "from": sst, "to": "deprecated"})
                print(f"  {old_id} → deprecated (superseded, soft — файл сохранён)")

    if new == "curated":
        res = surface_to_memory(env, moved)
        lessons.audit_append(ppath, {"action": "surface", "id": lid,
                                     "ok": res["ok"], "reason": res["reason"]})
        if res["ok"]:
            print(f"  всплыло в память mAInd (scope {moved.get('scope')}) — "
                  f"появится на SessionStart.")
        else:
            warn(f"в память не всплыло: {res['reason']}. Урок curated на диске — "
                 f"повтори surfacing позже (демон mAInd / maind CLI).")


# ── deprecate ────────────────────────────────────────────────────────────────
def cmd_deprecate(env, argv):
    """analyst deprecate <id> — soft-демоут урока (не удаляется, остаётся для аудита)."""
    opts, pos = parse_args(argv, {"--project": "str", "--yes": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("analyst deprecate <id> — перевести урок в deprecated (soft, не удаляется).")
        return
    lid = pos[0]
    ppath = os.getcwd()
    lesson, cur = lessons.find_lesson(ppath, lid)
    if lesson is None:
        die(f"урок не найден: {lid}")
    if cur == "deprecated":
        print(f"{lid} уже deprecated.")
        return
    _moved, old, _new = lessons.move_lesson(ppath, lid, "deprecated")
    lessons.audit_append(ppath, {"action": "deprecate", "id": lid, "from": old, "to": "deprecated"})
    print(f"✓ {lid}: {old} → deprecated (soft — не удалён, доступен для аудита)")
