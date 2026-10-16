"""Constants maind: memory ports, node types/graph edges, defaults, timings."""
from aicore.util.project import LANGUAGE_BY_TYPE as _LANGUAGE_BY_TYPE

# ── memory (agent-memory daemon) ───────────────────────────────────────────
MEMORY_HTTP_PORT = 4111
MEMORY_STREAM_PORT = 4112
MEMORY_VIEWER_PORT = 4113
MEMORY_DEFAULT_HOST = "127.0.0.1"
MEMORY_DEFAULT_URL = f"http://{MEMORY_DEFAULT_HOST}:{MEMORY_HTTP_PORT}"

# Workers iii-* in config/memory/iii-config.yaml (for status/doctor).
MEMORY_WORKERS = (
    "iii-http", "iii-state", "iii-queue", "iii-pubsub",
    "iii-cron", "iii-stream", "iii-observability",
)

# Memory buckets (scope's). Parity with graph by namespace'am: group facts are visible inside
# namespace and isolated between groups.
# project:<id>  — private project bucket;
# ns:<name>      — general bucket namespace-groups (analogue cross-edges of the graph inside ns);
# global        — entire ecosystem (wildcard-infrastructure + ecosystem-wide facts).
GLOBAL_SCOPE = "global"
NS_SCOPE_PREFIX = "ns:"

# Digest-budget SessionStart: digest - project-only default, limited
# bytes (not only count), with per-item cropping. Norms - findings/P0-rag-context-economy.md
# (additionalContext ≤500–1500 current/session; ~4 char/current → 4000 char ≈ 1000–1200 current).
DIGEST_BUDGET_CHARS = 4000
DIGEST_ITEM_MAX_CHARS = 500
DIGEST_SHARED_MAX = 0 # project-only default; shared — explicitly, by flag/config
DIGEST_TRUNCATE_SUFFIX = "… (→ recall)"
DIGEST_MIN_TAIL_CHARS = 150    # overflowing item cut only if the remaining budget ≥ this

# Waiting budget cross-machine memory calls (ADR-0001 P4.2). LUNGS — health/auth-probe
# (small answer); HEAVY - export/digest (entire pool, up to several MB). Measured per channel
# on LAN-host address (not loopback) —;
# defaults keep margin ABOVE measured number (real LAN/Wi-Fi will add jitter, which
# single-host measurement does not see) — practice guide findings §6 (1-2s light, 5-10 s heavy).
MEMORY_LIGHT_TIMEOUT_S = 3
MEMORY_HEAVY_TIMEOUT_S = 10
MEMORY_RETRIES = 2
MEMORY_RETRY_BACKOFF_S = 0.5

# ── graph ────────────────────────────────────────────────────────────────────
NODE_TYPES = {"project", "agent", "memory", "skill", "entity", "tool", "package", "doc"}
EDGE_TYPES = {"uses", "knows", "relates_to", "belongs_to", "depends_on", "provided_by",
              "requires"}
# Graph Layout: Federation (graph per project + index) — the only first-class;
# disabled disables graph commands. The engine is everywhere stdlib (code graph - separate MCP-layer
# above the project CODE, not the adapter of this graph; see docs/guide/code-graph.md).
GRAPH_ADAPTERS = {"federation", "disabled"}
# Outdated values adapter — are accepted with a warning and normalized to federation.
LEGACY_GRAPH_ADAPTERS = {"memory", "graphify", "networkx"}
GRAPH_VERSION = 1

