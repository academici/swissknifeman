"""Hub agent registry: register/heartbeat/list/kill/reap (~/.maind/agents.json).

State is derived at read time from heartbeat age, configured interval, and PID
liveness. The persisted file therefore contains facts only."""
import json
import os
import signal

from .common import (atomic_write_json, die, load_json_db, now_iso, parse_args,
                     parse_iso, pid_alive)
from .config import load_config
from .constants import AGENT_STALE_FACTOR, HEARTBEAT_DEFAULT_MS

AGENTS_DEFAULT = {"version": 1, "agents": []}


def load(env):
    return load_json_db(env.agents_db, AGENTS_DEFAULT)


def save(env, db):
    atomic_write_json(env.agents_db, db, version=1)


# ── State derivation (shared time/PID primitives from core) ──────────────────
def _age_ms(last, now):
    a, b = parse_iso(last), parse_iso(now)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() * 1000


def _state(agent, now, interval_ms):
    if pid_alive(agent.get("pid")) is False:
        return "dead"
    age = _age_ms(agent.get("last_heartbeat"), now)
    if age is not None and age > interval_ms * AGENT_STALE_FACTOR:
        return "stale"
    return "alive"


def _interval(config):
    return int(((config or {}).get("agents") or {}).get(
        "heartbeat_interval_ms", HEARTBEAT_DEFAULT_MS))


# ── Operations ──────────────────────────────────────────────────────────────
def register(env, agent_id, *, pid=None, project=None, kind="generic", now=None):
    """Upsert an agent by ID; preserve registered_at and refresh heartbeat."""
    now = now or now_iso()
    db = load(env)
    for a in db["agents"]:
        if a["id"] == agent_id:
            a["last_heartbeat"] = now
            if pid is not None:
                a["pid"] = pid
            if project is not None:
                a["project"] = project
            if kind:
                a["kind"] = kind
            save(env, db)
            return a
    rec = {"id": agent_id, "kind": kind, "pid": pid, "project": project,
           "registered_at": now, "last_heartbeat": now}
    db["agents"].append(rec)
    save(env, db)
    return rec


def heartbeat(env, agent_id, now=None):
    now = now or now_iso()
    db = load(env)
    for a in db["agents"]:
        if a["id"] == agent_id:
            a["last_heartbeat"] = now
            save(env, db)
            return a
    die(f"agent not registered: {agent_id} (first maind agents register)")


def listing(env, config, now=None):
    """Return all agents with derived state ∈ {alive, stale, dead}."""
    now = now or now_iso()
    interval = _interval(config)
    out = []
    for a in load(env)["agents"]:
        rec = dict(a)
        rec["state"] = _state(a, now, interval)
        out.append(rec)
    return out


def kill(env, agent_id, *, force=False):
    """Signal a live agent process when present, then remove its registry record."""
    db = load(env)
    for i, a in enumerate(db["agents"]):
        if a["id"] == agent_id:
            pid = a.get("pid")
            if pid:
                sig = signal.SIGKILL if force else signal.SIGTERM
                try:
                    os.kill(int(pid), sig)
                except (ProcessLookupError, PermissionError, OSError, ValueError):
                    pass
            db["agents"].pop(i)
            save(env, db)
            return True
    die(f"agent not found: {agent_id}")


def reap(env, config, now=None):
    """Remove dead and stale agents; return the number removed."""
    now = now or now_iso()
    interval = _interval(config)
    db = load(env)
    before = len(db["agents"])
    db["agents"] = [a for a in db["agents"]
                    if _state(a, now, interval) not in ("dead", "stale")]
    removed = before - len(db["agents"])
    if removed:
        save(env, db)
    return removed


# ── CLI ─────────────────────────────────────────────────────────────────────
def cmd_agents(env, argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("maind agents <list|kill|heartbeat|register> [<id>] "
              "[--all --json --force --pid N --project P --kind K]")
        return
    sub, rest = argv[0], argv[1:]
    handlers = {"list": _cmd_list, "kill": _cmd_kill,
                "heartbeat": _cmd_heartbeat, "register": _cmd_register}
    handler = handlers.get(sub)
    if handler is None:
        die(f"unknown subcommand agents: {sub} (list|kill|heartbeat|register)")
    handler(env, rest)


def _cmd_list(env, argv):
    opts, _ = parse_args(argv, {"--all": "bool", "--json": "bool"})
    config, _src = load_config(env)
    agents = listing(env, config)
    if not opts["all"]:
        agents = [a for a in agents if a["state"] != "dead"]
    if opts["json"]:
        print(json.dumps(agents, ensure_ascii=False, indent=2))
        return
    if not agents:
        print("no agents (register: maind agents register <id>)")
        return
    print(f"Agents ({len(agents)}):")
    for a in agents:
        print(f"  {a['state']:<6} {a['id']:<24} {a.get('kind', '-'):<10} "
              f"proj={a.get('project') or '-':<14} last={a.get('last_heartbeat', '-')}")


def _cmd_kill(env, argv):
    opts, pos = parse_args(argv, {"--force": "bool"}, max_pos=1)
    if not pos:
        die("specify id agent: maind agents kill <id> [--force]")
    kill(env, pos[0], force=opts["force"])
    print(f"agent stopped and removed from the registry: {pos[0]}")


def _cmd_heartbeat(env, argv):
    _opts, pos = parse_args(argv, {}, max_pos=1)
    if not pos:
        die("specify id agent: maind agents heartbeat <id>")
    heartbeat(env, pos[0])
    print(f"heartbeat: {pos[0]}")


def _cmd_register(env, argv):
    opts, pos = parse_args(argv, {"--pid": "str", "--project": "str", "--kind": "str"},
                           max_pos=1)
    if not pos:
        die("specify id agent: maind agents register <id> [--project P --pid N]")
    rec = register(env, pos[0],
                   pid=int(opts["pid"]) if opts["pid"] else None,
                   project=opts["project"] or None,
                   kind=opts["kind"] or "generic")
    print(f"registered: {rec['id']} (scope: project:{rec.get('project') or '-'})")
