"""maind analyze — единый пост-ран разбор прогона «всё ли сработало как надо».

После задачи-с-планом источники исхода читаются по отдельности (run-report хука, лог Bash,
observer, git, health). analyze агрегирует их в ОДИН отчёт с вердиктом GREEN/ATTENTION/RED —
read-only, деградирует по наличию источника (нет run-report → форензика: bash-лог без кодов
возврата + git; вердикт помечается confidence=low, чтобы не переобещать).

Первичный источник — run-report (SessionEnd-хук harness пишет <project>/.claude/runs/<sid>.json
из транскрипта). Смычка с RAG-дисциплиной: dev-loop `tool_failures` (движок был недоступен →
факт не проверен) выносятся в блок «Непроверено → ПОВТОРНЫЙ ПРОХОД».

stdlib-only; Env передаётся явно. Переиспользует health.health_report, projects, core.run_cmd."""
import hashlib
import json
import os
import statistics
from pathlib import Path

from core.pathology import detect as pathology_detect

from .common import find_run_report, parse_args, read_ndjson_iter, run_cmd, safe_load_json
from .config import load_config
from .health import _target


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


# ── источник 5: health (хаб жив? переиспользуем health_report) ────────────────
def health_slice(env, config, project):
    """Компактный срез health_report (память/граф/round-trip). None при любой ошибке —
    здоровье хаба ортогонально задаче, не роняем разбор из-за него."""
    try:
        from .health import health_report
        rep = health_report(env, config, project)
        return {"status": rep.get("status"), "memory_daemon": rep.get("memory_daemon"),
                "maind_mcp": rep.get("maind_mcp"), "roundtrip": rep.get("memory_roundtrip")}
    except Exception:
        return None


# ── источник 6: usage-токены (run-report schema=2; аддитивный, молча отсутствует на schema=1) ──
_TREND_K = 20        # окно тренда (последние K прогонов, БЕЗ текущей сессии)
_TREND_MIN_N = 3      # меньше — сравнивать не с чем, показываем только текущие числа


