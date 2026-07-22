"""analyst digest — детерминированное извлечение КАНДИДАТ-уроков из run-report прогона.

Первичный источник — run-report (SessionEnd-хук harness пишет <project>/.claude/runs/<sid>.json,
уже дистиллировав транскрипт). digest берёт ТОЛЬКО высокоточные сигналы (не «угадывает инсайты»
— это осознанная граница MVP):

  A. resolved-failure — проверка (тест/линт) падала и затем прошла в том же прогоне
     («сработало после N попыток») → урок-gotcha с evidence test-pass;
  B. workaround — агент явно записал обходку в dev-loop-сигнал (devloop.workarounds);
  C. pathology — детектор `core.pathology.detect` нашёл патологию С готовой ремедиацией
     (file-reread/tool-error-loop/protected-write/no-verify) И код РЕЦИДИВИРУЕТ: та же
     патология встречалась ≥2 раз в последних 5 прогонах проекта. Разовое срабатывание —
     шум одной сессии, урок не создаёт (остальное — сигнал для `maind analyze`, не для памяти);
  D. workflow_relaunch — run-report hook (P1.2, `_lib.py`) уже сгруппировал вызовы `Workflow`
     по `runId`/имени и отдал готовую группу `{name, count, statuses}` при `count ≥
     _WF_RELAUNCH_MIN`. Диагностический, не тревожный сигнал (findings/P1-workflow-rootcause.md,
     plans/2026.07.15-TELEMETRY-OPT): «воркфлоу-скрипт потребовал N итераций resume/отладки
     внутри одной сессии» — не ошибка (штатный `resumeFromRunId`-паттерн), но кандидат-урок
     «доводить скрипт в изолированном dev-loop, не в основной интерактивной сессии».

Кандидаты пишутся в ephemeral (LOCAL, unreviewed). Суть фикса человек уточняет на `analyst review`;
промоут — только человек. Извлекатели A/B — ЧИСТЫЕ функции (run_report → [lesson]) ради
тестируемости; C (`extract_pathologies`) — осознанное исключение из этого правила: правило
рецидива требует смотреть ИСТОРИЮ прогонов проекта, а не только текущий run_report, поэтому
она читает (read-only) `<project>/.claude/runs/*.json` — IO ограничен чтением, ничего не пишет.
Защитно: любое отсутствующее/битое поле run-report пропускается, digest не падает."""
import json
import os
import re
from pathlib import Path

from core.pathology import detect as detect_pathologies

from .common import die, find_run_report, parse_args, safe_load_json
from .lessons import (ACTIVE_STATES, add_candidate, audit_append,
                      classify_consolidation, event_append, jaccard,
                      new_lesson, similar_lessons)
from .runs import neutral_run_report

_SIMILAR_CMD = 0.6   # порог «та же по сути команда» для пары fail→pass

# ── фильтр «настоящая проверка vs разведка» для сигнала A ──────────────────────
# Хук (run-report/_lib.py TEST_PAT/LINT_PAT) кладёт в bash.tests/lints ЛЮБУЮ команду
# с подстрокой раннера — включая разведку вроде `ls .bin | grep -E 'vitest|pest'`.
# Такая «падала→прошла» пара даёт мусорный урок (trigger≈action, чинить нечего).
# Отсекаем: урок из resolved-failure имеет смысл, только если команда РЕАЛЬНО исполняет
# тест/линт-раннер, а не ищет его имя грепом и не пробит наличие через `|| ...`.

# Раннер действительно ЗАПУСКАЕТСЯ: имя в позиции команды (после разделителя/начала,
# в т.ч. `vendor/bin/pest`, `npm test`), а не аргумент grep/ls. `\b(?<![-/])` не ловит
# `--test`/`some/test`; для `vendor/bin/pest` и `npm test` — явные подвыражения.
_RUNNER_EXEC = re.compile(
    r"(?:(?:^|[;&|]\s*|\bcd\s+\S+\s+|\bxargs\s+)"
    r"(?:pytest|phpunit|pest|jest|vitest|unittest|ruff|flake8|pylint|mypy|eslint|"
    r"phpstan|psalm|pint|black|isort|tsc|prettier|composer|py_compile)\b"
    r"|vendor/bin/(?:pest|phpunit|pint|phpstan|psalm)\b"
    r"|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|lint)\b"
    r"|(?:go|cargo)\s+test\b"
    # Laravel: `php artisan test` (+ ключи вроде --filter) и Sail-обёртка `sail test`
    # (документированный shortcut Sail на `artisan test`, sail/bin/sail) — N2a: без
    # этой ветки резолвится доминирующий раннер Laravel-стека экосистемы, петля
    # обучения не видела ни одного «упал→прошёл» на нём.
    r"|(?:php\s+artisan|sail)\s+test\b"
    r"|(?<![\w.])(?:validate|test)\.sh\b)", re.I)  # путь scripts/validate.sh — это ЗАПУСК

