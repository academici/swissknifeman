"""Константы maind: порты памяти, типы узлов/рёбер графа, дефолты, тайминги."""

# ── память (agent-memory daemon) ───────────────────────────────────────────
MEMORY_HTTP_PORT = 4111
MEMORY_STREAM_PORT = 4112
MEMORY_VIEWER_PORT = 4113
MEMORY_DEFAULT_HOST = "127.0.0.1"
MEMORY_DEFAULT_URL = f"http://{MEMORY_DEFAULT_HOST}:{MEMORY_HTTP_PORT}"

# Воркеры iii-* в config/memory/iii-config.yaml (для status/doctor).
MEMORY_WORKERS = (
    "iii-http", "iii-state", "iii-queue", "iii-pubsub",
    "iii-cron", "iii-stream", "iii-observability",
)

# Глобальный scope/namespace памяти для фактов всей экосистемы.
GLOBAL_SCOPE = "global"

# ── граф ────────────────────────────────────────────────────────────────────
NODE_TYPES = {"project", "agent", "memory", "skill", "entity", "tool", "package", "doc"}
EDGE_TYPES = {"uses", "knows", "relates_to", "belongs_to", "depends_on", "provided_by",
              "requires"}
# Раскладка графа: федерация (граф на проект + индекс) — единственная первоклассная;
# disabled выключает граф-команды. Движок везде stdlib (graphify — отдельный MCP-слой
# над КОДОМ проекта, не адаптер этого графа; см. docs/guide/graphify.md).
GRAPH_ADAPTERS = {"federation", "disabled"}
# Устаревшие значения adapter — принимаются с предупреждением и нормализуются в federation.
LEGACY_GRAPH_ADAPTERS = {"memory", "graphify", "networkx"}
GRAPH_VERSION = 1

# Планы графа (природа связи) и источник, из которого ребро/узел получены (derive).
GRAPH_PLANES = {"code", "doc", "meta", "runtime"}
LINK_VIA = {"code", "doc", "override", "skills"}

# ── агенты ──────────────────────────────────────────────────────────────────
HEARTBEAT_DEFAULT_MS = 30000
MAX_IDLE_DEFAULT_MS = 300000
AGENT_STALE_FACTOR = 3   # пропущенных heartbeat'ов до статуса "stale"

# ── наблюдаемость ───────────────────────────────────────────────────────────
SERVICE_NAME = "maind"
