"""Project connections read from the graph (topology lives in config/graph, never in memory)."""


def linked_projects(env, config, project):
    """Related projects from the project graph (neighbors project:<id> → others project:*)."""
    from .federation import project_graph, store_path
    from pathlib import Path
    if not Path(store_path(env, config, project)).exists():
        return []
    g = project_graph(env, config, project)
    pid = project["id"]
    out = []
    for n in g.neighbors(f"project:{pid}", depth=1, direction="out"):
        if n["id"].startswith("project:"):
            other = n["id"].split(":", 1)[1]
            if other != pid and other not in out:
                out.append(other)
    return sorted(out)
