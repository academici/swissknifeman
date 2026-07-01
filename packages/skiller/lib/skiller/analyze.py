"""analyze-run — детерминированный пост-ран разбор прогона по JSONL-транскриптам.

Реальные токены/тайминги/cache-hit по агентам + эффективные/мёртвые скиллы —
из логов Claude Code (`~/.claude/projects/<slug>/…`). stdlib-only, не жжёт токены.

Дополняет качественный скилл `system/session-observer` (тот — про «почему/дрейф»
через агента; этот — про ЦИФРЫ детерминированно). Использует поле `usage`
(input/output/cache_read), которое остальной тулинг не трогает.

Честное ограничение: загрузка скилла детектится ТОЛЬКО по явным `Skill`-tool-
вызовам; нативный `skills:`-preload субагента и авто-триггер плагина по description
как Skill-вызов НЕ видны → «DEAD» эвристичен (помечаем в выводе).
"""
import json
import os
from datetime import datetime
from pathlib import Path

from .common import die, parse_flags


# --- path-резолв логов (как в system/session-observer) ------------------------
def project_slug(project_path):
    """Каталог логов проекта = абсолютный путь с '/'→'-' (leading '/' → '-')."""
    return str(Path(project_path).resolve()).replace("/", "-")


def logs_root(env, project_path):
    return env.home / ".claude" / "projects" / project_slug(project_path)


def find_session_logs(env, project_path, session=None):
    """(main_jsonl, [subagent_jsonl], session_id, logs_root). session=None → последний.
    main-транскрипты лежат прямо в каталоге логов; сабагенты — в <session>/subagents/."""
    root = logs_root(env, project_path)
    if not root.is_dir():
        return None, [], None, root
    mains = sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if session:
        cand = root / f"{session}.jsonl"
        main = cand if cand.is_file() else None
        sid = session
    else:
        main = mains[0] if mains else None
        sid = main.stem if main else None
    subs = []
    if sid:
        subs = sorted((root / sid / "subagents").glob("agent-*.jsonl"))
    return main, subs, sid, root


# --- парсинг ------------------------------------------------------------------
def parse_transcript(path):
    """Толерантный JSONL-парсер: пропускает битые/пустые строки, возвращает [dict]."""
    events = []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return events
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(o, dict):
            events.append(o)
    return events


def _iter_content(msg):
    c = msg.get("content") if isinstance(msg, dict) else None
    return c if isinstance(c, list) else []


def skill_key(name):
    """Нормализация имени скилла к последнему сегменту:
    general/verify-claims → verify-claims; skm:verify-claims → verify-claims."""
    s = str(name)
    for sep in (":", "/"):
        if sep in s:
            s = s.split(sep)[-1]
    return s.strip()


# --- агрегация по одному агенту (один транскрипт) -----------------------------
def agent_stats(events, label):
    st = {
        "agent": label, "model": None,
        "in": 0, "out": 0, "cache_read": 0, "cache_creation": 0,
        "iterations": 0, "assistant_msgs": 0, "tool_errors": 0,
        "tools": {}, "stop_reasons": {}, "skills": {},
        "ts_min": None, "ts_max": None,
    }
    for o in events:
        ts = o.get("timestamp")
        if isinstance(ts, str):
            if st["ts_min"] is None or ts < st["ts_min"]:
                st["ts_min"] = ts
            if st["ts_max"] is None or ts > st["ts_max"]:
                st["ts_max"] = ts
        m = o.get("message")
        if not isinstance(m, dict):
            continue
        if o.get("type") == "assistant":
            st["assistant_msgs"] += 1
            if m.get("model"):
                st["model"] = m["model"]
            u = m.get("usage")
            if isinstance(u, dict):
                st["in"] += u.get("input_tokens") or 0
                st["out"] += u.get("output_tokens") or 0
                st["cache_read"] += u.get("cache_read_input_tokens") or 0
                st["cache_creation"] += u.get("cache_creation_input_tokens") or 0
                it = u.get("iterations")
                if isinstance(it, int):
                    st["iterations"] += it
            sr = m.get("stop_reason")
            if sr:
                st["stop_reasons"][sr] = st["stop_reasons"].get(sr, 0) + 1
            for b in _iter_content(m):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name = b.get("name", "?")
                    st["tools"][name] = st["tools"].get(name, 0) + 1
                    if name == "Skill":
                        inp = b.get("input") or {}
                        sk = inp.get("skill") or inp.get("command")
                        if sk:
                            k = skill_key(sk)
                            st["skills"][k] = st["skills"].get(k, 0) + 1
        elif o.get("type") == "user":
            for b in _iter_content(m):
                if isinstance(b, dict) and b.get("is_error"):
                    st["tool_errors"] += 1
    return st


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def wall_seconds(ts_min, ts_max):
    a, b = _dt(ts_min), _dt(ts_max)
    if a and b:
        return max(0.0, (b - a).total_seconds())
    return 0.0


