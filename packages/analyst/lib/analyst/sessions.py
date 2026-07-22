"""analyst sessions — недельные медианы токен-оверхеда по ЖИВЫМ jsonl-транскриптам
Claude Code (`~/.claude/projects/<encoded-cwd>/<sid>.jsonl`), НЕ по `usage-trend.ndjson`
run-report (тот источник читает `token_report.py` — здесь другой: сырые транскрипты
сессии, доступные даже без включённого хука run-report).

Референс-логика — scratchpad-скрипт `analyze_sessions.py` (сессия 4af788f3, СКРИПТ ВНЕ
РЕПО — сюда перенесена только выжимка алгоритма, findings/P0-rag-context-economy.md):
  - `first_turn_overhead` = input + cache_creation ПЕРВОЙ assistant-записи сессии
    (не сумма по всем — единый источник математики теперь `core.usage.feed_event`,
    см. P5.3 правку `core/usage.py`, дублировать её здесь не нужно);
  - `fresh_per_turn` = (Σinput + Σcache_creation) / turns (`turns` = число
    assistant-событий, `core.usage.finish(...)["msgs"]`);
  - путь транскрипта: `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl`.

Кодирование cwd (ПРОВЕРЕНО чтением живых каталогов `~/.claude/projects/*` этой
машины, не угадано): Claude Code заменяет КАЖДЫЙ `/` абсолютного пути на `-`
(ведущий `/` → ведущий `-` имени каталога) — подтверждено на ~20 живых проектах
разной вложенности. Поведение для литеральных `.`/`_` внутри сегментов пути НЕ
удалось перепроверить на живых каталогах (среди подключённых проектов таких путей
нет) — если `analyst sessions` не находит каталог для проекта с точкой/подчёркиванием
в пути, это ESCALATION-REQUIRED, а не повод менять кодировку наугад (см. Escalation
Needed P5.3 в phases/P5.md).

Недельный ключ — ISO-календарная неделя (`%G-W%V`) первой временной метки сессии
(`ts_min` аккумулятора). `--weeks N` — последние N недель, для которых есть сессии.
Trend-warn (ТЗ): медиана `first_turn_overhead` недели N выросла >20% к неделе N-1 —
простое сравнение медиан, без экзотики (stdlib `statistics`, без pandas/numpy). Сравниваются
только КАЛЕНДАРНО смежные недели (`_is_next_iso_week`) — при пропуске недель (нет сессий)
warn не печатается, чтобы не путать разрыв с рецидивом."""
import json
import os
import statistics
from datetime import date, datetime
from pathlib import Path

from core import usage as core_usage

from .common import HOME, die, parse_args, warn

TREND_WARN_MULT = 1.2   # >20% рост медианы week-over-week (ТЗ)
TOP_ANOMALIES = 5


# ── пути/кодирование cwd ──────────────────────────────────────────────────────────
def encode_cwd(cwd):
    """abs-путь → имя каталога транскриптов (см. докстринг модуля: '/' → '-',
    подтверждено на живых `~/.claude/projects/*`)."""
    p = os.path.abspath(os.path.expanduser(str(cwd)))
    return p.replace(os.sep, "-")


def sessions_dir(cwd, home=None):
    base = Path(home) if home else HOME
    return base / ".claude" / "projects" / encode_cwd(cwd)


def _session_files(cwd, home=None):
    d = sessions_dir(cwd, home=home)
    if not d.is_dir():
        return []
    return sorted(d.glob("*.jsonl"))


