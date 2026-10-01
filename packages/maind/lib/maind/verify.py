"""maind verify — proof-of-life of three planes: do they actually write in them or «idle».

Read-only live metering (no guesswork «seems to work»):
  • agent-memory — is the demon alive? how many records, of which seed (auto from onboard) vs real,
    when the last entry. This way you can see whether knowledge is being accumulated or only seeds are lying around.
  • maind-graph - coverage (how much enabled-projects have sides), nodes/ribs, freshness.
  • code graph (Serena) — on which projects it was rolled out `.serena/`, symbol cache freshness.
Plus URL web viewers. The TOTAL column is highlighted «idle»-symptoms. `--json` — machine.

stdlib-only; Env is passed explicitly. Reuses memory.export/health and federation.store_path."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .common import parse_args, parse_iso
from .config import load_config
from .federation import _enabled_projects, store_path
from .memory import export, health, resolve_ports

MEMORY_VIEWER_URL = "http://127.0.0.1:3113"   # built-in viewer agentmemory
SEED_PREFIX = "[maind:"                        # seeds/controlled facts from onboard/seed


def _age(dt):
    """Human readable age datetime (aware) from now: «just now» / «5m» / «3h» / «2d»."""
    if dt is None:
        return "—"
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    if secs < 90:
        return "just now"
    for div, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if secs >= div:
            return f"{int(secs // div)}{unit} back"
    return "just now"


def _mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
    except OSError:
        return None


def classify_memories(mems):
    """Net dump classification: seed (managed onboard) vs real + last entry.
    Without network - dedicated for testability (does live metering memory_report)."""
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
    """Live memory measurement. Demon dump flat (namespace not in record) — take one common one."""
    _http, _stream, url = resolve_ports(env, config)
    up = health(url)
    rep = {"plane": "agent-memory", "url": url, "viewer": MEMORY_VIEWER_URL, "up": up,
           "total": 0, "seed": 0, "real": 0, "last": None}
    if up:
        rep.update(classify_memories(export(url, "global")))  # dump flat → 1 request
    return rep


def graph_report(env, config):
    """Coating maind-column by enabled-projects: who has a store, nodes/ribs, freshness."""
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
    """On which projects was it physically rolled out?serena/ (code graph lives in the project repo)."""
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
    print("\nmAInd verify — proof of work of three planes (read-only)\n")

    print("agent-memory  " + "─" * 48)
    print(f"  daemon:      {'✓ replies' if mem['up'] else '✗ NOT responding (maind start --only memory)'}"
          f"  ({mem['url']})")
    if mem["up"]:
        print(f"  entries:    {mem['total']}  (seed {mem['seed']} · real {mem['real']})")
        print(f"  last:  {(parse_iso(mem['last']) and _age(parse_iso(mem['last']))) or '—'}"
              f"  ({(mem['last'] or '—')[:16].replace('T', ' ')})")
        print(f"  viewer:      {mem['viewer']}")
        if mem["real"] == 0:
            warn.append("memory: only seed-facts onboard — projects do not write real knowledge")

    print("\nmaind-graph  " + "─" * 50)
    print(f"  coverage:   {len(gr['built'])}/{gr['total']} enabled-projects have sides")
    for b in gr["built"]:
        print(f"    ✓ {b['id']:<16} {b['nodes']}y/{b['edges']}p  ({b['age']})")
    if gr["missing"]:
        head = ", ".join(gr["missing"][:6]) + (f" … (+{len(gr['missing']) - 6})"
                                               if len(gr["missing"]) > 6 else "")
        print(f"  NOT built ({len(gr['missing'])}): {head}")
        warn.append(f"graph: not built for {len(gr['missing'])} projects - `maind graph derive --all`")

    print("\ncode graph (Serena)  " + "─" * 43)
    if sr["deployed"]:
        print(f"  rolled out:   {len(sr['deployed'])} projects (.serena/ in the project repo)")
        for s in sr["deployed"]:
            print(f"    ✓ {s['id']:<16} cache {'yes' if s['cache'] else 'no'}  ({s['age']})")
    else:
        print("  rolled out: nowhere (turns on `code:true` + sync)")
    print("  (code graph - per-project; webdashboard Serena by flag in code_graph.args)")

    print("\nRESULT  " + "─" * 56)
    if warn:
        for w in warn:
            print(f"  ⚠ {w}")
    else:
        print("  ✓ all three planes are alive and filling")
    print()


def cmd_verify(env, argv):
    """maind verify [--json] — living proof: do they write to memory/graph/code-graph or idle."""
    if argv and argv[0] in ("-h", "--help"):
        print("maind verify [--json]  — read-only proof of three planes "
              "(memory · maind-graph · code graph): is the demon alive, is it filling, covering.")
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
