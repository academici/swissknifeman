"""maind analyze — единый пост-ран разбор прогона «всё ли сработало как надо».

После задачи-с-планом источники исхода читаются по отдельности (run-report хука, лог Bash,
observer, git, health). analyze агрегирует их в ОДИН отчёт с вердиктом GREEN/ATTENTION/RED —
read-only, деградирует по наличию источника (нет run-report → форензика: bash-лог без кодов
возврата + git; вердикт помечается confidence=low, чтобы не переобещать).

Первичный источник — run-report (SessionEnd-хук harness пишет <project>/.claude/runs/<sid>.json
из транскрипта). Смычка с RAG-дисциплиной: dev-loop `tool_failures` (движок был недоступен →
факт не проверен) выносятся в блок «Непроверено → ПОВТОРНЫЙ ПРОХОД».

stdlib-only; Env передаётся явно. Переиспользует health.health_report, projects, core.run_cmd."""
import json
import os
from pathlib import Path

from ..common import find_run_report, find_run_report_result, parse_args, read_ndjson_iter, run_cmd
from core.runs import find_analytics_events
from ..config import load_config
from ..health import _target


# ── источник 1: run-report (первичный) — единый core.find_run_report (раскрывает ~)


# ── источник 2: лог Bash (форензика; БЕЗ кодов возврата — PreToolUse) ─────────
# паттерны те же, что в run-report/_lib.py (осознанный дубль: хук автономен, не импортируем).
_TEST_HINT = ("pytest", "phpunit", "pest", "jest", "vitest", "go test", "cargo test",
              "npm test", "npm run test", "yarn test", "unittest", "validate.sh", "test.sh")
_LINT_HINT = ("ruff", "flake8", "pylint", "mypy", "eslint", "pint", "phpstan", "psalm",
              "black", "isort", "tsc", "prettier", "py_compile")


def bash_log_forensics(env, project_path, session=None):
    """Счётчик команд из ~/.claude/logs/bash-commands.jsonl по cwd-префиксу проекта (+session).
    ВНИМАНИЕ: лог пишется PreToolUse → БЕЗ кодов возврата: видно, что тест/линт ГОНЯЛИ, не
    прошли ли (это знает run-report). None если лог отсутствует."""
    log = env.home / ".claude" / "logs" / "bash-commands.jsonl"
    if not log.is_file():
        return None
    base = os.path.abspath(os.path.expanduser(str(project_path)))
    total, tests, lints = 0, [], []
    try:
        for rec in read_ndjson_iter(log):
            cwd = rec.get("cwd") or ""
            if not (cwd == base or cwd.startswith(base + os.sep)):
                continue
            if session and rec.get("session") != session:
                continue
            cmd = (rec.get("command") or "")
            total += 1
            low = cmd.lower()
            if any(h in low for h in _TEST_HINT):
                tests.append(cmd[:160])
            if any(h in low for h in _LINT_HINT):
                lints.append(cmd[:160])
    except OSError:
        return None
    return {"total": total, "tests": tests, "lints": lints}


# ── источник 3: observer (best-effort, схема не заморожена) ───────────────────
def observer_forensics(project_path):
    """<project>/.claude/observer/runtime.jsonl: LOOP-алерты/ошибки. Схема observer
    экспериментальна → защитно: сигнал ловим подстрокой по сырой строке. None если нет файла."""
    f = Path(project_path) / ".claude" / "observer" / "runtime.jsonl"
    if not f.is_file():
        return None
    lines, alerts = 0, []
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                lines += 1
                low = line.lower()
                if ("loop" in low or "\"error\"" in low or "alert" in low) and len(alerts) < 20:
                    alerts.append(line[:200])
    except OSError:
        return None
    return {"lines": lines, "alerts": alerts}


# ── источник 4: git ──────────────────────────────────────────────────────────
def git_status(project_path, base=None):
    """Чистота рабочего дерева (порцелан) + опционально diff --stat <base>...HEAD.
    None если не git-репозиторий. base=None → только рабочее дерево (без догадок о ветке)."""
    path = str(project_path)
    porc = run_cmd(["git", "-C", path, "status", "--porcelain"], capture=True, check=False)
    if porc.returncode != 0:
        return None
    changed = [ln for ln in (porc.stdout or "").splitlines() if ln.strip()]
    out = {"dirty": bool(changed), "working_files": len(changed)}
    if base:
        diff = run_cmd(["git", "-C", path, "diff", "--stat", f"{base}...HEAD"],
                       capture=True, check=False)
        out["base"] = base
        out["diffstat"] = (diff.stdout or "").strip() if diff.returncode == 0 else None
        if diff.returncode != 0:
            out["diff_error"] = (diff.stderr or "").strip()[:200]
    return out


