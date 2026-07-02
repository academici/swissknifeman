"""analyst token-report — токен-репорт по срезам (model/role) + двухслойный baseline (P4.1).

Источник — `<project>/.claude/analyze/usage-trend.ndjson` (пишет SessionEnd-хук run-report,
см. `packages/harness/configs/claude-code/hooks/run-report/run-report.py:_append_trend`,
SCHEMA=2). Формат СТРОКИ тренда (проверено чтением хука — не выдумано):
`{ts, session, in, out, cache_read, cache_creation, by_model:{model:{in,out}},
tools_total, files_changed, agents, wall_s, retr_chars}`.

Двухслойный baseline:
  - **rolling** — медиана+p90 out (+медиана in) последних `ROLLING_K` строк тренда
    (`statistics.median`/`statistics.quantiles(n=10)`, stdlib) — та же формула и то же K=20,
    что уже использует `maind.analyze.tokens_slice` (посессионный ATTENTION при живом прогоне).
    token-report применяет её агрегатно, по окну сессий, а не к одному текущему прогону.
  - **pinned** — `--baseline set --note "..."` замораживает rolling-стату текущего окна в
    `<project>/.claude/analyze/baseline.json`. Формат ОБЯЗАН совпадать с тем, что читает
    `maind.analyze._read_baseline` (сделано волной 1, НЕ трогаем): `totals.median_out`
    первично, `by_model.<model>.median_out` — fallback. Наш файл — надмножество (добавляет
    `median_in`/`p90_out`/`note`/`sessions`/`generated_at`) — maind эти поля просто не читает.

Regression-флаг (ТЗ): `out > 1.3×rolling.median_out` ИЛИ `out > rolling.p90_out`.
(Это НЕ тот же порог, что у `maind analyze` per-session ATTENTION — там `max(1.5×median, p90)`
для ОДНОЙ живой сессии; здесь порог мягче и агрегатный — разная чувствительность осознанна.)

Срезы: `--by model` — реальное поле тренда `by_model` (партиция in/out по модели ВНУТРИ
каждой сессии, пишет сам хук). `--by role` (label агента) — тренд его НЕ хранит (only
by_model), поэтому читаем полный `<project>/.claude/runs/<session>.json` (`usage.agents[].label`)
по каждой сессии окна — тот же паттерн read-only чтения run-report'ов, что уже использует
`digest._recent_run_reports`. Ретеншн `.claude/runs/` короче тренда (по умолчанию 30 файлов
против 2000 строк тренда) — сессии без сохранившегося файла просто выпадают из среза `role`
(честная деградация, без нулей и выдумывания).

`--by phase` (workflows[].name) — **ESCALATION-REQUIRED, не реализовано**: ни тренд, ни полный
run-report НЕ несут токены на уровне отдельного workflow (`workflows[]` — это только
`{name, status, summary}`, без in/out) — привязать конкретные токены к фазе нечем в текущей
схеме run-report (harness). Нужна доработка формата хука вне скоупа P4.1. `--by phase` вежливо
падает с этим объяснением, не выдумывая распределение."""
import json
import os
import statistics
from pathlib import Path

from .common import (atomic_write_json, die, find_run_report, now_iso, parse_args,
                     read_ndjson, safe_load_json, warn)

TREND_REL = Path(".claude") / "analyze" / "usage-trend.ndjson"
BASELINE_REL = Path(".claude") / "analyze" / "baseline.json"

ROLLING_K = 20          # окно rolling-baseline — совпадает с _TREND_K в maind.analyze
MIN_BASELINE_N = 3      # меньше — сравнивать не с чем (как _TREND_MIN_N в maind.analyze)
REGRESSION_MULT = 1.3   # ТЗ: регресс = out > 1.3×медиана ИЛИ out > p90
SUPPORTED_BY = ("model", "role", "phase")


# ── пути/чтение ────────────────────────────────────────────────────────────────
def trend_path(project_path):
    return Path(os.path.expanduser(str(project_path))) / TREND_REL


def baseline_path(project_path):
    return Path(os.path.expanduser(str(project_path))) / BASELINE_REL


def read_trend(project_path):
    """Строки usage-trend.ndjson по порядку записи (append-only, старые → новые).
    [] если файла нет/пуст — источник best-effort (пишет хук, ошибки хука не барьер)."""
    return read_ndjson(trend_path(project_path))