# Явная разведка: команда, СОДЕРЖАЩАЯ имя раннера лишь как аргумент поиска
# (`grep … vitest`, `ls … | grep pest`) — не исполнение, а проба присутствия (какой
# бы суффикс — `|| echo NO`, `2>/dev/null` — у неё ни был). N2b: бланкетный отказ по
# одному факту наличия `||` в команде рубил и легитимные guard-паттерны (`pytest ||
# exit 1`, `... | xargs pytest`) — раннер там реально исполняется и его exit-код
# определяет ветку `||`, отбрасывать такой resolved-failure неверно; различение
# «проба vs прогон» и так делает проверка ниже (раннер в первом сегменте до
# `|`/`;`/`&`).
_DIAGNOSTIC_CMD = re.compile(r"\b(?:grep|rg|ag|find|ls|cat|which|command\s+-v)\b", re.I)


def _is_real_check(cmd):
    """True, если команда действительно ЗАПУСКАЕТ тест/линт-раннер (а не ищет его грепом).
    Отсекает диагностический шум из сигнала A — resolved-failure на такой паре давал бы
    урок с trigger≈action, чинить в котором нечего."""
    if not cmd or not _RUNNER_EXEC.search(cmd):
        return False
    # раннер упомянут ТОЛЬКО как аргумент разведки, реального запуска нет → шум
    if _DIAGNOSTIC_CMD.search(cmd) and not _RUNNER_EXEC.search(re.split(r"[|;&]", cmd)[0]):
        return False
    return True

# источник run-report — единый core.find_run_report (раскрывает ~ в пути)

# ── сигнал C: патологии-рецидивы (core.pathology + правило рецидива) ─────────
PATHOLOGY_WINDOW = 5     # правило рецидива: окно из скольких последних прогонов смотрим
PATHOLOGY_MIN_HITS = 2   # код должен встретиться минимум в стольких прогонах окна

# Коды с готовой ремедиацией → потенциальный урок (при рецидиве). Остальные коды
# core.pathology.detect — сигналы для analyze/дэшборда, в память НЕ идут (нет
# конкретного «что делать», только диагноз — учить агента нечему).
_PATHOLOGY_REMEDIATIONS = {
    "file-reread": "держи карту прочитанного; для повторного обращения используй "
                   "заметки/план, не re-read",
    "tool-error-loop": "после 2 одинаковых отказов инструмента меняй подход, не долби",
    "protected-write": "generated-файлы паков не редактируй — оверрайды в "
                       ".claude/rules/*-overrides.md",
    "no-verify": "изменил код — прогони тесты до завершения сессии",
}


def _fmt_num(v):
    """Компактная строка числа для evidence-тегов: float без длинного хвоста, остальное str()."""
    if isinstance(v, float):
        return str(round(v, 3))
    return str(v)