# ── источник 6: непросмотренные уроки analyst (петля обучения ждёт человека) ───
# ephemeral/candidate — уроки, которые digest извлёк, но человек ещё не отревьюил/промоутнул.
# Копятся молча (digest пишет автоматически, review — вручную); analyze напоминает про них.
_PENDING_LESSON_STATES = ("ephemeral", "candidate")


def pending_lessons(project_path):
    """Сколько уроков analyst ждут ревью человека (ephemeral+candidate). 0 если каталога нет.
    Read-only счётчик файлов — analyst-стор живёт в <project>/.claude/analyst/lessons/<state>/."""
    roots = (Path(os.path.expanduser(str(project_path))) / ".swissknife" / "analyst" / "lessons",
             Path(os.path.expanduser(str(project_path))) / ".claude" / "analyst" / "lessons")
    total = 0
    seen = set()
    for base in roots:
        for state in _PENDING_LESSON_STATES:
            d = base / state
            if d.is_dir():
                for p in d.glob("*.json"):
                    key = (state, p.name)
                    if p.is_file() and key not in seen:
                        seen.add(key)
                        total += 1
    return total


def analytics_slice(project_path, session=None):
    """Neutral analytics consumer; it deliberately has no provider raw-path knowledge."""
    events = find_analytics_events(project_path, session=session)
    providers = sorted({event.provider_id for event in events})
    metrics = {}
    provenance = []
    for event in sorted(events, key=lambda item: (item.occurred_at, item.event_id)):
        for name, value in event.metrics.items():
            metrics[name] = metrics.get(name, 0) + value
        provenance.append(dict(event.provenance))
    return {"events": len(events), "providers": providers,
            "run_report": {"contract_version": "1.0.0", "session_id": session,
                           "metrics": {name: metrics[name] for name in sorted(metrics)},
                           "provenance": provenance}}


# ── источник 5: health (хаб жив? переиспользуем health_report) ────────────────
def health_slice(env, config, project):
    """Компактный срез health_report (память/граф/round-trip). None при любой ошибке —
    здоровье хаба ортогонально задаче, не роняем разбор из-за него."""
    try:
        from ..health import health_report
        rep = health_report(env, config, project)
        return {"status": rep.get("status"), "memory_daemon": rep.get("memory_daemon"),
                "maind_mcp": rep.get("maind_mcp"), "roundtrip": rep.get("memory_roundtrip")}
    except Exception:
        return None


# ── вердикт ──────────────────────────────────────────────────────────────────
def compute_verdict(run_report, git, observer, *, evidence_diagnostics=()):
    """(verdict, confidence, red, reasons, repass) из собранных срезов.
    RED — упавший тест/воркфлоу. ATTENTION — линт/tool-провалы/deferred/workarounds/грязное
    дерево/LOOP. repass — dev-loop tool_failures (движок был недоступен → факт не проверен)."""
    red, reasons, repass = [], [], []
    confidence = "high" if run_report else "low"

    if run_report:
        bash = run_report.get("bash") or {}
        for t in bash.get("tests") or []:
            if isinstance(t, dict) and not t.get("ok", True):
                red.append(f"тест упал: {t.get('command', '?')}")
        for wf in run_report.get("workflows") or []:
            if isinstance(wf, dict) and str(wf.get("status", "")).lower() in ("failed", "error"):
                red.append(f"воркфлоу {wf.get('name', '?')}: {wf.get('status')}")
        for lint in bash.get("lints") or []:
            if isinstance(lint, dict) and not lint.get("ok", True):
                reasons.append(f"линт не прошёл: {lint.get('command', '?')}")
        tf = run_report.get("tool_failures") or []
        if tf:
            reasons.append(f"tool-провалов в транскрипте: {len(tf)}")
        dl = run_report.get("devloop") or {}
        if dl.get("deferred"):
            reasons.append(f"отложено (deferred): {len(dl['deferred'])}")
        if dl.get("workarounds"):
            reasons.append(f"обходки (workarounds): {len(dl['workarounds'])}")
        if dl.get("open_questions"):
            reasons.append(f"открытые вопросы: {len(dl['open_questions'])}")
        for item in (dl.get("tool_failures") or []):
            repass.append(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False))

        # наблюдаемость памяти/графа (ключ run-report.maind — аддитивный; старый отчёт → пусто).
        maind = run_report.get("maind") or {}
        graph_calls = sum(v.get("calls", 0) for k, v in maind.items() if k.startswith("graph_"))
        by_name = (run_report.get("tools") or {}).get("by_name") or {}
        scan = sum(by_name.get(t, 0) for t in ("Read", "Grep", "Glob"))
        # КОСВЕННАЯ эвристика: тяжёлое файловое сканирование при нуле обращений к графу.
        # Формулировка «не использовался», НЕ «бесполезен» — прямой корреляции «граф спас grep» нет.
        if scan >= 30 and graph_calls == 0:
            reasons.append(f"код-граф не использовался при тяжёлом сканировании "
                           f"({scan} Read/Grep/Glob, граф ×0) — граф/Serena дешевле; "
                           f"устарел → maind sync --only graph")
        recall = maind.get("memory_recall") or {}
        if recall.get("calls", 0) >= 2 and recall.get("found_total", 0) == 0:
            reasons.append(f"память опрашивалась (recall ×{recall['calls']}), но пуста/не по адресу "
                           f"— проверь scope/наполнение (maind memory count)")

    for diagnostic in evidence_diagnostics:
        if diagnostic.get("code") == "RUN_REPORT_PROJECT_MISMATCH":
            reasons.append("RUN_REPORT_PROJECT_MISMATCH: чужой run-report исключён из verdict")

    if git and git.get("dirty"):
        reasons.append(f"рабочее дерево не чисто: {git.get('working_files', '?')} файл(ов)")
    if observer and observer.get("alerts"):
        reasons.append(f"observer-алертов: {len(observer['alerts'])}")

    if red:
        verdict = "RED"
    elif reasons or repass:
        verdict = "ATTENTION"
    else:
        verdict = "GREEN"
    return verdict, confidence, red, reasons, repass