def read_pinned_baseline(project_path):
    """<project>/.claude/analyze/baseline.json → {median_out, median_in, p90_out, note,
    generated_at, sessions}. None — файла нет/битый/без totals.median_out (тот же контракт,
    что maind.analyze._read_baseline: totals.median_out — обязательное поле формата)."""
    data = safe_load_json(baseline_path(project_path), None)
    if not isinstance(data, dict):
        return None
    totals = data.get("totals")
    if not isinstance(totals, dict) or not isinstance(totals.get("median_out"), (int, float)):
        return None
    return {"median_out": totals.get("median_out"), "median_in": totals.get("median_in"),
           "p90_out": totals.get("p90_out"), "note": data.get("note"),
           "generated_at": data.get("generated_at"), "sessions": data.get("sessions")}


# ── статистика (stdlib) ─────────────────────────────────────────────────────────
def rolling_stats(rows):
    """Медиана/p90 out (+медиана in) по набору строк тренда. None при < MIN_BASELINE_N
    строк — сравнивать не с чем, честно не считаем (не подсовываем шумовую статистику
    по 1-2 точкам как настоящий baseline)."""
    if len(rows) < MIN_BASELINE_N:
        return None
    outs = [r.get("out", 0) or 0 for r in rows]
    ins = [r.get("in", 0) or 0 for r in rows]
    return {
        "n": len(rows),
        "median_out": statistics.median(outs),
        "median_in": statistics.median(ins),
        "p90_out": statistics.quantiles(outs, n=10, method="inclusive")[-1],
    }


def is_regression(out_value, stats):
    """out_value > 1.3×median ИЛИ > p90 (ТЗ). False, если стата ещё не набралась
    (stats=None) или медиана нулевая (сравнивать не с чем — не делим на 0)."""
    if not stats or not stats.get("median_out"):
        return False
    return out_value > REGRESSION_MULT * stats["median_out"] or out_value > stats["p90_out"]


# ── срезы ────────────────────────────────────────────────────────────────────────
def slice_by_model(rows):
    """{model: {sessions, in, out}} — партиция строк тренда по `by_model` (реальное поле
    usage-trend.ndjson, пишет run-report._append_trend — партиция in/out по модели внутри
    каждой сессии)."""
    buckets = {}
    for r in rows:
        bm = r.get("by_model")
        if not isinstance(bm, dict):
            continue
        for model, vals in bm.items():
            if not isinstance(vals, dict):
                continue
            b = buckets.setdefault(model, {"sessions": 0, "in": 0, "out": 0})
            b["sessions"] += 1
            b["in"] += vals.get("in", 0) or 0
            b["out"] += vals.get("out", 0) or 0
    return buckets


def slice_by_role(project_path, rows):
    """{label: {sessions, in, out}} — партиция по label агента (usage.agents[].label
    ПОЛНОГО run-report'а, `<project>/.claude/runs/<session>.json`; тренд label не хранит).
    Возвращает (buckets, {sessions_total, sessions_matched}) — matched честно показывает,
    сколько сессий окна реально попали в срез (ретеншн runs/ короче тренда)."""
    buckets = {}
    matched = 0
    for r in rows:
        sid = r.get("session")
        if not sid:
            continue
        rr = find_run_report(project_path, session=sid)
        agents = ((rr or {}).get("usage") or {}).get("agents") or []
        if not agents:
            continue
        matched += 1
        for a in agents:
            if not isinstance(a, dict):
                continue
            label = a.get("label") or "?"
            b = buckets.setdefault(label, {"sessions": 0, "in": 0, "out": 0})
            b["sessions"] += 1
            b["in"] += a.get("in", 0) or 0
            b["out"] += a.get("out", 0) or 0
    return buckets, {"sessions_total": len(rows), "sessions_matched": matched}


def _model_series(rows):
    """{model: {"in": [...], "out": [...]}} — по-сессионные ряды на модель (для baseline-пина:
    медиана/p90 считаются по СПИСКУ значений, не по сумме — см. build_baseline_doc)."""
    series = {}
    for r in rows:
        bm = r.get("by_model")
        if not isinstance(bm, dict):
            continue
        for model, vals in bm.items():
            if not isinstance(vals, dict):
                continue
            s = series.setdefault(model, {"in": [], "out": []})
            s["in"].append(vals.get("in", 0) or 0)
            s["out"].append(vals.get("out", 0) or 0)
    return series