def cache_hit(st):
    """Доля прочитанного из кэша от всего обработанного входа."""
    denom = st["in"] + st["cache_read"] + st["cache_creation"]
    return (st["cache_read"] / denom) if denom else 0.0


# --- скилл-usage: активный набор × реально загруженные ------------------------
def skill_usage(agents, active_names):
    """active_names: множество нормализованных имён активных скиллов проекта.
    → {loaded:{name:count}, effective:[...], dead:[...], loaded_outside:[...]}.
    dead = активные, ни разу не загруженные (кандидат снять/чинить триггеры)."""
    loaded = {}
    for a in agents:
        for k, c in a["skills"].items():
            loaded[k] = loaded.get(k, 0) + c
    active = set(active_names)
    effective = sorted(k for k in loaded if k in active)
    dead = sorted(active - set(loaded))
    loaded_outside = sorted(k for k in loaded if k not in active)
    return {"loaded": loaded, "effective": effective, "dead": dead,
            "loaded_outside": loaded_outside}


# --- скан маркеров прогона (эвристика: рантайм-отказы) -------------------------
# Только фразы, которые редко встречаются в авторском тексте — иначе ловим
# упоминания в самом коде/промпте задачи. Всё равно эвристика (см. caveat в рендере).
MARKERS = ("Rate limited", "Server is temporarily limiting",
           "StructuredOutput retry cap", "SingletonLock", "API Error")


def scan_markers(paths, cap=6):
    """Контекст вокруг маркеров рантайм-отказов (не дамп всей JSON-строки)."""
    counts, samples, seen = {}, [], set()
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            for mk in MARKERS:
                idx = line.find(mk)
                if idx != -1:
                    counts[mk] = counts.get(mk, 0) + 1
                    ctx = line[max(0, idx - 30):idx + len(mk) + 50].strip()
                    if ctx not in seen and len(samples) < cap:
                        seen.add(ctx)
                        samples.append(ctx)
                    break
    return {"counts": counts, "sample": samples}


def _first_user_text(events):
    """Первая строка первого user-текста агента — как человекочитаемая метка задачи."""
    def _first_line(txt):
        for ln in (txt or "").strip().splitlines():
            ln = ln.strip()
            if ln:
                return ln[:44]
        return None

    for e in events:
        if e.get("type") != "user":
            continue
        m = e.get("message") or {}
        c = m.get("content")
        if isinstance(c, str):                       # content как строка
            got = _first_line(c)
            if got:
                return got
        for b in _iter_content(m):                   # content как список блоков
            if isinstance(b, dict) and b.get("type") == "text":
                got = _first_line(b.get("text"))
                if got:
                    return got
    return None


# --- сборка отчёта ------------------------------------------------------------
def _active_skill_names(env, project_path):
    """Нормализованные имена активных скиллов проекта (best-effort; [] при ошибке)."""
    try:
        from .budget import budget_for_set, resolve_active_set
        from .config import load_config
        config = load_config(env, Path(project_path))
        skills, meta = resolve_active_set(env, Path(project_path), config)
        b = budget_for_set(skills, meta.get("pulled"))
        return {skill_key(i["name"]) for i in b["items"]}, None
    except SystemExit as e:
        return set(), f"active-set недоступен (die: {e})"
    except Exception as e:  # noqa: BLE001 — бюджет/реестр не должен ронять анализ
        return set(), f"active-set недоступен ({e})"


def build_report(env, project_path, session=None):
    main, subs, sid, root = find_session_logs(env, project_path, session)
    if main is None and not subs:
        return None, f"логи прогона не найдены в {root} (проект {project_path})"

    agents = []
    all_paths = []
    if main is not None:
        all_paths.append(main)
        agents.append(agent_stats(parse_transcript(main), f"main:{sid}"))
    for sp in subs:
        all_paths.append(sp)
        evs = parse_transcript(sp)
        label = _first_user_text(evs) or sp.stem.replace("agent-", "")[:12]
        agents.append(agent_stats(evs, label))

    totals = {"in": 0, "out": 0, "cache_read": 0, "cache_creation": 0}
    for a in agents:
        for k in totals:
            totals[k] += a[k]
    active_names, active_note = _active_skill_names(env, project_path)
    usage = skill_usage(agents, active_names)
    markers = scan_markers(all_paths)
    wall = wall_seconds(
        min((a["ts_min"] for a in agents if a["ts_min"]), default=None),
        max((a["ts_max"] for a in agents if a["ts_max"]), default=None))

    return {
        "session": sid, "project": str(project_path), "logs_root": str(root),
        "agents": agents, "totals": totals, "wall_seconds": wall,
        "skills": usage, "active_note": active_note, "markers": markers,
    }, None


