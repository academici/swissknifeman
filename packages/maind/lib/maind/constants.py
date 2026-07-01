"""Константы maind: порты памяти, типы узлов/рёбер графа, дефолты, тайминги."""
from core import LANGUAGE_BY_TYPE as _LANGUAGE_BY_TYPE

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
# disabled выключает граф-команды. Движок везде stdlib (код-граф — отдельный MCP-слой
# над КОДОМ проекта, не адаптер этого графа; см. docs/guide/code-graph.md).
GRAPH_ADAPTERS = {"federation", "disabled"}
# Устаревшие значения adapter — принимаются с предупреждением и нормализуются в federation.
LEGACY_GRAPH_ADAPTERS = {"memory", "graphify", "networkx"}
GRAPH_VERSION = 1

# Код-граф (граф КОДА внутри проекта) — ПОЛИТИКА В КОНФИГЕ, не в коде. Это лишь fallback-
# дефолт для merge_defaults (секция code_graph в .maind.json); реальные значения берутся из
# конфига (см. .maind.example.json) — игноры/команду/промпты редактируют там, не здесь.
# Движок по умолчанию — Serena (github.com/oraios/serena) через uvx: language-agnostic (LSP).
# Включается на проект полем `code: true` (legacy-alias `graphify: true`).
#
# ignores: исключают сторонние и СИМЛИНКНУТЫЕ first-party пакеты (vendor/packages) — они
#   графятся как СВОИ проекты (иначе дубли символов и рекурсивные симлинки testbench виснут).
# workspace_ignores: для монорепо/консьюмера, где пакеты под packages/* — их НЕ игнорим
#   (единый граф app↔пакеты), но режем vendor и ВЛОЖЕННЫЕ **/vendor.
# initial_prompt/workspace_prompt: нативно даются модели при активации проекта Serena.
# Serena пиннована на тег релиза (НЕ bare-main): breaking-изменение в main не сломает
# код-граф у всех проектов внезапно. Бамп — здесь, в ОДНОМ месте; актуальный релиз сверять
# на github.com/oraios/serena/releases. (verified 2026-06-26: последний v1.5.3)
SERENA_SRC = "git+https://github.com/oraios/serena@v1.5.3"
CODE_GRAPH_DEFAULTS = {
    "enabled_default": False,
    "engine": "serena",
    "command": "uvx",
    "args": [
        "--from", SERENA_SRC,
        "serena", "start-mcp-server",
        "--context", "ide-assistant",
        "--project", "{root}",
        "--enable-web-dashboard", "false",
    ],
    "index_args": [
        "--from", SERENA_SRC,
        "serena", "project", "index", "{root}",
    ],
    "server_name": "serena",
    "language_by_type": dict(_LANGUAGE_BY_TYPE),  # единый источник — core.project
    "ignores": ["vendor", "node_modules", "packages", "storage",
                "bootstrap/cache", "public/build", "dist", ".git"],
    "workspace_ignores": ["vendor", "node_modules", "**/vendor", "**/node_modules",
                          "storage", "bootstrap/cache", "public/build", "dist", ".git"],
    "initial_prompt": (
        "Навигацию по коду этого проекта веди через symbol-инструменты Serena "
        "(get_symbols_overview, find_symbol, find_referencing_symbols, find_implementations) "
        "вместо чтения файлов целиком — это точнее и экономит токены. Код связанных пакетов "
        "экосистемы живёт в их собственных проектах; межпроектные связи — в mAInd (maind graph)."
    ),
    "workspace_prompt": (
        "Этот проект — workspace: его код + локально разрабатываемые пакеты экосистемы под "
        "packages/* образуют ЕДИНЫЙ граф. Навигацию веди symbol-инструментами Serena "
        "(get_symbols_overview, find_symbol, find_referencing_symbols, find_implementations). "
        "Папки packages/* — это РЕАЛЬНЫЕ репозитории пакетов (через симлинк): найдя улучшение в "
        "пакете, предложи его и, ПО ПОДТВЕРЖДЕНИЮ пользователя, правь прямо в packages/<пакет>/… "
        "— изменение затронет сам пакет и всех его консьюмеров."
    ),
    "pre_index": True,
    "feature_log_hook": True,
}

# perplexity-web — keyless-мост (браузерный профиль) как hub-managed MCP-сервер.
# Раскатывается в проекты как `maind`/Serena (deploy/sync), а не вписывается вручную
# хардкод-путём в каждый .mcp.json. Политика — секция mcp.perplexity_web конфига:
#   enabled  — глобальный фан-аут (per-project override `perplexity_web: true|false`);
#   pool     — модель пулов (один пул = демон+профиль+окно браузера, README пакета):
#              "default"|<литерал> → общий пул (переиспользует текущий логин);
#              "per-project"       → пул = id проекта (свой логин на проект);
#              "per-namespace"     → пул = "ns-<namespace>" (логин на группу);
#              per-project override — `perplexity_web_pool: "<имя>"`;
#   bin      — fallback-путь к start.sh пакета (machine-specific → живёт в хаб-конфиге,
#              НЕ в коде); оборачивается индирекцией `${PERPLEXITY_WEB_MCP_BIN:-<bin>}`,
#              как `${MAIND_BIN:-maind}` — переносимо между машинами/CI.
PERPLEXITY_WEB_DEFAULTS = {
    "enabled": False,
    "pool": "default",
    "bin": "",
    "env_var": "PERPLEXITY_WEB_MCP_BIN",
    "server_name": "perplexity-web",
}

# Планы графа (природа связи) и источник, из которого ребро/узел получены (derive).
GRAPH_PLANES = {"code", "doc", "meta", "runtime"}
LINK_VIA = {"code", "doc", "override", "skills"}

# ── агенты ──────────────────────────────────────────────────────────────────
HEARTBEAT_DEFAULT_MS = 30000
MAX_IDLE_DEFAULT_MS = 300000
AGENT_STALE_FACTOR = 3   # пропущенных heartbeat'ов до статуса "stale"

# ── наблюдаемость ───────────────────────────────────────────────────────────
SERVICE_NAME = "maind"

# ── соседние пакеты экосистемы (siblings) ────────────────────────────────────
# Как найти лаунчер соседа: env-override · проект в config.json · path_key · bin.
# Живёт здесь (нейтральный data-модуль), а не в orchestrate — чтобы и orchestrate
# (run_capability), и sync (_skiller_profiles_dir) брали один источник без lazy-импорта
# друг друга. Чистые данные, никаких зависимостей.
SIBLINGS = {
    "brain": {"env": "MAIND_BRAIN_BIN", "project_id": "brain",
              "path_key": "vault_path", "bin": "bin/brain"},
    # монорепо academici: лаунчер skiller живёт в подпакете packages/skiller/, а
    # local_path указывает на корень репо (где .git) — отсюда вложенный bin-путь.
    # Ключ sibling и project_id — "swissknifeman" (id проекта-репо в config.json).
    "swissknifeman": {"env": "MAIND_SKM_BIN", "project_id": "swissknifeman",
                      "path_key": "local_path",
                      "bin": "packages/skiller/bin/skiller"},
    # harness живёт в том же монорепо (local_path проекта-репо swissknifeman).
    "harness": {"env": "MAIND_HARNESS_BIN", "project_id": "swissknifeman",
                "path_key": "local_path",
                "bin": "packages/harness/bin/harness"},
}