# ── сборка отчёта (чистая — без die) ──────────────────────────────────────────────
def compute_report(project_path, *, sessions=None, by="model", vs_baseline=False):
    """Чистая (без побочных die) сборка отчёта. None — тренда нет вообще (нужно
    отличать «нет проекта/тренда» от «пустой срез» — `--all-projects` продолжает по
    остальным проектам, одиночный `cmd_token_report` превращает None в вежливый die).

    rolling-baseline считается ВСЕГДА по последним `ROLLING_K` строкам тренда (фикс.
    окно, как `_TREND_K` в maind.analyze) — НЕЗАВИСИМО от `sessions` (это окно ОТЧЁТА,
    может быть уже/шире базового: report window ⊆/⊇ baseline window, оба — «последние N»)."""
    all_rows = read_trend(project_path)
    if not all_rows:
        return None
    window_n = sessions or ROLLING_K
    window = all_rows[-window_n:]
    baseline_rows = all_rows[-ROLLING_K:]
    stats = rolling_stats(baseline_rows)

    pinned = read_pinned_baseline(project_path) if vs_baseline else None

    sess_rows = []
    for r in window:
        out = r.get("out", 0) or 0
        row = {"session": r.get("session"), "ts": r.get("ts"),
              "in": r.get("in", 0) or 0, "out": out,
              "regression": is_regression(out, stats)}
        if pinned:
            row["ratio_pinned"] = (out / pinned["median_out"]) if pinned.get("median_out") else None
        sess_rows.append(row)

    role_meta = None
    if by == "role":
        buckets, role_meta = slice_by_role(project_path, window)
    else:  # "model" (единственная другая поддерживаемая опция на этом этапе — phase отсекается выше)
        buckets = slice_by_model(window)

    slice_rows = []
    for key in sorted(buckets):
        b = buckets[key]
        n = b["sessions"] or 1
        avg_out = b["out"] / n
        row = {"key": key, "sessions": b["sessions"], "in": b["in"], "out": b["out"],
              "avg_out": avg_out,
              "ratio_median": (avg_out / stats["median_out"]) if stats and stats.get("median_out") else None,
              "regression": is_regression(avg_out, stats)}
        if pinned:
            row["ratio_pinned"] = (avg_out / pinned["median_out"]) if pinned.get("median_out") else None
        slice_rows.append(row)

    return {
        "project": str(project_path), "by": by,
        "sessions_requested": window_n, "sessions_window": len(window),
        "sessions_total_in_trend": len(all_rows),
        "rolling": stats,
        "sessions": sess_rows,
        "slices": slice_rows,
        "role_meta": role_meta,
        "regression_count": sum(1 for s in sess_rows if s["regression"]),
        "vs_baseline_requested": bool(vs_baseline),
        "pinned_baseline": pinned,
    }


def build_baseline_doc(rows, note):
    """Снимок для `.claude/analyze/baseline.json`. Формат СОВМЕСТИМ с
    `maind.analyze._read_baseline` (`totals.median_out` — обязательное поле контракта,
    НЕ переименовывать без синхронной правки maind); `by_model.<model>.median_out` —
    его fallback-путь, тоже сохранён. None — рядов < MIN_BASELINE_N, пинить нечего."""
    stats = rolling_stats(rows)
    if stats is None:
        return None
    doc = {
        "generated_at": now_iso(),
        "note": note,
        "sessions": stats["n"],
        "totals": {"median_out": stats["median_out"], "median_in": stats["median_in"],
                  "p90_out": stats["p90_out"]},
        "by_model": {},
    }
    for model, s in _model_series(rows).items():
        outs, ins = s["out"], s["in"]
        p90 = (statistics.quantiles(outs, n=10, method="inclusive")[-1]
              if len(outs) >= 2 else float(outs[0]))
        doc["by_model"][model] = {"sessions": len(outs), "median_out": statistics.median(outs),
                                  "median_in": statistics.median(ins), "p90_out": p90}
    return doc


