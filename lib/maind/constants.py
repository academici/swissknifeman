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
NODE_TYPES = {"project", "agent", "memory", "skill", "entity", "tool"}
EDGE_TYPES = {"uses", "knows", "relates_to", "belongs_to", "depends_on", "provided_by"}
GRAPH_ADAPTERS = {"memory", "graphify", "disabled"}
GRAPH_VERSION = 1

# ── агенты ──────────────────────────────────────────────────────────────────
HEARTBEAT_DEFAULT_MS = 30000
MAX_IDLE_DEFAULT_MS = 300000
AGENT_STALE_FACTOR = 3   # пропущенных heartbeat'ов до статуса "stale"

# ── наблюдаемость ───────────────────────────────────────────────────────────
SERVICE_NAME = "maind"