# ── метрики одной сессии ──────────────────────────────────────────────────────────
def _week_key(ts):
    """ISO-неделя ('2026-W28') из ISO-таймстемпа; None на мусоре/отсутствии —
    сессия без определённой недели не бакетится (честная деградация)."""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def session_metrics(path):
    """Read-only provider acquisition from a local transcript.

    This source is allowed only as bounded legacy input: it neither normalizes raw bodies
    nor writes `.claude`; absent neutral usage semantics remain absent rather than invented.
    """
    acc = core_usage.new_acc()
    try:
        for ev in core_usage.iter_jsonl(path):
            core_usage.feed_event(acc, ev)
    except Exception:
        return None
    agg = core_usage.finish(acc, label=Path(path).stem)
    if agg["msgs"] == 0:
        return None
    week = _week_key(acc.get("ts_min"))
    if week is None:
        return None
    fresh = (agg["in"] + agg["cache_creation"]) / agg["msgs"]
    return {
        "session": Path(path).stem, "week": week, "ts_min": acc.get("ts_min"),
        "first_turn_overhead": agg["first_turn_overhead"], "turns": agg["msgs"],
        "in": agg["in"], "cache_creation": agg["cache_creation"],
        "cache_read": agg["cache_read"], "out": agg["out"],
        "fresh_per_turn": fresh,
    }


def load_sessions(cwd, home=None):
    """Метрики всех сессий проекта, по возрастанию времени. [] — каталога/сессий нет
    (не ошибка: проект мог не запускаться с этого cwd — честная пустота)."""
    rows = []
    for f in _session_files(cwd, home=home):
        m = session_metrics(f)
        if m is not None:
            rows.append(m)
    rows.sort(key=lambda r: r["ts_min"] or "")
    return rows


# ── недельная агрегация ────────────────────────────────────────────────────────────
def _median(values):
    return statistics.median(values) if values else None


def _is_next_iso_week(prev_week, cur_week):
    """True, если cur_week — КАЛЕНДАРНО следующая ISO-неделя за prev_week (без
    пропусков между ними, не просто соседний индекс в списке присутствующих недель)."""
    py, pw = (int(x) for x in prev_week.split("-W"))
    cy, cw = (int(x) for x in cur_week.split("-W"))
    prev_monday = date.fromisocalendar(py, pw, 1)
    cur_monday = date.fromisocalendar(cy, cw, 1)
    return (cur_monday - prev_monday).days == 7


def weekly_buckets(rows):
    """{week: [session-metrics...]} — группировка по ISO-неделе."""
    buckets = {}
    for r in rows:
        buckets.setdefault(r["week"], []).append(r)
    return buckets


def build_report(cwd, weeks=None, home=None):
    """Чистая сборка отчёта (без die/print). None — сессий вообще нет (нужно отличать
    от «есть сессии, но окно weeks пустое» — тут такого не бывает: weeks режет уже
    непустой список недель)."""
    rows = load_sessions(cwd, home=home)
    if not rows:
        return None
    buckets = weekly_buckets(rows)
    weeks_sorted = sorted(buckets)
    if weeks:
        weeks_sorted = weeks_sorted[-weeks:]

    weekly = []
    for wk in weeks_sorted:
        wrows = buckets[wk]
        overheads = [r["first_turn_overhead"] for r in wrows if r["first_turn_overhead"] is not None]
        fresh = [r["fresh_per_turn"] for r in wrows if r["fresh_per_turn"] is not None]
        weekly.append({
            "week": wk, "sessions": len(wrows),
            "median_first_turn_overhead": _median(overheads),
            "median_fresh_per_turn": _median(fresh),
        })

    warnings = []
    for i in range(1, len(weekly)):
        prev, cur = weekly[i - 1], weekly[i]
        pm, cm = prev["median_first_turn_overhead"], cur["median_first_turn_overhead"]
        if pm and cm and cm > TREND_WARN_MULT * pm and _is_next_iso_week(prev["week"], cur["week"]):
            growth_pct = (cm / pm - 1) * 100
            warnings.append(
                f"{prev['week']}→{cur['week']}: медиана first_turn_overhead выросла "
                f"на {growth_pct:.0f}% ({pm:.0f}→{cm:.0f}) — рецидив контекст-инцидента?")

    window_rows = [r for r in rows if r["week"] in weeks_sorted]
    top_anomalies = sorted(
        window_rows, key=lambda r: r["first_turn_overhead"] or 0, reverse=True
    )[:TOP_ANOMALIES]

    return {
        "cwd": str(cwd), "sessions_dir": str(sessions_dir(cwd, home=home)),
        "weeks_requested": weeks, "weeks": weekly,
        "sessions_total": len(rows), "sessions_window": len(window_rows),
        "trend_warnings": warnings, "top_anomalies": top_anomalies,
    }