# ── сборка отчёта ────────────────────────────────────────────────────────────
def analyze_report(env, config, project, *, session=None, base=None, with_health=True):
    """Собрать полный отчёт разбора одного проекта (read-only)."""
    pid = project["id"]
    local = project.get("local_path")
    ppath = os.path.expanduser(local) if local else os.getcwd()

    lookup = find_run_report_result(ppath, session, project_id=pid)
    run_report = lookup.report
    # bash-лог коррелируем по РЕАЛЬНОЙ сессии run-report'а (в проде session_id run-report ==
    # id сессии Claude == session в bash-логе); явный --session имеет приоритет.
    effective_session = session or (run_report or {}).get("session_id")
    bash_log = bash_log_forensics(env, ppath, effective_session)
    observer = observer_forensics(ppath)
    git = git_status(ppath, base)
    health = health_slice(env, config, project) if with_health else None

    diagnostics = []
    if lookup.diagnostic is not None:
        diagnostic = dict(lookup.diagnostic)
        diagnostic["conflicts"] = [dict(row) for row in diagnostic.get("conflicts", ())]
        diagnostics.append(diagnostic)
    verdict, confidence, red, reasons, repass = compute_verdict(
        run_report, git, observer, evidence_diagnostics=diagnostics)
    return {
        "project": pid, "path": ppath,
        "verdict": verdict, "confidence": confidence,
        "red": red, "reasons": reasons, "repass": repass,
        "run_report": run_report, "run_report_diagnostics": diagnostics, "bash_log": bash_log,
        "observer": observer, "git": git, "health": health,
        "pending_lessons": pending_lessons(ppath),
        "analytics": analytics_slice(ppath, effective_session),
    }


# ── человекочитаемый вывод ───────────────────────────────────────────────────
_ICON = {"GREEN": "✓", "ATTENTION": "⚠", "RED": "✗"}


