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

# Бакеты памяти (scope'ы). Паритет с графом по namespace'ам: факты группы видны внутри
# namespace и изолированы между группами.
#   project:<id>  — приватный бакет проекта;
#   ns:<имя>      — общий бакет namespace-группы (аналог cross-рёбер графа внутри ns);
#   global        — вся экосистема (wildcard-инфраструктура + ecosystem-wide факты).
GLOBAL_SCOPE = "global"
NS_SCOPE_PREFIX = "ns:"

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

# Универсальный код-граф (граф КОДА внутри проекта) по умолчанию — Serena
# (github.com/oraios/serena) через uvx: language-agnostic (LSP), даёт символы/ссылки/
# реализации/обзор. Проверено рабочим (MCP initialize + 22 code-инструмента). Включается
# на проект полем `graphify: true`; движок переопределяется полями graphify_command /
# graphify_args (плейсхолдер {root} → путь проекта) / graphify_server_name.
CODE_MCP_NAME = "serena"
CODE_MCP_COMMAND = "uvx"
CODE_MCP_ARGS = [
    "--from", "git+https://github.com/oraios/serena",
    "serena", "start-mcp-server",
    "--context", "ide-assistant",
    "--project", "{root}",
    "--enable-web-dashboard", "false",
]

# Дефолтный .serena/project.yml, который maind кладёт в проект при graphify:true (движок
# Serena). Язык — по типу проекта; игноры исключают сторонние и СИМЛИНКНУТЫЕ first-party
# пакеты (vendor/packages) — они индексируются как СВОИ проекты, иначе дубли символов и
# рекурсивные симлинки (testbench) зацикливают скан. initial_prompt — нативный механизм
# Serena: текст даётся модели при активации проекта (нацеливает на symbol-инструменты).
SERENA_LANG_BY_TYPE = {"php-package": "php", "node-package": "typescript"}
SERENA_IGNORES = ["vendor", "node_modules", "packages", "storage",
                  "bootstrap/cache", "public/build", "dist", ".git"]
SERENA_INITIAL_PROMPT = (
    "Навигацию по коду этого проекта веди через symbol-инструменты Serena "
    "(get_symbols_overview, find_symbol, find_referencing_symbols, find_implementations) "
    "вместо чтения файлов целиком — это точнее и экономит токены. Код связанных пакетов "
    "экосистемы живёт в их собственных проектах; межпроектные связи — в mAInd "
    "(maind graph)."
)

# Планы графа (природа связи) и источник, из которого ребро/узел получены (derive).
GRAPH_PLANES = {"code", "doc", "meta", "runtime"}
LINK_VIA = {"code", "doc", "override", "skills"}

# ── агенты ──────────────────────────────────────────────────────────────────
HEARTBEAT_DEFAULT_MS = 30000
MAX_IDLE_DEFAULT_MS = 300000
AGENT_STALE_FACTOR = 3   # пропущенных heartbeat'ов до статуса "stale"

# ── наблюдаемость ───────────────────────────────────────────────────────────
SERVICE_NAME = "maind"