# ── человекочитаемый вывод ────────────────────────────────────────────────────────
def _fmt_k(n):
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.1f}k" if abs(n) >= 1000 else str(int(n))


def _print_human(rep):
    print(f"\nanalyst sessions — {rep['cwd']}")
    print(f"  каталог транскриптов: {rep['sessions_dir']}")
    print(f"  сессий всего: {rep['sessions_total']} · в окне: {rep['sessions_window']}\n")
    if not rep["weeks"]:
        print("  Пусто — нет недель в окне.\n")
        return
    print(f"  {'неделя':<10} {'сессий':>7} {'медиана first_turn_overhead':>28} "
          f"{'медиана fresh/turn':>19}")
    for w in rep["weeks"]:
        print(f"  {w['week']:<10} {w['sessions']:>7} "
              f"{_fmt_k(w['median_first_turn_overhead']):>28} "
              f"{_fmt_k(w['median_fresh_per_turn']):>19}")
    if rep["top_anomalies"]:
        print("\n  топ-аномалии (макс. first_turn_overhead в окне):")
        for r in rep["top_anomalies"]:
            print(f"    · {r['session']} ({r['week']}): {_fmt_k(r['first_turn_overhead'])}")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────────
def _project_path(env, opts):
    """--project ID → local_path из реестра config.json (тот же паттерн, что
    `token_report._cmd_all_projects`/`scan.enabled_projects` — не дублируем резолв).
    Без --project — текущий каталог (как весь остальной P1 analyst)."""
    pid = opts.get("project")
    if not pid:
        return os.getcwd()
    from .scan import enabled_projects, load_projects

    cfg = env.default_config
    if not Path(cfg).is_file():
        die(f"реестр проектов не найден: {cfg} — --project нужен config.json "
            "(корень монорепо экосистемы)")
    projects = enabled_projects(load_projects(cfg))
    match = next((p for p in projects if p["id"] == pid), None)
    if match is None:
        die(f"проект '{pid}' не найден в enabled-реестре: {cfg}")
    return os.path.expanduser(match["local_path"])


def cmd_sessions(env, argv):
    """analyst sessions [--project P] [--weeks N] [--json] — недельные медианы
    first_turn_overhead/fresh-per-turn из живых jsonl-транскриптов сессий
    (`~/.claude/projects/<encoded-cwd>/*.jsonl`) + trend-warn week-over-week >20%
    роста медианы first_turn_overhead."""
    opts, _ = parse_args(argv, {"--project": "str", "--weeks": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst sessions [--project P] [--weeks N] [--json]\n"
              "  Недельные медианы first_turn_overhead/fresh-per-turn из живых\n"
              "  jsonl-транскриптов сессий (~/.claude/projects/<encoded-cwd>/*.jsonl).\n"
              "  --project P — резолв local_path по id из config.json (реестр узла);\n"
              "  без --project — текущий каталог.\n"
              "  Warn в stderr, если медиана first_turn_overhead недели выросла >20%\n"
              "  к предыдущей неделе (рецидив-сигнал контекст-инцидента).")
        return

    weeks = None
    if opts["weeks"]:
        try:
            weeks = int(opts["weeks"])
        except ValueError:
            die(f"--weeks ждёт целое число, получено: {opts['weeks']}")
        if weeks <= 0:
            die("--weeks должен быть положительным")

    cwd = _project_path(env, opts)
    rep = build_report(cwd, weeks=weeks)
    if rep is None:
        die(f"нет сессий: {sessions_dir(cwd)} — нет jsonl-транскриптов для этого cwd "
            "(проект не запускался отсюда, либо кодировка каталога отличается — см. "
            "докстринг analyst/sessions.py)")

    if opts["json"]:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
    for w in rep["trend_warnings"]:
        warn(w)