def pin_baseline(project_path, sessions, note):
    """--baseline set --note "..." → .claude/analyze/baseline.json (атомарно, core.io).
    die — тренда нет ИЛИ рядов недостаточно (< MIN_BASELINE_N); в обоих случаях НИЧЕГО
    не пишем (валидация до единственного побочного эффекта)."""
    all_rows = read_trend(project_path)
    if not all_rows:
        die(f"нет тренда токенов: {trend_path(project_path)} — пинить нечего "
            f"(включи хук run-report: harness hooks --target . --run-report on)")
    window_n = sessions or ROLLING_K
    rows = all_rows[-window_n:]
    doc = build_baseline_doc(rows, note)
    if doc is None:
        die(f"недостаточно сессий для baseline: {len(rows)} < {MIN_BASELINE_N} "
            f"— прогони больше сессий, затем повтори --baseline set")
    atomic_write_json(baseline_path(project_path), doc)
    return doc


# ── человекочитаемый вывод ────────────────────────────────────────────────────────
def _fmt_k(n):
    """Компактное 'тысячное' число (48501 → '48k'), как _fmt_tokens_k в maind.analyze —
    единый визуальный язык токен-чисел по репо."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.0f}k" if abs(n) >= 1000 else str(int(n))


def _print_human(rep):
    print(f"\nanalyst token-report — {rep['project']}  ·  срез: {rep['by']}\n")
    print(f"  окно: {rep['sessions_window']}/{rep['sessions_total_in_trend']} сессий "
          f"(запрошено {rep['sessions_requested']})")
    stats = rep["rolling"]
    if stats:
        print(f"  rolling baseline (K={ROLLING_K}, N={stats['n']}): "
              f"медиана out {_fmt_k(stats['median_out'])} · p90 out {_fmt_k(stats['p90_out'])}")
    else:
        print(f"  rolling baseline: недостаточно истории (< {MIN_BASELINE_N} сессий) — "
              "регресс-флаг пока не считается")
    if rep.get("vs_baseline_requested"):
        pinned = rep.get("pinned_baseline")
        if pinned:
            print(f"  pinned baseline:  медиана out {_fmt_k(pinned['median_out'])}"
                  f"  ({pinned.get('note') or '—'} · {pinned.get('generated_at') or '?'})")
        else:
            print("  pinned baseline:  не установлен — "
                  "analyst token-report --baseline set --note \"...\"")
    if rep.get("role_meta"):
        m = rep["role_meta"]
        print(f"  role-срез: {m['sessions_matched']}/{m['sessions_total']} сессий с "
              "сохранившимся run-report'ом (ретеншн .claude/runs короче тренда)")

    if not rep["slices"]:
        print("\n  Пусто — в окне нет данных для среза (сессии есть, но не сматчились).\n")
        return

    print(f"\n  {'срез':<28} {'сессий':>7} {'out (сумма)':>13} {'out (сред.)':>12} "
          f"{'vs медиана':>11}  флаг")
    for row in rep["slices"]:
        ratio = f"{row['ratio_median']:.1f}×" if row.get("ratio_median") is not None else "—"
        flag = "⚠ РЕГРЕСС" if row["regression"] else ""
        print(f"  {row['key']:<28} {row['sessions']:>7} {_fmt_k(row['out']):>13} "
              f"{_fmt_k(row['avg_out']):>12} {ratio:>11}  {flag}")

    print(f"\n  сессий с индивидуальным регрессом (окно): "
          f"{rep['regression_count']}/{rep['sessions_window']}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────────
def _cmd_all_projects(env, sessions, by, vs_baseline, as_json):
    """--all-projects: обход config.json:projects[] (тот же реестр/фильтр, что analyst
    scan — переиспользуем enabled_projects/load_projects, не дублируем). Проект без
    тренда → честная строка «нет тренда», не роняет обход остальных проектов."""
    from .scan import enabled_projects, load_projects

    cfg = env.default_config
    if not Path(cfg).is_file():
        die(f"реестр проектов не найден: {cfg} — --all-projects нужен config.json "
            "(корень монорепо экосистемы)")
    projects = enabled_projects(load_projects(cfg))
    if not projects:
        warn("нет enabled-проектов в реестре")

    results = []
    for pr in projects:
        ppath = os.path.expanduser(pr["local_path"])
        rep = compute_report(ppath, sessions=sessions, by=by, vs_baseline=vs_baseline)
        if rep is None:
            results.append({"project": pr["id"], "path": ppath, "error": "нет тренда токенов"})
            continue
        rep["project_id"] = pr["id"]
        results.append(rep)

    if as_json:
        print(json.dumps({"by": by, "projects": results}, ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst token-report --all-projects — {len(projects)} проект(ов) · срез: {by}\n")
    if not results:
        print("  (нет проектов в реестре)\n")
        return
    for rep in results:
        if rep.get("error"):
            print(f"  · {rep['project']}: {rep['error']}")
            continue
        print(f"── {rep['project_id']} " + "─" * max(2, 50 - len(rep["project_id"])))
        _print_human(rep)
    print()


def cmd_token_report(env, argv):
    """analyst token-report [--sessions N] [--by model|role] [--vs-baseline]
    [--all-projects] [--json]  ·  analyst token-report --baseline set --note "..."
    — токен-репорт по срезам usage-trend.ndjson + двухслойный baseline (rolling K=20 +
    pinned). --by phase недоступен (см. docstring модуля — ESCALATION-REQUIRED)."""
    opts, _ = parse_args(argv, {
        "--sessions": "str", "--by": "str", "--vs-baseline": "bool",
        "--all-projects": "bool", "--json": "bool",
        "--baseline": "str", "--note": "str",
    })
    if opts["help"]:
        print("analyst token-report [--sessions N] [--by model|role] [--vs-baseline] "
              "[--all-projects] [--json]\n"
              "analyst token-report --baseline set --note \"...\"\n"
              "  Токен-репорт по срезам usage-trend.ndjson: rolling-baseline (медиана+p90\n"
              "  последних K=20) + regression-флаг (out > 1.3×медиана ИЛИ > p90).\n"
              "  --vs-baseline добавляет сравнение с pinned .claude/analyze/baseline.json\n"
              "  (его читает и maind analyze). --baseline set пинит текущее окно.\n"
              "  ВНИМАНИЕ: --by phase недоступен — run-report не хранит токены на уровне\n"
              "  workflows[] (только name/status/summary). Доступно: model, role.")
        return

    by = opts["by"] or "model"
    if by not in SUPPORTED_BY:
        die(f"--by ждёт model|role|phase, получено: {by}")
    if by == "phase":
        die("--by phase недоступен: run-report хранит workflows[] БЕЗ токенов (только "
            "name/status/summary) — привязать out/in к фазе нечем текущей схемой run-report "
            "(ESCALATION-REQUIRED — доработка формата хука вне скоупа P4.1). "
            "Доступно: --by model, --by role.")

    sessions = None
    if opts["sessions"]:
        try:
            sessions = int(opts["sessions"])
        except ValueError:
            die(f"--sessions ждёт целое число, получено: {opts['sessions']}")
        if sessions <= 0:
            die("--sessions должен быть положительным")

    if opts["baseline"]:
        if opts["baseline"] != "set":
            die(f"--baseline поддерживает только значение 'set', получено: {opts['baseline']}")
        if opts["all_projects"]:
            die("--baseline set работает для одного проекта (текущий каталог) — "
                "--all-projects не поддерживается")
        note = (opts["note"] or "").strip()
        if not note:
            die('--baseline set требует --note "..." (зачем пин — видно в release-discipline)')
        ppath = os.getcwd()
        doc = pin_baseline(ppath, sessions, note)
        if opts["json"]:
            print(json.dumps({"written": str(baseline_path(ppath)), **doc},
                             ensure_ascii=False, indent=2))
        else:
            print(f"\n✓ baseline закреплён: {baseline_path(ppath)}")
            print(f"  N={doc['sessions']} · медиана out {_fmt_k(doc['totals']['median_out'])} "
                  f"· p90 out {_fmt_k(doc['totals']['p90_out'])}")
            print(f"  note: {doc['note']}\n")
        return

    if opts["all_projects"]:
        _cmd_all_projects(env, sessions, by, opts["vs_baseline"], opts["json"])
        return

    ppath = os.getcwd()
    rep = compute_report(ppath, sessions=sessions, by=by, vs_baseline=opts["vs_baseline"])
    if rep is None:
        die(f"нет тренда токенов: {trend_path(ppath)} — включи хук run-report "
            f"(harness hooks --target . --run-report on) и прогони хотя бы одну сессию")
    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
