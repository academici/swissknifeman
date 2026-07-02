"""analyst digest — детерминированное извлечение КАНДИДАТ-уроков из run-report прогона.

Первичный источник — run-report (SessionEnd-хук harness пишет <project>/.claude/runs/<sid>.json,
уже дистиллировав транскрипт). digest берёт ТОЛЬКО высокоточные сигналы (не «угадывает инсайты»
— это осознанная граница MVP):

  A. resolved-failure — проверка (тест/линт) падала и затем прошла в том же прогоне
     («сработало после N попыток») → урок-gotcha с evidence test-pass;
  B. workaround — агент явно записал обходку в dev-loop-сигнал (devloop.workarounds).

Кандидаты пишутся в ephemeral (LOCAL, unreviewed). Суть фикса человек уточняет на `analyst review`;
промоут — только человек. Извлекатели — ЧИСТЫЕ функции (run_report → [lesson]) ради тестируемости.
Защитно: любое отсутствующее/битое поле run-report пропускается, digest не падает."""
import json
import os
from pathlib import Path

from .common import die, find_run_report, parse_args
from .lessons import (ACTIVE_STATES, add_candidate, audit_append,
                      classify_consolidation, event_append, jaccard,
                      new_lesson, similar_lessons)

_SIMILAR_CMD = 0.6   # порог «та же по сути команда» для пары fail→pass

# источник run-report — единый core.find_run_report (раскрывает ~ в пути)


# ── извлекатели (чистые) ─────────────────────────────────────────────────────
def _check_entries(run_report):
    """[{command, ok}] тестов+линтов прогона (защитно, только с непустой командой)."""
    bash = run_report.get("bash") or {}
    out = []
    for key in ("tests", "lints"):
        for e in (bash.get(key) or []):
            if isinstance(e, dict) and e.get("command"):
                out.append(e)
    return out


def extract_resolved_failures(run_report, *, scope, project):
    """Сигнал A: команда, которая падала и затем прошла (по Jaccard ≥ порог) → gotcha."""
    sid = run_report.get("session_id") or ""
    files = run_report.get("files_changed") or []
    entries = _check_entries(run_report)
    failed = [e for e in entries if not e.get("ok", True)]
    passed = [e for e in entries if e.get("ok", True)]
    out, seen = [], set()
    for f in failed:
        fcmd = f.get("command", "")
        if fcmd in seen:
            continue
        best = max((jaccard(fcmd, p.get("command", "")) for p in passed), default=0.0)
        if best < _SIMILAR_CMD:
            continue
        seen.add(fcmd)
        attempts = sum(1 for e in entries if jaccard(fcmd, e.get("command", "")) >= _SIMILAR_CMD)
        top_files = [Path(x).name for x in files[:3]]
        trigger = f"проверка падала и была исправлена в прогоне: {fcmd}"
        # action — чистый семантический текст (Jaccard/surfacing); счётчики+файлы → meta;
        # инструкция ревьюеру → review_hint (в память не уходят).
        action = f"исправить причину падения проверки: {fcmd}"
        out.append(new_lesson(
            trigger=trigger, action=action, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="resolved-failure",
            evidence=[f"session:{sid}", "test-pass", f"attempts:{attempts}"],
            meta={"attempts": attempts, "files": top_files},
            review_hint="Уточни СУТЬ фикса при review (что именно поправили).",
            tests_total=attempts, tests_passed=max(attempts - 1, 0)))
    return out


def extract_workarounds(run_report, *, scope, project):
    """Сигнал B: явно записанные dev-loop обходки (devloop.workarounds) → gotcha."""
    sid = run_report.get("session_id") or ""
    devloop = run_report.get("devloop") or {}
    out, seen = [], set()
    for w in (devloop.get("workarounds") or []):
        text = w if isinstance(w, str) else json.dumps(w, ensure_ascii=False)
        text = " ".join(text.split()).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        trigger = f"ситуация потребовала обходки: {text[:60]}"
        out.append(new_lesson(
            trigger=trigger, action=text, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="workaround",
            evidence=[f"session:{sid}", "workaround"]))
    return out


def extract_candidates(run_report, *, scope, project):
    """Все высокоточные кандидаты прогона (A + B). Дубли по id схлопываются на записи."""
    if not isinstance(run_report, dict):
        return []
    return (extract_resolved_failures(run_report, scope=scope, project=project)
            + extract_workarounds(run_report, scope=scope, project=project))


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_digest(env, argv):
    """analyst digest [--cwd] [--session UUID] [--dry-run] [--json]
    — извлечь кандидат-уроки из свежего run-report в .claude/analyst/lessons/ephemeral/."""
    opts, _ = parse_args(argv, {"--cwd": "bool", "--session": "str",
                                "--project": "str", "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst digest [--cwd] [--session UUID] [--dry-run] [--json]\n"
              "  Детерминированно извлекает кандидат-уроки из run-report прогона "
              "(resolved-failure / workaround) → ephemeral. Промоут — человек.")
        return

    ppath = os.getcwd()
    rr = find_run_report(ppath, opts["session"] or None)
    if not rr:
        die("нет run-report в .claude/runs — включи захват прогона: "
            "harness hooks --target . --run-report on, затем проведи сессию Claude Code")

    project = Path(os.path.abspath(ppath)).name
    scope = f"project:{project}"
    cands = extract_candidates(rr, scope=scope, project=project)

    if opts["dry_run"] or opts["json"]:
        payload = {"session": rr.get("session_id"), "project": project,
                   "candidates": [{"id": c["id"], "kind": c["kind"], "detector": c["provenance"]["detector"],
                                   "trigger": c["trigger"]} for c in cands]}
        if opts["json"]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"\nanalyst digest (dry-run) — session {payload['session']}: "
                  f"{len(cands)} кандидат(ов)\n")
            for c in payload["candidates"]:
                print(f"  • [{c['detector']}] {c['trigger']}")
            print()
        return

    created = skipped = 0
    for L in cands:
        # семантический дедуп (П-6): NOOP по mem0-классификации = дубликат активного
        # урока (та же ситуация И действие) → не плодим. add_candidate ловит лишь точный id.
        sim = similar_lessons(ppath, L["trigger"], L["action"],
                              states=ACTIVE_STATES, threshold=0.4)
        if classify_consolidation(L["trigger"], L["action"], sim)["action"] == "NOOP":
            skipped += 1
            continue
        _lesson, was_new = add_candidate(ppath, L)
        if not was_new:
            skipped += 1
            continue
        created += 1
        audit_append(ppath, {"action": "digest", "id": L["id"],
                             "detector": L["provenance"]["detector"],
                             "session": rr.get("session_id"), "state": "ephemeral"})
        # событие-сигнал для confidence: прогон, где урок «сработал» (fix/обходка прошли).
        # append-only; recompute восстановит S/N из events.ndjson (не из этого счётчика).
        event_append(ppath, {"id": L["id"], "source": "digest",
                             "session": rr.get("session_id"),
                             "sessions_total": 1, "sessions_success": 1,
                             "tests_total": int(L.get("tests_total", 0)),
                             "tests_passed": int(L.get("tests_passed", 0))})

    print(f"\nanalyst digest — session {rr.get('session_id')}: "
          f"{created} нов(ых) кандидат(ов) в ephemeral"
          f"{f', {skipped} пропущено (дубль/похоже на существующий)' if skipped else ''}.")
    if created:
        print("  Смотри: analyst review   ·   промоут (человек): analyst promote <id>\n")
    else:
        print("  Новых высокоточных сигналов в прогоне не найдено.\n")
