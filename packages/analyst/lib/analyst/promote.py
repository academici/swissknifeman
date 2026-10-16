"""analyst promote / deprecate — man-gate of the lesson life cycle.

Invariant: transition to CURATED — ALWAYS explicit
human consent (confirm on tty or --yes on CLI = conscious input). Auto-recording is disabled.
Each transition is a record in audit.ndjson (append-only provenance). When exiting curated lesson
comes to mind mAInd (subprocess, graceful: the demon lay down / no CLI → the lesson remains on the disk,
surfacing repeat later - the promotion on the disk does not roll back).

Confidence-gates by numbers (N≥15/conf≥0.6 …) and mem0 auto-resolve - phase P3; in MVP transition
is done by a person consciously."""
import os

from . import lessons
from aicore.util.cli import parse_args, run_cmd
from aicore.util.partners import partner_command
from aicore.util.term import confirm, die, warn

# Promotion pipeline (deprecated — separate `deprecate`, not in that order).
ORDER = ("ephemeral", "candidate", "curated")


def _next_state(cur):
    i = ORDER.index(cur)
    return ORDER[i + 1] if i + 1 < len(ORDER) else None


# ── surfacing to memory mAInd (graceful) ──────────────────────────────────────
def _resolve_maind_bin(env):
    """The maind executable (legacy MAIND_BIN, SKM_MAIND_BIN, SKM_MAIND_ROOT, PATH). None if not found.
    Single resolver - `aicore.util.partners.partner_command`."""
    argv = partner_command("maind", legacy_env=("MAIND_BIN",))
    return argv[0] if argv else None


def _fact_text(lesson):
    """Abstracted fact for memory: trigger→action + pointer to evidence.
    WITHOUT code/raw materials/secrets - the person filtered them to review before promotion in curated."""
    ev = ", ".join(lesson.get("evidence") or [])
    kind = lesson.get("kind", "lesson")
    text = f"[analyst:{kind}] {lesson.get('trigger', '')} → {lesson.get('action', '')}"
    return text + (f" (evidence: {ev})" if ev else "")


def surface_to_memory(env, lesson):
    """Recall lesson in memory mAInd (scope lesson). {ok, reason}. Never quits -
    surfacing is optional, the promoter is already committed to disk."""
    binp = _resolve_maind_bin(env)
    if not binp:
        return {"ok": False, "reason": "CLI maind not found (surfacing optional)"}
    scope = lesson.get("scope") or "global"
    try:
        res = run_cmd([binp, "memory", "remember", "--scope", scope,
                       "--type", "analyst-lesson", _fact_text(lesson)],
                      capture=True, check=False, timeout=20)
    except SystemExit as e:            # run_cmd die (not found/timeout/OSError) — degrading
        return {"ok": False, "reason": f"launch maind failed: {e}"}
    if res.returncode == 0:
        return {"ok": True, "reason": ""}
    tail = (res.stderr or res.stdout or "non-zero code").strip()[:160]
    return {"ok": False, "reason": tail}


def _record_surface_result(project_path, lesson_id, res):
    """Enter in class promoted_at (success) / promote_failed (failure) — is idempotent.
    Gives visibility of delivery and makes it possible `promote --retry-failed` (otherwise the lesson is marked
    curated, but it is not in memory and cannot be repeated - id is already in curated)."""
    lesson, st = lessons.find_lesson(project_path, lesson_id)
    if lesson is None:
        return
    lesson = dict(lesson)
    if res["ok"]:
        lesson["promoted_at"] = lessons.now_iso()
        lesson.pop("promote_failed", None)
    else:
        lesson["promote_failed"] = True
    lessons.save_lesson(project_path, lesson, st)


def _retry_failed(env, ppath):
    """Revisit memory curated-lessons with promote_failed=true (idempotent)."""
    failed = [L for L, _st in lessons.list_lessons(ppath, "curated")
              if L.get("promote_failed")]
    if not failed:
        print("No curated-lessons with promote_failed — nothing to send.")
        return
    ok = 0
    for L in failed:
        res = surface_to_memory(env, L)
        lessons.audit_append(ppath, {"action": "surface-retry", "id": L["id"],
                                     "ok": res["ok"], "reason": res["reason"]})
        _record_surface_result(ppath, L["id"], res)
        if res["ok"]:
            ok += 1
            print(f"✓ {L['id']}: sent to memory mAInd")
        else:
            warn(f"{L['id']}: failed again - {res['reason']}")
    print(f"\nretry-failed: {ok}/{len(failed)} sent to memory.")


