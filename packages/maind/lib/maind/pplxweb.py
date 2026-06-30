"""maind perplexity-web — резолвер политики hub-managed MCP-сервера perplexity-web.

perplexity-web (keyless-мост через браузерный профиль, отдельный Node-пакет) раздаётся в
проекты единым источником истины — секцией `mcp.perplexity_web` конфига, а не вписывается
вручную хардкод-путём в каждый .mcp.json (как было: swissknifeman/edufy/botkit). Здесь —
только резолвер: enabled (с per-project override), модель пулов и сборка MCP-entry.

Пул = демон + профиль + окно браузера (см. README пакета): один общий пул переиспользует
текущий логин, изолированный пул требует своего логина. Команда обёрнута индирекцией
`${PERPLEXITY_WEB_MCP_BIN:-<bin>}` — переносимо, без захардкоженного /home/... в .mcp.json.
stdlib-only; внешний пакет — через свой start.sh (subprocess на стороне клиента MCP)."""
from .constants import PERPLEXITY_WEB_DEFAULTS


def settings(config):
    """Слитая политика perplexity-web: mcp.perplexity_web поверх PERPLEXITY_WEB_DEFAULTS."""
    raw = (config.get("mcp") or {}).get("perplexity_web") or {}
    st = dict(PERPLEXITY_WEB_DEFAULTS)
    st.update(raw)
    return st


def server_name(st):
    return st.get("server_name") or "perplexity-web"


def enabled(project, st):
    """Включён ли perplexity-web для проекта: per-project override `perplexity_web`
    (true|false) имеет приоритет над глобальным `enabled`."""
    override = project.get("perplexity_web")
    if override is not None:
        return bool(override)
    return bool(st.get("enabled", False))


def resolve_pool(project, st):
    """Имя пула браузера для проекта. Приоритет: per-project `perplexity_web_pool` →
    модель `pool` (per-project → id, per-namespace → ns-<имя>, иначе литерал)."""
    override = project.get("perplexity_web_pool")
    if override:
        return str(override)
    model = st.get("pool") or "default"
    if model == "per-project":
        return project.get("id") or "default"
    if model == "per-namespace":
        ns = next(iter(project.get("namespaces") or []), None)
        return f"ns-{ns}" if ns else "default"
    return model  # литеральное имя пула (напр. "default") — общий пул для всех


def entry(project, st):
    """MCP-entry perplexity-web: команда через индирекцию `${ENV:-bin}` (bin — fallback из
    конфига; без bin — bare `${ENV}`, требует выставленного env), пул в --pool."""
    pool = resolve_pool(project, st)
    bin_path = st.get("bin") or ""
    env_var = st.get("env_var") or "PERPLEXITY_WEB_MCP_BIN"
    command = f"${{{env_var}:-{bin_path}}}" if bin_path else f"${{{env_var}}}"
    return {"command": command, "args": [f"--pool={pool}"]}