def _fmt_tokens_k(n):
    """Компактное 'тысячное' число для строки tokens: 48501 → '48k', 500 → '500'."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.0f}k" if abs(n) >= 1000 else str(int(n))


def _read_usage_trend(project_path, exclude_session, limit=_TREND_K):
    """Последние `limit` строк <project>/.claude/analyze/usage-trend.ndjson, ИСКЛЮЧАЯ текущую
    сессию (иначе прогон сравнивал бы себя с собой). read_ndjson_iter уже защитен (нет файла/
    битые строки → пусто), здесь только фильтр+хвост."""
    f = Path(project_path) / ".claude" / "analyze" / "usage-trend.ndjson"
    rows = [r for r in read_ndjson_iter(f) if r.get("session") != exclude_session]
    return rows[-limit:]


def _read_baseline(project_path):
    """<project>/.claude/analyze/baseline.json — pinned-снимок медиан. Формат не заморожен
    (спека: `{by_model|totals: {median_out,...}}`) → читаем защитно: totals.median_out, а при
    его отсутствии — median_out первой numeric-подходящей записи by_model. Любое отклонение
    формата/отсутствие файла → None (сравнение с pinned baseline просто не показывается)."""
    b = safe_load_json(Path(project_path) / ".claude" / "analyze" / "baseline.json", None)
    if not isinstance(b, dict):
        return None
    node = b.get("totals")
    if not isinstance(node, dict):
        by_model = b.get("by_model")
        node = next((v for v in (by_model or {}).values() if isinstance(v, dict)), None)
    if not isinstance(node, dict):
        return None
    median_out = node.get("median_out")
    return {"median_out": median_out} if isinstance(median_out, (int, float)) else None


def tokens_slice(run_report, project_path, session=None):
    """Блок usage-токенов текущего прогона + сравнение с трендом/pinned baseline.

    ТОЛЬКО run-report schema=2 с непустым usage.totals — иначе None (молча, без предупреждений:
    schema=1 просто не несёт usage). Тренд/baseline — best-effort надстройка поверх текущих чисел,
    отсутствие файла/недостаток строк (<_TREND_MIN_N) не блокирует сами текущие in/out/cache-hit."""
    if not run_report or run_report.get("schema") != 2:
        return None
    usage = run_report.get("usage")
    if not isinstance(usage, dict):
        return None
    totals = usage.get("totals") or {}
    out = totals.get("out", 0)
    block = {
        "in": totals.get("in", 0), "out": out,
        "cache_read": totals.get("cache_read", 0), "cache_creation": totals.get("cache_creation", 0),
        "cache_hit": usage.get("cache_hit"),
        "trend": None, "baseline": None,
    }
    exclude = session or run_report.get("session_id")
    trend_rows = _read_usage_trend(project_path, exclude)
    if len(trend_rows) >= _TREND_MIN_N:
        outs = [r.get("out", 0) for r in trend_rows]
        median_out = statistics.median(outs)
        median_in = statistics.median([r.get("in", 0) for r in trend_rows])
        p90_out = statistics.quantiles(outs, n=10, method="inclusive")[-1]
        block["trend"] = {
            "n": len(trend_rows), "median_out": median_out, "median_in": median_in,
            "p90_out": p90_out,
            "ratio_out": (out / median_out) if median_out else None,
        }
    baseline = _read_baseline(project_path)
    if baseline:
        bmo = baseline["median_out"]
        block["baseline"] = {"median_out": bmo, "ratio_out": (out / bmo) if bmo else None}
    return block


# ── источник 7: pack-drift (agent-pack'и harness — без импорта harness) ───────
def pack_drift(ppath):
    """generated-файлы agent-pack'ов харнеса, правленные локально мимо override.

    Самодостаточно (maind НЕ импортирует harness — правило репо, пакеты изолированы):
    путь лока и формула sha256 продублированы буквально из harness.agentpacks
    (LOCK_REL/sha256_text) — единственный источник схемы лока остаётся harness,
    здесь только читаем то, что он уже написал. Нет .claude/agent-pack.lock.json → []."""
    lock = safe_load_json(Path(ppath) / ".claude" / "agent-pack.lock.json", None)
    packs = lock.get("packs") if isinstance(lock, dict) else None
    if not isinstance(packs, dict):
        return []
    reasons = []
    for pdata in packs.values():
        files = pdata.get("files") if isinstance(pdata, dict) else None
        for f in files if isinstance(files, list) else []:
            if not isinstance(f, dict):
                continue
            base_sha, target = f.get("base_sha256"), f.get("target")
            if not base_sha or not target or f.get("kind") == "merge":
                continue
            owned = f.get("user_owned")
            if owned is True:
                continue
            # ВРЕМЕННЫЙ допуск: локи без поля user_owned (записаны до его появления в схеме)
            # для review-gate.env.ini — единственного уже известного user_owned-таргета всех
            # паков, ещё не пережившего ре-рендер с новым полем. Остальные target без поля —
            # трактуем как НЕ user_owned (совпадает с default .get(..., False) в harness).
            if owned is None and str(target).endswith("review-gate.env.ini"):
                continue
            try:
                disk_sha = hashlib.sha256(
                    (Path(ppath) / target).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            except (OSError, UnicodeDecodeError):
                disk_sha = None
            if disk_sha != base_sha:
                reasons.append(f"generated-файл пака правлен локально: {target} — "
                               f"перенеси правку в override и восстанови (harness agent-packs render)")
    return reasons


# ── источник 8: патологии (core.pathology — детекторы поверх run-report, C-2) ─
def pathology_slice(run_report):
    """core.pathology.detect() поверх run_report, разложенный по severity:
    attention-находки уходят evidence-строками в reasons вердикта (через compute_verdict,
    та же механика, что pack_drift), info-находки — отдельно, в rep['efficiency'] (не влияют
    на вердикт). detect() сама защитна (None/не-dict/битые срезы → []) — здесь только разбор."""
    findings = pathology_detect(run_report)
    attention = [f["evidence"] for f in findings if f.get("severity") == "attention"]
    efficiency = [f for f in findings if f.get("severity") == "info"]
    return attention, efficiency


# ── вердикт ──────────────────────────────────────────────────────────────────
def compute_verdict(run_report, git, observer, tokens=None, pack_drift=None,
                    pathology_attention=None):
    """(verdict, confidence, red, reasons, repass) из собранных срезов.
    RED — упавший тест/воркфлоу. ATTENTION — линт/tool-провалы/deferred/workarounds/грязное
    дерево/LOOP/аномальные токены (см. tokens_slice)/pack-drift (см. pack_drift)/attention-
    патологии (см. pathology_slice, core.pathology). repass — dev-loop tool_failures (движок
    был недоступен → факт не проверен). RED от токенов, pack-drift и патологий НЕ бывает —
    только ATTENTION (info-патологии вердикт вообще не трогают, см. rep['efficiency'])."""
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

    if git and git.get("dirty"):
        reasons.append(f"рабочее дерево не чисто: {git.get('working_files', '?')} файл(ов)")
    if observer and observer.get("alerts"):
        reasons.append(f"observer-алертов: {len(observer['alerts'])}")
    for r in (pack_drift or []):
        reasons.append(r)
    for r in (pathology_attention or []):     # ЖЁСТКО: только reasons.append, никогда red
        reasons.append(r)

    trend = (tokens or {}).get("trend")
    if trend and trend.get("median_out"):    # median_out=0 — сравнивать не с чем, не делим на 0
        threshold = max(1.5 * trend["median_out"], trend["p90_out"])
        if tokens["out"] > threshold:
            reasons.append(f"токены ×{tokens['out'] / trend['median_out']:.1f} "
                           f"vs медиана тренда")

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

    run_report = find_run_report(ppath, session)
    # bash-лог коррелируем по РЕАЛЬНОЙ сессии run-report'а (в проде session_id run-report ==
    # id сессии Claude == session в bash-логе); явный --session имеет приоритет.
    effective_session = session or (run_report or {}).get("session_id")
    bash_log = bash_log_forensics(env, ppath, effective_session)
    observer = observer_forensics(ppath)
    git = git_status(ppath, base)
    health = health_slice(env, config, project) if with_health else None
    tokens = tokens_slice(run_report, ppath, effective_session)
    drift = pack_drift(ppath)
    pathology_attention, efficiency = pathology_slice(run_report)

    verdict, confidence, red, reasons, repass = compute_verdict(
        run_report, git, observer, tokens, pack_drift=drift,
        pathology_attention=pathology_attention)
    return {
        "project": pid, "path": ppath,
        "verdict": verdict, "confidence": confidence,
        "red": red, "reasons": reasons, "repass": repass,
        "run_report": run_report, "bash_log": bash_log,
        "observer": observer, "git": git, "health": health, "tokens": tokens,
        "pack_drift": drift, "efficiency": efficiency,
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

    tk = rep.get("tokens")
    if tk:                                    # молча отсутствует на schema=1/без usage
        print("\ntokens  " + "─" * 53)
        line = (f"  in {_fmt_tokens_k(tk['in'])} · out {_fmt_tokens_k(tk['out'])}")
        if tk.get("cache_hit") is not None:
            line += f" · cache-hit {tk['cache_hit'] * 100:.0f}%"
        tr = tk.get("trend")
        if tr:
            line += (f" · медиана out ({tr['n']} прогонов) {_fmt_tokens_k(tr['median_out'])}")
            if tr.get("ratio_out") is not None:
                line += f" → ×{tr['ratio_out']:.1f}"
        print(line)
        bl = tk.get("baseline")
        if bl:
            bline = f"  pinned baseline: медиана out {_fmt_tokens_k(bl['median_out'])}"
            if bl.get("ratio_out") is not None:
                bline += f" → ×{bl['ratio_out']:.1f}"
            print(bline)

    eff = rep.get("efficiency")
    if eff:                                   # info-патологии — не влияют на вердикт, только к сведению
        print("\nЭффективность  " + "─" * 44)
        for f in eff:
            print(f"  · {f.get('code')}: {f.get('evidence')}")

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
