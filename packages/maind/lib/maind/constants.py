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

# Digest-бюджет SessionStart (2026.07.12-CONTEXT-ECONOMY D10, P1.1): дайджест — project-only по умолчанию, ограничен
# байтами (не только count), с per-item обрезкой. Нормы — findings/P0-rag-context-economy.md
# (additionalContext ≤500–1500 ток/сессию; ~4 симв/ток → 4000 симв ≈ 1000–1200 ток).
DIGEST_BUDGET_CHARS = 4000
DIGEST_ITEM_MAX_CHARS = 500
DIGEST_SHARED_MAX = 0          # project-only дефолт (D10); shared — явно, флагом/конфигом
DIGEST_TRUNCATE_SUFFIX = "… (→ recall)"
DIGEST_MIN_TAIL_CHARS = 150    # переполняющий item обрезаем только если остаток бюджета ≥ это

# Бюджет ожидания cross-machine вызовов памяти (ADR-0001 P4.2). ЛЁГКИЕ — health/auth-пробник
# (маленький ответ); ТЯЖЁЛЫЕ — export/digest (весь пул, до нескольких МБ). Измерено по каналу
# на LAN-адресе хоста (не loopback) — plans/2026.07.25-ECO-OPT/findings/P4.2-remote-link-measure.md;
# дефолты держат запас НАД измеренным числом (реальный LAN/Wi-Fi добавит джиттер, которого
# однохостовый замер не видит) — ориентир практики findings §6 (1-2с лёгкие, 5-10с тяжёлые).
MEMORY_LIGHT_TIMEOUT_S = 3
MEMORY_HEAVY_TIMEOUT_S = 10
MEMORY_RETRIES = 2
MEMORY_RETRY_BACKOFF_S = 0.5

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
# на github.com/oraios/serena/releases. (verified 2026-07-27: пин на commit-SHA D110 —
# @v1.5.3/@v1.6.1 оба старше схемы .serena/project.yml, которую пишет наш провиженер
# с ccd4505b (language_servers); стабильного тега с этой схемой у апстрима нет)
SERENA_SRC = "git+https://github.com/oraios/serena@026b007bb889366283c925527e9a3bab317f66c1"
# Обязательные ключи .serena/project.yml (Serena `_from_dict` FIELDS_WITHOUT_DEFAULTS), которых
# ожидает пиннованная выше версия — офлайновая копия факта, а не запрос к апстриму (D111, P5.4).
# Факт снят прямым чтением исходника пина (Serena 1.6.2.dev0, пин 026b007b…):
# serena/config/serena_config.py:341 (путь внутри uv-архива, вне этого репозитория),
# сверка 2026-07-27 (findings/P5-audit-closure-facts.md §3, plan D117). Остальные ключи
# .serena/project.yml имеют дефолты (data.setdefault) и сюда не входят.
# Обновляется ТЕМ ЖЕ швом, что SERENA_SRC: бампнул пин — сверь этот набор с новым
# serena/resources/project.template.yml (или релиз-нотами схемы), иначе гейт связности
# (codegraph.check_schema_connectivity) начнёт красить ложное расхождение или пропустит настоящее.
SERENA_SCHEMA_FIELDS = frozenset({"project_name", "language_servers"})
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
    "pre_index": False,
    "feature_log_hook": False,
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
#   bin      — machine-local путь к start.sh пакета (живёт в хаб-конфиге, НЕ в коде).
#              MCP-клиенты запускают команду напрямую и не раскрывают shell-подстановки.
PERPLEXITY_WEB_DEFAULTS = {
    "enabled": False,
    "pool": "default",
    "bin": "",
    "server_name": "perplexity-web",
}

# mcp.emit_example — default-on (P2.4): рядом с реальным .mcp.json эмитить портируемый
# .mcp.json.example с плейсхолдерами вместо machine-specific путей и вести .gitignore.
# Единственный носитель дефолта — merge_defaults читает отсюда; opt-out — явный `false`
# в config.json (уважается, см. mcpconfig.write_example/reconcile_gitignore).
EMIT_EXAMPLE_DEFAULT = True

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