# ── promote ──────────────────────────────────────────────────────────────────
def cmd_promote(env, argv):
    """analyst promote <id> [--to candidate|curated] [--yes] [--supersedes ID] [--force]
    | analyst promote --retry-failed — sent curated-lessons that were not remembered."""
    opts, pos = parse_args(argv, {"--to": "str", "--yes": "bool", "--supersedes": "str",
                                  "--force": "bool", "--retry-failed": "bool",
                                  "--project": "str", "--json": "bool"},
                           max_pos=1)
    if opts["retry_failed"]:
        _retry_failed(env, os.getcwd())
        return
    if opts["help"] or not pos:
        print("analyst promote <id> [--to candidate|curated] [--yes] [--supersedes ID] [--force]\n"
              "  ephemeral→candidate→curated. Go to curated — only with the consent of the person\n"
              "  (confirm on tty or --yes); curated comes to mind mAInd.\n"
              "  Conflict with active lesson → flag-and-ask (solve --supersedes ID | --force).\n"
              "analyst promote --retry-failed\n"
              "  Resurface curated-lessons with promote_failed=true (memory was unavailable).")
        return
    lid = pos[0]
    ppath = os.getcwd()
    lesson, cur = lessons.find_lesson(ppath, lid)
    if lesson is None:
        die(f"lesson not found: {lid} (see analyst review)")
    if cur == "deprecated":
        die("lesson deprikate - promotion from deprecated in MVP not supported")

    # mem0-consolidation: conflict with active → flag-and-ask (auto-resolve disabled)
    sim = lessons.similar_lessons(ppath, lesson.get("trigger", ""), lesson.get("action", ""),
                                  states=lessons.ACTIVE_STATES, threshold=0.4, exclude_id=lid)
    cons = lessons.classify_consolidation(lesson.get("trigger", ""), lesson.get("action", ""), sim)
    if cons["action"] == "CONFLICT" and not opts["force"] and not opts["supersedes"]:
        print(f"⚠ Conflict: {cons['reason']}")
        print("flag-and-ask — auto-resolve is disabled. Decide explicitly:\n"
              f"  analyst promote {lid} --supersedes {cons['target']}   # soft-deprikate old\n"
              f"  analyst promote {lid} --force                          # ignore conflict")
        return

    target = opts["to"] or _next_state(cur)
    if target is None:
        die(f"lesson is already in '{cur}' — there is nowhere to promote")
    if target not in ORDER:
        die(f"--to allows: {', '.join(ORDER)}")
    if ORDER.index(target) <= ORDER.index(cur):
        die(f"cannot be downgraded/leave: {cur}→{target} (demo: analyst deprecate {lid})")

    # man-gate: exit to curated — always explicit consent
    if target == "curated" and not opts["yes"]:
        if not confirm(f"Promote to CURATED (will go into memory mAInd) lesson {lid}?"):
            print("Canceled - go to curated requires human consent (--yes or confirmation).")
            return

    moved, old, new = lessons.move_lesson(ppath, lid, target)
    lessons.audit_append(ppath, {"action": "promote", "id": lid, "from": old, "to": new,
                                 "by": "human", "consent": "yes" if opts["yes"] else "confirm"})
    # signal event: the person confirmed the lesson → positive observation for confidence
    # (append-only; recompute will take this into account when recalculating S/N).
    lessons.event_append(ppath, {"id": lid, "source": "promote",
                                 "sessions_total": 1, "sessions_success": 1})
    print(f"✓ {lid}: {old} → {new}")

    # supersedes: soft-invalidate of the lesson being replaced (temporal-ranking, NOT physical removal).
    if opts["supersedes"]:
        old_id = opts["supersedes"]
        sup, sst = lessons.find_lesson(ppath, old_id)
        if sup is None:
            warn(f"--supersedes: lesson {old_id} not found - label supersedes not included")
        else:
            moved = dict(moved, supersedes=old_id)
            lessons.save_lesson(ppath, moved, new)
            if sst != "deprecated":
                lessons.save_lesson(ppath, dict(sup, superseded_by=lid,
                                                superseded_at=lessons.now_iso()), sst)
                lessons.move_lesson(ppath, old_id, "deprecated")
                lessons.audit_append(ppath, {"action": "supersede", "id": old_id,
                                             "by": lid, "from": sst, "to": "deprecated"})
                print(f"  {old_id} → deprecated (superseded, soft — file saved)")

    if new == "curated":
        res = surface_to_memory(env, moved)
        lessons.audit_append(ppath, {"action": "surface", "id": lid,
                                     "ok": res["ok"], "reason": res["reason"]})
        _record_surface_result(ppath, lid, res)
        if res["ok"]:
            print(f"  came to mind mAInd (scope {moved.get('scope')}) — "
                  f"will appear on SessionStart.")
        else:
            warn(f"did not come to mind: {res['reason']}. Lesson curated on disk "
                 f"(promote_failed) — forwarded: analyst promote --retry-failed.")


# ── deprecate ────────────────────────────────────────────────────────────────
def cmd_deprecate(env, argv):
    """analyst deprecate <id> — soft-lesson demo (is not deleted, remains for audit)."""
    opts, pos = parse_args(argv, {"--project": "str", "--yes": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("analyst deprecate <id> — translate lesson to deprecated (soft, is not deleted).")
        return
    lid = pos[0]
    ppath = os.getcwd()
    lesson, cur = lessons.find_lesson(ppath, lid)
    if lesson is None:
        die(f"lesson not found: {lid}")
    if cur == "deprecated":
        print(f"{lid} already deprecated.")
        return
    _moved, old, _new = lessons.move_lesson(ppath, lid, "deprecated")
    lessons.audit_append(ppath, {"action": "deprecate", "id": lid, "from": old, "to": "deprecated"})
    print(f"✓ {lid}: {old} → deprecated (soft — not deleted, available for audit)")