def _recent_run_reports(project_path, current, limit=PATHOLOGY_WINDOW):
    """Последние `limit` run-report'ов проекта (текущий гарантированно среди них — даже
    если ещё не долетел на диск/там лежит устаревшая версия под тем же session_id).

    Остальное читаем с диска `<project>/.claude/runs/*.json`, свежие по mtime первыми;
    битые/не-dict файлы пропускаем (safe_load_json). Дёшево: run-report — компактный JSON."""
    runs_dir = Path(os.path.expanduser(str(project_path))) / ".claude" / "runs"
    on_disk = []
    if runs_dir.is_dir():
        files = sorted((p for p in runs_dir.glob("*.json") if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            rec = safe_load_json(p, None)
            if isinstance(rec, dict):
                on_disk.append(rec)
    cur_sid = current.get("session_id") if isinstance(current, dict) else None
    if cur_sid:
        on_disk = [r for r in on_disk if r.get("session_id") != cur_sid]
    reports = ([current] if isinstance(current, dict) else []) + on_disk
    return reports[:limit]


def _pathology_hit_counts(project_path, current):
    """{code: сколько прогонов из окна содержат ≥1 находку этого кода}. detect гоняем
    по каждому прогону окна отдельно — он чистый и дешёвый (см. core/pathology.py)."""
    counts = {}
    for rr in _recent_run_reports(project_path, current):
        for code in {f.get("code") for f in detect_pathologies(rr)}:
            counts[code] = counts.get(code, 0) + 1
    return counts


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
    # только НАСТОЯЩИЕ прогоны раннера — разведку/пробинг (`grep vitest`, `... || echo`)
    # хук кладёт в bash.tests по подстроке, но урок из неё мусорный (см. _is_real_check).
    entries = [e for e in _check_entries(run_report) if _is_real_check(e.get("command", ""))]
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


def extract_pathologies(run_report, project_path):
    """Сигнал C: патологии прогона (`core.pathology.detect`) с готовой ремедиацией
    И рецидивом — тот же код встретился ≥PATHOLOGY_MIN_HITS раз в последних
    PATHOLOGY_WINDOW прогонах проекта (текущий включительно). Разовое срабатывание
    урок не создаёт (шум одной сессии); коды без ремедиации в _PATHOLOGY_REMEDIATIONS
    в уроки не идут вовсе (это сигналы для analyze, не для памяти).

    scope/project выводятся из project_path (как в cmd_digest) — сигнатура намеренно
    (run_report, project_path), а не (run_report, *, scope, project): C нужен реальный
    путь проекта, чтобы прочитать историю прогонов (см. docstring модуля про IO-исключение)."""
    if not isinstance(run_report, dict):
        return []
    findings = detect_pathologies(run_report)
    if not findings:
        return []
    project = Path(os.path.expanduser(str(project_path))).name
    scope = f"project:{project}"
    sid = run_report.get("session_id") or ""
    hit_counts = None  # считаем лениво: история читается только если в отчёте вообще есть кандидатный код
    out, seen = [], set()
    for f in findings:
        code = f.get("code")
        remediation = _PATHOLOGY_REMEDIATIONS.get(code)
        if not remediation or code in seen:
            continue
        if hit_counts is None:
            hit_counts = _pathology_hit_counts(project_path, run_report)
        hits = hit_counts.get(code, 0)
        if hits < PATHOLOGY_MIN_HITS:
            continue
        seen.add(code)
        trigger = (f"рецидив патологии прогона «{code}» ({hits}/{PATHOLOGY_WINDOW} "
                  f"последних прогонов): {f.get('evidence') or ''}")
        out.append(new_lesson(
            trigger=trigger, action=remediation, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector=code,
            evidence=[f"session:{sid}", f"recurred:{hits}/{PATHOLOGY_WINDOW}",
                     f"metric:{_fmt_num(f.get('metric'))}",
                     f"threshold:{_fmt_num(f.get('threshold'))}"],
            meta={"severity": f.get("severity"), "data": f.get("data") or {}}))
    return out


def extract_workflow_relaunch(run_report, *, scope, project):
    """Сигнал D: срез `workflow_relaunch` run-report'а (P1.2) — готовые группы
    `{name, count, statuses}` уже отфильтрованы хуком по порогу `_WF_RELAUNCH_MIN`.
    Диагностический кандидат, не «ошибка»: N resume/relaunch одного воркфлоу в одной
    сессии — прокси «скрипт нестабилен, дебажился на лету внутри основной сессии»
    (findings/P1-workflow-rootcause.md)."""
    sid = run_report.get("session_id") or ""
    out = []
    for g in (run_report.get("workflow_relaunch") or []):
        if not isinstance(g, dict) or not g.get("name") or not g.get("count"):
            continue
        name, count, statuses = g["name"], g["count"], g.get("statuses") or {}
        trigger = f"workflow «{name}» перезапускался/резюмился {count}× в одной сессии"
        action = ("довести скрипт воркфлоу до стабильного состояния в изолированном "
                  "dev-loop ДО фан-аута, не отлаживать его правками внутри основной "
                  "интерактивной сессии (resumeFromRunId после Edit — штатно, но частое "
                  "повторение сигналит незрелость только что написанного скрипта)")
        out.append(new_lesson(
            trigger=trigger, action=action, kind="gotcha", scope=scope,
            session_id=sid, project=project, detector="workflow-relaunch",
            evidence=[f"session:{sid}", f"count:{count}"],
            meta={"name": name, "statuses": statuses}))
    return out


def extract_candidates(run_report, *, scope, project, project_path=None):
    """Все высокоточные кандидаты прогона (A + B + C + D). Дубли по id схлопываются на записи.

    project_path — опционален (обратная совместимость чистых A/B-вызовов без пути на
    диске, см. тесты): без него сигнал C (требует историю прогонов) просто не запускается."""
    if not isinstance(run_report, dict):
        return []
    out = (extract_resolved_failures(run_report, scope=scope, project=project)
           + extract_workarounds(run_report, scope=scope, project=project)
           + extract_workflow_relaunch(run_report, scope=scope, project=project))
    if project_path is not None:
        out += extract_pathologies(run_report, project_path)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_digest(env, argv):
    """analyst digest [--cwd] [--session UUID] [--dry-run] [--json]
    — извлечь кандидат-уроки из свежего run-report в .claude/analyst/lessons/ephemeral/."""
    opts, _ = parse_args(argv, {"--cwd": "bool", "--session": "str",
                                "--project": "str", "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst digest [--cwd] [--session UUID] [--dry-run] [--json]\n"
              "  Детерминированно извлекает кандидат-уроки из run-report прогона "
              "(resolved-failure / workaround / рецидивирующая патология) → ephemeral. "
              "Промоут — человек.")
        return

    ppath = os.getcwd()
    rr = neutral_run_report(ppath, opts["session"] or None)
    if rr is None:
        rr = find_run_report(ppath, opts["session"] or None)
    if not rr:
        die("нет run-report в .claude/runs — включи захват прогона: "
            "harness hooks --target . --run-report on, затем проведи сессию Claude Code")

    project = Path(os.path.abspath(ppath)).name
    scope = f"project:{project}"
    cands = extract_candidates(rr, scope=scope, project=project, project_path=ppath)

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
