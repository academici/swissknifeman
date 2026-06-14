"""Оркестрация узла: maind start (воркеры) + maind status (сводка)."""
import json

from .agents import listing as agents_listing
from .common import die, parse_args
from .config import load_config
from .graph import open_graph, seed_from_config
from .memory import start as memory_start
from .memory import status as memory_status
from .projects import listing as projects_listing


def cmd_start(env, argv):
    opts, _ = parse_args(argv, {"--only": "str"})
    only = (opts["only"] or "").lower()
    if only and only not in ("memory", "graph"):
        die(f"--only: ожидается memory|graph (получено: '{only}')")
    config, source = load_config(env)

    if only in ("", "memory"):
        memory_start(env, config)
    if only in ("", "graph"):
        # граф — файл; «запуск» = загрузить + засеять проекты/связи из конфига.
        g = open_graph(env, config)
        seed_from_config(g, config)
        g.save()
        s = g.stats()
        print(f"граф готов: {g.db_path} ({s['nodes']} узлов, {s['edges']} рёбер)")
    if only == "":
        print(f"конфиг: {source}")


def cmd_status(env, argv):
    opts, _ = parse_args(argv, {"--json": "bool"})
    config, source = load_config(env)
    mem = memory_status(env, config)
    adapter = config["graph"]["adapter"]
    gstats = open_graph(env, config).stats() if adapter != "disabled" \
        else {"nodes": 0, "edges": 0}
    agents = agents_listing(env, config)
    alive = sum(1 for a in agents if a["state"] == "alive")
    projects = projects_listing(env, config)

    snapshot = {
        "config_source": source,
        "node": config.get("node", {}),
        "memory": {"running": mem["running"], "url": mem["url"],
                   "pid": mem["pid"], "stream_port": mem["stream_port"]},
        "graph": {"adapter": adapter, "nodes": gstats["nodes"],
                  "edges": gstats["edges"]},
        "agents": {"total": len(agents), "alive": alive},
        "projects": {"total": len(projects)},
    }
    if opts["json"]:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return

    node = config.get("node", {})
    name = node.get("name") or node.get("id") or "—"
    print(f"mAInd — узел «{name}» (конфиг: {source})")
    print(f"  память:   {'запущена' if mem['running'] else 'остановлена'} — "
          f"{mem['url']}" + (f" (pid {mem['pid']})" if mem["pid"] else ""))
    print(f"  граф:     {adapter} — {gstats['nodes']} узлов, {gstats['edges']} рёбер")
    print(f"  агенты:   {alive} живых / {len(agents)} всего")
    print(f"  проекты:  {len(projects)}")
