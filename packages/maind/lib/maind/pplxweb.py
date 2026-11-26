"""Resolve policy for the hub-managed perplexity-web MCP server.

`mcp.perplexity_web` is the single source of truth for deployment, overrides,
pool selection, and the executable launcher path.
The external Node package is launched by the MCP client, so this module remains
stdlib-only."""
from .constants import PERPLEXITY_WEB_DEFAULTS


def settings(config):
    """Merge mcp.perplexity_web over PERPLEXITY_WEB_DEFAULTS."""
    raw = (config.get("mcp") or {}).get("perplexity_web") or {}
    st = dict(PERPLEXITY_WEB_DEFAULTS)
    st.update(raw)
    return st


def server_name(st):
    return st.get("server_name") or "perplexity-web"


def enabled(project, st):
    """Use the per-project perplexity_web override before global enabled."""
    override = project.get("perplexity_web")
    if override is not None:
        return bool(override)
    return bool(st.get("enabled", False))


def resolve_pool(project, st):
    """Resolve the project browser pool: override, configured model, or literal."""
    override = project.get("perplexity_web_pool")
    if override:
        return str(override)
    model = st.get("pool") or "default"
    if model == "per-project":
        return project.get("id") or "default"
    if model == "per-namespace":
        ns = next(iter(project.get("namespaces") or []), None)
        return f"ns-{ns}" if ns else "default"
    return model  # Literal pool name, for example "default".


def entry(project, st):
    """Build an MCP entry with an executable command and --pool.

    MCP clients spawn the command directly; they do not run a shell to expand
    ``${VAR:-default}``.  ``bin`` is therefore the resolved, machine-local
    launcher path supplied by the hub configuration.
    """
    pool = resolve_pool(project, st)
    bin_path = st.get("bin") or ""
    return {"command": bin_path, "args": [f"--pool={pool}"]}
