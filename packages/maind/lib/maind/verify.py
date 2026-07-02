"""maind verify — пруф-оф-лайф трёх плоскостей: пишут ли в них реально или «вхолостую».

Read-only живой замер (без догадок «вроде работает»):
  • agent-memory — демон жив? сколько записей, из них seed (авто от onboard) vs реальные,
    когда последняя запись. Так видно, накапливаются ли знания или лежат только сиды.
  • maind-граф — покрытие (сколько enabled-проектов имеют стор), узлы/рёбра, свежесть.
  • код-граф (Serena) — на каких проектах раскатан `.serena/`, свежесть кэша символов.
Плюс URL веб-вьюеров. Колонка ИТОГ подсвечивает «вхолостую»-симптомы. `--json` — машинно.

stdlib-only; Env передаётся явно. Переиспользует memory.export/health и federation.store_path."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .common import parse_args, parse_iso
from .config import load_config
from .federation import _enabled_projects, store_path
from .memory import export, health, resolve_ports

MEMORY_VIEWER_URL = "http://127.0.0.1:3113"   # встроенный вьюер agentmemory
SEED_PREFIX = "[maind:"                        # сиды/управляемые факты от onboard/seed


def _age(dt):
    """Человекочитаемый возраст datetime (aware) от now: «только что» / «5м» / «3ч» / «2д»."""
    if dt is None:
        return "—"
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    if secs < 90:
        return "только что"
    for div, unit in ((86400, "д"), (3600, "ч"), (60, "м")):
        if secs >= div:
            return f"{int(secs // div)}{unit} назад"
    return "только что"


def _mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    except OSError:
        return None


def classify_memories(mems):
    """Чистая классификация дампа: seed (управляемые onboard) vs реальные + последняя запись.
    Без сети — выделено для тестируемости (живой замер делает memory_report)."""
    seed = real = 0
    times = []
    for m in mems:
        if (m.get("content", "") or "").startswith(SEED_PREFIX):
            seed += 1
        else:
            real += 1
        ts = parse_iso(m.get("createdAt") or m.get("updatedAt"))
        if ts:
            times.append(ts)
    return {"total": len(mems), "seed": seed, "real": real,
            "last": max(times).isoformat() if times else None}


def memory_report(env, config):
    """Живой замер памяти. Дамп демона плоский (namespace в записи нет) — берём один общий."""
    _http, _stream, url = resolve_ports(env, config)
    up = health(url)
    rep = {"plane": "agent-memory", "url": url, "viewer": MEMORY_VIEWER_URL, "up": up,
           "total": 0, "seed": 0, "real": 0, "last": None}
    if up:
        rep.update(classify_memories(export(url, "global")))  # дамп плоский → 1 запрос
    return rep


def graph_report(env, config):
    """Покрытие maind-графа по enabled-проектам: у кого есть стор, узлы/рёбра, свежесть."""
    projects = _enabled_projects(config)
    built, missing = [], []
    for p in projects:
        sp = Path(store_path(env, config, p))
        if not sp.exists():
            missing.append(p["id"])
            continue
        try:
            d = json.loads(sp.read_text())
            nodes, edges = len(d.get("nodes", [])), len(d.get("edges", d.get("links", [])))
        except (json.JSONDecodeError, OSError):
            nodes = edges = -1
        mt = _mtime(sp)
        built.append({"id": p["id"], "nodes": nodes, "edges": edges,
                      "age": _age(mt), "mtime": mt.isoformat() if mt else None})
    return {"plane": "maind-graph", "total": len(projects),
            "built": built, "missing": missing}


def serena_report(config):
    """На каких проектах физически раскатан .serena/ (код-граф живёт в репо проекта)."""
    out = []
    for p in _enabled_projects(config):
        lp = p.get("local_path")
        if not lp:
            continue
        sdir = Path(os.path.expanduser(lp)) / ".serena"
        if not sdir.is_dir():
            continue
        cache = sdir / "cache"
        mt = _mtime(cache if cache.is_dir() else sdir)
        out.append({"id": p["id"], "cache": cache.is_dir(),
                    "age": _age(mt), "mtime": mt.isoformat() if mt else None})
    return {"plane": "code-graph", "deployed": out}


def _print_human(mem, gr, sr):
    warn = []
    print("\nmAInd verify — пруф работы трёх плоскостей (read-only)\n")

    print("agent-memory  " + "─" * 48)
    print(f"  демон:      {'✓ отвечает' if mem['up'] else '✗ НЕ отвечает (maind start --only memory)'}"
          f"  ({mem['url']})")
    if mem["up"]:
        print(f"  записей:    {mem['total']}  (seed {mem['seed']} · реальных {mem['real']})")
        print(f"  последняя:  {(parse_iso(mem['last']) and _age(parse_iso(mem['last']))) or '—'}"
              f"  ({(mem['last'] or '—')[:16].replace('T', ' ')})")
        print(f"  вьюер:      {mem['viewer']}")
        if mem["real"] == 0:
            warn.append("память: только seed-факты onboard — проекты не пишут реальных знаний")

    print("\nmaind-граф  " + "─" * 50)
    print(f"  покрытие:   {len(gr['built'])}/{gr['total']} enabled-проектов имеют стор")
    for b in gr["built"]:
        print(f"    ✓ {b['id']:<16} {b['nodes']}у/{b['edges']}р  ({b['age']})")
    if gr["missing"]:
        head = ", ".join(gr["missing"][:6]) + (f" … (+{len(gr['missing']) - 6})"
                                               if len(gr["missing"]) > 6 else "")
        print(f"  НЕ построены ({len(gr['missing'])}): {head}")
        warn.append(f"граф: не построен для {len(gr['missing'])} проектов — `maind graph derive --all`")

    print("\nкод-граф (Serena)  " + "─" * 43)
    if sr["deployed"]:
        print(f"  раскатан:   {len(sr['deployed'])} проектов (.serena/ в репо проекта)")
        for s in sr["deployed"]:
            print(f"    ✓ {s['id']:<16} кэш {'есть' if s['cache'] else 'нет'}  ({s['age']})")
    else:
        print("  раскатан:   нигде (включается `code:true` + sync)")
    print("  (граф кода — per-project; веб-dashboard Serena по флагу в code_graph.args)")

    print("\nИТОГ  " + "─" * 56)
    if warn:
        for w in warn:
            print(f"  ⚠ {w}")
    else:
        print("  ✓ все три плоскости живы и наполняются")
    print()


def cmd_verify(env, argv):
    """maind verify [--json] — живой пруф: пишут ли в память/граф/код-граф или вхолостую."""
    if argv and argv[0] in ("-h", "--help"):
        print("maind verify [--json]  — read-only пруф трёх плоскостей "
              "(память · maind-граф · код-граф): жив ли демон, наполняется ли, покрытие.")
        return
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, _src = load_config(env)
    mem = memory_report(env, config)
    gr = graph_report(env, config)
    sr = serena_report(config)
    if opts["json"]:
        print(json.dumps({"memory": mem, "graph": gr, "code_graph": sr},
                         ensure_ascii=False, indent=2))
        return
    _print_human(mem, gr, sr)