# --- рендер -------------------------------------------------------------------
def _k(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(int(n))


def _dur(sec):
    if sec >= 3600:
        return f"{sec / 3600:.1f}h"
    if sec >= 60:
        return f"{sec / 60:.0f}m"
    return f"{sec:.0f}s"


def _short_model(m):
    if not m:
        return "?"
    m = m.replace("claude-", "")
    for tier in ("haiku", "sonnet", "opus", "fable"):
        if tier in m:
            return tier
    return m.split("-")[0]


def render_report(r):
    out = []
    t = r["totals"]
    denom = t["in"] + t["cache_read"] + t["cache_creation"]
    hit = (t["cache_read"] / denom * 100) if denom else 0.0
    models = {}
    for a in r["agents"]:
        models[_short_model(a["model"])] = models.get(_short_model(a["model"]), 0) + 1
    out.append("")
    out.append("━━━ ПОСТ-РАН РАЗБОР ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append(f"run:     {r['session']}   агентов {len(r['agents'])}   "
               f"wall ~{_dur(r['wall_seconds'])}")
    out.append(f"tokens:  in {_k(t['in'])} · out {_k(t['out'])} · "
               f"cache-read {_k(t['cache_read'])} (hit {hit:.0f}%)")
    out.append(f"модели:  " + " ".join(f"{k}×{v}" for k, v in sorted(models.items())))

    out.append("")
    out.append("─── Агенты (токены in/out · cache · инструменты) ───────")
    for a in sorted(r["agents"], key=lambda x: x["out"] + x["in"], reverse=True):
        ch = cache_hit(a) * 100
        tools = ", ".join(f"{k}×{v}" for k, v in
                          sorted(a["tools"].items(), key=lambda i: -i[1])[:4]) or "-"
        err = f" · {a['tool_errors']} tool-err" if a["tool_errors"] else ""
        out.append(f"  {a['agent'][:44]:<44} {_short_model(a['model']):<6} "
                   f"{_k(a['in'])}/{_k(a['out'])}  cache {ch:.0f}%  "
                   f"~{_dur(wall_seconds(a['ts_min'], a['ts_max']))}{err}")
        if tools != "-":
            out.append(f"      tools: {tools}")

    sk = r["skills"]
    out.append("")
    out.append("─── Скиллы (детект частичный: только Skill-tool) ───────")
    if sk["effective"]:
        out.append("  эффективные (загружены): "
                   + ", ".join(f"{k}×{sk['loaded'][k]}" for k in sk["effective"]))
    if sk["loaded_outside"]:
        out.append("  загружены вне активного набора: "
                   + ", ".join(sk["loaded_outside"]))
    if sk["dead"]:
        out.append("  DEAD (в наборе, 0 загрузок → чинить триггеры/снять): "
                   + ", ".join(sk["dead"]))
    if not (sk["effective"] or sk["dead"] or sk["loaded_outside"]):
        out.append("  (Skill-вызовов не найдено; активный набор — см. skiller budget)")
    if r["active_note"]:
        out.append(f"  ⚠ {r['active_note']} — «DEAD» не вычислен")

    mk = r["markers"]
    if mk["counts"]:
        out.append("")
        out.append("─── Рантайм-отказы (эвристика: возможны упоминания в тексте) ─")
        out.append("  " + " · ".join(f"{k}×{v}" for k, v in mk["counts"].items()))
        for s in mk["sample"][:5]:
            out.append(f"    | {s}")
    out.append("")
    return "\n".join(out)


# --- CLI ----------------------------------------------------------------------
def cmd_analyze_run(env, argv):
    opts = parse_flags(argv, {
        "--session": "str", "--last": "bool", "--project": "str",
        "--json": "bool", "--store": "bool"})
    if opts["help"]:
        print("skiller analyze-run [--last | --session ID] [--project DIR] "
              "[--json] [--store]")
        print("  Пост-ран разбор прогона по JSONL-логам: токены/тайминги/cache-hit")
        print("  по агентам + эффективные/мёртвые скиллы. --store → JSON в "
              ".claude/analyze/.")
        return

    if opts.get("project"):
        project = Path(os.path.expanduser(opts["project"])).resolve()
    else:
        from .config import find_project_root
        project, _via = find_project_root(env)
        if project is None:
            project = Path.cwd()

    session = opts.get("session") or None
    report, err = build_report(env, project, session)
    if err:
        die(err)

    if opts.get("store"):
        d = Path(project) / ".claude" / "analyze"
        d.mkdir(parents=True, exist_ok=True)
        fp = d / f"{report['session'] or 'run'}.json"
        fp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        if not opts.get("json"):
            print(f"Сохранено: {fp}  (задел под кросс-сессионный тренд / maind)")

    if opts.get("json"):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_report(report))
