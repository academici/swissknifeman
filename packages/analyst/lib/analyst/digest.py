"""analyst digest — детерминированное извлечение КАНДИДАТ-уроков из run-report прогона.

Первичный источник — run-report (SessionEnd-хук harness пишет <project>/.claude/runs/<sid>.json,
уже дистиллировав транскрипт). digest берёт ТОЛЬКО высокоточные сигналы (не «угадывает инсайты»
— это осознанная граница MVP, см. research/analyst-self-learning-system.md §11):

  A. resolved-failure — проверка (тест/линт) падала и затем прошла в том же прогоне
     («сработало после N попыток») → урок-gotcha с evidence test-pass;
  B. workaround — агент явно записал обходку в dev-loop-сигнал (devloop.workarounds).

Кандидаты пишутся в ephemeral (LOCAL, unreviewed). Суть фикса человек уточняет на `analyst review`;
промоут — только человек. Извлекатели — ЧИСТЫЕ функции (run_report → [lesson]) ради тестируемости.
Защитно: любое отсутствующее/битое поле run-report пропускается, digest не падает."""
import json
import os
from pathlib import Path

from .common import die, parse_args, safe_load_json
from .lessons import (add_candidate, audit_append, event_append, jaccard,
                      new_lesson)

_SIMILAR_CMD = 0.6   # порог «та же по сути команда» для пары fail→pass


# ── источник: run-report ─────────────────────────────────────────────────────
def find_run_report(project_path, session=None):
    """Свежий (или по session) <project>/.claude/runs/*.json. None если нет каталога/файлов."""
    runs = Path(os.path.expanduser(str(project_path))) / ".claude" / "runs"
    if not runs.is_dir():
        return None
    if session:
        f = runs / f"{session}.json"
        return safe_load_json(f, None) if f.is_file() else None
    files = [p for p in runs.glob("*.json") if p.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return safe_load_json(latest, None)


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
        top_files = ", ".join(Path(x).name for x in files[:3]) or "—"
        trigger = f"проверка падала и была исправлена в прогоне: {fcmd}"
        action = (f"разобрано за {attempts} попыт(ки); затронутые файлы: {top_files}. "
                  f"Уточни СУТЬ фикса при review (что именно поправили).")
        out.append(new_lesson(
            trigger=trigger, action=action, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="resolved-failure",
            evidence=[f"session:{sid}", "test-pass", f"attempts:{attempts}"],
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

    created = 0
    for L in cands:
        _lesson, was_new = add_candidate(ppath, L)
        if was_new:
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

    dup = len(cands) - created
    print(f"\nanalyst digest — session {rr.get('session_id')}: "
          f"{created} нов(ых) кандидат(ов) в ephemeral"
          f"{f', {dup} уже были' if dup else ''}.")
    if created:
        print("  Смотри: analyst review   ·   промоут (человек): analyst promote <id>\n")
    else:
        print("  Новых высокоточных сигналов в прогоне не найдено.\n")