def _print_human(rep):
    v = rep["verdict"]
    conf = "" if rep["confidence"] == "high" else "  (confidence: low — форензика без run-report)"
    print(f"\n{_ICON.get(v, '·')} mAInd analyze — project:{rep['project']} → {v}{conf}\n")

    rr = rep.get("run_report")
    print("run-report  " + "─" * 48)
    if rr:
        tools = rr.get("tools") or {}
        bash = rr.get("bash") or {}
        tpass = sum(1 for t in (bash.get("tests") or []) if t.get("ok"))
        tfail = sum(1 for t in (bash.get("tests") or []) if not t.get("ok"))
        lpass = sum(1 for x in (bash.get("lints") or []) if x.get("ok"))
        lfail = sum(1 for x in (bash.get("lints") or []) if not x.get("ok"))
        gen = (rr.get("generated_at") or "")[:16].replace("T", " ")
        print(f"  сессия:     {rr.get('session_id', '?')}  ({gen})")
        print(f"  инструментов: {tools.get('total', 0)}  · файлов изменено: "
              f"{len(rr.get('files_changed') or [])}")
        md = rr.get("maind") or {}
        if md:
            mem_calls = sum(v.get("calls", 0) for k, v in md.items() if k.startswith("memory_"))
            graph_calls = sum(v.get("calls", 0) for k, v in md.items() if k.startswith("graph_"))
            graph_found = sum(v.get("found_total", 0) for k, v in md.items() if k.startswith("graph_"))
            recall = md.get("memory_recall") or {}
            print(f"  mAInd:      память ×{mem_calls} "
                  f"(recall ×{recall.get('calls', 0)}→{recall.get('found_total', 0)} фактов) · "
                  f"граф ×{graph_calls}→{graph_found} соседей")
        print(f"  тесты:      {tpass} ok / {tfail} FAIL     линт: {lpass} ok / {lfail} FAIL")
        if rr.get("workflows"):
            for wf in rr["workflows"]:
                print(f"    воркфлоу {wf.get('name', '?')}: {wf.get('status', '?')}"
                      f"{('  — ' + wf['summary']) if wf.get('summary') else ''}")
        if rr.get("tool_failures"):
            print(f"  tool-провалы: {len(rr['tool_failures'])}")
            for tf in rr["tool_failures"][:5]:
                print(f"    ✗ {tf.get('tool', '?')}: {tf.get('snippet', '')[:100]}")
    else:
        print("  нет — форензика по bash-логу/git. Включить: "
              "harness hooks --target <проект> --run-report on")

    bl = rep.get("bash_log")
    print("\nbash-лог (форензика · без кодов возврата)  " + "─" * 14)
    if bl:
        print(f"  команд:     {bl['total']}  · тест-прогонов: {len(bl['tests'])}"
              f"  · линт-прогонов: {len(bl['lints'])}")
        print("  (лог PreToolUse — видно ЧТО гоняли, не прошло ли; pass/fail — в run-report)")
    else:
        print("  нет лога ~/.claude/logs/bash-commands.jsonl")

    git = rep.get("git")
    print("\ngit  " + "─" * 55)
    if git:
        print(f"  дерево:     {'НЕ чисто' if git.get('dirty') else 'чисто'}"
              f"  ({git.get('working_files', 0)} незакоммиченных)")
        if git.get("diffstat") is not None:
            tail = git["diffstat"].splitlines()[-1] if git["diffstat"] else "нет изменений"
            print(f"  vs {git.get('base')}: {tail}")
    else:
        print("  не git-репозиторий (или git недоступен)")

    if rep.get("observer"):
        ob = rep["observer"]
        print("\nobserver  " + "─" * 50)
        print(f"  записей: {ob['lines']}  · алертов (loop/error): {len(ob['alerts'])}")

    if rep.get("health"):
        h = rep["health"]
        print("\nhealth (хаб)  " + "─" * 46)
        print(f"  статус: {h.get('status')}  · память-демон: "
              f"{'up' if h.get('memory_daemon') else 'down'}  · round-trip: "
              f"{'ok' if h.get('roundtrip') else 'нет'}")

    print("\nИТОГ  " + "─" * 56)
    for r in rep["red"]:
        print(f"  ✗ {r}")
    for r in rep["reasons"]:
        print(f"  ⚠ {r}")
    if rep["repass"]:
        print("  Непроверено → ПОВТОРНЫЙ ПРОХОД (движок был недоступен при формировании):")
        for item in rep["repass"]:
            print(f"    ↻ {item}")
    if not (rep["red"] or rep["reasons"] or rep["repass"]):
        print("  ✓ прогон чистый: тесты/линт зелёные, дерево чисто, обходок/отложек нет")
    # напоминание о петле обучения (не влияет на вердикт — уроки ждут человека, не баг прогона)
    pending = rep.get("pending_lessons") or 0
    if pending:
        print(f"  📚 {pending} урок(ов) analyst ждут ревью — analyst review · промоут: analyst promote <id>")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_analyze(env, argv):
    """maind analyze [--project ID | --cwd] [--session UUID] [--base B] [--json] [--no-health]
    — пост-ран разбор прогона: run-report + bash-лог + observer + git + health → вердикт."""
    opts, _ = parse_args(argv, {"--project": "str", "--cwd": "bool", "--session": "str",
                                "--base": "str", "--json": "bool", "--no-health": "bool"})
    if opts["help"]:
        print("maind analyze [--project ID | --cwd] [--session UUID] [--base B] "
              "[--json] [--no-health]\n"
              "  Пост-ран разбор «всё ли сработало»: run-report (первично) + bash-лог + "
              "observer + git + health → GREEN/ATTENTION/RED.")
        return
    config, _src = load_config(env)
    project = _target(env, config, opts)
    rep = analyze_report(env, config, project, session=opts["session"] or None,
                         base=opts["base"] or None, with_health=not opts["no_health"])
    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
    # ненулевой код на RED — чтобы analyze годился как гейт в скриптах
    if rep["verdict"] == "RED":
        raise SystemExit(1)
