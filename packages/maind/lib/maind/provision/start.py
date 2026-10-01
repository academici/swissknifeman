"""Hub orchestration: maind start workers and maind status summary."""
import json

from ..agents import listing as agents_listing
from ..common import die, parse_args
from ..config import load_config
from ..memory import start as memory_start
from ..memory import status as memory_status
from ..projects import listing as projects_listing
from .workspace import audit as workspace_audit


def cmd_start(env, argv):
    opts, _ = parse_args(argv, {"--only": "str"})
    only = (opts["only"] or "").lower()
    if only and only not in ("memory", "graph"):
        die(f"--only: pending memory|graph (received: '{only}')")
    config, source = load_config(env)

    if only in ("", "memory"):
        memory_start(env, config)
    if only in ("", "graph"):
        # Graph startup derives links from sources of truth and materializes the federation.
        from ..federation import Federation, graph_disabled
        if graph_disabled(config):
            print("graph disabled (graph.adapter = disabled)")
        else:
            from ..derive import derive_all
            derive_all(env, config)
            s = Federation(env, config).stats()
            print(f"graph ready (federation): {s['nodes']} nodes, {s['edges']} ribs, "
                  f"{s.get('cross_edges', 0)} cross-project")
    if only == "":
        print(f"config: {source}")


def cmd_status(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, source = load_config(env)
    mem = memory_status(env, config)
    adapter = config["graph"]["adapter"]
    if adapter == "disabled":
        gstats = {"nodes": 0, "edges": 0}
    else:
        from ..federation import Federation
        gstats = Federation(env, config).stats()
    agents = agents_listing(env, config)
    alive = sum(1 for a in agents if a["state"] == "alive")
    projects = projects_listing(env, config)
    configured = sum(1 for p in projects if p.get("deployed"))
    wa = workspace_audit(env, config)

    snapshot = {
        "config_source": source,
        "node": config.get("node", {}),
        "memory": {"running": mem["running"], "url": mem["url"],
                   "pid": mem["pid"], "stream_port": mem["stream_port"]},
        "graph": {"adapter": adapter, "nodes": gstats["nodes"],
                  "edges": gstats["edges"]},
        "agents": {"total": len(agents), "alive": alive},
        "projects": {"total": len(projects), "configured": configured},
        "workspace": {"trusted": len(wa["covered"]),
                      "registry": wa["registry_count"], "settings": wa["settings"]},
    }
    if opts["json"]:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return

    node = config.get("node", {})
    name = node.get("name") or node.get("id") or "—"
    print(f"mAInd — node «{name}» (config: {source})")
    print(f"  memory:   {'started' if mem['running'] else 'stopped'} — "
          f"{mem['url']}" + (f" (pid {mem['pid']})" if mem["pid"] else ""))
    print(f"  graph:     {adapter} — {gstats['nodes']} nodes, {gstats['edges']} ribs")
    print(f"  agents:   {alive} alive / {len(agents)} total")
    print(f"  projects:  {len(projects)} (connected: {configured})")
    print(f"  trust:  {len(wa['covered'])}/{wa['registry_count']} projects "
          f"(.claude/settings.local.json)")