# Code graph (CODE graph inside the project) — POLICY IS IN THE CONFIG, not in the code. It's just fallback-
# default for merge_defaults (section code_graph in .maind.json); real values are taken from
# config (see .maind.example.json) — ignores/command/prompts are edited there, not here.
# Default engine - Serena (github.com/oraios/serena) via uvx: language-agnostic (LSP).
# Included in the project by the field `code: true` (legacy-alias `graphify: true`).
#
# ignores: exclude third-party and SIMLINKED first-party packages (vendor/packages) — they
# are listed as OWN projects (otherwise duplicate symbols and recursive symlinks testbench hang).
# workspace_ignores: for monorepo/consumer, where are the packages under packages/* — DO NOT ignore them
# (single graph app↔packages), but we cut it vendor and NESTED **/vendor.
# initial_prompt/workspace_prompt: models are given natively when the project is activated Serena.
# Serena pinned to release tag (NOT bare-main): breaking-change to main won't break
# code graph for all projects suddenly. Bump - here, in ONE place; Check current release
# on github.com/oraios/serena/releases. The release tag is resolved to its immutable commit
# so a moved tag cannot silently change the engine in every project (verified 2026-10-04:
# v1.7.0 -> 949a27ef1e5fda1a6e7b561e777bcece345c6ffd).
SERENA_SRC = "git+https://github.com/oraios/serena@949a27ef1e5fda1a6e7b561e777bcece345c6ffd"
# Required keys .serena/project.yml (Serena `_from_dict` FIELDS_WITHOUT_DEFAULTS), which
# expects the version pinned above - an offline copy of the fact, and not a request to the upstream.
# The fact was checked in Serena 1.7.0 (pin 949a27ef…):
# serena/config/serena_config.py `FIELDS_WITHOUT_DEFAULTS` still requires exactly this pair.
# Other keys
# .serena/project.yml have defaults (data.setdefault) are not included here.
# Updated with the SAME seam as SERENA_SRC: bumped the pin - check this set with the new one
# serena/resources/project.template.yml (or schema release notes), otherwise connectivity gate
# (codegraph.check_schema_connectivity) will begin to paint a false discrepancy or miss the real one.
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
    "language_by_type": dict(_LANGUAGE_BY_TYPE),  # single source - core.project
    "ignores": ["vendor", "node_modules", "packages", "storage",
                "bootstrap/cache", "public/build", "dist", ".git"],
    "workspace_ignores": ["vendor", "node_modules", "**/vendor", "**/node_modules",
                          "storage", "bootstrap/cache", "public/build", "dist", ".git"],
    "initial_prompt": (
        "Navigate through the code of this project via symbol-tools Serena "
        "(get_symbols_overview, find_symbol, find_referencing_symbols, find_implementations) "
        "instead of reading entire files - this is more accurate and saves tokens. Related package code "
        "ecosystems live in their own projects; inter-project communications - in mAInd (maind graph)."
    ),
    "workspace_prompt": (
        "This project is workspace: his code + locally developed ecosystem packages for "
        "packages/* form a SINGLE graph. Lead the navigation symbol-tools Serena "
        "(get_symbols_overview, find_symbol, find_referencing_symbols, find_implementations). "
        "Folders packages/* — these are REAL package repositories (via symlink): having found an improvement in "
        "package, offer it and, BY CONFIRMATION of the user, edit directly to packages/<package>/… "
        "— the change will affect the package itself and all its consumers."
    ),
    "pre_index": False,
}

# perplexity-web — keyless-bridge (browser profile) like hub-managed MCP-server.
# Rolled out into projects like `maind`/Serena (deploy/sync), and not entered manually
# hardcode-path to each .mcp.json. Politics - section mcp.perplexity_web config:
# enabled  — global fan-out (per-project override `perplexity_web: true|false`);
# pool     — pool model (one pool = demon+profile+browser window, README package):
# "default"|<literal> → shared pool (reuses the current login);
# "per-project"       → pool = id project (your login for the project);
# "per-namespace"     → pool = "ns-<namespace>" (group login);
# per-project override — `perplexity_web_pool: "<name>"`;
# bin      — machine-local path to start.sh package (lives in the hub config, NOT in the code).
# MCP-clients run the command directly and do not expand shell-substitutions.
PERPLEXITY_WEB_DEFAULTS = {
    "enabled": False,
    "pool": "default",
    "bin": "",
    "server_name": "perplexity-web",
}

# mcp.emit_example — default-on: next to the real one.mcp.json issue portable
# .mcp.json.example with placeholders instead machine-specific paths and lead .gitignore.
# The only carrier of default is merge_defaults reads from here; opt-out — explicit `false`
# in config.json (respected, see mcpconfig.write_example/reconcile_gitignore).
EMIT_EXAMPLE_DEFAULT = True

# Graph Plans (nature of connection) and the source from which the edge/node received (derive).
GRAPH_PLANES = {"code", "doc", "meta", "runtime"}
LINK_VIA = {"code", "doc", "override", "skills"}

# ── agents ──────────────────────────────────────────────────────────────────
HEARTBEAT_DEFAULT_MS = 30000
MAX_IDLE_DEFAULT_MS = 300000
AGENT_STALE_FACTOR = 3   # missing heartbeat'ov to status "stale"

# ── observability ───────────────────────────────────────────────────────────
SERVICE_NAME = "maind"
